import os
import threading
import telebot
import requests
from flask import Flask

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is active 24/7!"

MODELS = [
    "gemini-flash-latest",
    "gemini-2.0-flash",
    "gemini-1.5-flash"
]

def ask_gemini(prompt):
    if not GEMINI_API_KEY:
        return "خطا: کلید GEMINI_API_KEY در قسمت Environment پنل Render وارد نشده است."

    # بر اساس cURL رسمی گوگل، کلید حتماً باید در هدر ارسال شود
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY
    }
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    last_error = ""
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            data = response.json()
            
            if response.status_code == 200 and "candidates" in data and len(data["candidates"]) > 0:
                parts = data["candidates"][0].get("content", {}).get("parts", [])
                if parts and "text" in parts[0]:
                    return parts[0]["text"]
            else:
                err_msg = data.get("error", {}).get("message", response.text)
                last_error = f"مدل {model} (کد {response.status_code}): {err_msg}"
        except Exception as e:
            last_error = f"خطای ارتباطی: {str(e)}"
            continue

    return f"خطا در دریافت پاسخ از گوگل:\n{last_error}"

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
    
