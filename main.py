import os
import re
import json
import time
import io
import asyncio
import uuid
import threading
import base64
import random
import urllib.parse
import requests
import telebot
import edge_tts
import numpy as np
import cv2
import qrcode
from PIL import Image, ImageFilter
from telebot import types
from flask import Flask

# ۱. دریافت کلیدها از Environment
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()  # کلید رایگان Google AI Studio (فعلاً استفاده نمی‌شه)
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "").strip()  # برای سرچ در اینترنت
JINA_API_KEY = os.environ.get("JINA_API_KEY", "").strip()      # برای خواندن سند (اختیاری؛ بدون کلید هم با محدودیت کمتر کار می‌کنه)
POLLINATIONS_API_KEY = os.environ.get("POLLINATIONS_API_KEY", "").strip()  # لازم برای مدل kontext (ساخت عکس بر اساس عکس مرجع)
BRSAPI_KEY = os.environ.get("BRSAPI_KEY", "").strip()  # برای قیمت طلا/ارز/کریپتو ایران (رایگان از BrsApi.ir)

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# مدل گفتگوی عادی (پیش‌فرض، اگه کاربر مدلی انتخاب نکرده باشه)
VISION_MODEL_NAME = "qwen/qwen3.6-27b"  # مدل ویژن Groq برای پردازش عکس
STT_MODEL_NAME = "whisper-large-v3-turbo"  # مدل تبدیل ویس به متن (چندزبانه، فارسی هم پشتیبانی می‌کنه)

# مدل‌های قابل انتخاب برای حالت گفتگو — با زدن «شروع گفتگو» کاربر از بین این‌ها انتخاب می‌کنه
# نکته: مدل‌های groq/compound و groq/compound-mini (که خودشون سرچ می‌کردن) به‌خاطر
# گیر کردن مکرر روی محدودیت نرخ (rate limit / خطای ۴۲۹) کاملاً از لیست حذف شدن.
CHAT_MODEL_OPTIONS = [
    {"id": "openai/gpt-oss-20b", "label": "⚡ سریع", "desc": "پاسخ‌گویی سریع برای گفتگوی روزمره"},
    {"id": "openai/gpt-oss-120b", "label": "🧠 قوی‌تر", "desc": "مدل بزرگ‌تر برای سوال‌های پیچیده‌تر"},
    {"id": "qwen/qwen3.6-27b", "label": "🖇 چندمنظوره", "desc": "متن و تصویر با هم، مناسب تحلیل ترکیبی"},
]
DEFAULT_CHAT_MODEL = CHAT_MODEL_OPTIONS[0]["id"]

# مدل انتخابی هر چت (chat_id -> model_id)
CHAT_MODEL_CHOICE = {}

SYSTEM_PROMPT = "You are a helpful AI assistant that answers in the user's language (mostly Persian). Answer clearly and accurately."

# دکمه‌های منوی اصلی
BTN_START_CHAT = "🟢 شروع گفتگو"
BTN_IMAGE = "🖼 ساخت عکس"
BTN_STT = "🎙 ویس به متن"
BTN_TTS = "🔊 متن به گفتار"
BTN_SEARCH = "🔎 سرچ در اینترنت"
BTN_DOC = "📄 خواندن سند"
BTN_UPSCALE = "🔍 افزایش کیفیت عکس"
BTN_WEATHER = "🌤 وضعیت هوا"
BTN_CURRENCY = "💱 تبدیل ارز"
BTN_UNIT = "📏 تبدیل واحد"
BTN_QR = "🔳 QR کد"
BTN_TRANSLATE = "🌐 ترجمه‌ی سریع"
BTN_CRYPTO = "🪙 قیمت کریپتو"
BTN_GOLD = "💰 دلار و طلا (ایران)"
# دکمه‌های پایان هر حالت
BTN_END_CHAT = "🔴 پایان گفتگو"
BTN_END_IMAGE = "🔴 پایان ساخت عکس"
BTN_END_STT = "🔴 پایان ویس به متن"
BTN_END_TTS = "🔴 پایان متن به گفتار"
BTN_END_SEARCH = "🔴 پایان سرچ"
BTN_END_DOC = "🔴 پایان خواندن سند"
BTN_END_UPSCALE = "🔴 پایان افزایش کیفیت"
BTN_END_WEATHER = "🔴 پایان وضعیت هوا"
BTN_END_CURRENCY = "🔴 پایان تبدیل ارز"
BTN_END_UNIT = "🔴 پایان تبدیل واحد"
BTN_END_QR = "🔴 پایان QR کد"
BTN_END_TRANSLATE = "🔴 پایان ترجمه"
BTN_END_CRYPTO = "🔴 پایان قیمت کریپتو"
BTN_END_GOLD = "🔴 پایان دلار و طلا"

# روش‌های افزایش کیفیت عکس — کاربر با زدن دکمه‌ی «افزایش کیفیت عکس» یکی رو انتخاب می‌کنه
UPSCALE_METHOD_OPTIONS = [
    {"id": "pillow", "label": "🅿️ Pillow (شارپ)", "desc": "بزرگ‌نمایی + فیلتر شارپ‌کننده"},
    {"id": "opencv", "label": "🅾️ OpenCV (Cubic)", "desc": "بزرگ‌نمایی هوشمند با درون‌یابی Cubic"},
    {"id": "combo", "label": "🔀 ترکیبی (هر دو)", "desc": "بزرگ‌نمایی OpenCV + شارپ Pillow"},
]
DEFAULT_UPSCALE_METHOD = "combo"
UPSCALE_METHOD_CHOICE = {}  # chat_id -> method id
UPSCALE_METHOD_BUTTON_TEXTS = {f"{opt['label']} — {opt['desc']}": opt["id"] for opt in UPSCALE_METHOD_OPTIONS}

# صدای پیش‌فرض برای تبدیل متن به گفتار (edge-tts) — فارسی، زن
TTS_VOICE = "fa-IR-DilaraNeural"

# متن دکمه‌های انتخاب مدل (کیبورد پایین صفحه) → آیدی مدل
MODEL_BUTTON_TEXTS = {f"{opt['label']} — {opt['desc']}": opt["id"] for opt in CHAT_MODEL_OPTIONS}

# ==== تنظیمات عضویت اجباری ====
# یوزرنیم کانال‌هایی که کاربر باید عضوشون باشه (بدون @ ولی با @ هم کار می‌کنه، کد خودش مدیریت می‌کنه)
# نکته مهم: ربات باید در همه‌ی این کانال‌ها ادمین باشه، وگرنه نمی‌تونه وضعیت عضویت رو چک کنه.
REQUIRED_CHANNELS = [
    "@WiseGPTbotChannel",
]

CALLBACK_CHECK_JOIN = "check_join"
# ================================

# حافظه‌ی مکالمه: برای هر چت (chat_id) لیستی از پیام‌های قبلی نگه می‌داریم.
# توجه: چون در حافظه (RAM) ذخیره می‌شه، با ری‌استارت شدن سرویس روی Render پاک می‌شه.
CONVERSATION_HISTORY = {}
MAX_HISTORY_MESSAGES = 20  # حداکثر تعداد پیام (کاربر+ربات) که برای هر چت نگه داشته می‌شه

# وضعیت هر چت: None (منوی اصلی) / "choosing_model" (در حال انتخاب مدل) / "chat" (حالت گفتگو) / "image" / "stt"
CHAT_MODE = {}


def get_mode(chat_id):
    return CHAT_MODE.get(chat_id)


def set_mode(chat_id, mode):
    CHAT_MODE[chat_id] = mode


def get_history(chat_id):
    return CONVERSATION_HISTORY.setdefault(chat_id, [])


def trim_history(chat_id):
    history = CONVERSATION_HISTORY.get(chat_id, [])
    if len(history) > MAX_HISTORY_MESSAGES:
        CONVERSATION_HISTORY[chat_id] = history[-MAX_HISTORY_MESSAGES:]


def main_menu_keyboard():
    """
    دکمه‌های منوی اصلی رو خودکار می‌چینه تا با اضافه شدن قابلیت جدید، منو
    به‌جای طولانی و عمودی شدن، فشرده بمونه:
    - تا ۴ دکمه: دو ستون (دوتا-دوتا)
    - از ۵ دکمه به بالا: سه ستون (سه‌تا-سه‌تا) تا فضای کمتری بگیره
    اگه تعداد دکمه‌ها بخش‌پذیر نباشه، آخرین ردیف با تعداد کمتر پر می‌شه.
    """
    buttons = [
        BTN_START_CHAT, BTN_IMAGE, BTN_STT, BTN_TTS, BTN_SEARCH, BTN_DOC, BTN_UPSCALE,
        BTN_WEATHER, BTN_CURRENCY, BTN_UNIT, BTN_QR, BTN_TRANSLATE, BTN_CRYPTO, BTN_GOLD,
    ]  # هر قابلیت جدید رو همینجا اضافه کن
    columns = 3 if len(buttons) >= 5 else 2

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for i in range(0, len(buttons), columns):
        row = buttons[i:i + columns]
        keyboard.row(*[types.KeyboardButton(b) for b in row])
    return keyboard


def chat_active_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(types.KeyboardButton(BTN_END_CHAT))
    return keyboard


def image_active_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(types.KeyboardButton(BTN_END_IMAGE))
    return keyboard


def stt_active_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(types.KeyboardButton(BTN_END_STT))
    return keyboard


def tts_active_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(types.KeyboardButton(BTN_END_TTS))
    return keyboard


def search_active_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(types.KeyboardButton(BTN_END_SEARCH))
    return keyboard


def doc_active_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(types.KeyboardButton(BTN_END_DOC))
    return keyboard


