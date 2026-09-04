import os
import telebot
from steamguard import maFile
import json
import flask

TOKEN = os.environ.get('TELEGRAM_TOKEN')

# Загружаем SDA
try:
    with open('maFile.maFile', 'r') as f:
        ma_file_data = json.load(f)
    sg = maFile.from_json(ma_file_data)
    print("SDA загружен успешно!")
except Exception as e:
    print(f"Ошибка: {e}")
    sg = None

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['code'])
def send_code(message):
    if sg:
        code = sg.get_code()
        bot.reply_to(message, f"🔑 Код: `{code}`", parse_mode='Markdown')
    else:
        bot.reply_to(message, "❌ Ошибка генерации кода")

# Для Render
app = flask.Flask(__name__)
@app.route('/')
def health():
    return "Bot is running!"

if __name__ == '__main__':
    import threading
    threading.Thread(target=bot.infinity_polling).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))