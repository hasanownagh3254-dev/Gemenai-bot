import os
import re
import json
import time
import threading
import base64
import random
import urllib.parse
import requests
import telebot
from telebot import types
from flask import Flask

# ۱. دریافت کلیدها از Environment
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()

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
# دکمه‌های حالت گفتگو / حالت ساخت عکس / حالت ویس به متن
BTN_END_CHAT = "🔴 پایان گفتگو"
BTN_END_IMAGE = "🔴 پایان ساخت عکس"
BTN_END_STT = "🔴 پایان ویس به متن"

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
    buttons = [BTN_START_CHAT, BTN_IMAGE, BTN_STT]  # هر قابلیت جدید رو همینجا اضافه کن
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


# ۴. تابع کمکی برای پاکسازی و تقسیم پیام‌های طولانی (محدودیت تلگرام: ۴۰۹۶ کاراکتر)
TELEGRAM_MAX_LEN = 4000  # کمی کمتر از ۴۰۹۶ برای اطمینان


# ۳د. ساخت عکس از روی توضیح متنی با سرویس رایگان Pollinations.ai (بدون نیاز به API Key)
# نکته: این سرویس جدا از Groq است، چون Groq مدل ساخت عکس (Text-to-Image) ندارد.
def generate_image(prompt):
    encoded_prompt = urllib.parse.quote(prompt)
    seed = random.randint(1, 1_000_000)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&seed={seed}&nologo=true"
    response = requests.get(url, timeout=60)
    if response.status_code == 200 and response.headers.get("content-type", "").startswith("image"):
        return response.content
    return None


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
        "🎙 ویس به متن: ویس بفرست، متنش رو برات می‌نویسم.\n\n"
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
        "🖼 حالت ساخت عکس فعال شد. توضیح بده چه عکسی می‌خوای بسازم (هرچی دقیق‌تر باشه، نتیجه بهتره).\n"
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


# ۹. دریافت و پاسخ به عکس‌ها (فقط در حالت گفتگو)
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    chat_id = message.chat.id

    if not check_membership_and_notify(message):
        return

    if get_mode(chat_id) != "chat":
        bot.send_message(
            chat_id,
            "برای ارسال عکس، اول باید وارد حالت «شروع گفتگو» بشی 👇",
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
            image_bytes = generate_image(message.text)
            if image_bytes:
                bot.send_photo(chat_id, photo=image_bytes, caption=f"🖼 {message.text}", reply_markup=image_active_keyboard())
            else:
                bot.send_message(chat_id, "❌ متاسفانه ساخت عکس با خطا مواجه شد. دوباره امتحان کن.", reply_markup=image_active_keyboard())
        except Exception as e:
            print(f"Error generating image: {e}")
            try:
                bot.send_message(chat_id, f"❌ خطا در ساخت عکس: {str(e)}", reply_markup=image_active_keyboard())
            except Exception:
                pass

    elif mode == "choosing_model":
        bot.send_message(
            chat_id,
            "لطفاً یکی از دکمه‌های مدل رو از کیبورد پایین انتخاب کن 👇",
            reply_markup=model_selection_keyboard()
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

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
