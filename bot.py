import os
import re
import json
import time
import threading
import base64
import requests
import telebot
from telebot import types
from flask import Flask

# Û±. Ø¯Ø±ÛŒØ§ÙØª Ú©Ù„ÛŒØ¯Ù‡Ø§ Ø§Ø² Environment
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

MODEL_NAME = "openai/gpt-oss-20b"
VISION_MODEL_NAME = "qwen/qwen3.6-27b"  # Ù…Ø¯Ù„ ÙˆÛŒÚ˜Ù† Groq Ø¨Ø±Ø§ÛŒ Ù¾Ø±Ø¯Ø§Ø²Ø´ Ø¹Ú©Ø³

SYSTEM_PROMPT = "You are a helpful AI assistant. Answer clearly and accurately."

BTN_START_CHAT = "ðŸŸ¢ Ø´Ø±ÙˆØ¹ Ú¯ÙØªÚ¯Ùˆ"
BTN_END_CHAT = "ðŸ”´ Ù¾Ø§ÛŒØ§Ù† Ú¯ÙØªÚ¯Ùˆ"

# Ø­Ø§ÙØ¸Ù‡â€ŒÛŒ Ù…Ú©Ø§Ù„Ù…Ù‡: Ø¨Ø±Ø§ÛŒ Ù‡Ø± Ú†Øª (chat_id) Ù„ÛŒØ³ØªÛŒ Ø§Ø² Ù¾ÛŒØ§Ù…â€ŒÙ‡Ø§ÛŒ Ù‚Ø¨Ù„ÛŒ Ù†Ú¯Ù‡ Ù…ÛŒâ€ŒØ¯Ø§Ø±ÛŒÙ….
# ØªÙˆØ¬Ù‡: Ú†ÙˆÙ† Ø¯Ø± Ø­Ø§ÙØ¸Ù‡ (RAM) Ø°Ø®ÛŒØ±Ù‡ Ù…ÛŒâ€ŒØ´Ù‡ØŒ Ø¨Ø§ Ø±ÛŒâ€ŒØ§Ø³ØªØ§Ø±Øª Ø´Ø¯Ù† Ø³Ø±ÙˆÛŒØ³ Ø±ÙˆÛŒ Render Ù¾Ø§Ú© Ù…ÛŒâ€ŒØ´Ù‡.
CONVERSATION_HISTORY = {}
MAX_HISTORY_MESSAGES = 20  # Ø­Ø¯Ø§Ú©Ø«Ø± ØªØ¹Ø¯Ø§Ø¯ Ù¾ÛŒØ§Ù… (Ú©Ø§Ø±Ø¨Ø±+Ø±Ø¨Ø§Øª) Ú©Ù‡ Ø¨Ø±Ø§ÛŒ Ù‡Ø± Ú†Øª Ù†Ú¯Ù‡ Ø¯Ø§Ø´ØªÙ‡ Ù…ÛŒâ€ŒØ´Ù‡

# ÙˆØ¶Ø¹ÛŒØª ÙØ¹Ø§Ù„/ØºÛŒØ±ÙØ¹Ø§Ù„ Ø¨ÙˆØ¯Ù† Ú¯ÙØªÚ¯Ùˆ Ø¨Ø±Ø§ÛŒ Ù‡Ø± Ú†Øª
ACTIVE_CHATS = {}  # chat_id -> True/False


def get_history(chat_id):
    return CONVERSATION_HISTORY.setdefault(chat_id, [])


def trim_history(chat_id):
    history = CONVERSATION_HISTORY.get(chat_id, [])
    if len(history) > MAX_HISTORY_MESSAGES:
        CONVERSATION_HISTORY[chat_id] = history[-MAX_HISTORY_MESSAGES:]


def is_chat_active(chat_id):
    return ACTIVE_CHATS.get(chat_id, False)


def main_menu_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(types.KeyboardButton(BTN_START_CHAT))
    keyboard.row(types.KeyboardButton(BTN_END_CHAT))
    return keyboard


