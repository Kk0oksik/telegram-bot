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
import sqlite3
import requests
from datetime import datetime, timedelta
from telebot import types

# ===== НАСТРОЙКИ =====
TOKEN = os.environ.get('TELEGRAM_TOKEN')
PASSWORD = "_Axolotl_"

# Ваш Telegram ID (бот сразу вас узнаёт)
MY_USER_ID = 6724886955
verified_users = {MY_USER_ID}

# ===== КУКИ PLAYEROK =====
PLAYEROK_COOKIES = {
    "__ddg1_": "UBzmNVPp3kE4YFKjtLKY",
    "__ddg10_": "1788558251",
    "__ddg8_": "nIpHwCDBajO0YwPD",
    "__ddg9_": "178.40.243.98",
    "_tt_enable_cookie": "1",
    "_ttp": "01M1Q5X644PB9G8YC2DJDFHFNG_.tt.1.1788558088324",
    "_ym_d": "1788558088",
    "_ym_isad": "2",
    "_ym_uid": "1786713386408136126",
    "_ym_visorc": "b",
    "auid": "1f1a8a96-6a47-67b0-daae-9edf244a05b0",
    "tmr_lvid": "f12b94e65a96fdc52ab8a1d7813c24f0",
    "tmr_lvidTS": "1786713386743",
    "ttcsid": "1788558088326::XVleuxVtDoxsBLYhp3jg.1.1788558092127.0::1.-1070.0::0.0.0.0::0.0.0",
    "ttcsid_D3OFSBRC77UED4260FFG": "1788558088325::m7kuZBhj-UZzktqrfz9m.1.1788558092127.1",
    "fakeauid": "2b2639c0e32ed2dbdab30e2313ab8569",
    "need_page_reload": "false",
    "tmr_detect": "0%7C1788558090367"
}

# ===== АЛФАВИТ STEAM GUARD =====
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

# ===== БАЗА ДАННЫХ =====
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

# ===== ФУНКЦИИ БД =====
def add_account(name, login, password, shared_secret):
    conn = sqlite3.connect('lots.db')
    c = conn.cursor()
    c.execute("INSERT INTO accounts (name, login, password, shared_secret) VALUES (?, ?, ?, ?)",
              (name, login, password, shared_secret))
    conn.commit()
    conn.close()

def get_all_accounts():
    conn = sqlite3.connect('lots.db')
    c = conn.cursor()
    c.execute("SELECT id, name, login FROM accounts")
    rows = c.fetchall()
    conn.close()
    return rows

def get_account_by_name(name):
    conn = sqlite3.connect('lots.db')
    c = conn.cursor()
    c.execute("SELECT id, login, password, shared_secret FROM accounts WHERE name=?", (name,))
    row = c.fetchone()
    conn.close()
    return row

def get_account_by_login(login):
    conn = sqlite3.connect('lots.db')
    c = conn.cursor()
    c.execute("SELECT id, name, login, password, shared_secret FROM accounts WHERE login=?", (login,))
    row = c.fetchone()
    conn.close()
    if row:
        return {'id': row[0], 'name': row[1], 'login': row[2], 'password': row[3], 'shared_secret': row[4]}
    return None

def delete_account(account_id):
    conn = sqlite3.connect('lots.db')
    c = conn.cursor()
    c.execute("DELETE FROM lots WHERE account_id=?", (account_id,))
    c.execute("DELETE FROM accounts WHERE id=?", (account_id,))
    conn.commit()
    conn.close()

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
    c.execute("DELETE FROM lots WHERE account_id=? AND id != ?", (account_id, lot_id))
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

# ===== PLAYEROK (чистый requests) =====
playerok_session = requests.Session()
playerok_session.cookies.update(PLAYEROK_COOKIES)
playerok_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Content-Type': 'application/json',
    'Accept': 'application/json',
})

# === Функции для работы с Playerok (заглушки) ===
def get_playerok_chats():
    try:
        resp = playerok_session.get('https://playerok.com')
        if resp.status_code == 200:
            return [{'id': 1, 'buyer': 'Тестовый покупатель', 'last_message': 'Куки работают'}]
        return []
    except Exception as e:
        print(f"Ошибка получения чатов: {e}")
        return []

def get_playerok_messages(chat_id):
    return [{'from': 'buyer', 'text': 'Пример сообщения'}]

def send_playerok_message(chat_id, text):
    return f"Сообщение '{text}' отправлено (заглушка)"

# ===== БОТ =====
bot = telebot.TeleBot(TOKEN)

user_data = {}
rent_timers = {}

