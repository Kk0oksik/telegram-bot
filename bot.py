import os
import telebot
from steamguard import SteamGuardAuthenticator
import json
import flask

TOKEN = os.environ.get('TELEGRAM_TOKEN')

# Загружаем SDA
try:
    with open('mafile.mafile', 'r') as f:
        ma_file = json.load(f)
    sg = SteamGuardAuthenticator.from_mafile(ma_file)
    print("SDA загружен успешно!")
except Exception as e:
    print(f"Ошибка загрузки SDA: {e}")
    sg = None

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['code'])
def send_code(message):
    if sg:
        code = sg.generate_code()
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