# Û². ÙˆØ¨â€ŒØ³Ø±ÙˆØ± Flask Ø¨Ø±Ø§ÛŒ Ø²Ù†Ø¯Ù‡ Ù†Ú¯Ù‡ Ø¯Ø§Ø´ØªÙ† Ø³Ø±ÙˆØ± Render
@app.route("/")
def home():
    return "Bot is running 24/7!", 200


# ØªØ§Ø¨Ø¹ Ú©Ù…Ú©ÛŒ Ø¨Ø±Ø§ÛŒ ÙØ±Ø§Ø®ÙˆØ§Ù†ÛŒ Ø§Ù…Ù† API Ú¯Ø±ÙˆÚ© (Ø¨Ø§ Ø±ÙØ¹ Ù…Ø´Ú©Ù„ Ø§Ù†Ú©ÙˆØ¯ÛŒÙ†Ú¯ UTF-8)
def call_groq_api(payload, timeout):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    # Ù†Ú©ØªÙ‡ Ù…Ù‡Ù…: Ø¨Ø¯ÙˆÙ† Ø§ÛŒÙ† Ø®Ø·ØŒ Ø§Ú¯Ø± Ø³Ø±ÙˆØ± Ù‡Ø¯Ø± charset Ù†ÙØ±Ø³ØªÙ‡ Ø¨Ø§Ø´Ù‡ØŒ requests ÙØ±Ø¶ Ù…ÛŒâ€ŒÚ©Ù†Ù‡
    # Ù…ØªÙ† ISO-8859-1 Ø§Ø³Øª Ùˆ Ú©Ø§Ø±Ø§Ú©ØªØ±Ù‡Ø§ÛŒ ÙØ§Ø±Ø³ÛŒ/ÛŒÙˆÙ†ÛŒÚ©Ø¯ Ø¨Ù‡â€ŒØµÙˆØ±Øª Ø®Ø±Ø§Ø¨ (mojibake) Ù†Ù…Ø§ÛŒØ´ Ø¯Ø§Ø¯Ù‡ Ù…ÛŒâ€ŒØ´Ù†.
    response.encoding = "utf-8"
    data = json.loads(response.text)

    if response.status_code == 200 and "choices" in data and len(data["choices"]) > 0:
        return data["choices"][0]["message"]["content"]
    else:
        err_msg = data.get("error", {}).get("message", response.text)
        return f"âŒ Ø®Ø·Ø§ÛŒ Groq (Ú©Ø¯ {response.status_code}): {err_msg}"


# Û³. Ø§Ø±Ø³Ø§Ù„ Ø¯Ø±Ø®ÙˆØ§Ø³Øª Ø¨Ù‡ API Ù…Ø¯Ù„ Groq (Ù…ØªÙ†) Ù‡Ù…Ø±Ø§Ù‡ Ø¨Ø§ ØªØ§Ø±ÛŒØ®Ú†Ù‡ Ù…Ú©Ø§Ù„Ù…Ù‡
def ask_groq(chat_id, prompt):
    if not GROQ_API_KEY:
        return "âŒ Ø®Ø·Ø§: Ù…ØªØºÛŒØ± GROQ_API_KEY Ø¯Ø± Render ØªÙ†Ø¸ÛŒÙ… Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª."

    history = get_history(chat_id)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1024,
        "reasoning_format": "hidden"  # Ø¬Ù„ÙˆÚ¯ÛŒØ±ÛŒ Ø§Ø² Ù†Ù…Ø§ÛŒØ´ ØªÚ¯ <think> Ø¯Ø± Ø¬ÙˆØ§Ø¨
    }

    try:
        reply = call_groq_api(payload, timeout=20)
    except Exception as e:
        return f"âŒ Ø®Ø·Ø§ÛŒ Ø§Ø±ØªØ¨Ø§Ø·ÛŒ: {str(e)}"

    # ÙÙ‚Ø· ÙˆÙ‚ØªÛŒ Ø¬ÙˆØ§Ø¨ Ù…ÙˆÙÙ‚ Ø¨ÙˆØ¯ØŒ Ø¨Ù‡ ØªØ§Ø±ÛŒØ®Ú†Ù‡ Ø§Ø¶Ø§ÙÙ‡ Ú©Ù† (Ù¾ÛŒØ§Ù…â€ŒÙ‡Ø§ÛŒ Ø®Ø·Ø§ Ø±Ùˆ Ø°Ø®ÛŒØ±Ù‡ Ù†Ù…ÛŒâ€ŒÚ©Ù†ÛŒÙ…)
    if not reply.startswith("âŒ"):
        history.append({"role": "user", "content": prompt})
        history.append({"role": "assistant", "content": reply})
        trim_history(chat_id)

    return reply


