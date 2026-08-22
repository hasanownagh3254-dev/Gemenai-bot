import os
import threading
import telebot
import requests
from flask import Flask

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is active 24/7!"

MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

def ask_groq(prompt):
    # چاپ طول کلید در لاگ‌ها برای اطمینان از خوانده شدن متغیر
    print(f"DEBUG: Loaded API Key length = {len(GROQ_API_KEY)}")
    
    if not GROQ_API_KEY:
        return "خطا: متغیر GROQ_API_KEY روی سرور Render یافت نشد یا خالی است."

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    last_error = ""
    for model in MODELS:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}]
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            data = response.json()
            
            if response.status_code == 200 and "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            else:
                err_msg = data.get("error", {}).get("message", response.text)
                last_error = f"مدل {model} (کد {response.status_code}): {err_msg}"
        except Exception as e:
            last_error = f"خطای ارتباطی: {str(e)}"
            continue

    return f"خطا در دریافت پاسخ از Groq:\n{last_error}"

@bot.message_handler(func=lambda message: True)
def answer(message):
    try:
        reply_text = ask_groq(message.text)
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
    
