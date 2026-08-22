import os
import threading
import telebot
import requests
from flask import Flask

TELEGRAM_TOKEN = "8764118938:AAERKImEtZ5zT2JYFLmIBGSNOg5ynSQP4CI"
GEMINI_API_KEY = "AQ.Ab8RN6KksS0Ol06rjL4ZXZ785fTNUlopkjjVkyAKYlLhFbRBTA"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is active 24/7!"

MODELS = [
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-2.0-flash"
]

def ask_gemini(prompt):
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    for attempt in range(2):
        for model in MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=15)
                data = response.json()
                if "candidates" in data:
                    return data["candidates"][0]["content"]["parts"][0]["text"]
            except Exception:
                continue
    return "سرورهای گوگل در حال حاضر بسیار شلوغ هستند. لطفاً چند ثانیه دیگر دوباره پیام بفرستید."

@bot.message_handler(func=lambda message: True)
def answer(message):
    try:
        reply_text = ask_gemini(message.text)
        bot.reply_to(message, reply_text)
    except Exception as e:
        bot.reply_to(message, f"System Error: {str(e)}")

def run_bot():
    print("Bot is running...")
    bot.infinity_polling()

if __name__ == "__main__":
    t = threading.Thread(target=run_bot)
    t.start()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
  