# Û³Ø¨. Ø§Ø±Ø³Ø§Ù„ Ø¹Ú©Ø³ Ø¨Ù‡ Ù…Ø¯Ù„ ÙˆÛŒÚ˜Ù† Groq Ø¨Ø±Ø§ÛŒ Ù¾Ø±Ø¯Ø§Ø²Ø´
def ask_groq_vision(image_bytes, prompt="Ø§ÛŒÙ† ØªØµÙˆÛŒØ± Ø±Ø§ ØªÙˆØµÛŒÙ Ú©Ù†."):
    if not GROQ_API_KEY:
        return "âŒ Ø®Ø·Ø§: Ù…ØªØºÛŒØ± GROQ_API_KEY Ø¯Ø± Render ØªÙ†Ø¸ÛŒÙ… Ù†Ø´Ø¯Ù‡ Ø§Ø³Øª."

    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    image_data_url = f"data:image/jpeg;base64,{b64_image}"

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
        "max_tokens": 1024,
        "reasoning_format": "hidden",  # Ø¬Ù„ÙˆÚ¯ÛŒØ±ÛŒ Ø§Ø² Ù†Ù…Ø§ÛŒØ´ ØªÚ¯ <think> Ø¯Ø± Ø¬ÙˆØ§Ø¨
        "reasoning_effort": "none"     # Ø®Ø§Ù…ÙˆØ´ Ú©Ø±Ø¯Ù† Ú©Ø§Ù…Ù„ Ø­Ø§Ù„Øª ÙÚ©Ø± Ú©Ø±Ø¯Ù† Ø¨Ø±Ø§ÛŒ Ù…Ø¯Ù„ qwen3
    }

    try:
        return call_groq_api(payload, timeout=30)
    except Exception as e:
        return f"âŒ Ø®Ø·Ø§ÛŒ Ø§Ø±ØªØ¨Ø§Ø·ÛŒ: {str(e)}"


# Û´. ØªØ§Ø¨Ø¹ Ú©Ù…Ú©ÛŒ Ø¨Ø±Ø§ÛŒ Ù¾Ø§Ú©Ø³Ø§Ø²ÛŒ Ùˆ ØªÙ‚Ø³ÛŒÙ… Ù¾ÛŒØ§Ù…â€ŒÙ‡Ø§ÛŒ Ø·ÙˆÙ„Ø§Ù†ÛŒ (Ù…Ø­Ø¯ÙˆØ¯ÛŒØª ØªÙ„Ú¯Ø±Ø§Ù…: Û´Û°Û¹Û¶ Ú©Ø§Ø±Ø§Ú©ØªØ±)
TELEGRAM_MAX_LEN = 4000  # Ú©Ù…ÛŒ Ú©Ù…ØªØ± Ø§Ø² Û´Û°Û¹Û¶ Ø¨Ø±Ø§ÛŒ Ø§Ø·Ù…ÛŒÙ†Ø§Ù†