def schedule_end_rent(lot_id, chat_id, rent_end):
    def end_rent_task():
        end_rent(lot_id)
        bot.send_message(chat_id, f"⏰ Аренда лота {lot_id} завершена!")
        if lot_id in rent_timers:
            del rent_timers[lot_id]
    now = datetime.now()
    delta = (rent_end - now).total_seconds()
    if delta > 0:
        timer = threading.Timer(delta, end_rent_task)
        timer.daemon = True
        timer.start()
        rent_timers[lot_id] = timer

# ===== ЗАЩИТА ПАРОЛЕМ =====
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    if user_id in verified_users:
        bot.reply_to(message, "✅ Доступ уже открыт. Используйте /menu.")
    else:
        bot.reply_to(message, "🔐 Введите пароль: `!пароль _Axolotl_`", parse_mode='Markdown')

@bot.message_handler(func=lambda msg: msg.text and msg.text.startswith('!пароль'))
def check_password(message):
    user_id = message.from_user.id
    entered = message.text.replace('!пароль', '').strip()
    if entered == PASSWORD:
        verified_users.add(user_id)
        bot.reply_to(message, "✅ Доступ разрешён! Используйте /menu.")
    else:
        bot.reply_to(message, "❌ Неверный пароль.")

# ===== ДОБАВЛЕНИЕ АККАУНТА =====
@bot.message_handler(commands=['addaccount'])
def add_account_start(message):
    user_id = message.from_user.id
    if user_id not in verified_users:
        bot.reply_to(message, "❌ Доступ запрещён.")
        return
    user_data[user_id] = {'action': 'add_account', 'step': 'name'}
    bot.reply_to(message, "Введите **имя** аккаунта:", parse_mode='Markdown')

@bot.message_handler(func=lambda msg: msg.from_user.id in user_data and user_data[msg.from_user.id]['action'] == 'add_account')
def add_account_steps(message):
    user_id = message.from_user.id
    step = user_data[user_id].get('step')
    if step == 'name':
        user_data[user_id]['name'] = message.text.strip()
        user_data[user_id]['step'] = 'login'
        bot.reply_to(message, "Введите **логин**:")
    elif step == 'login':
        user_data[user_id]['login'] = message.text.strip()
        user_data[user_id]['step'] = 'password'
        bot.reply_to(message, "Введите **пароль**:")
    elif step == 'password':
        user_data[user_id]['password'] = message.text.strip()
        user_data[user_id]['step'] = 'shared_secret'
        bot.reply_to(message, "Введите **shared_secret**:")
    elif step == 'shared_secret':
        shared_secret = message.text.strip()
        try:
            add_account(user_data[user_id]['name'], user_data[user_id]['login'], user_data[user_id]['password'], shared_secret)
            bot.reply_to(message, f"✅ Аккаунт **{user_data[user_id]['name']}** добавлен!")
        except Exception as e:
            bot.reply_to(message, f"❌ Ошибка: {e}")
        del user_data[user_id]

# ===== ДОБАВЛЕНИЕ ЛОТА =====
@bot.message_handler(commands=['addlot'])
def add_lot_start(message):
    user_id = message.from_user.id
    if user_id not in verified_users:
        bot.reply_to(message, "❌ Доступ запрещён.")
        return
    user_data[user_id] = {'action': 'add_lot', 'step': 'name'}
    bot.reply_to(message, "Введите **название** лота:", parse_mode='Markdown')

@bot.message_handler(func=lambda msg: msg.from_user.id in user_data and user_data[msg.from_user.id]['action'] == 'add_lot')
def add_lot_steps(message):
    user_id = message.from_user.id
    step = user_data[user_id].get('step')
    if step == 'name':
        user_data[user_id]['name'] = message.text.strip()
        user_data[user_id]['step'] = 'link'
        bot.reply_to(message, "Введите **ссылку** на лот:")
    elif step == 'link':
        user_data[user_id]['link'] = message.text.strip()
        user_data[user_id]['step'] = 'account'
        bot.reply_to(message, "Введите **имя аккаунта**:")
    elif step == 'account':
        account_name = message.text.strip()
        lot_id = add_lot(user_data[user_id]['name'], user_data[user_id]['link'], account_name)
        if lot_id:
            bot.reply_to(message, f"✅ Лот **{user_data[user_id]['name']}** добавлен! ID: {lot_id}")
        else:
            bot.reply_to(message, f"❌ Аккаунт '{account_name}' не найден.")
        del user_data[user_id]

# ===== ПРОСМОТР АККАУНТОВ =====
@bot.message_handler(commands=['accounts'])
def show_accounts(message):
    user_id = message.from_user.id
    if user_id not in verified_users:
        bot.reply_to(message, "❌ Доступ запрещён.")
        return
    accounts = get_all_accounts()
    if not accounts:
        bot.reply_to(message, "📭 Аккаунтов нет.")
        return
    text = "📋 **Аккаунты:**\n\n"
    for acc in accounts:
        text += f"🔹 **{acc[0]}.** {acc[1]} (логин: {acc[2]})\n"
    bot.reply_to(message, text, parse_mode='Markdown')

