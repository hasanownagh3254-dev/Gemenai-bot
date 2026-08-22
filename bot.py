import os
import threading
import requests
import telebot
from flask import Flask

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is active 24/7!"

# مدل‌های فعال و رسمی فعلی Groq
ACTIVE_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b"
]

def ask_groq(prompt):
    if not GROQ_API_KEY:
        return "❌ خطا: متغیر GROQ_API_KEY در Render پیدا نشد."

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }

    last_error = ""
    for model in ACTIVE_MODELS:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful AI assistant. Answer clearly and accurately."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 1024
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            data = response.json()

            if response.status_code == 200 and "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            else:
                err_msg = data.get("error", {}).get("message", response.text)
                last_error = f"مدل {model} (کد {response.status_code}): {err_msg}"
        except Exception as e:
            last_error = f"خطای ارتباطی: {str(e)}"
            continue

    return f"❌ خطای دریافت پاسخ از Groq:\n{last_error}"

@bot.message_handler(func=lambda message: True)
def answer(message):
    if not message.text:
        return

    try:
        bot.send_chat_action(message.chat.id, "typing")
        reply = ask_groq(message.text)
        bot.reply_to(message, reply)
    except Exception as e:
        bot.reply_to(message, f"❌ خطای ربات:\n{str(e)}")

def run_bot():
    print("Bot is running...")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
    