def clean_text(text):
    if not text:
        return text
    # Ø­Ø°Ù ØªÚ¯â€ŒÙ‡Ø§ÛŒ <think>...</think> Ø¨Ø§Ù‚ÛŒÙ…Ø§Ù†Ø¯Ù‡ (Ø§Ú¯Ø± Ù…Ø¯Ù„ Ø¨Ø§ ÙˆØ¬ÙˆØ¯ reasoning_format Ù‡Ù… Ø¨ÙØ±Ø³ØªÙ‡)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"</?think>", "", text)
    # Ø­Ø°Ù Ù†Ø´Ø§Ù†Ù‡â€ŒÙ‡Ø§ÛŒ Ù…Ø§Ø±Ú©â€ŒØ¯Ø§ÙˆÙ† Ú©Ù‡ ØªÙ„Ú¯Ø±Ø§Ù… Ø¨Ø¯ÙˆÙ† parse_mode Ø±Ù†Ø¯Ø±Ø´ÙˆÙ† Ù†Ù…ÛŒâ€ŒÚ©Ù†Ù‡
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"^[ \t]*[\*\-][ \t]+", "â€¢ ", text, flags=re.MULTILINE)
    text = re.sub(r"^#{1,6}[ \t]*", "", text, flags=re.MULTILINE)
    return text.strip()


def send_long_message(message, text, reply_markup=None):
    text = clean_text(text)
    if not text:
        text = "(Ù¾Ø§Ø³Ø®ÛŒ Ø¯Ø±ÛŒØ§ÙØª Ù†Ø´Ø¯)"

    chunks = [text[i:i + TELEGRAM_MAX_LEN] for i in range(0, len(text), TELEGRAM_MAX_LEN)]

    for i, chunk in enumerate(chunks):
        is_last = (i == len(chunks) - 1)
        markup = reply_markup if is_last else None
        if i == 0:
            bot.reply_to(message, chunk, reply_markup=markup)
        else:
            bot.send_message(message.chat.id, chunk, reply_markup=markup)


# Ûµ. Ø¯Ø³ØªÙˆØ± Ø´Ø±ÙˆØ¹ Ø±Ø¨Ø§Øª: Ù†Ù…Ø§ÛŒØ´ Ù…Ù†ÙˆÛŒ Ø§ØµÙ„ÛŒ
@bot.message_handler(commands=['start'])
def handle_start(message):
    chat_id = message.chat.id
    ACTIVE_CHATS[chat_id] = False
    bot.send_message(
        chat_id,
        "ðŸ‘‹ Ø¨Ù‡ Ø±Ø¨Ø§Øª Ø®ÙˆØ´ Ø§ÙˆÙ…Ø¯ÛŒ!\n\nØ¨Ø±Ø§ÛŒ Ø´Ø±ÙˆØ¹ Ú¯ÙØªÚ¯Ùˆ Ø¨Ø§ Ù‡ÙˆØ´ Ù…ØµÙ†ÙˆØ¹ÛŒØŒ Ø¯Ú©Ù…Ù‡â€ŒÛŒ Â«Ø´Ø±ÙˆØ¹ Ú¯ÙØªÚ¯ÙˆÂ» Ø±Ùˆ Ø¨Ø²Ù†. "
        "Ù‡Ø± ÙˆÙ‚Øª Ø®ÙˆØ§Ø³ØªÛŒ Ú¯ÙØªÚ¯Ùˆ ØªÙ…Ø§Ù… Ø¨Ø´Ù‡ØŒ Ø¯Ú©Ù…Ù‡â€ŒÛŒ Â«Ù¾Ø§ÛŒØ§Ù† Ú¯ÙØªÚ¯ÙˆÂ» Ø±Ùˆ Ø¨Ø²Ù†.",
        reply_markup=main_menu_keyboard()
    )


# Û¶. Ø¯Ø³ØªÙˆØ± /reset Ø¨Ø±Ø§ÛŒ Ù¾Ø§Ú© Ú©Ø±Ø¯Ù† Ø­Ø§ÙØ¸Ù‡ Ù…Ú©Ø§Ù„Ù…Ù‡ (Ø¨Ø¯ÙˆÙ† ØªØºÛŒÛŒØ± ÙˆØ¶Ø¹ÛŒØª ÙØ¹Ø§Ù„/ØºÛŒØ±ÙØ¹Ø§Ù„)
@bot.message_handler(commands=['reset', 'new'])
def handle_reset(message):
    CONVERSATION_HISTORY[message.chat.id] = []
    bot.reply_to(message, "âœ… Ø­Ø§ÙØ¸Ù‡ Ù…Ú©Ø§Ù„Ù…Ù‡ Ù¾Ø§Ú© Ø´Ø¯.")


