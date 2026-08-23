import os
import time
import threading
import requests
import telebot
from flask import Flask

# ۱. دریافت کلیدها از Environment
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# مدل اختصاصی Groq
MODEL_NAME = "llama-3.3-70b-versatile"

# ۲. وب‌سرور برای زنده نگه داشتن سرور در Render
@app.route("/")
def home():
    return "Bot is running 24/7!", 200

# ۳. ارسال درخواست به Groq
def ask_groq(prompt):
    if not GROQ_API_KEY:
        return "❌ خطا: متغیر GROQ_API_KEY در Render تنظیم نشده است."

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You are a helpful AI assistant. Answer clearly and accurately."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 1024
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        data = response.json()

        if response.status_code == 200 and "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"]
        else:
            err_msg = data.get("error", {}).get("message", response.text)
            return f"❌ خطای Groq (کد {response.status_code}): {err_msg}"
    except Exception as e:
        return f"❌ خطای ارتباطی: {str(e)}"

# ۴. دریافت و پاسخ به پیام‌ها
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if not message.text:
        return

    try:
        bot.send_chat_action(message.chat.id, "typing")
        reply = ask_groq(message.text)
        bot.reply_to(message, reply)
    except Exception as e:
        print(f"Error handling message: {e}")

# ۵. اجرای ربات با حلقه‌ی بازیابی خودکار (ضد کرش و ضد تداخل ۴۰۹)
def run_telegram_bot():
    print("شروع سیستم بازیابی خودکار ربات...")
    while True:
        try:
            bot.remove_webhook(drop_pending_updates=True)
            time.sleep(2)
            print("اتصال ربات به تلگرام برقرار شد.")
            bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)
        except Exception as e:
            print(f"خطای موقت در اتصال ({e}). تلاش مجدد تا ۵ ثانیه دیگر...")
            time.sleep(5)

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