# ===== УДАЛЕНИЕ АККАУНТА =====
@bot.message_handler(commands=['delaccount'])
def delete_account_cmd(message):
    user_id = message.from_user.id
    if user_id not in verified_users:
        bot.reply_to(message, "❌ Доступ запрещён.")
        return
    try:
        account_id = int(message.text.split()[1])
        delete_account(account_id)
        bot.reply_to(message, f"✅ Аккаунт {account_id} удалён.")
    except:
        bot.reply_to(message, "❌ Используй: /delaccount ID")

# ===== ЛОТЫ =====
@bot.message_handler(commands=['lots'])
def show_lots_cmd(message):
    user_id = message.from_user.id
    if user_id not in verified_users:
        bot.reply_to(message, "❌ Доступ запрещён.")
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
    if user_id not in verified_users:
        bot.reply_to(message, "❌ Доступ запрещён.")
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
    if user_id not in verified_users:
        bot.reply_to(message, "❌ Доступ запрещён.")
        return
    try:
        lot_id = int(message.text.split()[1])
        lot = get_lot(lot_id)
        if not lot:
            bot.reply_to(message, f"❌ Лот {lot_id} не найден")
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

# ===== КОМАНДЫ ПОКУПАТЕЛЯ =====
@bot.message_handler(func=lambda msg: msg.text and msg.text.lower() == '!login')
def cmd_login(message):
    user_id = message.from_user.id
    if user_id not in verified_users:
        bot.reply_to(message, "❌ Доступ запрещён.")
        return
    active = get_active_lot_for_user(user_id)
    if not active:
        bot.reply_to(message, "❌ У вас нет активной аренды.")
        return
    bot.reply_to(message, f"🔑 Логин: `{active[3]}`", parse_mode='Markdown')

@bot.message_handler(func=lambda msg: msg.text and msg.text.lower() == '!password')
def cmd_password(message):
    user_id = message.from_user.id
    if user_id not in verified_users:
        bot.reply_to(message, "❌ Доступ запрещён.")
        return
    active = get_active_lot_for_user(user_id)
    if not active:
        bot.reply_to(message, "❌ У вас нет активной аренды.")
        return
    bot.reply_to(message, f"🔑 Пароль: `{active[4]}`", parse_mode='Markdown')

@bot.message_handler(func=lambda msg: msg.text and msg.text.lower() == '!code')
def cmd_code(message):
    user_id = message.from_user.id
    if user_id not in verified_users:
        bot.reply_to(message, "❌ Доступ запрещён.")
        return
    active = get_active_lot_for_user(user_id)
    if not active:
        bot.reply_to(message, "❌ У вас нет активной аренды.")
        return
    shared_secret = active[5]
    if not shared_secret:
        bot.reply_to(message, "❌ shared_secret отсутствует.")
        return
    code = generate_steam_code(shared_secret)
    if code:
        bot.reply_to(message, f"`{code}`", parse_mode='Markdown')
    else:
        bot.reply_to(message, "❌ Ошибка генерации кода")