def upscale_active_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(types.KeyboardButton(BTN_END_UPSCALE))
    return keyboard


def upscale_method_selection_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for button_text in UPSCALE_METHOD_BUTTON_TEXTS:
        keyboard.row(types.KeyboardButton(button_text))
    return keyboard


def _simple_end_keyboard(end_button_text):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(types.KeyboardButton(end_button_text))
    return keyboard


def weather_active_keyboard():
    return _simple_end_keyboard(BTN_END_WEATHER)


def currency_active_keyboard():
    return _simple_end_keyboard(BTN_END_CURRENCY)


def unit_active_keyboard():
    return _simple_end_keyboard(BTN_END_UNIT)


def qr_active_keyboard():
    return _simple_end_keyboard(BTN_END_QR)


def translate_active_keyboard():
    return _simple_end_keyboard(BTN_END_TRANSLATE)


def crypto_active_keyboard():
    return _simple_end_keyboard(BTN_END_CRYPTO)


def gold_active_keyboard():
    return _simple_end_keyboard(BTN_END_GOLD)


def model_selection_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for button_text in MODEL_BUTTON_TEXTS:
        keyboard.row(types.KeyboardButton(button_text))
    return keyboard


def get_not_joined_channels(user_id):
    """کانال‌هایی که کاربر هنوز عضوشون نشده رو برمی‌گردونه."""
    not_joined = []
    for channel in REQUIRED_CHANNELS:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status in ("left", "kicked"):
                not_joined.append(channel)
        except Exception as e:
            # اگه ربات ادمین کانال نباشه یا یوزرنیم اشتباه باشه، این خطا میفته
            print(f"خطا در بررسی عضویت کانال {channel}: {e}")
            not_joined.append(channel)
    return not_joined


def force_sub_keyboard(not_joined_channels):
    keyboard = types.InlineKeyboardMarkup()
    for channel in not_joined_channels:
        username = channel.lstrip("@")
        keyboard.add(types.InlineKeyboardButton(f"📢 عضویت در {channel}", url=f"https://t.me/{username}"))
    keyboard.add(types.InlineKeyboardButton("✅ عضو شدم", callback_data=CALLBACK_CHECK_JOIN))
    return keyboard


def send_join_required_message(chat_id, not_joined_channels):
    bot.send_message(
        chat_id,
        "📣 برای استفاده از ربات، لطفاً ابتدا در کانال‌های زیر عضو شوید و سپس روی «✅ عضو شدم» بزنید.",
        reply_markup=force_sub_keyboard(not_joined_channels)
    )


def check_membership_and_notify(message):
    """اگه REQUIRED_CHANNELS خالی باشه یعنی عضویت اجباری غیرفعاله."""
    if not REQUIRED_CHANNELS:
        return True
    not_joined = get_not_joined_channels(message.from_user.id)
    if not_joined:
        send_join_required_message(message.chat.id, not_joined)
        return False
    return True


# ۲. وب‌سرور Flask برای زنده نگه داشتن سرور Render
@app.route("/")
def home():
    return "Bot is running 24/7!", 200


# تابع کمکی برای فراخوانی امن API گروک (با رفع مشکل انکودینگ UTF-8)
def call_groq_api(payload, timeout):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }
    response = requests.post(url, headers=headers, json=payload, timeout=timeout)
    # نکته مهم: بدون این خط، اگر سرور هدر charset نفرسته باشه، requests فرض می‌کنه
    # متن ISO-8859-1 است و کاراکترهای فارسی/یونیکد به‌صورت خراب (mojibake) نمایش داده می‌شن.
    response.encoding = "utf-8"
    data = json.loads(response.text)

    if response.status_code == 200 and "choices" in data and len(data["choices"]) > 0:
        return data["choices"][0]["message"]["content"]
    elif response.status_code == 413:
        return "❌ درخواستت (متن یا تاریخچه‌ی گفتگو) خیلی حجیمه. با /reset حافظه رو پاک کن و دوباره امتحان کن."
    elif response.status_code == 429:
        return "❌ سرویس موقتاً شلوغه (محدودیت نرخ). چند ثانیه صبر کن و دوباره امتحان کن."
    else:
        err_msg = data.get("error", {}).get("message", response.text)
        return f"❌ خطای Groq (کد {response.status_code}): {err_msg}"


# ۳. ارسال درخواست به API مدل Groq (متن) همراه با تاریخچه مکالمه
def ask_groq(chat_id, prompt):
    if not GROQ_API_KEY:
        return "❌ خطا: متغیر GROQ_API_KEY در Render تنظیم نشده است."

    history = get_history(chat_id)
    model_id = CHAT_MODEL_CHOICE.get(chat_id, DEFAULT_CHAT_MODEL)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1024
    }
    # مدل‌های خانواده‌ی gpt-oss از reasoning_format پشتیبانی می‌کنن (برای مخفی کردن تگ <think>)
    if "gpt-oss" in model_id:
        payload["reasoning_format"] = "hidden"

    try:
        reply = call_groq_api(payload, timeout=45)
    except Exception as e:
        return f"❌ خطای ارتباطی: {str(e)}"

    # فقط وقتی جواب موفق بود، به تاریخچه اضافه کن (پیام‌های خطا رو ذخیره نمی‌کنیم)
    if not reply.startswith("❌"):
        history.append({"role": "user", "content": prompt})
        history.append({"role": "assistant", "content": reply})
        trim_history(chat_id)

    return reply


# ۳ب. ارسال عکس به مدل ویژن Groq برای پردازش
def ask_groq_vision(image_bytes, prompt="این تصویر را توصیف کن."):
    if not GROQ_API_KEY:
        return "❌ خطا: متغیر GROQ_API_KEY در Render تنظیم نشده است."

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
        "reasoning_format": "hidden",  # جلوگیری از نمایش تگ <think> در جواب
        "reasoning_effort": "none"     # خاموش کردن کامل حالت فکر کردن برای مدل qwen3
    }

    try:
        return call_groq_api(payload, timeout=30)
    except Exception as e:
        return f"❌ خطای ارتباطی: {str(e)}"


# ۳ج. تبدیل ویس به متن با مدل Whisper گروک (چندزبانه، فارسی رو هم خوب تشخیص می‌ده)
def transcribe_voice(audio_bytes, filename="voice.ogg"):
    if not GROQ_API_KEY:
        return "❌ خطا: متغیر GROQ_API_KEY در Render تنظیم نشده است."

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    files = {"file": (filename, audio_bytes)}
    data = {"model": STT_MODEL_NAME}

    try:
        response = requests.post(url, headers=headers, files=files, data=data, timeout=60)
        response.encoding = "utf-8"
        result = json.loads(response.text)

        if response.status_code == 200 and "text" in result:
            text = result["text"].strip()
            return text if text else "(چیزی توی ویس تشخیص داده نشد)"
        else:
            err_msg = result.get("error", {}).get("message", response.text)
            return f"❌ خطای Groq (کد {response.status_code}): {err_msg}"
    except Exception as e:
        return f"❌ خطای ارتباطی: {str(e)}"


