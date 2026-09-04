import os, telebot, json, flask, threading, hmac, hashlib, base64, struct, time, sqlite3
from datetime import datetime, timedelta
from telebot import types

TOKEN = os.environ.get('TELEGRAM_TOKEN')
PASSWORD = "_Axolotl_"

# ... (все функции базы данных и генератор кода остаются без изменений) ...

# ===== ИЗМЕНЕНИЯ =====
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    if is_user_verified(user_id):
        bot.reply_to(message, "✅ Доступ уже открыт.")
    else:
        bot.reply_to(message, "🔐 Введите пароль: `!пароль _Axolotl_`", parse_mode='Markdown')

@bot.message_handler(func=lambda msg: msg.text and msg.text.startswith('!пароль'))
def check_password(message):
    user_id = message.from_user.id
    # Удаляем команду и пробелы
    entered = message.text.replace('!пароль', '').strip()
    if entered == PASSWORD:
        verify_user(user_id)
        bot.reply_to(message, f"✅ Доступ разрешён! (ID: {user_id})")
        # Проверяем, что запись появилась
        if is_user_verified(user_id):
            bot.send_message(message.chat.id, "✅ Подтверждено: вы в базе.")
        else:
            bot.send_message(message.chat.id, "⚠️ Не удалось сохранить в базу. Попробуйте перезапустить бота.")
    else:
        bot.reply_to(message, "❌ Неверный пароль.")

# ===== В callback_handler добавим диагностику =====
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    # Диагностика
    bot.send_message(call.message.chat.id, f"DEBUG: user_id={user_id}, verified={is_user_verified(user_id)}")
    if not is_user_verified(user_id):
        bot.answer_callback_query(call.id, "❌ Доступ запрещён. Введите пароль заново.")
        return
    # ... остальной код обработки кнопок ...