# Û·. Ø¯Ú©Ù…Ù‡ Â«Ø´Ø±ÙˆØ¹ Ú¯ÙØªÚ¯ÙˆÂ»
@bot.message_handler(func=lambda message: message.text == BTN_START_CHAT)
def handle_start_chat_button(message):
    chat_id = message.chat.id
    ACTIVE_CHATS[chat_id] = True
    CONVERSATION_HISTORY[chat_id] = []  # Ø´Ø±ÙˆØ¹ ØªØ§Ø²Ù‡
    bot.send_message(
        chat_id,
        "âœ… Ú¯ÙØªÚ¯Ùˆ Ø´Ø±ÙˆØ¹ Ø´Ø¯! Ù‡Ø± Ø³ÙˆØ§Ù„ÛŒ Ø¯Ø§Ø±ÛŒ Ø¨Ù¾Ø±Ø³ ÛŒØ§ Ø¹Ú©Ø³ Ø¨ÙØ±Ø³Øª.\nØ¨Ø±Ø§ÛŒ Ù¾Ø§ÛŒØ§Ù† Ø¯Ø§Ø¯Ù†ØŒ Ø¯Ú©Ù…Ù‡â€ŒÛŒ Â«Ù¾Ø§ÛŒØ§Ù† Ú¯ÙØªÚ¯ÙˆÂ» Ø±Ùˆ Ø¨Ø²Ù†.",
        reply_markup=main_menu_keyboard()
    )


# Û¸. Ø¯Ú©Ù…Ù‡ Â«Ù¾Ø§ÛŒØ§Ù† Ú¯ÙØªÚ¯ÙˆÂ»
@bot.message_handler(func=lambda message: message.text == BTN_END_CHAT)
def handle_end_chat_button(message):
    chat_id = message.chat.id
    ACTIVE_CHATS[chat_id] = False
    CONVERSATION_HISTORY[chat_id] = []
    bot.send_message(
        chat_id,
        "ðŸ”´ Ú¯ÙØªÚ¯Ùˆ Ù¾Ø§ÛŒØ§Ù† ÛŒØ§ÙØª. Ù‡Ø± ÙˆÙ‚Øª Ø®ÙˆØ§Ø³ØªÛŒ Ø¯ÙˆØ¨Ø§Ø±Ù‡ Ø´Ø±ÙˆØ¹ Ú©Ù†ÛŒØŒ Ø¯Ú©Ù…Ù‡â€ŒÛŒ Â«Ø´Ø±ÙˆØ¹ Ú¯ÙØªÚ¯ÙˆÂ» Ø±Ùˆ Ø¨Ø²Ù†.",
        reply_markup=main_menu_keyboard()
    )


# Û¹. Ø¯Ø±ÛŒØ§ÙØª Ùˆ Ù¾Ø§Ø³Ø® Ø¨Ù‡ Ø¹Ú©Ø³â€ŒÙ‡Ø§ (ÙÙ‚Ø· ÙˆÙ‚ØªÛŒ Ú¯ÙØªÚ¯Ùˆ ÙØ¹Ø§Ù„ Ø¨Ø§Ø´Ø¯)
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id
    if not is_chat_active(chat_id):
        bot.send_message(
            chat_id,
            "Ø¨Ø±Ø§ÛŒ Ø´Ø±ÙˆØ¹ØŒ Ø§ÙˆÙ„ Ø¯Ú©Ù…Ù‡â€ŒÛŒ Â«Ø´Ø±ÙˆØ¹ Ú¯ÙØªÚ¯ÙˆÂ» Ø±Ùˆ Ø¨Ø²Ù† ðŸ‘‡",
            reply_markup=main_menu_keyboard()
        )
        return

    try:
        bot.send_chat_action(chat_id, "typing")

        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        user_prompt = message.caption if message.caption else "Ø§ÛŒÙ† ØªØµÙˆÛŒØ± Ø±Ø§ ØªÙˆØµÛŒÙ Ú©Ù†."

        reply = ask_groq_vision(downloaded_file, user_prompt)
        send_long_message(message, reply)
    except Exception as e:
        print(f"Error handling photo: {e}")
        try:
            bot.reply_to(message, f"âŒ Ø®Ø·Ø§ Ø¯Ø± Ù¾Ø±Ø¯Ø§Ø²Ø´ Ø¹Ú©Ø³: {str(e)}")
        except Exception:
            pass


