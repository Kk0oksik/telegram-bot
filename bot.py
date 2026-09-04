import os
import telebot
import json
import flask
import threading
import hmac
import hashlib
import base64
import struct
import time

TOKEN = os.environ.get('TELEGRAM_TOKEN')

# === ТОЧНЫЙ ГЕНЕРАТОР КОДА STEAM GUARD ===
def generate_steam_code(shared_secret):
    try:
        secret = base64.b64decode(shared_secret)
        interval = int(time.time()) // 30
        msg = struct.pack('>Q', interval)
        h = hmac.new(secret, msg, hashlib.sha1).digest()
        offset = h[-1] & 0xF
        code_bytes = h[offset:offset+4]
        code_int = struct.unpack('>I', code_bytes)[0]
        code_int &= 0x7FFFFFFF
        code = str(code_int % 100000)
        return code.zfill(5)
    except Exception as e:
        print(f"Ошибка: {e}")
        return None

# === Загрузка SDA ===
try:
    with open('maFile.maFile', 'r') as f:
        data = json.load(f)
    shared_secret = data.get('shared_secret')
    if shared_secret:
        print("✅ SDA загружен!")
        print(f"🔑 Ключ найден: {shared_secret[:10]}...")
    else:
        print("❌ Ошибка: shared_secret не найден")
        shared_secret = None
except Exception as e:
    print(f"❌ Ошибка: {e}")
    shared_secret = None

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['code'])
def send_code(message):
    if shared_secret:
        code = generate_steam_code(shared_secret)
        if code:
            bot.reply_to(message, f"`{code}`", parse_mode='Markdown')
        else:
            bot.reply_to(message, "❌ Ошибка генерации")
    else:
        bot.reply_to(message, "❌ SDA не загружен")

@bot.message_handler(func=lambda msg: msg.text and msg.text.lower().startswith('!код'))
def auto_code(message):
    if shared_secret:
        code = generate_steam_code(shared_secret)
        if code:
            bot.reply_to(message, f"`{code}`", parse_mode='Markdown')
        else:
            bot.reply_to(message, "❌ Ошибка генерации")
    else:
        bot.reply_to(message, "❌ SDA не загружен")

app = flask.Flask(__name__)
@app.route('/')
def health():
    return "Bot is running!"

if __name__ == '__main__':
    print("🚀 Бот запущен!")
    threading.Thread(target=bot.infinity_polling).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))