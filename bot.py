import os
import telebot
import json
import flask
import threading
from steam_guard import SteamGuard

TOKEN = os.environ.get('TELEGRAM_TOKEN')

# Загружаем SDA
try:
    with open('maFile.maFile', 'r') as f:
        ma_file_data = json.load(f)
    sg = SteamGuard.from_mafile(ma_file_data)
    print("✅ SDA загружен успешно!")
except Exception as e:
    print(f"❌ Ошибка загрузки SDA: {e}")
    sg = None

bot = telebot.TeleBot(TOKEN)

# === Команда /code ===
@bot.message_handler(commands=['code'])
def send_code(message):
    if sg:
        code = sg.generate_code()
        bot.reply_to(message, f"`{code}`", parse_mode='Markdown')
    else:
        bot.reply_to(message, "❌ Ошибка: SDA не загружен")

# === Команда !код ===
@bot.message_handler(func=lambda msg: msg.text and msg.text.lower().startswith('!код'))
def auto_code(message):
    if sg:
        code = sg.generate_code()
        bot.reply_to(message, f"`{code}`", parse_mode='Markdown')
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