# ۳ج. تبدیل متن به گفتار با edge-tts (رایگان، بدون کلید، فارسی هم پشتیبانی می‌کنه)
async def _generate_speech_async(text, voice, output_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def generate_speech(text, voice=TTS_VOICE):
    max_chars = 3000
    text = text[:max_chars]
    output_path = f"/tmp/tts_{uuid.uuid4().hex}.mp3"
    try:
        asyncio.run(_generate_speech_async(text, voice, output_path))
        with open(output_path, "rb") as f:
            audio_bytes = f.read()
        return audio_bytes, None
    except Exception as e:
        return None, str(e)
    finally:
        if os.path.exists(output_path):
            os.remove(output_path)


# ۳د. سرچ واقعی در وب با Tavily (نتیجه شامل خلاصه‌ی آماده + لینک منابع)
def ask_tavily_search(query):
    if not TAVILY_API_KEY:
        return "❌ خطا: متغیر TAVILY_API_KEY در Render تنظیم نشده است."

    url = "https://api.tavily.com/search"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {TAVILY_API_KEY}"}
    payload = {
        "query": query,
        "search_depth": "advanced",
        "include_answer": "advanced",
        "max_results": 5
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.encoding = "utf-8"
        data = json.loads(response.text)
    except Exception as e:
        return f"❌ خطای ارتباطی: {str(e)}"

    if response.status_code != 200:
        err_msg = data.get("error", data.get("detail", response.text))
        return f"❌ خطای Tavily (کد {response.status_code}): {err_msg}"

    answer = (data.get("answer") or "").strip()
    results = data.get("results", [])[:3]

    parts = []
    if answer:
        parts.append(answer)
    if results:
        sources = "\n".join(f"🔗 {r.get('title', 'منبع')}: {r.get('url', '')}" for r in results)
        parts.append("منابع:\n" + sources)

    return "\n\n".join(parts) if parts else "(چیزی پیدا نشد)"


# ۳ه. تبدیل PDF به متن با Jina Reader (بدون نیاز به دانلود فایل روی سرور خودمون)
def read_pdf_via_jina(telegram_file_url):
    jina_url = f"https://r.jina.ai/{telegram_file_url}"
    headers = {}
    if JINA_API_KEY:
        headers["Authorization"] = f"Bearer {JINA_API_KEY}"

    try:
        response = requests.get(jina_url, headers=headers, timeout=60)
        response.encoding = "utf-8"
    except Exception as e:
        return None, f"❌ خطای ارتباطی با Jina Reader: {str(e)}"

    if response.status_code != 200:
        return None, f"❌ خطای Jina Reader (کد {response.status_code}): {response.text[:300]}"

    return response.text, None


# ۳و. خلاصه‌سازی/پاسخ‌گویی درباره‌ی متن استخراج‌شده از سند، با مدل سریع Groq
def summarize_document_text(document_text, question):
    if not GROQ_API_KEY:
        return "❌ خطا: متغیر GROQ_API_KEY در Render تنظیم نشده است."

    # سند رو کمی کوتاه می‌کنیم تا از محدودیت توکن رد نشیم
    max_chars = 20000
    trimmed = document_text[:max_chars]

    prompt = f"متن زیر از یک سند استخراج شده:\n\n{trimmed}\n\n---\n\nبراساس این متن، به فارسی جواب بده: {question}"
    payload = {
        "model": "openai/gpt-oss-20b",
        "messages": [
            {"role": "system", "content": "You answer in Persian based only on the document text provided by the user."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.5,
        "max_tokens": 1024,
        "reasoning_format": "hidden"
    }
    try:
        return call_groq_api(payload, timeout=30)
    except Exception as e:
        return f"❌ خطای ارتباطی: {str(e)}"


# ۴. تابع کمکی برای پاکسازی و تقسیم پیام‌های طولانی (محدودیت تلگرام: ۴۰۹۶ کاراکتر)
TELEGRAM_MAX_LEN = 4000  # کمی کمتر از ۴۰۹۶ برای اطمینان


# ۳د. ساخت عکس از روی توضیح متنی با سرویس رایگان Pollinations.ai (بدون نیاز به API Key)
# نکته: این سرویس جدا از Groq است، چون Groq مدل ساخت عکس (Text-to-Image) ندارد.
def generate_image(prompt):
    encoded_prompt = urllib.parse.quote(prompt)
    seed = random.randint(1, 1_000_000)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&seed={seed}&nologo=true"

    try:
        response = requests.get(url, timeout=60)
    except Exception as e:
        print(f"Image generation request error: {e}")
        return None, f"خطای ارتباطی: {str(e)}"

    content_type = response.headers.get("content-type", "")
    if response.status_code == 200 and content_type.startswith("image"):
        return response.content, None

    # لاگ کردن جزئیات دقیق برای عیب‌یابی (توی Render قابل مشاهده‌ست)
    body_preview = response.text[:300] if not content_type.startswith("image") else "(باینری تصویر نامعتبر)"
    print(f"Image generation failed — status={response.status_code}, content-type={content_type}, body={body_preview}")
    error_detail = f"کد {response.status_code}"
    if body_preview and not body_preview.startswith("(باینری"):
        error_detail += f" — {body_preview}"
    return None, error_detail


# ۳ک. ساخت عکس بر اساس عکس مرجع (مدل kontext) — طبق مستندات رسمی، باید فایل عکس مستقیم آپلود بشه
# (نه فقط URL)، از endpoint جدید gen.pollinations.ai/v1/images/edits
def generate_image_from_reference(image_bytes, prompt, filename="input.jpg"):
    if not POLLINATIONS_API_KEY:
        return None, "برای ساخت عکس بر اساس عکس مرجع، باید متغیر POLLINATIONS_API_KEY رو در Render تنظیم کنی (رایگان از enter.pollinations.ai)."

    url = "https://gen.pollinations.ai/v1/images/edits"
    headers = {"Authorization": f"Bearer {POLLINATIONS_API_KEY}"}
    files = {"image": (filename, image_bytes)}
    data = {"prompt": prompt, "model": "kontext"}

    try:
        response = requests.post(url, headers=headers, files=files, data=data, timeout=90)
    except Exception as e:
        print(f"Kontext request error: {e}")
        return None, f"خطای ارتباطی: {str(e)}"

    content_type = response.headers.get("content-type", "")

    if response.status_code == 200:
        # اگه مستقیم باینری تصویر برگردوند
        if content_type.startswith("image"):
            return response.content, None
        # وگرنه طبق فرمت OpenAI-compatible، JSON با b64_json یا url برمی‌گردونه
        try:
            result = response.json()
            item = result.get("data", [{}])[0]
            if item.get("b64_json"):
                return base64.b64decode(item["b64_json"]), None
            if item.get("url"):
                img_resp = requests.get(item["url"], timeout=60)
                if img_resp.status_code == 200:
                    return img_resp.content, None
            return None, f"فرمت پاسخ ناشناخته: {str(result)[:300]}"
        except Exception as e:
            return None, f"خطا در پردازش پاسخ: {str(e)} — {response.text[:300]}"

    body_preview = response.text[:300]
    print(f"Kontext generation failed — status={response.status_code}, body={body_preview}")
    return None, f"کد {response.status_code} — {body_preview}"


# ۳ل. افزایش کیفیت عکس با کتابخونه‌های محلی Pillow و OpenCV (رایگان، بدون کلید، اجرا روی خود سرور)
def _upscale_with_pillow(image_bytes, scale=2):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    new_size = (img.width * scale, img.height * scale)
    img = img.resize(new_size, Image.LANCZOS)
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
    output = io.BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()


def _upscale_with_opencv(image_bytes, scale=2):
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    new_size = (img.shape[1] * scale, img.shape[0] * scale)
    resized = cv2.resize(img, new_size, interpolation=cv2.INTER_CUBIC)
    success, buffer = cv2.imencode(".png", resized)
    if not success:
        return None
    return buffer.tobytes()


def _apply_pillow_sharpen_only(image_bytes):
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
    output = io.BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()


def upscale_image(image_bytes, method="combo", scale=2):
    try:
        if method == "pillow":
            return _upscale_with_pillow(image_bytes, scale), None

        elif method == "opencv":
            result = _upscale_with_opencv(image_bytes, scale)
            if result is None:
                return None, "عکس قابل خواندن نبود (فرمت پشتیبانی‌نشده یا فایل خراب)."
            return result, None

        else:  # combo: بزرگ‌نمایی هوشمند OpenCV + شارپ‌کردن Pillow
            resized = _upscale_with_opencv(image_bytes, scale)
            if resized is None:
                return None, "عکس قابل خواندن نبود (فرمت پشتیبانی‌نشده یا فایل خراب)."
            return _apply_pillow_sharpen_only(resized), None
    except Exception as e:
        print(f"Local upscale error: {e}")
        return None, f"خطا در پردازش عکس: {str(e)}"


# ۳م. وضعیت هوا با Open-Meteo (رایگان، بدون کلید)
def get_weather(city_name):
    try:
        geo_url = "https://geocoding-api.open-meteo.com/v1/search"
        geo_resp = requests.get(geo_url, params={"name": city_name, "count": 1, "language": "fa"}, timeout=15)
        geo_data = geo_resp.json()
        results = geo_data.get("results")
        if not results:
            return f"❌ شهری با نام «{city_name}» پیدا نشد."

        place = results[0]
        lat, lon = place["latitude"], place["longitude"]
        display_name = place.get("name", city_name)
        country = place.get("country", "")

        weather_url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
            "timezone": "auto"
        }
        weather_resp = requests.get(weather_url, params=params, timeout=15)
        current = weather_resp.json().get("current", {})

        weather_codes = {
            0: "☀️ صاف", 1: "🌤 عمدتاً صاف", 2: "⛅️ نیمه‌ابری", 3: "☁️ ابری",
            45: "🌫 مه", 48: "🌫 مه یخی", 51: "🌦 نم‌نم باران", 61: "🌧 باران",
            63: "🌧 باران متوسط", 65: "🌧 باران شدید", 71: "🌨 برف", 73: "🌨 برف متوسط",
            75: "❄️ برف شدید", 80: "🌦 رگبار", 95: "⛈ رعدوبرق"
        }
        code = current.get("weather_code")
        condition = weather_codes.get(code, "نامشخص")

        return (
            f"📍 {display_name}, {country}\n\n"
            f"{condition}\n"
            f"🌡 دما: {current.get('temperature_2m')}°C\n"
            f"💧 رطوبت: {current.get('relative_humidity_2m')}%\n"
            f"💨 سرعت باد: {current.get('wind_speed_10m')} کیلومتر/ساعت"
        )
    except Exception as e:
        print(f"Weather error: {e}")
        return f"❌ خطا در دریافت وضعیت هوا: {str(e)}"


# ۳ن. تبدیل ارز با Frankfurter (رایگان، بدون کلید)
def convert_currency(text):
    # فرمت‌های قابل قبول: "100 USD to EUR"، "100 دلار به یورو"
    match = re.search(r"([\d.,]+)\s*([a-zA-Zآ-ی]+)\s*(?:to|به)\s*([a-zA-Zآ-ی]+)", text, re.IGNORECASE)
    if not match:
        return "❌ فرمت درست نیست. مثال: «100 USD to EUR» یا «100 دلار به یورو»"

    amount_str, from_cur, to_cur = match.groups()
    amount = float(amount_str.replace(",", ""))

    currency_aliases = {
        "دلار": "USD", "یورو": "EUR", "پوند": "GBP", "ین": "JPY",
        "لیر": "TRY", "درهم": "AED", "یوان": "CNY", "روبل": "RUB",
        "تومان": "IRR", "ریال": "IRR",
    }
    from_cur = currency_aliases.get(from_cur, from_cur.upper())
    to_cur = currency_aliases.get(to_cur, to_cur.upper())

    try:
        url = "https://api.frankfurter.app/latest"
        response = requests.get(url, params={"amount": amount, "from": from_cur, "to": to_cur}, timeout=15)
        data = response.json()
        if "rates" not in data or to_cur not in data.get("rates", {}):
            return f"❌ تبدیل {from_cur} به {to_cur} پشتیبانی نمی‌شه (ارزهای غیررسمی مثل تومان ایران رو این سرویس نداره)."
        result = data["rates"][to_cur]
        return f"💱 {amount:,.2f} {from_cur} = {result:,.2f} {to_cur}"
    except Exception as e:
        print(f"Currency error: {e}")
        return f"❌ خطا در تبدیل ارز: {str(e)}"


# ۳س. تبدیل واحد (کاملاً محلی، بدون سرویس خارجی)
UNIT_CONVERSIONS = {
    ("km", "mile"): 0.621371, ("mile", "km"): 1.60934,
    ("kg", "lb"): 2.20462, ("lb", "kg"): 0.453592,
    ("c", "f"): None, ("f", "c"): None,  # نیاز به فرمول جدا
    ("m", "ft"): 3.28084, ("ft", "m"): 0.3048,
    ("cm", "inch"): 0.393701, ("inch", "cm"): 2.54,
    ("l", "gallon"): 0.264172, ("gallon", "l"): 3.78541,
}
UNIT_ALIASES = {
    "کیلومتر": "km", "مایل": "mile", "کیلوگرم": "kg", "کیلو": "kg", "پوند": "lb",
    "سانتیگراد": "c", "فارنهایت": "f", "متر": "m", "فوت": "ft",
    "سانتی‌متر": "cm", "سانتیمتر": "cm", "اینچ": "inch", "لیتر": "l", "گالن": "gallon",
}


def convert_unit(text):
    match = re.search(r"([\d.,]+)\s*([a-zA-Zآ-ی]+)\s*(?:to|به)\s*([a-zA-Zآ-ی]+)", text, re.IGNORECASE)
    if not match:
        return "❌ فرمت درست نیست. مثال: «10 km to mile» یا «10 کیلومتر به مایل»"

    value_str, from_unit, to_unit = match.groups()
    value = float(value_str.replace(",", ""))
    from_unit = UNIT_ALIASES.get(from_unit, from_unit.lower())
    to_unit = UNIT_ALIASES.get(to_unit, to_unit.lower())

    if from_unit == "c" and to_unit == "f":
        result = value * 9 / 5 + 32
        return f"📏 {value}°C = {result:.2f}°F"
    if from_unit == "f" and to_unit == "c":
        result = (value - 32) * 5 / 9
        return f"📏 {value}°F = {result:.2f}°C"

    factor = UNIT_CONVERSIONS.get((from_unit, to_unit))
    if factor is None:
        return f"❌ تبدیل {from_unit} به {to_unit} پشتیبانی نمی‌شه. واحدهای پشتیبانی‌شده: km, mile, kg, lb, c, f, m, ft, cm, inch, l, gallon"

    result = value * factor
    return f"📏 {value} {from_unit} = {result:.4f} {to_unit}"


# ۳ع. ساخت و خواندن کد QR (کاملاً محلی)
def generate_qr(text):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    output = io.BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()


def read_qr(image_bytes):
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    detector = cv2.QRCodeDetector()
    data, points, _ = detector.detectAndDecode(img)
    return data if data else None


# ۳ص. ترجمه‌ی سریع با همون مدل Groq فعلی (بدون سرویس/کلید اضافه)
def translate_text(text):
    payload = {
        "model": "openai/gpt-oss-20b",
        "messages": [
            {"role": "system", "content": (
                "You are a translation engine. Detect the input language. "
                "If it's Persian, translate to natural English. Otherwise, translate to natural Persian. "
                "Reply with ONLY the translation, nothing else — no notes, no quotes, no explanation."
            )},
            {"role": "user", "content": text}
        ],
        "temperature": 0.3,
        "max_tokens": 1024,
        "reasoning_format": "hidden"
    }
    try:
        return call_groq_api(payload, timeout=20)
    except Exception as e:
        return f"❌ خطای ارتباطی: {str(e)}"


# ۳ق. قیمت طلا/ارز/کریپتوی ایران با BrsApi.ir — با کش مشترک (هر ۳ دقیقه یک‌بار برای همه‌ی کاربرا)
def _normalize_coin_query(text):
    # حذف فاصله‌ی معمولی، نیم‌فاصله (ZWNJ)، و کوچک‌کردن حروف، تا مثلاً «بیت کوین»،
    # «بیت‌کوین» (با نیم‌فاصله)، و «بیتکوین» همه یکسان در نظر گرفته بشن
    text = text.strip().lower()
    text = text.replace("\u200c", "").replace(" ", "")
    return text


BRSAPI_URL = "https://Api.BrsApi.ir/Market/Gold_Currency.php"
MARKET_CACHE_REFRESH_SECONDS = 180  # هر ۳ دقیقه
MARKET_CACHE = {"data": None, "last_updated": 0}
MARKET_CACHE_LOCK = threading.Lock()

# چندتا اسم فارسی رایج برای جستجوی راحت‌تر (علاوه بر symbol/name/name_en خودِ API)
MARKET_QUERY_ALIASES = {
    "دلار": "USD", "یورو": "EUR", "طلا": "IR_GOLD_18K", "طلای 18": "IR_GOLD_18K",
    "طلای هجده": "IR_GOLD_18K", "طلای ۱۸": "IR_GOLD_18K", "طلا ۱۸": "IR_GOLD_18K",
    "بیت کوین": "BTC", "بیتکوین": "BTC", "اتریوم": "ETH", "تتر": "USDT",
    "دوج کوین": "DOGE", "بایننس": "BNB",
}
MARKET_QUERY_ALIASES_NORMALIZED = {_normalize_coin_query(k): v for k, v in MARKET_QUERY_ALIASES.items()}

DEFAULT_MARKET_SYMBOLS = ["USD", "EUR", "IR_GOLD_18K"]


def fetch_market_data():
    """درخواست واقعی به BrsApi و به‌روزرسانی کش. این تابع رو فقط ترد پس‌زمینه (هر ۳ دقیقه) یا در صورت خالی بودن کش صدا بزن."""
    if not BRSAPI_KEY:
        return False, "متغیر BRSAPI_KEY در Render تنظیم نشده است."
    try:
        # فایروال BrsApi درخواست‌هایی با User-Agent پیش‌فرض کتابخونه‌های برنامه‌نویسی (مثل python-requests) رو
        # مسدود می‌کنه؛ برای همین یه User-Agent شبیه مرورگر واقعی می‌فرستیم.
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        }
        response = requests.get(BRSAPI_URL, params={"key": BRSAPI_KEY}, headers=headers, timeout=20)
        if response.status_code != 200:
            body_preview = response.text[:300]
            print(f"BrsApi fetch failed — status={response.status_code}, body={body_preview}")
            return False, f"کد {response.status_code} — {body_preview}"
        data = response.json()
        with MARKET_CACHE_LOCK:
            MARKET_CACHE["data"] = data
            MARKET_CACHE["last_updated"] = time.time()
        return True, None
    except Exception as e:
        print(f"BrsApi fetch error: {e}")
        return False, str(e)


def market_cache_updater_loop():
    while True:
        fetch_market_data()
        time.sleep(MARKET_CACHE_REFRESH_SECONDS)


def _get_market_data():
    """کش رو برمی‌گردونه؛ اگه خالی بود، یک‌بار به‌صورت آنی تلاش می‌کنه و خطای واقعی رو هم برمی‌گردونه."""
    with MARKET_CACHE_LOCK:
        data = MARKET_CACHE.get("data")
    if data:
        return data, None

    ok, err = fetch_market_data()
    if ok:
        with MARKET_CACHE_LOCK:
            return MARKET_CACHE.get("data"), None
    return None, err


def find_market_item(query, data):
    normalized = _normalize_coin_query(query)
    symbol_query = MARKET_QUERY_ALIASES_NORMALIZED.get(normalized, query.strip().upper())

    for category in ("gold", "currency", "cryptocurrency"):
        for item in data.get(category, []):
            if _normalize_coin_query(item.get("symbol", "")) == _normalize_coin_query(symbol_query):
                return item
            if normalized in (_normalize_coin_query(item.get("name", "")), _normalize_coin_query(item.get("name_en", ""))):
                return item
    return None


def format_market_item(item):
    name = item.get("name", item.get("symbol", "؟"))
    unit = item.get("unit", "")
    price = item.get("price")
    change = item.get("change_percent")

    try:
        price_num = float(price)
        price_display = f"{price_num:,.0f}" if unit == "تومان" else f"{price_num:,.4f}"
    except (TypeError, ValueError):
        price_display = str(price)

    line = f"💰 {name}\n💵 قیمت: {price_display} {unit}".rstrip()
    if change is not None:
        arrow = "📈" if change >= 0 else "📉"
        line += f"\n{arrow} تغییر: {change}%"
    return line


def get_market_price_text(query):
    if not BRSAPI_KEY:
        return "❌ سرویس قیمت هنوز تنظیم نشده (نیاز به BRSAPI_KEY در Render)."

    data, err = _get_market_data()
    if data is None:
        print(f"Market data fetch failed: {err}")
        return f"❌ خطا در دریافت داده از سرویس قیمت.\nجزئیات: {err}"

    item = find_market_item(query, data)
    if item is None:
        return f"❌ چیزی با نام «{query}» پیدا نشد. اسم دقیق‌تر (مثل دلار، یورو، بیت‌کوین) رو امتحان کن."
    return format_market_item(item)


def get_default_market_bundle_text():
    if not BRSAPI_KEY:
        return "❌ سرویس قیمت هنوز تنظیم نشده (نیاز به BRSAPI_KEY در Render)."

    data, err = _get_market_data()
    if data is None:
        print(f"Market data fetch failed: {err}")
        return f"❌ خطا در دریافت داده از سرویس قیمت.\nجزئیات: {err}"

    lines = []
    for symbol in DEFAULT_MARKET_SYMBOLS:
        item = find_market_item(symbol, data)
        if item:
            lines.append(format_market_item(item))
    if not lines:
        return "❌ داده‌ای برای نمادهای پیش‌فرض پیدا نشد."
    return "\n\n".join(lines)


def clean_text(text):
    if not text:
        return text
    # حذف تگ‌های <think>...</think> باقیمانده (اگر مدل با وجود reasoning_format هم بفرسته)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"</?think>", "", text)
    # حذف نشانه‌های مارک‌داون که تلگرام بدون parse_mode رندرشون نمی‌کنه
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"^[ \t]*[\*\-][ \t]+", "• ", text, flags=re.MULTILINE)
    text = re.sub(r"^#{1,6}[ \t]*", "", text, flags=re.MULTILINE)
    return text.strip()


def split_code_blocks(text):
    """
    متن رو به بخش‌های متن عادی و بخش‌های کد (بین ```) تقسیم می‌کنه.
    خروجی: لیستی از تاپل‌های ("text", content) یا ("code", content, lang)
    """
    pattern = re.compile(r"```(\w+)?\n?(.*?)```", re.DOTALL)
    segments = []
    last_end = 0
    for m in pattern.finditer(text):
        if m.start() > last_end:
            segments.append(("text", text[last_end:m.start()]))
        lang = m.group(1) or ""
        code = m.group(2).strip("\n")
        if code:
            segments.append(("code", code, lang))
        last_end = m.end()
    if last_end < len(text):
        segments.append(("text", text[last_end:]))
    return segments


def send_long_message(message, text, reply_markup=None):
    chat_id = message.chat.id
    segments = split_code_blocks(text)
    has_code = any(seg[0] == "code" for seg in segments)

    if not has_code:
        # مسیر ساده: بدون بلوک کد، مثل قبل متن رو تکه‌تکه می‌کنیم و می‌فرستیم
        content = clean_text(text)
        if not content:
            content = "(پاسخی دریافت نشد)"
        chunks = [content[i:i + TELEGRAM_MAX_LEN] for i in range(0, len(content), TELEGRAM_MAX_LEN)]
        for i, chunk in enumerate(chunks):
            is_last = (i == len(chunks) - 1)
            markup = reply_markup if is_last else None
            if i == 0:
                bot.reply_to(message, chunk, reply_markup=markup)
            else:
                bot.send_message(chat_id, chunk, reply_markup=markup)
        return

    # مسیر با بلوک کد: هر بخش کد رو با فرمت مخصوص تلگرام (قابل کپی، مونواسپیس) می‌فرستیم
    parts = []
    for seg in segments:
        if seg[0] == "text":
            cleaned = clean_text(seg[1])
            if cleaned:
                parts.append(("text", cleaned, None))
        else:
            _, code, lang = seg
            parts.append(("code", code, lang))

    if not parts:
        parts = [("text", "(پاسخی دریافت نشد)", None)]

    first_sent = False
    last_part_index = len(parts) - 1

    for idx, (kind, content, lang) in enumerate(parts):
        is_last_part = (idx == last_part_index)
        if kind == "code":
            max_code_len = TELEGRAM_MAX_LEN - 20
            code_chunks = [content[i:i + max_code_len] for i in range(0, len(content), max_code_len)] or [""]
            for cidx, cchunk in enumerate(code_chunks):
                is_last_chunk = is_last_part and (cidx == len(code_chunks) - 1)
                markup = reply_markup if is_last_chunk else None
                fenced = f"```{lang}\n{cchunk}\n```"
                try:
                    if not first_sent:
                        bot.reply_to(message, fenced, parse_mode="Markdown", reply_markup=markup)
                    else:
                        bot.send_message(chat_id, fenced, parse_mode="Markdown", reply_markup=markup)
                except Exception:
                    # اگه به هر دلیلی پارس مارک‌داون خطا داد، بدون فرمت‌دهی می‌فرستیم تا پیام گم نشه
                    if not first_sent:
                        bot.reply_to(message, cchunk, reply_markup=markup)
                    else:
                        bot.send_message(chat_id, cchunk, reply_markup=markup)
                first_sent = True
        else:
            text_chunks = [content[i:i + TELEGRAM_MAX_LEN] for i in range(0, len(content), TELEGRAM_MAX_LEN)]
            for tidx, tchunk in enumerate(text_chunks):
                is_last_chunk = is_last_part and (tidx == len(text_chunks) - 1)
                markup = reply_markup if is_last_chunk else None
                if not first_sent:
                    bot.reply_to(message, tchunk, reply_markup=markup)
                else:
                    bot.send_message(chat_id, tchunk, reply_markup=markup)
                first_sent = True


# ۵. دستور شروع ربات: نمایش منوی اصلی
@bot.message_handler(commands=['start'])
def handle_start(message):
    chat_id = message.chat.id

    if not check_membership_and_notify(message):
        return

    set_mode(chat_id, None)
    bot.send_message(
        chat_id,
        "👋 به ربات خوش اومدی!\n\n"
        "🟢 شروع گفتگو: گفتگوی آزاد با هوش مصنوعی (متن و عکس)، با حفظ تاریخچه.\n"
        "🖼 ساخت عکس: از روی توضیح متنی، عکس می‌سازم.\n"
        "🎙 ویس به متن: ویس بفرست، متنش رو برات می‌نویسم.\n"
        "🔊 متن به گفتار: متن بفرست، به فایل صوتی تبدیلش می‌کنم.\n"
        "🔎 سرچ در اینترنت: توی وب سرچ می‌کنم و خلاصه‌ی به‌روز با منابع می‌دم.\n"
        "📄 خواندن سند: یک PDF بفرست، می‌خونمش و خلاصه یا جواب سوالت رو می‌دم.\n"
        "🔍 افزایش کیفیت عکس: عکس بفرست، کیفیت و رزولوشنش رو بالا می‌برم.\n"
        "🌤 وضعیت هوا | 💱 تبدیل ارز | 📏 تبدیل واحد\n"
        "🔳 QR کد | 🌐 ترجمه‌ی سریع | 🪙 قیمت کریپتو | 💰 دلار و طلا\n\n"
        "یکی از گزینه‌های زیر رو انتخاب کن 👇",
        reply_markup=main_menu_keyboard()
    )


# ۶. دستور /reset برای پاک کردن حافظه مکالمه (بدون تغییر وضعیت فعلی)
@bot.message_handler(commands=['reset', 'new'])
def handle_reset(message):
    CONVERSATION_HISTORY[message.chat.id] = []
    bot.reply_to(message, "✅ حافظه مکالمه پاک شد.")


# ۷. دکمه «شروع گفتگو» — منوی انتخاب مدل رو با کیبورد پایین صفحه نشون می‌ده
@bot.message_handler(func=lambda message: message.text == BTN_START_CHAT)
def handle_start_chat_button(message):
    if not check_membership_and_notify(message):
        return

    chat_id = message.chat.id
    set_mode(chat_id, "choosing_model")
    bot.send_message(
        chat_id,
        "با کدوم مدل می‌خوای گفتگو کنی؟ 👇",
        reply_markup=model_selection_keyboard()
    )


# ۷ب. انتخاب مدل از همون کیبورد پایین صفحه
@bot.message_handler(func=lambda message: message.text in MODEL_BUTTON_TEXTS)
def handle_select_model(message):
    chat_id = message.chat.id
    if get_mode(chat_id) != "choosing_model":
        return  # این دکمه‌ها فقط وقتی توی حالت انتخاب مدل هستیم معتبرن

    model_id = MODEL_BUTTON_TEXTS[message.text]
    CHAT_MODEL_CHOICE[chat_id] = model_id
    set_mode(chat_id, "chat")
    CONVERSATION_HISTORY[chat_id] = []  # شروع تازه

    model_label = next(o["label"] for o in CHAT_MODEL_OPTIONS if o["id"] == model_id)
    bot.send_message(
        chat_id,
        f"✅ گفتگو با مدل {model_label} شروع شد! هر سوالی داری بپرس یا عکس بفرست.\n"
        "برای پایان دادن، دکمه‌ی «پایان گفتگو» رو بزن.",
        reply_markup=chat_active_keyboard()
    )


# ۸. دکمه «پایان گفتگو»
@bot.message_handler(func=lambda message: message.text == BTN_END_CHAT)
def handle_end_chat_button(message):
    chat_id = message.chat.id
    set_mode(chat_id, None)
    CONVERSATION_HISTORY[chat_id] = []
    bot.send_message(
        chat_id,
        "🔴 گفتگو پایان یافت. از منوی زیر یکی رو انتخاب کن.",
        reply_markup=main_menu_keyboard()
    )


# ۸ب. دکمه «ساخت عکس»
@bot.message_handler(func=lambda message: message.text == BTN_IMAGE)
def handle_image_button(message):
    if not check_membership_and_notify(message):
        return

    chat_id = message.chat.id
    set_mode(chat_id, "image")
    bot.send_message(
        chat_id,
        "🖼 حالت ساخت عکس فعال شد. یا فقط متن بفرست تا از صفر عکس بسازم، "
        "یا یه عکس بفرست همراه با کپشن (توضیح تغییری که می‌خوای) تا بر اساس اون عکس، عکس جدید بسازم.\n"
        "برای خروج از این حالت، دکمه‌ی «پایان ساخت عکس» رو بزن.",
        reply_markup=image_active_keyboard()
    )


# ۸ه. دکمه «پایان ساخت عکس»
@bot.message_handler(func=lambda message: message.text == BTN_END_IMAGE)
def handle_end_image_button(message):
    chat_id = message.chat.id
    set_mode(chat_id, None)
    bot.send_message(
        chat_id,
        "🔴 حالت ساخت عکس پایان یافت. از منوی زیر یکی رو انتخاب کن.",
        reply_markup=main_menu_keyboard()
    )


# ۸و. دکمه «ویس به متن»
@bot.message_handler(func=lambda message: message.text == BTN_STT)
def handle_stt_button(message):
    if not check_membership_and_notify(message):
        return

    chat_id = message.chat.id
    set_mode(chat_id, "stt")
    bot.send_message(
        chat_id,
        "🎙 حالت ویس به متن فعال شد. یک پیام صوتی (ویس) بفرست تا متنش رو برات بنویسم.\n"
        "برای خروج از این حالت، دکمه‌ی «پایان ویس به متن» رو بزن.",
        reply_markup=stt_active_keyboard()
    )


# ۸ز. دکمه «پایان ویس به متن»
@bot.message_handler(func=lambda message: message.text == BTN_END_STT)
def handle_end_stt_button(message):
    chat_id = message.chat.id
    set_mode(chat_id, None)
    bot.send_message(
        chat_id,
        "🔴 حالت ویس به متن پایان یافت. از منوی زیر یکی رو انتخاب کن.",
        reply_markup=main_menu_keyboard()
    )


# ۸ز۲. دکمه «متن به گفتار»
@bot.message_handler(func=lambda message: message.text == BTN_TTS)
def handle_tts_button(message):
    if not check_membership_and_notify(message):
        return

    chat_id = message.chat.id
    set_mode(chat_id, "tts")
    bot.send_message(
        chat_id,
        "🔊 حالت متن به گفتار فعال شد. هر متنی بفرستی، به فایل صوتی تبدیلش می‌کنم.\n"
        "برای خروج از این حالت، دکمه‌ی «پایان متن به گفتار» رو بزن.",
        reply_markup=tts_active_keyboard()
    )


# ۸ز۳. دکمه «پایان متن به گفتار»
@bot.message_handler(func=lambda message: message.text == BTN_END_TTS)
def handle_end_tts_button(message):
    chat_id = message.chat.id
    set_mode(chat_id, None)
    bot.send_message(
        chat_id,
        "🔴 حالت متن به گفتار پایان یافت. از منوی زیر یکی رو انتخاب کن.",
        reply_markup=main_menu_keyboard()
    )


# ۸ح. دکمه «سرچ در اینترنت»
@bot.message_handler(func=lambda message: message.text == BTN_SEARCH)
def handle_search_button(message):
    if not check_membership_and_notify(message):
        return

    chat_id = message.chat.id
    set_mode(chat_id, "search")
    bot.send_message(
        chat_id,
        "🔎 حالت سرچ در اینترنت فعال شد. هر چی می‌خوای درباره‌ش جستجو کنم رو بنویس؛ "
        "توی وب سرچ می‌کنم و خلاصه‌ی به‌روزش رو با منابع می‌فرستم.\n"
        "برای خروج از این حالت، دکمه‌ی «پایان سرچ» رو بزن.",
        reply_markup=search_active_keyboard()
    )


# ۸ط. دکمه «پایان سرچ»
@bot.message_handler(func=lambda message: message.text == BTN_END_SEARCH)
def handle_end_search_button(message):
    chat_id = message.chat.id
    set_mode(chat_id, None)
    bot.send_message(
        chat_id,
        "🔴 حالت سرچ پایان یافت. از منوی زیر یکی رو انتخاب کن.",
        reply_markup=main_menu_keyboard()
    )


# ۸ی. دکمه «خواندن سند»
@bot.message_handler(func=lambda message: message.text == BTN_DOC)
def handle_doc_button(message):
    if not check_membership_and_notify(message):
        return

    chat_id = message.chat.id
    set_mode(chat_id, "doc")
    bot.send_message(
        chat_id,
        "📄 حالت خواندن سند فعال شد. یک فایل PDF بفرست (می‌تونی همراهش توی کپشن سوالت رو هم بنویسی، "
        "وگرنه خودم خلاصه‌ش می‌کنم).\nبرای خروج از این حالت، دکمه‌ی «پایان خواندن سند» رو بزن.",
        reply_markup=doc_active_keyboard()
    )


# ۸ک. دکمه «پایان خواندن سند»
@bot.message_handler(func=lambda message: message.text == BTN_END_DOC)
def handle_end_doc_button(message):
    chat_id = message.chat.id
    set_mode(chat_id, None)
    bot.send_message(
        chat_id,
        "🔴 حالت خواندن سند پایان یافت. از منوی زیر یکی رو انتخاب کن.",
        reply_markup=main_menu_keyboard()
    )


# ۸ک۲. دکمه «افزایش کیفیت عکس» — اول انتخاب روش رو نشون می‌ده
@bot.message_handler(func=lambda message: message.text == BTN_UPSCALE)
def handle_upscale_button(message):
    if not check_membership_and_notify(message):
        return

    chat_id = message.chat.id
    set_mode(chat_id, "choosing_upscale_method")
    bot.send_message(
        chat_id,
        "🔍 با کدوم روش می‌خوای کیفیت عکس رو افزایش بدم؟ 👇",
        reply_markup=upscale_method_selection_keyboard()
    )


# ۸ک۲ب. انتخاب روش افزایش کیفیت از کیبورد پایین صفحه
@bot.message_handler(func=lambda message: message.text in UPSCALE_METHOD_BUTTON_TEXTS)
def handle_select_upscale_method(message):
    chat_id = message.chat.id
    if get_mode(chat_id) != "choosing_upscale_method":
        return  # این دکمه‌ها فقط توی حالت انتخاب روش معتبرن

    method_id = UPSCALE_METHOD_BUTTON_TEXTS[message.text]
    UPSCALE_METHOD_CHOICE[chat_id] = method_id
    set_mode(chat_id, "upscale")

    method_label = next(o["label"] for o in UPSCALE_METHOD_OPTIONS if o["id"] == method_id)
    bot.send_message(
        chat_id,
        f"✅ روش {method_label} انتخاب شد. یک عکس بفرست تا کیفیت و رزولوشنش رو افزایش بدم.\n"
        "برای خروج از این حالت، دکمه‌ی «پایان افزایش کیفیت» رو بزن.",
        reply_markup=upscale_active_keyboard()
    )


# ۸ک۳. دکمه «پایان افزایش کیفیت»
@bot.message_handler(func=lambda message: message.text == BTN_END_UPSCALE)
def handle_end_upscale_button(message):
    chat_id = message.chat.id
    set_mode(chat_id, None)
    bot.send_message(
        chat_id,
        "🔴 حالت افزایش کیفیت پایان یافت. از منوی زیر یکی رو انتخاب کن.",
        reply_markup=main_menu_keyboard()
    )


# ۸ل. دکمه «وضعیت هوا»
@bot.message_handler(func=lambda message: message.text == BTN_WEATHER)
def handle_weather_button(message):
    if not check_membership_and_notify(message):
        return
    chat_id = message.chat.id
    set_mode(chat_id, "weather")
    bot.send_message(chat_id, "🌤 اسم شهر رو بفرست (مثلاً «تهران» یا «Istanbul»).\nبرای خروج، دکمه‌ی «پایان وضعیت هوا» رو بزن.", reply_markup=weather_active_keyboard())


@bot.message_handler(func=lambda message: message.text == BTN_END_WEATHER)
def handle_end_weather_button(message):
    chat_id = message.chat.id
    set_mode(chat_id, None)
    bot.send_message(chat_id, "🔴 حالت وضعیت هوا پایان یافت. از منوی زیر یکی رو انتخاب کن.", reply_markup=main_menu_keyboard())


# ۸م. دکمه «تبدیل ارز»
@bot.message_handler(func=lambda message: message.text == BTN_CURRENCY)
def handle_currency_button(message):
    if not check_membership_and_notify(message):
        return
    chat_id = message.chat.id
    set_mode(chat_id, "currency")
    bot.send_message(chat_id, "💱 مبلغ رو به این فرمت بفرست: «100 USD to EUR» یا «100 دلار به یورو».\nبرای خروج، دکمه‌ی «پایان تبدیل ارز» رو بزن.", reply_markup=currency_active_keyboard())


@bot.message_handler(func=lambda message: message.text == BTN_END_CURRENCY)
def handle_end_currency_button(message):
    chat_id = message.chat.id
    set_mode(chat_id, None)
    bot.send_message(chat_id, "🔴 حالت تبدیل ارز پایان یافت. از منوی زیر یکی رو انتخاب کن.", reply_markup=main_menu_keyboard())


# ۸ن. دکمه «تبدیل واحد»
@bot.message_handler(func=lambda message: message.text == BTN_UNIT)
def handle_unit_button(message):
    if not check_membership_and_notify(message):
        return
    chat_id = message.chat.id
    set_mode(chat_id, "unit")
    bot.send_message(chat_id, "📏 مقدار رو به این فرمت بفرست: «10 km to mile» یا «10 کیلومتر به مایل».\nبرای خروج، دکمه‌ی «پایان تبدیل واحد» رو بزن.", reply_markup=unit_active_keyboard())


@bot.message_handler(func=lambda message: message.text == BTN_END_UNIT)
def handle_end_unit_button(message):
    chat_id = message.chat.id
    set_mode(chat_id, None)
    bot.send_message(chat_id, "🔴 حالت تبدیل واحد پایان یافت. از منوی زیر یکی رو انتخاب کن.", reply_markup=main_menu_keyboard())


# ۸س. دکمه «QR کد»
@bot.message_handler(func=lambda message: message.text == BTN_QR)
def handle_qr_button(message):
    if not check_membership_and_notify(message):
        return
    chat_id = message.chat.id
    set_mode(chat_id, "qr")
    bot.send_message(
        chat_id,
        "🔳 برای ساخت QR، یه متن یا لینک بفرست. برای خوندن QR، یه عکس از کد QR بفرست.\n"
        "برای خروج، دکمه‌ی «پایان QR کد» رو بزن.",
        reply_markup=qr_active_keyboard()
    )


@bot.message_handler(func=lambda message: message.text == BTN_END_QR)
def handle_end_qr_button(message):
    chat_id = message.chat.id
    set_mode(chat_id, None)
    bot.send_message(chat_id, "🔴 حالت QR کد پایان یافت. از منوی زیر یکی رو انتخاب کن.", reply_markup=main_menu_keyboard())


# ۸ف. دکمه «ترجمه‌ی سریع»
@bot.message_handler(func=lambda message: message.text == BTN_TRANSLATE)
def handle_translate_button(message):
    if not check_membership_and_notify(message):
        return
    chat_id = message.chat.id
    set_mode(chat_id, "translate")
    bot.send_message(chat_id, "🌐 یه متن بفرست (فارسی یا انگلیسی)، خودکار ترجمه‌ش می‌کنم.\nبرای خروج، دکمه‌ی «پایان ترجمه» رو بزن.", reply_markup=translate_active_keyboard())


@bot.message_handler(func=lambda message: message.text == BTN_END_TRANSLATE)
def handle_end_translate_button(message):
    chat_id = message.chat.id
    set_mode(chat_id, None)
    bot.send_message(chat_id, "🔴 حالت ترجمه پایان یافت. از منوی زیر یکی رو انتخاب کن.", reply_markup=main_menu_keyboard())


# ۸ص. دکمه «قیمت کریپتو»
@bot.message_handler(func=lambda message: message.text == BTN_CRYPTO)
def handle_crypto_button(message):
    if not check_membership_and_notify(message):
        return
    chat_id = message.chat.id
    set_mode(chat_id, "crypto")
    bot.send_message(chat_id, "🪙 اسم ارز دیجیتال رو بفرست (مثلاً «بیت کوین» یا «bitcoin»).\nبرای خروج، دکمه‌ی «پایان قیمت کریپتو» رو بزن.", reply_markup=crypto_active_keyboard())


@bot.message_handler(func=lambda message: message.text == BTN_END_CRYPTO)
def handle_end_crypto_button(message):
    chat_id = message.chat.id
    set_mode(chat_id, None)
    bot.send_message(chat_id, "🔴 حالت قیمت کریپتو پایان یافت. از منوی زیر یکی رو انتخاب کن.", reply_markup=main_menu_keyboard())


# ۸ص۲. دکمه «دلار و طلا (ایران)» — بلافاصله قیمت‌های پیش‌فرض رو نشون می‌ده
@bot.message_handler(func=lambda message: message.text == BTN_GOLD)
def handle_gold_button(message):
    if not check_membership_and_notify(message):
        return
    chat_id = message.chat.id
    set_mode(chat_id, "gold")
    bot.send_chat_action(chat_id, "typing")

    reply = get_default_market_bundle_text()

    bot.send_message(
        chat_id,
        reply + "\n\nمی‌تونی «دلار»، «یورو»، «طلا»، «بیت‌کوین» و... رو هم جدا بپرسی.\nبرای خروج، دکمه‌ی «پایان دلار و طلا» رو بزن.",
        reply_markup=gold_active_keyboard()
    )


@bot.message_handler(func=lambda message: message.text == BTN_END_GOLD)
def handle_end_gold_button(message):
    chat_id = message.chat.id
    set_mode(chat_id, None)
    bot.send_message(chat_id, "🔴 حالت دلار و طلا پایان یافت. از منوی زیر یکی رو انتخاب کن.", reply_markup=main_menu_keyboard())


# ۸د. دکمه شیشه‌ای «✅ عضو شدم» زیر پیام عضویت اجباری
@bot.callback_query_handler(func=lambda call: call.data == CALLBACK_CHECK_JOIN)
def handle_check_join(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    not_joined = get_not_joined_channels(user_id)

    if not_joined:
        bot.answer_callback_query(call.id, "❌ هنوز عضو همه‌ی کانال‌ها نشدی!", show_alert=True)
        try:
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=force_sub_keyboard(not_joined))
        except Exception:
            pass
    else:
        bot.answer_callback_query(call.id, "✅ عضویت شما تایید شد!")
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except Exception:
            pass
        bot.send_message(
            chat_id,
            "👋 خوش اومدی! از منوی زیر یکی رو انتخاب کن.",
            reply_markup=main_menu_keyboard()
        )


# ۹. دریافت و پاسخ به عکس‌ها (حالت گفتگو: توصیف عکس / حالت ساخت عکس: ساخت عکس جدید بر اساس عکس مرجع)
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id

    if not check_membership_and_notify(message):
        return

    mode = get_mode(chat_id)

    if mode == "image":
        if not message.caption:
            bot.send_message(
                chat_id,
                "❗️ برای ساخت عکس جدید بر اساس این عکس، باید توی کپشن (زیرنویس) عکس توضیح بدی چه تغییری/عکسی می‌خوای. "
                "مثلاً: «این آدم رو تبدیل به یه شوالیه کن».",
                reply_markup=image_active_keyboard()
            )
            return

        try:
            bot.send_chat_action(chat_id, "upload_photo")

            file_id = message.photo[-1].file_id
            file_info = bot.get_file(file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            image_bytes, error_detail = generate_image_from_reference(downloaded_file, message.caption)
            if image_bytes:
                bot.send_photo(chat_id, photo=image_bytes, caption=f"🖼 {message.caption}", reply_markup=image_active_keyboard())
            else:
                bot.send_message(chat_id, f"❌ ساخت عکس با خطا مواجه شد.\nجزئیات: {error_detail}", reply_markup=image_active_keyboard())
        except Exception as e:
            print(f"Error generating image from reference: {e}")
            try:
                bot.send_message(chat_id, f"❌ خطا در ساخت عکس: {str(e)}", reply_markup=image_active_keyboard())
            except Exception:
                pass
        return

    if mode == "upscale":
        try:
            bot.send_chat_action(chat_id, "upload_photo")

            file_id = message.photo[-1].file_id
            file_info = bot.get_file(file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            method = UPSCALE_METHOD_CHOICE.get(chat_id, DEFAULT_UPSCALE_METHOD)
            image_bytes, error_detail = upscale_image(downloaded_file, method=method)
            if image_bytes:
                bot.send_photo(chat_id, photo=image_bytes, caption="🔍 کیفیت افزایش یافت", reply_markup=upscale_active_keyboard())
            else:
                bot.send_message(chat_id, f"❌ افزایش کیفیت با خطا مواجه شد.\nجزئیات: {error_detail}", reply_markup=upscale_active_keyboard())
        except Exception as e:
            print(f"Error upscaling image: {e}")
            try:
                bot.send_message(chat_id, f"❌ خطا در افزایش کیفیت: {str(e)}", reply_markup=upscale_active_keyboard())
            except Exception:
                pass
        return

    if mode == "qr":
        try:
            bot.send_chat_action(chat_id, "typing")

            file_id = message.photo[-1].file_id
            file_info = bot.get_file(file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            qr_text = read_qr(downloaded_file)
            if qr_text:
                bot.send_message(chat_id, f"🔳 محتوای QR:\n{qr_text}", reply_markup=qr_active_keyboard())
            else:
                bot.send_message(chat_id, "❌ هیچ کد QR توی این عکس پیدا نشد.", reply_markup=qr_active_keyboard())
        except Exception as e:
            print(f"Error reading QR: {e}")
            try:
                bot.send_message(chat_id, f"❌ خطا در خواندن QR: {str(e)}", reply_markup=qr_active_keyboard())
            except Exception:
                pass
        return

    if mode != "chat":
        bot.send_message(
            chat_id,
            "برای ارسال عکس، اول باید یکی از حالت‌های مربوط به عکس رو از منو انتخاب کنی 👇",
            reply_markup=main_menu_keyboard()
        )
        return

    try:
        bot.send_chat_action(chat_id, "typing")

        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        user_prompt = message.caption if message.caption else "این تصویر را توصیف کن."

        reply = ask_groq_vision(downloaded_file, user_prompt)
        send_long_message(message, reply)
    except Exception as e:
        print(f"Error handling photo: {e}")
        try:
            bot.reply_to(message, f"❌ خطا در پردازش عکس: {str(e)}")
        except Exception:
            pass


# ۹ب. دریافت و پاسخ به پیام‌های صوتی (فقط در حالت ویس به متن)
@bot.message_handler(content_types=['voice', 'audio'])
def handle_voice(message):
    chat_id = message.chat.id

    if not check_membership_and_notify(message):
        return

    if get_mode(chat_id) != "stt":
        bot.send_message(
            chat_id,
            "برای تبدیل ویس به متن، اول باید وارد حالت «ویس به متن» بشی 👇",
            reply_markup=main_menu_keyboard()
        )
        return

    try:
        bot.send_chat_action(chat_id, "typing")

        voice_or_audio = message.voice or message.audio
        file_id = voice_or_audio.file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        text = transcribe_voice(downloaded_file, filename="voice.ogg")
        bot.reply_to(message, f"📝 {text}", reply_markup=stt_active_keyboard())
    except Exception as e:
        print(f"Error handling voice: {e}")
        try:
            bot.send_message(chat_id, f"❌ خطا در پردازش ویس: {str(e)}", reply_markup=stt_active_keyboard())
        except Exception:
            pass


# ۹ج. دریافت و پردازش سند (PDF) — فقط در حالت «خواندن سند»
@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id

    if not check_membership_and_notify(message):
        return

    if get_mode(chat_id) != "doc":
        bot.send_message(
            chat_id,
            "برای خوندن و خلاصه‌سازی سند، اول باید وارد حالت «خواندن سند» بشی 👇",
            reply_markup=main_menu_keyboard()
        )
        return

    doc = message.document

    # فایل‌های خیلی بزرگ رو Bot API تلگرام اصلاً اجازه‌ی دانلود نمی‌ده (سقف ۲۰ مگابایت)
    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        bot.send_message(chat_id, "❌ حجم فایل بیش از ۲۰ مگابایته و قابل پردازش نیست.", reply_markup=doc_active_keyboard())
        return

    try:
        bot.send_chat_action(chat_id, "typing")

        # به‌جای دانلود فایل روی سرور خودمون، فقط لینک فایل تلگرام رو به Jina Reader می‌دیم
        file_info = bot.get_file(doc.file_id)
        telegram_file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"

        document_text, error = read_pdf_via_jina(telegram_file_url)
        if error:
            bot.send_message(chat_id, error, reply_markup=doc_active_keyboard())
            return

        question = message.caption if message.caption else "این سند رو خلاصه کن و نکات مهمش رو بگو."
        reply = summarize_document_text(document_text, question)
        send_long_message(message, reply, reply_markup=doc_active_keyboard())
    except Exception as e:
        print(f"Error handling document: {e}")
        try:
            bot.send_message(chat_id, f"❌ خطا در پردازش سند: {str(e)}", reply_markup=doc_active_keyboard())
        except Exception:
            pass


# ۱۰. دریافت و پاسخ به پیام‌های متنی — رفتار بسته به حالت فعلی (منو / انتخاب مدل / گفتگو / ساخت عکس)
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    if not message.text:
        return

    chat_id = message.chat.id

    if not check_membership_and_notify(message):
        return

    mode = get_mode(chat_id)

    if mode == "chat":
        try:
            bot.send_chat_action(chat_id, "typing")
            reply = ask_groq(chat_id, message.text)
            send_long_message(message, reply, reply_markup=chat_active_keyboard())
        except Exception as e:
            print(f"Error handling message: {e}")
            try:
                bot.send_message(chat_id, f"❌ یه خطا پیش اومد: {str(e)}\nدوباره امتحان کن.", reply_markup=chat_active_keyboard())
            except Exception:
                pass

    elif mode == "image":
        try:
            bot.send_chat_action(chat_id, "upload_photo")
            image_bytes, error_detail = generate_image(message.text)
            if image_bytes:
                bot.send_photo(chat_id, photo=image_bytes, caption=f"🖼 {message.text}", reply_markup=image_active_keyboard())
            else:
                bot.send_message(chat_id, f"❌ ساخت عکس با خطا مواجه شد.\nجزئیات: {error_detail}", reply_markup=image_active_keyboard())
        except Exception as e:
            print(f"Error generating image: {e}")
            try:
                bot.send_message(chat_id, f"❌ خطا در ساخت عکس: {str(e)}", reply_markup=image_active_keyboard())
            except Exception:
                pass

    elif mode == "tts":
        try:
            bot.send_chat_action(chat_id, "record_voice")
            audio_bytes, error = generate_speech(message.text)
            if error:
                bot.send_message(chat_id, f"❌ خطا در ساخت گفتار: {error}", reply_markup=tts_active_keyboard())
            else:
                bot.send_audio(chat_id, audio=audio_bytes, title="متن به گفتار", reply_markup=tts_active_keyboard())
        except Exception as e:
            print(f"Error generating speech: {e}")
            try:
                bot.send_message(chat_id, f"❌ خطا در ساخت گفتار: {str(e)}", reply_markup=tts_active_keyboard())
            except Exception:
                pass

    elif mode == "search":
        try:
            bot.send_chat_action(chat_id, "typing")
            reply = ask_tavily_search(message.text)
            send_long_message(message, reply, reply_markup=search_active_keyboard())
        except Exception as e:
            print(f"Error handling search: {e}")
            try:
                bot.send_message(chat_id, f"❌ یه خطا پیش اومد: {str(e)}\nدوباره امتحان کن.", reply_markup=search_active_keyboard())
            except Exception:
                pass

    elif mode == "doc":
        bot.send_message(chat_id, "📄 لطفاً یک فایل PDF بفرست، نه متن.", reply_markup=doc_active_keyboard())

    elif mode == "upscale":
        bot.send_message(chat_id, "🔍 لطفاً یک عکس بفرست، نه متن.", reply_markup=upscale_active_keyboard())

    elif mode == "weather":
        try:
            bot.send_chat_action(chat_id, "typing")
            reply = get_weather(message.text.strip())
            bot.send_message(chat_id, reply, reply_markup=weather_active_keyboard())
        except Exception as e:
            bot.send_message(chat_id, f"❌ خطا: {str(e)}", reply_markup=weather_active_keyboard())

    elif mode == "currency":
        try:
            reply = convert_currency(message.text.strip())
            bot.send_message(chat_id, reply, reply_markup=currency_active_keyboard())
        except Exception as e:
            bot.send_message(chat_id, f"❌ خطا: {str(e)}", reply_markup=currency_active_keyboard())

    elif mode == "unit":
        try:
            reply = convert_unit(message.text.strip())
            bot.send_message(chat_id, reply, reply_markup=unit_active_keyboard())
        except Exception as e:
            bot.send_message(chat_id, f"❌ خطا: {str(e)}", reply_markup=unit_active_keyboard())

    elif mode == "qr":
        try:
            bot.send_chat_action(chat_id, "upload_photo")
            qr_bytes = generate_qr(message.text.strip())
            bot.send_photo(chat_id, photo=qr_bytes, caption="🔳 کد QR ساخته شد", reply_markup=qr_active_keyboard())
        except Exception as e:
            bot.send_message(chat_id, f"❌ خطا در ساخت QR: {str(e)}", reply_markup=qr_active_keyboard())

    elif mode == "translate":
        try:
            bot.send_chat_action(chat_id, "typing")
            reply = translate_text(message.text)
            bot.send_message(chat_id, reply, reply_markup=translate_active_keyboard())
        except Exception as e:
            bot.send_message(chat_id, f"❌ خطا: {str(e)}", reply_markup=translate_active_keyboard())

    elif mode == "crypto":
        try:
            bot.send_chat_action(chat_id, "typing")
            reply = get_market_price_text(message.text.strip())
            bot.send_message(chat_id, reply, reply_markup=crypto_active_keyboard())
        except Exception as e:
            bot.send_message(chat_id, f"❌ خطا: {str(e)}", reply_markup=crypto_active_keyboard())

    elif mode == "gold":
        try:
            bot.send_chat_action(chat_id, "typing")
            reply = get_market_price_text(message.text.strip())
            bot.send_message(chat_id, reply, reply_markup=gold_active_keyboard())
        except Exception as e:
            bot.send_message(chat_id, f"❌ خطا: {str(e)}", reply_markup=gold_active_keyboard())

    elif mode == "choosing_model":
        bot.send_message(
            chat_id,
            "لطفاً یکی از دکمه‌های مدل رو از کیبورد پایین انتخاب کن 👇",
            reply_markup=model_selection_keyboard()
        )

    elif mode == "choosing_upscale_method":
        bot.send_message(
            chat_id,
            "لطفاً یکی از روش‌های افزایش کیفیت رو از کیبورد پایین انتخاب کن 👇",
            reply_markup=upscale_method_selection_keyboard()
        )

    else:
        bot.send_message(
            chat_id,
            "لطفاً اول از منوی زیر یکی از گزینه‌ها رو انتخاب کن 👇",
            reply_markup=main_menu_keyboard()
        )


# ۱۱. اجرای ربات تلگرام به صورت ایمن و خودکار
def run_telegram_bot():
    print("شروع سیستم بازیابی خودکار ربات...")
    while True:
        try:
            # پاکسازی وب‌هوک به روش استاندارد و بدون پارامترهای ناسازگار
            try:
                bot.remove_webhook()
            except Exception as e:
                print(f"Webhook removal note: {e}")

            time.sleep(1)
            print("اتصال ربات به تلگرام برقرار شد. در حال گوش دادن به پیام‌ها...")
            bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)
        except Exception as e:
            print(f"خطای موقت در اتصال ({e}). تلاش مجدد تا ۵ ثانیه دیگر...")
            time.sleep(5)


if __name__ == "__main__":
    # ثبت خودکار لیست دستورات ربات (همون منوی کنار جعبه پیام) — نیازی به بات‌فادر نیست
    try:
        bot.set_my_commands([
            types.BotCommand("start", "نمایش منوی اصلی ربات"),
            types.BotCommand("reset", "پاک کردن حافظه مکالمه"),
        ])
    except Exception as e:
        print(f"Command menu setup note: {e}")

    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()

    # ترد پس‌زمینه: هر ۳ دقیقه قیمت طلا/ارز/کریپتو رو یک‌بار برای همه‌ی کاربرا به‌روز می‌کنه
    if BRSAPI_KEY:
        market_thread = threading.Thread(target=market_cache_updater_loop, daemon=True)
        market_thread.start()
    else:
        print("BRSAPI_KEY تنظیم نشده — قابلیت دلار/طلا/کریپتو غیرفعال می‌مونه تا وقتی اضافه بشه.")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
