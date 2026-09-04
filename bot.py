import os
import telebot
from steamguard import SteamGuard

TOKEN = os.environ.get('TELEGRAM_TOKEN')  # токен берётся из настроек Render
SDA_MAFILE = 'maFile.maFile'  # положи файл .maFile в ту же папку
SDA_PASSWORD = 'твой_пароль'  # впиши свой пароль от SDA

bot = telebot.TeleBot(TOKEN)
sg = SteamGuard.from_mafile(SDA_MAFILE, SDA_PASSWORD)

@bot.message_handler(commands=['code'])
def send_code(message):
    code = sg.generate_code()
    bot.reply_to(message, f"Код: {code}")

# Для Render нужно слушать порт
import flask
app = flask.Flask(__name__)
@app.route('/')
def health():
    return "Bot is running!"

if __name__ == '__main__':
    import threading
    threading.Thread(target=bot.infinity_polling).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))