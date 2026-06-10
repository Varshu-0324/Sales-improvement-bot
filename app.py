import os
import json
from flask import Flask, render_template_string, request, jsonify
import google.generativeai as genai
from datetime import datetime
from pymongo import MongoClient

# Configure Gemini API key
genai.configure(api_key="AIzaSyCrrsRX-0vHtLIa_LO6XeDMwUEhMptP5rg")  # Replace with your actual API key

# MongoDB setup
client = MongoClient("mongodb+srv://varshini:<db_password>@cluster0.lwtnhbk.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["sales_chatbot"]
sessions = db["sales_sessions"]

app = Flask(__name__)

# Initial question to start the chat
initial_question = {
    "id": "q1",
    "question": "🎯 What is your primary sales goal?",
    "options": ["Increase conversion rate", "Expand customer base", "Boost repeat purchases"]
}

@app.route('/')
def index():
    return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <title>Sales Strategy Chatbot</title>
    <style>
        body { font-family: sans-serif; background: #f8f8f8; padding: 20px; }
        #chat { max-width: 600px; margin: auto; background: #fff; padding: 20px; border-radius: 10px; border: 1px solid #ccc; }
        .bot, .user, .option { padding: 10px; margin: 10px 0; border-radius: 8px; }
        .bot { background: #eef; }
        .user { background: #d0f0d0; text-align: right; }
        .option { background: #ddeeff; cursor: pointer; border: 1px solid #99c; }
        h2 { text-align: center; }
    </style>
</head>
<body>
    <h2>🧠 Smart Sales Strategy Chatbot</h2>
    <div id="chat"></div>
    <script>
        let conversation = [];
        const chat = document.getElementById("chat");

        function addMessage(text, className) {
            const div = document.createElement("div");
            div.className = className;
            div.textContent = text;
            chat.appendChild(div);
            chat.scrollTop = chat.scrollHeight;
        }

        function askNext(question) {
            if (!question) {
                getRecommendation();
                return;
            }
            addMessage(question.question, "bot");
            question.options.forEach(opt => {
                const btn = document.createElement("button");
                btn.className = "option";
                btn.textContent = opt;
                btn.onclick = () => {
                    addMessage(opt, "user");
                    conversation.push({ id: question.id, question: question.question, answer: opt });
                    // Disable all buttons after selection
                    btn.parentElement.querySelectorAll("button").forEach(b => b.disabled = true);
                    fetch("/next_question", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ conversation })
                    })
                    .then(res => res.json())
                    .then(data => askNext(data.next_question))
                    .catch(err => {
                        console.error(err);
                        addMessage("❌ Error fetching next question.", "bot");
                    });
                };
                chat.appendChild(btn);
            });
        }

        function getRecommendation() {
            addMessage("🔍 Generating your tailored sales strategy...", "bot");

            // Remove all buttons before recommendation
            document.querySelectorAll(".option").forEach(btn => btn.remove());

            fetch("/get_recommendation", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ conversation })
            })
            .then(res => res.json())
            .then(data => {
                if (data.recommendation) {
                    addMessage(data.recommendation, "bot");
                } else {
                    addMessage("❌ No recommendation received.", "bot");
                }
            })
            .catch(err => {
                console.error(err);
                addMessage("❌ Failed to generate recommendation.", "bot");
            });
        }

        // Start chat with initial question
        askNext({{ initial_question|tojson }});
    </script>
</body>
</html>
''', initial_question=initial_question)


@app.route('/next_question', methods=['POST'])
def next_question():
    data = request.get_json()
    conversation = data.get("conversation", [])

    # Stop at 10 questions
    if len(conversation) >= 10:
        return jsonify({"next_question": None})

    prompt = """
You are a smart sales assistant chatbot. Based on the conversation history below, generate the next best sales-related question along with 3 to 4 relevant multiple-choice options.
Respond only with a JSON object formatted exactly like this:
{
  "question": "Your question here?",
  "options": ["Option1", "Option2", "Option3", "Option4"]
}

Do NOT include any explanation or additional text.

Conversation so far:
"""
    for entry in conversation:
        prompt += f"{entry['question']} Answer: {entry['answer']}\n"

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        raw_text = response.text.strip()

        # Strip code block formatting if present
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].strip()

        json_output = json.loads(raw_text)

        next_question = {
            "id": f"q{len(conversation) + 1}",
            "question": json_output["question"],
            "options": json_output["options"]
        }

    except Exception as e:
        print("Error parsing Gemini output:", e)
        next_question = {
            "id": f"q{len(conversation) + 1}",
            "question": "❌ Could not generate a follow-up question. Would you like to try again?",
            "options": ["Yes", "No"]
        }

    return jsonify({"next_question": next_question})


@app.route('/get_recommendation', methods=['POST'])
def get_recommendation():
    data = request.get_json()
    conversation = data.get("conversation", [])

    # Prepare the prompt
    prompt = "You are a business consultant. Based on the following sales dialogue, suggest a smart, actionable sales strategy:\n\n"
    for entry in conversation:
        prompt += f"{entry['question']} Answer: {entry['answer']}\n"
    prompt += "\nReturn 2-3 specific recommendations."

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        print("Gemini response:\n", response.text)  # Debugging line

        if response.text and response.text.strip():
            recommendation = response.text.strip()
        else:
            recommendation = "⚠️ Gemini did not return a valid recommendation. Please try again."

    except Exception as e:
        print("Gemini error:", str(e))
        recommendation = f"❌ Error calling Gemini: {str(e)}"

    # Log the session in MongoDB
    try:
        sessions.insert_one({
            "timestamp": datetime.now().isoformat(),
            "conversation": conversation,
            "recommendation": recommendation
        })
    except Exception as mongo_err:
        print("MongoDB insert error:", mongo_err)

    return jsonify({"recommendation": recommendation})


if __name__ == '__main__':
    app.run(debug=True)
