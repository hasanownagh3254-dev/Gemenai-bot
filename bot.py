import os
import time
import threading
import base64
import requests
import telebot
from flask import Flask

# Û±. Ø¯Ø±ÛŒØ§ÙØª Ú©Ù„ÛŒØ¯Ù‡Ø§ Ø§Ø² Environment
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

MODEL_NAME = "openai/gpt-oss-20b"
VISION_MODEL_NAME = "qwen/qwen3.6-27b"  # Ù…Ø¯Ù„ ÙˆÛŒÚ˜Ù† Groq Ø¨Ø±Ø§ÛŒ Ù¾Ø±Ø¯Ø§Ø²Ø´ Ø¹Ú©Ø³

# Û². ÙˆØ¨â€ŒØ³Ø±ÙˆØ± Flask Ø¨Ø±Ø§ÛŒ Ø²Ù†Ø¯Ù‡ Ù†Ú¯Ù‡ Ø¯Ø§Ø´ØªÙ† Ø³Ø±ÙˆØ± Render
@app.route("/")
def home():
    return "Bot is running 24/7!", 200

# Û³. Ø§Ø±Ø³Ø§Ù„ Ø¯Ø±Ø®ÙˆØ§Ø³Øª Ø¨Ù‡ API Ù…Ø¯Ù„ Groq (Ù…ØªÙ†)
def ask_groq(prompt):
    if not GROQ_API_KEY:
        return "âŒ Ø®Ø·Ø§: Ù…ØªØºÛŒØ± GROQ_API_KEY Ø¯Ø± Render ØªÙ†Ø¸ÛŒÙ… Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª."

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
            return f"âŒ Ø®Ø·Ø§ÛŒ Groq (Ú©Ø¯ {response.status_code}): {err_msg}"
    except Exception as e:
        return f"âŒ Ø®Ø·Ø§ÛŒ Ø§Ø±ØªØ¨Ø§Ø·ÛŒ: {str(e)}"

# Û³Ø¨. Ø§Ø±Ø³Ø§Ù„ Ø¹Ú©Ø³ Ø¨Ù‡ Ù…Ø¯Ù„ ÙˆÛŒÚ˜Ù† Groq Ø¨Ø±Ø§ÛŒ Ù¾Ø±Ø¯Ø§Ø²Ø´
def ask_groq_vision(image_bytes, prompt="Ø§ÛŒÙ† ØªØµÙˆÛŒØ± Ø±Ø§ ØªÙˆØµÛŒÙ Ú©Ù†."):
    if not GROQ_API_KEY:
        return "âŒ Ø®Ø·Ø§: Ù…ØªØºÛŒØ± GROQ_API_KEY Ø¯Ø± Render ØªÙ†Ø¸ÛŒÙ… Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª."

    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    image_data_url = f"data:image/jpeg;base64,{b64_image}"

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }

    payload = {
        "model": VISION_MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data_url}}
                ]
            }
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
            return f"âŒ Ø®Ø·Ø§ÛŒ Groq (Ú©Ø¯ {response.status_code}): {err_msg}"
    except Exception as e:
        return f"âŒ Ø®Ø·Ø§ÛŒ Ø§Ø±ØªØ¨Ø§Ø·ÛŒ: {str(e)}"

# Û´. Ø¯Ø±ÛŒØ§ÙØª Ùˆ Ù¾Ø§Ø³Ø® Ø¨Ù‡ Ø¹Ú©Ø³â€ŒÙ‡Ø§ (Ø¨Ø§ÛŒØ¯ Ù‚Ø¨Ù„ Ø§Ø² Ù‡Ù†Ø¯Ù„Ø± Ù…ØªÙ†ÛŒ Ø¹Ù…ÙˆÙ…ÛŒ ØªØ¹Ø±ÛŒÙ Ø´ÙˆØ¯)
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        bot.send_chat_action(message.chat.id, "typing")

        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        user_prompt = message.caption if message.caption else "Ø§ÛŒÙ† ØªØµÙˆÛŒØ± Ø±Ø§ ØªÙˆØµÛŒÙ Ú©Ù†."

        reply = ask_groq_vision(downloaded_file, user_prompt)
        bot.reply_to(message, reply)
    except Exception as e:
        print(f"Error handling photo: {e}")
        bot.reply_to(message, f"âŒ Ø®Ø·Ø§ Ø¯Ø± Ù¾Ø±Ø¯Ø§Ø²Ø´ Ø¹Ú©Ø³: {str(e)}")

# Ûµ. Ø¯Ø±ÛŒØ§ÙØª Ùˆ Ù¾Ø§Ø³Ø® Ø¨Ù‡ Ù¾ÛŒØ§Ù…â€ŒÙ‡Ø§ÛŒ Ù…ØªÙ†ÛŒ
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

# Û¶. Ø§Ø¬Ø±Ø§ÛŒ Ø±Ø¨Ø§Øª ØªÙ„Ú¯Ø±Ø§Ù… Ø¨Ù‡ ØµÙˆØ±Øª Ø§ÛŒÙ…Ù† Ùˆ Ø®ÙˆØ¯Ú©Ø§Ø±
def run_telegram_bot():
    print("Ø´Ø±ÙˆØ¹ Ø³ÛŒØ³ØªÙ… Ø¨Ø§Ø²ÛŒØ§Ø¨ÛŒ Ø®ÙˆØ¯Ú©Ø§Ø± Ø±Ø¨Ø§Øª...")
    while True:
        try:
            # Ù¾Ø§Ú©Ø³Ø§Ø²ÛŒ ÙˆØ¨â€ŒÙ‡ÙˆÚ© Ø¨Ù‡ Ø±ÙˆØ´ Ø§Ø³ØªØ§Ù†Ø¯Ø§Ø±Ø¯ Ùˆ Ø¨Ø¯ÙˆÙ† Ù¾Ø§Ø±Ø§Ù…ØªØ±Ù‡Ø§ÛŒ Ù†Ø§Ø³Ø§Ø²Ú¯Ø§Ø±
            try:
                bot.remove_webhook()
            except Exception as e:
                print(f"Webhook removal note: {e}")

            time.sleep(1)
            print("Ø§ØªØµØ§Ù„ Ø±Ø¨Ø§Øª Ø¨Ù‡ ØªÙ„Ú¯Ø±Ø§Ù… Ø¨Ø±Ù‚Ø±Ø§Ø± Ø´Ø¯. Ø¯Ø± Ø­Ø§Ù„ Ú¯ÙˆØ´ Ø¯Ø§Ø¯Ù† Ø¨Ù‡ Ù¾ÛŒØ§Ù…â€ŒÙ‡Ø§...")
            bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)
        except Exception as e:
            print(f"Ø®Ø·Ø§ÛŒ Ù…ÙˆÙ‚Øª Ø¯Ø± Ø§ØªØµØ§Ù„ ({e}). ØªÙ„Ø§Ø´ Ù…Ø¬Ø¯Ø¯ ØªØ§ Ûµ Ø«Ø§Ù†ÛŒÙ‡ Ø¯ÛŒÚ¯Ø±...")
            time.sleep(5)

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
