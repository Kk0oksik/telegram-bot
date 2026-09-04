import os
import telebot
import json
import flask
import hmac
import time
import struct
import base64

TOKEN = os.environ.get('TELEGRAM_TOKEN')

# Функция для генерации кода Steam Guard
def generate_steam_code(shared_secret):
    try:
        # Декодируем shared_secret из base64
        secret = base64.b64decode(shared_secret)
        
        # Получаем текущее время в 30-секундных интервалах
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
        
        # Получаем 5-значный код
        code = str(code_int % 100000)
        return code.zfill(5)
    except Exception as e:
        print(f"Ошибка генерации кода: {e}")
        return None

# Загружаем SDA
try:
    with open('maFile.maFile', 'r') as f:
        ma_file_data = json.load(f)
    
    # Получаем shared_secret из файла
    shared_secret = ma_file_data.get('shared_secret')
    if shared_secret:
        print("SDA загружен успешно!")
    else:
        print("Ошибка: shared_secret не найден в файле")
        shared_secret = None
except Exception as e:
    print(f"Ошибка загрузки SDA: {e}")
    shared_secret = None

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['code'])
def send_code(message):
    if shared_secret:
        code = generate_steam_code(shared_secret)
        if code:
            bot.reply_to(message, f"🔑 Код: `{code}`", parse_mode='Markdown')
        else:
            bot.reply_to(message, "❌ Ошибка генерации кода")
    else:
        bot.reply_to(message, "❌ Ошибка: shared_secret не найден")

# Для Render
app = flask.Flask(__name__)
@app.route('/')
def health():
    return "Bot is running!"

if __name__ == '__main__':
    import threading
    import hashlib
    threading.Thread(target=bot.infinity_polling).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))