# ===== ТЕСТОВАЯ КОМАНДА /test =====
@bot.message_handler(commands=['test'])
def test_playerok(message):
    user_id = message.from_user.id
    if user_id not in verified_users:
        bot.reply_to(message, "❌ Доступ запрещён.")
        return

    url = "https://playerok.com/graphql"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Cookie': '; '.join([f"{k}={v}" for k, v in PLAYEROK_COOKIES.items()])
    }
    # Стандартный запрос на получение чатов (подберите правильный)
    payload = {
        "operationName": "getChats",
        "query": """
        query getChats {
            chats {
                id
                user {
                    username
                }
                last_message {
                    text
                }
            }
        }
        """
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        bot.reply_to(message, f"📡 Статус: {resp.status_code}\nОтвет:\n{resp.text[:1500]}")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

# ===== ЧАТЫ PLAYEROK =====
@bot.message_handler(commands=['chats'])
def list_chats(message):
    user_id = message.from_user.id
    if user_id not in verified_users:
        bot.reply_to(message, "❌ Доступ запрещён.")
        return
    chats = get_playerok_chats()
    if not chats:
        bot.reply_to(message, "📭 Чатов нет или ошибка подключения.")
        return
    text = "💬 **Список чатов:**\n\n"
    for chat in chats:
        text += f"🔹 **{chat['id']}.** {chat['buyer']}\n   {chat['last_message']}\n"
    bot.reply_to(message, text + "\nИспользуй `/chat ID` для просмотра.", parse_mode='Markdown')

@bot.message_handler(commands=['chat'])
def open_chat(message):
    user_id = message.from_user.id
    if user_id not in verified_users:
        bot.reply_to(message, "❌ Доступ запрещён.")
        return
    try:
        chat_id = int(message.text.split()[1])
        msgs = get_playerok_messages(chat_id)
        text = f"💬 **Чат {chat_id}:**\n\n"
        for msg in msgs:
            sender = "Покупатель" if msg['from'] == 'buyer' else "Вы"
            text += f"**{sender}:** {msg['text']}\n"
        bot.reply_to(message, text, parse_mode='Markdown')
        bot.reply_to(message, f"Ответить: `/reply {chat_id} Текст`")
    except:
        bot.reply_to(message, "❌ Используй: /chat ID")

@bot.message_handler(commands=['reply'])
def reply_to_chat(message):
    user_id = message.from_user.id
    if user_id not in verified_users:
        bot.reply_to(message, "❌ Доступ запрещён.")
        return
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            bot.reply_to(message, "❌ Используй: /reply ID Текст")
            return
        chat_id = int(parts[1])
        text = parts[2]
        result = send_playerok_message(chat_id, text)
        bot.reply_to(message, f"✅ {result}")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

# ===== МЕНЮ =====
@bot.message_handler(commands=['menu'])
def menu_cmd(message):
    user_id = message.from_user.id
    if user_id not in verified_users:
        bot.reply_to(message, "❌ Доступ запрещён.")
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    btns = [
        ("➕ Добавить аккаунт", "add_account"),
        ("➕ Добавить лот", "add_lot"),
        ("📋 Аккаунты", "list_accounts"),
        ("🗑 Удалить аккаунт", "delete_account"),
        ("📋 Список лотов", "list_lots"),
        ("🗑 Удалить лот", "delete_lot"),
        ("⏳ Начать аренду", "rent_lot"),
        ("🔑 Логин", "get_login"),
        ("🔒 Пароль", "get_password"),
        ("🔢 Код", "get_code"),
        ("💬 Чаты", "list_chats"),
        ("🔍 Тест Playerok", "test_playerok"),
    ]
    for text, callback in btns:
        markup.add(types.InlineKeyboardButton(text, callback_data=callback))
    bot.reply_to(message, "📌 **Главное меню**", reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    if user_id not in verified_users:
        bot.answer_callback_query(call.id, "❌ Доступ запрещён.")
        return
    chat_id = call.message.chat.id
    cmds = {
        "add_account": "/addaccount",
        "add_lot": "/addlot",
        "list_accounts": "/accounts",
        "delete_account": "Введите /delaccount ID",
        "list_lots": "/lots",
        "delete_lot": "Введите /dellot ID",
        "rent_lot": "Введите /rent ID",
        "get_login": None,
        "get_password": None,
        "get_code": None,
        "list_chats": "/chats",
        "test_playerok": "/test",
    }
    if call.data in cmds:
        if cmds[call.data]:
            bot.send_message(chat_id, f"Введите {cmds[call.data]}")
        else:
            if call.data == "get_login":
                cmd_login(call.message)
            elif call.data == "get_password":
                cmd_password(call.message)
            elif call.data == "get_code":
                cmd_code(call.message)
    bot.answer_callback_query(call.id)

# ===== /HELP =====
@bot.message_handler(commands=['help'])
def help_cmd(message):
    user_id = message.from_user.id
    if user_id not in verified_users:
        bot.reply_to(message, "❌ Доступ запрещён.")
        return
    help_text = """
📖 **Команды продавца:**
/addaccount – добавить аккаунт (по шагам)
/addlot – добавить лот (по шагам)
/accounts – список аккаунтов
/delaccount ID – удалить аккаунт
/lots – список лотов
/dellot ID – удалить лот
/rent ID – начать аренду на 1 час
/chats – чаты Playerok
/chat ID – открыть чат
/reply ID Текст – ответить
/test – проверить Playerok API
/menu – меню с кнопками

📖 **Команды покупателя:**
!login – логин
!password – пароль
!code – код Steam Guard
    """
    bot.reply_to(message, help_text, parse_mode='Markdown')

# ===== ФОНОВЫЙ МОНИТОРИНГ ЧАТОВ =====
def monitor_playerok_chats():
    while True:
        try:
            chats = get_playerok_chats()
            for chat in chats:
                chat_id = chat['id']
                # Здесь позже добавим реальную проверку новых сообщений
                pass
        except Exception as e:
            print(f"Ошибка мониторинга: {e}")
        time.sleep(10)

monitor_thread = threading.Thread(target=monitor_playerok_chats, daemon=True)
monitor_thread.start()

# ===== FLASK =====
app = flask.Flask(__name__)
@app.route('/')
def health():
    return "Bot is running!"

if __name__ == '__main__':
    print("🚀 Бот запущен!")
    threading.Thread(target=bot.infinity_polling).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))