# Û±Û°. Ø¯Ø±ÛŒØ§ÙØª Ùˆ Ù¾Ø§Ø³Ø® Ø¨Ù‡ Ù¾ÛŒØ§Ù…â€ŒÙ‡Ø§ÛŒ Ù…ØªÙ†ÛŒ (ÙÙ‚Ø· ÙˆÙ‚ØªÛŒ Ú¯ÙØªÚ¯Ùˆ ÙØ¹Ø§Ù„ Ø¨Ø§Ø´Ø¯ØŒ Ø¨Ø§ Ø­ÙØ¸ ØªØ§Ø±ÛŒØ®Ú†Ù‡ Ù…Ú©Ø§Ù„Ù…Ù‡)
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if not message.text:
        return

    chat_id = message.chat.id

    if not is_chat_active(chat_id):
        bot.send_message(
            chat_id,
            "Ø¨Ø±Ø§ÛŒ Ø´Ø±ÙˆØ¹ØŒ Ø§ÙˆÙ„ Ø¯Ú©Ù…Ù‡â€ŒÛŒ Â«Ø´Ø±ÙˆØ¹ Ú¯ÙØªÚ¯ÙˆÂ» Ø±Ùˆ Ø¨Ø²Ù† ðŸ‘‡",
            reply_markup=main_menu_keyboard()
        )
        return

    try:
        bot.send_chat_action(chat_id, "typing")
        reply = ask_groq(chat_id, message.text)
        send_long_message(message, reply)
    except Exception as e:
        print(f"Error handling message: {e}")


# Û±Û±. Ø§Ø¬Ø±Ø§ÛŒ Ø±Ø¨Ø§Øª ØªÙ„Ú¯Ø±Ø§Ù… Ø¨Ù‡ ØµÙˆØ±Øª Ø§ÛŒÙ…Ù† Ùˆ Ø®ÙˆØ¯Ú©Ø§Ø±
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
    # Ø«Ø¨Øª Ø®ÙˆØ¯Ú©Ø§Ø± Ù„ÛŒØ³Øª Ø¯Ø³ØªÙˆØ±Ø§Øª Ø±Ø¨Ø§Øª (Ù‡Ù…ÙˆÙ† Ù…Ù†ÙˆÛŒ Ú©Ù†Ø§Ø± Ø¬Ø¹Ø¨Ù‡ Ù¾ÛŒØ§Ù…) â€” Ù†ÛŒØ§Ø²ÛŒ Ø¨Ù‡ Ø¨Ø§Øªâ€ŒÙØ§Ø¯Ø± Ù†ÛŒØ³Øª
    try:
        bot.set_my_commands([
            types.BotCommand("start", "Ù†Ù…Ø§ÛŒØ´ Ù…Ù†ÙˆÛŒ Ø§ØµÙ„ÛŒ Ø±Ø¨Ø§Øª"),
            types.BotCommand("reset", "Ù¾Ø§Ú© Ú©Ø±Ø¯Ù† Ø­Ø§ÙØ¸Ù‡ Ù…Ú©Ø§Ù„Ù…Ù‡"),
        ])
    except Exception as e:
        print(f"Command menu setup note: {e}")

    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
