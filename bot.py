import telebot
from groq import Groq
import time
import logging
import sys
import io
from telebot import types
import os
from flask import Flask, request

# UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv('BOT_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

# القنوات - اتركها فارغة [] لتعطيل الاشتراك الإجباري
CHANNELS = [
    "@namozagk",
]

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)
user_memory = {}
last_message_time = {}

# Flask app
app = Flask(__name__)

def check_subscription(user_id):
    if not CHANNELS:
        return True, None
    for channel in CHANNELS:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False, channel
        except:
            return False, channel
    return True, None

def get_subscribe_keyboard(failed_channel=None):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if CHANNELS:
        buttons = []
        for channel in CHANNELS:
            buttons.append(types.InlineKeyboardButton(
                f"✅ {channel}",
                url=f"https://t.me/{channel.replace('@', '')}"
            ))
        markup.add(*buttons)
    markup.add(types.InlineKeyboardButton("🔍 تحقق من الاشتراك", callback_data="check_sub"))
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    user_memory[user_id] = []

    is_sub, failed_channel = check_subscription(user_id)

    if not is_sub:
        bot.send_message(
            message.chat.id,
            f"🚫 **يجب الاشتراك في القنوات أولاً:**\n\n"
            f"🔗 [{failed_channel or CHANNELS[0]}]"
            f"(https://t.me/{failed_channel.replace('@', '') if failed_channel else CHANNELS[0][1:]})",
            parse_mode='Markdown',
            reply_markup=get_subscribe_keyboard(failed_channel)
        )
    else:
        bot.send_message(
            message.chat.id,
            "🎉 بوت دردشة في خدمتكم 🖐️\n"
            "معكم وائل في خدمتكم بأي سؤال وسأرد فوراً إن شاء الله\n\n"
            "/status - اختبار\n"
            "/models - النماذج\n"
            "/reset - مسح"
        )

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_callback(call):
    user_id = call.from_user.id
    is_sub, failed_channel = check_subscription(user_id)

    if is_sub:
        bot.edit_message_text(
            "✅ تم التحقق من الاشتراك! يمكنك الاستخدام الآن 👇",
            user_id,
            call.message.message_id
        )
        start(call.message)
    else:
        bot.answer_callback_query(
            f"❌ لم تشترك في {failed_channel or CHANNELS[0]} بعد!",
            show_alert=True
        )

@bot.message_handler(commands=['models'])
def models(message):
    if check_subscription(message.chat.id)[0]:
        bot.send_message(
            message.chat.id,
            "✅ النماذج المتاحة الآن:\n"
            "• wael0.1 (الأسرع)\n"
            "• wael0.2\n"
            "• wael0.3"
        )

@bot.message_handler(commands=['status'])
def status(message):
    if check_subscription(message.chat.id)[0]:
        try:
            completion = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": "اختبار"}],
                max_tokens=10
            )
            bot.send_message(message.chat.id, "✅ يعمل البوت تماماً!")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ {str(e)[:70]}")

@bot.message_handler(commands=['reset'])
def reset(message):
    if check_subscription(message.chat.id)[0]:
        user_memory[message.chat.id] = []
        bot.send_message(message.chat.id, "تم مسح الذاكرة.")

@bot.message_handler(func=lambda message: True)
def chat(message):
    user_id = message.chat.id

    is_sub, failed_channel = check_subscription(user_id)
    if not is_sub:
        bot.send_message(
            user_id,
            f"🚫 يجب الاشتراك في القنوات:\n\n"
            f"🔗 [{failed_channel}](https://t.me/{failed_channel.replace('@', '')})",
            parse_mode='Markdown',
            reply_markup=get_subscribe_keyboard(failed_channel)
        )
        return

    now = time.time()
    if user_id in last_message_time and now - last_message_time[user_id] < 3:
        return
    last_message_time[user_id] = now

    if user_id not in user_memory:
        user_memory[user_id] = []

    user_memory[user_id].append({"role": "user", "content": message.text})

    wait_msg = bot.send_message(user_id, "⏳ ...")

    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": "رد بالعربية بشرح مفصل."}] +
                     user_memory[user_id][-5:],
            temperature=0.7,
            max_tokens=800
        )

        reply = completion.choices[0].message.content
        user_memory[user_id].append({"role": "assistant", "content": reply})

        bot.delete_message(user_id, wait_msg.message_id)
        bot.send_message(user_id, reply)

    except Exception as e:
        print(f"خطأ: {e}")
        bot.delete_message(user_id, wait_msg.message_id)
        bot.send_message(user_id, "أنا أفكر ⏳")

# إعداد webhook مع Flask
@app.route('/' + BOT_TOKEN, methods=['POST'])
def receive_update():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200

@app.route('/', methods=['GET'])
def index():
    return 'Bot is running', 200

def set_webhook():
    base_url = os.getenv('RENDER_EXTERNAL_URL') or os.getenv('RENDER_URL')
    if not base_url:
        print("❌ لا يوجد RENDER_EXTERNAL_URL")
        return
    webhook_url = f"{base_url}/{BOT_TOKEN}"
    bot.remove_webhook()
    bot.set_webhook(url=webhook_url)
    print(f"✅ Webhook set to: {webhook_url}")

if __name__ == '__main__':
    set_webhook()
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
