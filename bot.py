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

# Алфавит Steam Guard (именно его использует SDA)
STEAM_ALPHABET = "23456789BCDFGHJKMNPQRTVWXY"

def generate_steam_code(shared_secret):
    try:
        # Декодируем shared_secret из base64
        secret = base64.b64decode(shared_secret)
        
        # Текущее время в 30-секундных интервалах
        interval = int(time.time()) // 30
        
        # Создаём HMAC-SHA1 подпись
        msg = struct.pack('>Q', interval)
        h = hmac.new(secret, msg, hashlib.sha1).digest()
        
        # Берём последние 4 бита как индекс
        offset = h[-1] & 0xF
        
        # Извлекаем 4 байта начиная с offset
        code_bytes = h[offset:offset+4]
        code_int = struct.unpack('>I', code_bytes)[0]
        code_int &= 0x7FFFFFFF  # Убираем старший бит
        
        # Генерируем 5-значный код с использованием алфавита Steam
        code = ""
        for _ in range(5):
            code += STEAM_ALPHABET[code_int % len(STEAM_ALPHABET)]
            code_int //= len(STEAM_ALPHABET)
        
        return code
    except Exception as e:
        print(f"Ошибка генерации кода: {e}")
        return None

# === Загрузка SDA ===
try:
    with open('maFile.maFile', 'r') as f:
        ma_file_data = json.load(f)
    
    shared_secret = ma_file_data.get('shared_secret')
    if shared_secret:
        print("✅ SDA загружен успешно!")
        # Проверяем, работает ли генерация
        test_code = generate_steam_code(shared_secret)
        if test_code:
            print(f"✅ Тестовый код: {test_code}")
        else:
            print("❌ Ошибка генерации тестового кода")
    else:
        print("❌ Ошибка: shared_secret не найден в файле")
        shared_secret = None
except Exception as e:
    print(f"❌ Ошибка загрузки SDA: {e}")
    shared_secret = None

bot = telebot.TeleBot(TOKEN)

# === Команда /code ===
@bot.message_handler(commands=['code'])
def send_code(message):
    if shared_secret:
        code = generate_steam_code(shared_secret)
        if code:
            bot.reply_to(message, f"`{code}`", parse_mode='Markdown')
        else:
            bot.reply_to(message, "❌ Ошибка генерации кода")
    else:
        bot.reply_to(message, "❌ Ошибка: SDA не загружен")

# === Команда !код ===
@bot.message_handler(func=lambda msg: msg.text and msg.text.lower().startswith('!код'))
def auto_code(message):
    if shared_secret:
        code = generate_steam_code(shared_secret)
        if code:
            bot.reply_to(message, f"`{code}`", parse_mode='Markdown')
        else:
            bot.reply_to(message, "❌ Ошибка генерации кода")
    else:
        bot.reply_to(message, "❌ Ошибка: SDA не загружен")

# === Flask для Render ===
app = flask.Flask(__name__)
@app.route('/')
def health():
    return "Bot is running!"

if __name__ == '__main__':
    print("🚀 Бот запущен!")
    threading.Thread(target=bot.infinity_polling).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))