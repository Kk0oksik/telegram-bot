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
import re
import sqlite3
from datetime import datetime, timedelta
from telebot import types

TOKEN = os.environ.get('TELEGRAM_TOKEN')
PASSWORD = "_Axolotl_"  # пароль для доступа (не показывается)

# === АЛФАВИТ STEAM GUARD ===
STEAM_ALPHABET = "23456789BCDFGHJKMNPQRTVWXY"

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
        code = ""
        for _ in range(5):
            code += STEAM_ALPHABET[code_int % len(STEAM_ALPHABET)]
            code_int //= len(STEAM_ALPHABET)
        return code
    except Exception as e:
        print(f"Ошибка генерации кода: {e}")
        return None

# === БАЗА ДАННЫХ ===
def init_db():
    conn = sqlite3.connect('lots.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, is_verified INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS accounts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE,
                  login TEXT,
                  password TEXT,
                  shared_secret TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS lots
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT,
                  link TEXT,
                  account_id INTEGER,
                  is_rented INTEGER DEFAULT 0,
                  rented_by INTEGER,
                  rent_end TEXT,
                  FOREIGN KEY(account_id) REFERENCES accounts(id))''')
    conn.commit()
    conn.close()

init_db()

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ БД ===
def is_user_verified(user_id):
    conn = sqlite3.connect('lots.db')
    c = conn.cursor()
    c.execute("SELECT is_verified FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row and row[0] == 1

def verify_user(user_id):
    conn = sqlite3.connect('lots.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, is_verified) VALUES (?, 1)", (user_id,))
    conn.commit()
    conn.close()

def add_account(name, login, password, shared_secret):
    conn = sqlite3.connect('lots.db')
    c = conn.cursor()
    c.execute("INSERT INTO accounts (name, login, password, shared_secret) VALUES (?, ?, ?, ?)",
              (name, login, password, shared_secret))
    conn.commit()
    conn.close()

def get_account_by_name(name):
    conn = sqlite3.connect('lots.db')
    c = conn.cursor()
    c.execute("SELECT id, login, password, shared_secret FROM accounts WHERE name=?", (name,))
    row = c.fetchone()
    conn.close()
    return row

def add_lot(name, link, account_name):
    account = get_account_by_name(account_name)
    if not account:
        return None
    account_id = account[0]
    conn = sqlite3.connect('lots.db')
    c = conn.cursor()
    c.execute("INSERT INTO lots (name, link, account_id, is_rented) VALUES (?, ?, ?, 0)",
              (name, link, account_id))
    lot_id = c.lastrowid
    conn.commit()
    conn.close()
    return lot_id

def get_all_lots():
    conn = sqlite3.connect('lots.db')
    c = conn.cursor()
    c.execute('''SELECT lots.id, lots.name, lots.link, lots.is_rented, accounts.name
                 FROM lots JOIN accounts ON lots.account_id = accounts.id''')
    rows = c.fetchall()
    conn.close()
    return rows

def get_lot(lot_id):
    conn = sqlite3.connect('lots.db')
    c = conn.cursor()
    c.execute("SELECT id, name, link, account_id, is_rented, rented_by, rent_end FROM lots WHERE id=?", (lot_id,))
    row = c.fetchone()
    conn.close()
    return row

def get_active_lot_for_user(user_id):
    conn = sqlite3.connect('lots.db')
    c = conn.cursor()
    c.execute('''SELECT lots.id, lots.name, lots.link, accounts.login, accounts.password, accounts.shared_secret
                 FROM lots JOIN accounts ON lots.account_id = accounts.id
                 WHERE lots.is_rented = 1 AND lots.rented_by = ?''', (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def start_rent(lot_id, user_id, rent_end):
    conn = sqlite3.connect('lots.db')
    c = conn.cursor()
    c.execute("SELECT account_id FROM lots WHERE id=?", (lot_id,))
    account_id = c.fetchone()[0]
    # Удаляем все другие лоты с этим же account_id
    c.execute("DELETE FROM lots WHERE account_id=? AND id != ?", (account_id, lot_id))
    # Помечаем текущий лот как арендованный
    c.execute("UPDATE lots SET is_rented=1, rented_by=?, rent_end=? WHERE id=?", (user_id, rent_end, lot_id))
    conn.commit()
    conn.close()

def end_rent(lot_id):
    conn = sqlite3.connect('lots.db')
    c = conn.cursor()
    c.execute("UPDATE lots SET is_rented=0, rented_by=NULL, rent_end=NULL WHERE id=?", (lot_id,))
    conn.commit()
    conn.close()

def delete_lot(lot_id):
    conn = sqlite3.connect('lots.db')
    c = conn.cursor()
    c.execute("DELETE FROM lots WHERE id=?", (lot_id,))
    conn.commit()
    conn.close()

# === ТАЙМЕРЫ ===
rent_timers = {}

def schedule_end_rent(lot_id, chat_id, rent_end):
    def end_rent_task():
        end_rent(lot_id)
        bot.send_message(chat_id, f"⏰ Аренда лота ID {lot_id} завершена! Пароль нужно сменить вручную.")
        if lot_id in rent_timers:
            del rent_timers[lot_id]
    now = datetime.now()
    delta = (rent_end - now).total_seconds()
    if delta > 0:
        timer = threading.Timer(delta, end_rent_task)
        timer.daemon = True
        timer.start()
        rent_timers[lot_id] = timer

# === БОТ ===
bot = telebot.TeleBot(TOKEN)

# === ЗАЩИТА ПАРОЛЕМ ===
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    if is_user_verified(user_id):
        bot.reply_to(message, "✅ Доступ уже открыт. Используйте команды.")
    else:
        # Пароль не показываем
        bot.reply_to(message, "🔐 Введите пароль командой:\n`!пароль <пароль>`", parse_mode='Markdown')

@bot.message_handler(func=lambda msg: msg.text and msg.text.startswith('!пароль'))
def check_password(message):
    user_id = message.from_user.id
    entered = message.text.replace('!пароль', '').strip()
    if entered == PASSWORD:
        verify_user(user_id)
        bot.reply_to(message, "✅ Доступ разрешён! Теперь вы можете использовать бота.")
    else:
        bot.reply_to(message, "❌ Неверный пароль.")

# === КОМАНДЫ ДЛЯ ПРОДАВЦА ===

@bot.message_handler(commands=['addaccount'])
def add_account_cmd(message):
    user_id = message.from_user.id
    if not is_user_verified(user_id):
        bot.reply_to(message, "❌ Доступ запрещён. Введите пароль.")
        return
    try:
        parts = message.text.split('|')
        if len(parts) < 4:
            bot.reply_to(message, "❌ Используй: /addaccount Имя | Логин | Пароль | shared_secret")
            return
        name = parts[0].replace('/addaccount', '').strip()
        login = parts[1].strip()
        password = parts[2].strip()
        shared_secret = parts[3].strip()
        add_account(name, login, password, shared_secret)
        bot.reply_to(message, f"✅ Аккаунт добавлен: {name}")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['addlot'])
def add_lot_cmd(message):
    user_id = message.from_user.id
    if not is_user_verified(user_id):
        bot.reply_to(message, "❌ Доступ запрещён. Введите пароль.")
        return
    try:
        parts = message.text.split('|')
        if len(parts) < 3:
            bot.reply_to(message, "❌ Используй: /addlot Название | Ссылка | Имя_аккаунта")
            return
        name = parts[0].replace('/addlot', '').strip()
        link = parts[1].strip()
        account_name = parts[2].strip()
        lot_id = add_lot(name, link, account_name)
        if lot_id:
            bot.reply_to(message, f"✅ Лот добавлен! ID: {lot_id}\nНазвание: {name}")
        else:
            bot.reply_to(message, f"❌ Аккаунт '{account_name}' не найден. Сначала добавьте аккаунт через /addaccount.")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['lots'])
def show_lots_cmd(message):
    user_id = message.from_user.id
    if not is_user_verified(user_id):
        bot.reply_to(message, "❌ Доступ запрещён. Введите пароль.")
        return
    lots = get_all_lots()
    if not lots:
        bot.reply_to(message, "📭 Активных лотов нет")
        return
    text = "📋 **Лоты:**\n\n"
    for lot in lots:
        status = "✅ свободен" if lot[3] == 0 else "⏳ в аренде"
        text += f"🔹 **{lot[0]}.** {lot[1]}\n   {lot[2]}\n   Аккаунт: {lot[4]}\n   Статус: {status}\n\n"
    bot.reply_to(message, text, parse_mode='Markdown')

@bot.message_handler(commands=['dellot'])
def delete_lot_cmd(message):
    user_id = message.from_user.id
    if not is_user_verified(user_id):
        bot.reply_to(message, "❌ Доступ запрещён. Введите пароль.")
        return
    try:
        lot_id = int(message.text.split()[1])
        delete_lot(lot_id)
        bot.reply_to(message, f"✅ Лот {lot_id} удалён.")
    except:
        bot.reply_to(message, "❌ Используй: /dellot ID")

@bot.message_handler(commands=['rent'])
def rent_lot_cmd(message):
    user_id = message.from_user.id
    if not is_user_verified(user_id):
        bot.reply_to(message, "❌ Доступ запрещён. Введите пароль.")
        return
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ Используй: /rent ID")
            return
        lot_id = int(parts[1])
        lot = get_lot(lot_id)
        if not lot:
            bot.reply_to(message, f"❌ Лот с ID {lot_id} не найден")
            return
        if lot[4] == 1:
            bot.reply_to(message, f"❌ Лот {lot_id} уже в аренде")
            return
        rent_end = datetime.now() + timedelta(hours=1)
        start_rent(lot_id, user_id, rent_end.isoformat())
        bot.reply_to(message, f"✅ Аренда лота {lot_id} начата до {rent_end.strftime('%H:%M')}")
        bot.send_message(message.chat.id, "🔄 Связанные лоты удалены.")
        schedule_end_rent(lot_id, message.chat.id, rent_end)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

# === КОМАНДЫ ДЛЯ ПОКУПАТЕЛЯ ===

@bot.message_handler(func=lambda msg: msg.text and msg.text.lower() == '!login')
def cmd_login(message):
    user_id = message.from_user.id
    if not is_user_verified(user_id):
        bot.reply_to(message, "❌ Доступ запрещён. Введите пароль.")
        return
    active = get_active_lot_for_user(user_id)
    if not active:
        bot.reply_to(message, "❌ У вас нет активной аренды.")
        return
    bot.reply_to(message, f"🔑 Логин: `{active[3]}`", parse_mode='Markdown')

@bot.message_handler(func=lambda msg: msg.text and msg.text.lower() == '!password')
def cmd_password(message):
    user_id = message.from_user.id
    if not is_user_verified(user_id):
        bot.reply_to(message, "❌ Доступ запрещён. Введите пароль.")
        return
    active = get_active_lot_for_user(user_id)
    if not active:
        bot.reply_to(message, "❌ У вас нет активной аренды.")
        return
    bot.reply_to(message, f"🔑 Пароль: `{active[4]}`", parse_mode='Markdown')

@bot.message_handler(func=lambda msg: msg.text and msg.text.lower() == '!code')
def cmd_code(message):
    user_id = message.from_user.id
    if not is_user_verified(user_id):
        bot.reply_to(message, "❌ Доступ запрещён. Введите пароль.")
        return
    active = get_active_lot_for_user(user_id)
    if not active:
        bot.reply_to(message, "❌ У вас нет активной аренды.")
        return
    shared_secret = active[5]
    # Отладка (убрать после проверки)
    bot.reply_to(message, f"DEBUG: shared_secret = {shared_secret[:10] if shared_secret else 'None'}...")
    if not shared_secret:
        bot.reply_to(message, "❌ shared_secret отсутствует для этого аккаунта.")
        return
    code = generate_steam_code(shared_secret)
    if code:
        bot.reply_to(message, f"`{code}`", parse_mode='Markdown')
    else:
        bot.reply_to(message, "❌ Ошибка генерации кода")

# === МЕНЮ С КНОПКАМИ ===
@bot.message_handler(commands=['menu'])
def menu_cmd(message):
    user_id = message.from_user.id
    if not is_user_verified(user_id):
        bot.reply_to(message, "❌ Доступ запрещён. Введите пароль.")
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_add_account = types.InlineKeyboardButton("➕ Добавить аккаунт", callback_data="add_account")
    btn_add_lot = types.InlineKeyboardButton("➕ Добавить лот", callback_data="add_lot")
    btn_lots = types.InlineKeyboardButton("📋 Список лотов", callback_data="list_lots")
    btn_delete_lot = types.InlineKeyboardButton("🗑 Удалить лот", callback_data="delete_lot")
    btn_rent = types.InlineKeyboardButton("⏳ Начать аренду", callback_data="rent_lot")
    btn_login = types.InlineKeyboardButton("🔑 Логин", callback_data="get_login")
    btn_password = types.InlineKeyboardButton("🔒 Пароль", callback_data="get_password")
    btn_code = types.InlineKeyboardButton("🔢 Код", callback_data="get_code")
    markup.add(btn_add_account, btn_add_lot, btn_lots, btn_delete_lot, btn_rent, btn_login, btn_password, btn_code)
    bot.reply_to(message, "📌 **Главное меню**", reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    if not is_user_verified(user_id):
        bot.answer_callback_query(call.id, "❌ Доступ запрещён")
        return
    chat_id = call.message.chat.id
    if call.data == "add_account":
        bot.send_message(chat_id, "Введите /addaccount Имя | Логин | Пароль | shared_secret")
    elif call.data == "add_lot":
        bot.send_message(chat_id, "Введите /addlot Название | Ссылка | Имя_аккаунта")
    elif call.data == "list_lots":
        show_lots_cmd(call.message)  # переиспользуем существующую функцию
    elif call.data == "delete_lot":
        bot.send_message(chat_id, "Введите /dellot ID")
    elif call.data == "rent_lot":
        bot.send_message(chat_id, "Введите /rent ID")
    elif call.data == "get_login":
        cmd_login(call.message)
    elif call.data == "get_password":
        cmd_password(call.message)
    elif call.data == "get_code":
        cmd_code(call.message)
    bot.answer_callback_query(call.id)

# === /HELP ===
@bot.message_handler(commands=['help'])
def help_cmd(message):
    user_id = message.from_user.id
    if not is_user_verified(user_id):
        bot.reply_to(message, "❌ Доступ запрещён. Введите пароль.")
        return
    help_text = """
📖 **Команды для продавца:**
/addaccount Имя | Логин | Пароль | shared_secret — добавить аккаунт
/addlot Название | Ссылка | Имя_аккаунта — добавить лот
/lots — показать все лоты
/dellot ID — удалить лот
/rent ID — начать аренду (на 1 час)
/menu — открыть меню с кнопками

📖 **Команды для покупателя (в чате):**
!login — логин от аккаунта
!password — пароль
!code — код Steam Guard
    """
    bot.reply_to(message, help_text, parse_mode='Markdown')

# === FLASK ===
app = flask.Flask(__name__)
@app.route('/')
def health():
    return "Bot is running!"

if __name__ == '__main__':
    print("🚀 Бот запущен!")
    threading.Thread(target=bot.infinity_polling).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))