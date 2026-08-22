import os
import threading
import requests
import telebot
from flask import Flask

# =========================
# دریافت کلیدها از Render
# =========================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

# =========================
# ساخت ربات
# =========================

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)


# =========================
# صفحه اصلی Render
# =========================

@app.route("/")
def home():
    return "Bot is active 24/7!"


# =========================
# ارسال پیام به Groq
# =========================

def ask_groq(prompt):

    if not GROQ_API_KEY:
        return "❌ خطا: GROQ_API_KEY در Render پیدا نشد."

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }

    payload = {
        "model": "openai/gpt-oss-20b",
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful AI assistant. Answer clearly and accurately."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_completion_tokens": 1024
    }

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=60
        )

        data = response.json()

        # پاسخ موفق
        if response.status_code == 200:

            if (
                "choices" in data
                and len(data["choices"]) > 0
                and "message" in data["choices"][0]
            ):
                return data["choices"][0]["message"]["content"]

            return "❌ Groq پاسخ معتبری برنگرداند."

        # خطای Groq
        if "error" in data:

            error_message = data["error"].get(
                "message",
                "خطای ناشناخته از Groq"
            )

            return (
                f"❌ خطای Groq\n\n"
                f"کد خطا: {response.status_code}\n"
                f"{error_message}"
            )

        return (
            f"❌ خطای ناشناخته از Groq\n\n"
            f"کد خطا: {response.status_code}\n"
            f"{response.text}"
        )

    except requests.exceptions.Timeout:

        return "❌ اتصال به Groq بیشتر از حد مجاز طول کشید."

    except requests.exceptions.RequestException as e:

        return f"❌ خطای اتصال به Groq:\n{str(e)}"

    except Exception as e:

        return f"❌ خطای برنامه:\n{str(e)}"


# =========================
# دریافت پیام‌های تلگرام
# =========================

@bot.message_handler(func=lambda message: True)
def answer(message):

    if not message.text:
        return

    try:

        bot.send_chat_action(
            message.chat.id,
            "typing"
        )

        reply = ask_groq(message.text)

        bot.reply_to(
            message
