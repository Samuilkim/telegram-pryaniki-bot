import re
import os
from datetime import datetime
import gspread
import logging
from oauth2client.service_account import ServiceAccountCredentials
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
from rapidfuzz import fuzz

# ------------- Настройки Google Sheets ------------------
def connect_to_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        "pryaniki-analitika-c144b76a284d.json", scope
    )
    client = gspread.authorize(creds)
    sheet = client.open("пряники аналитика").sheet1
    return sheet


def write_zayavka_to_sheet(date, magazin, use_special_price, summary, total):
    try:
        sheet = connect_to_sheet()

        # 👇 Суммируем весовые с помощью функции-агрегатора
        total_vesovye = aggregate_vesovye(summary)

        row = [
            date,
            magazin,
            "Да" if use_special_price else "Нет",
            summary.get("0.3", 0),
            summary.get("0.4", 0),
            summary.get("0.45", 0),
            summary.get("Белые", 0),
            summary.get("Черные", 0),
            summary.get("Розовые", 0),
            total_vesovye,  # 👈 Используем агрегированное значение
            summary.get("Белые весовые", 0),
            total,
        ]
        sheet.append_row(row)
        print("✅ Заявка успешно записана в Google Таблицу")
    except Exception as e:
        print("❌ Ошибка при записи в Google Таблицу:", e)

def write_skip_to_sheet(date, magazin, reason, return_summary):
    try:
        sheet = connect_to_sheet()

        total_vesovye = aggregate_vesovye(return_summary)

        row = [
            date,
            magazin,
            "Нет",
            return_summary.get("0.3", 0),
            return_summary.get("0.4", 0),
            return_summary.get("0.45", 0),
            return_summary.get("Белые", 0),
            return_summary.get("Черные", 0),
            return_summary.get("Розовые", 0),
            total_vesovye,
            return_summary.get("Белые весовые", 0),
            "",  # сумма
        ]
        sheet.append_row(row)
        print("✅ Пропуск записан в Google Таблицу")
    except Exception as e:
        print("❌ Ошибка при записи пропуска:", e)



# ------------- Логирование ------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

# ------------- Состояния диалога ------------------
CHOICE, MAGAZIN, RETURN, ORDER, RESTART, COMMENT, COMMENT_RETURN = range(7)

# ------------- Токен и чат ------------------
TOKEN = os.getenv("TELEGRAM_TOKEN")
TARGET_CHAT_ID = -1002805411399  # сюда приходят заявки

# ------------- Данные по пряникам ------------------
pryaniki_items = [
    {"name": "Белые пакеты", "category": "Белые", "aliases": ["белые пакеты", "бп", "белых", "белые", "бел"]},
    {"name": "Черные пакеты", "category": "Черные", "aliases": ["черные пакеты", "чп", "черн", "черные", "черных", "черные пак"]},
    {"name": "Розовые пакеты", "category": "Розовые", "aliases": ["розовые", "роз пак", "роз", "розовых", "розавые", "розовые пакеты"]},
    {"name": "Клубничные", "category": "0.3", "aliases": ["клубничные", "клубн", "клуб", "клубника"]},
    {"name": "Сливочные", "category": "0.3", "aliases": ["сливочные", "слив", "сливоч"]},
    {"name": "Лимонные", "category": "0.3", "aliases": ["лимонные", "лимон", "лим"]},
    {"name": "Апельсиновые", "category": "0.3", "aliases": ["апельсиновые", "апельс", "апельсин"]},
    {"name": "Фруктовые", "category": "0.3", "aliases": ["фруктовые", "фрукт", "фрук"]},
    {"name": "Итальянская карамель", "category": "0.3", "aliases": ["ит карамель", "карамель", "карам", "ит карам"]},
    {"name": "Топленка", "category": "0.3", "aliases": ["топленка", "топл", "топлен", "топленное молоко"]},
    {"name": "Ромашка", "category": "0.4", "aliases": ["ромашка", "ромаш", "ром"]},
    {"name": "Медовые", "category": "0.4", "aliases": ["медовые", "медов"]},
    {"name": "Маковые", "category": "0.4", "aliases": ["маковые", "мак", "маков"]},
    {"name": "Ванильные", "category": "0.4", "aliases": ["ванильные", "ваниль", "ван", "ванил"]},
    {"name": "Love Kz", "category": "0.4", "aliases": ["love kz", "love", "лов", "лав", "лов кз", "лав кз"]},
    {"name": "Ржаные", "category": "0.4", "aliases": ["ржаные", "ржан", "рж", "ржаной"]},
    {"name": "Сгущенка", "category": "0.45", "aliases": ["сгущенка", "сгущен", "сгущ", "снущ"]},
    {"name": "Айналайн", "category": "0.45", "aliases": ["айналайн", "айнал", "айнала"]},
    {"name": "Виноград", "category": "0.45", "aliases": ["виноград", "виноградные", "вин", "винаград"]},
    {"name": "Творожок", "category": "0.45", "aliases": ["творожок", "творог", "тваражок", "тварож", "твор"]},
    {"name": "Белые весовые", "category": "Белые весовые", "aliases": [
        "бел весовые", "бел вес", "вес бел", "белые весовые", "белвес", "белвесовые", "белые вес",
        "бел. весовые", "бел. вес", "белые вес.", "бел.вес", "бел.вес.", "белвес.", "белвесовые."
    ]},
    {"name": "Весовые круглые", "category": "Весовые (круглые и овальные)", "aliases": [
        "круглые", "кругл", "вес кругл", "кругл вес", "весовые кругл", 
        "весовые кругл.", "кругл. весовые", "вес. кругл", "вес. кругл.", 
        "вес.кругл", "вес.округл", "круглый вес", "вес круглый", "круглый"
    ]},
    { "name": "Весовые овальные", "category": "Весовые (круглые и овальные)", "aliases": [
        "овальные", "овал", "вес овал", "весовые овальные", "овальн", "овальн.",
        "вес. овал", "вес.овальн", "овал вес", "вес овальный", "овальный"
    ]},
    {"name": "0.3", "category": "0.3", "aliases": ["0.3", "0,3"]},
    {"name": "0.4", "category": "0.4", "aliases": ["0.4", "0,4"]},
    {"name": "0.45", "category": "0.45", "aliases": ["0.45", "0,45"]},
    {"name": "Весовые", "category": "Весовые", "aliases": [
        "весовые", "вес", "весовое", "вес.", "вес,", "весо", "весовой", "весовое.", "весовое,"
    ]},
]

regular_prices = {
    "0.3": 400,
    "0.4": 460,
    "0.45": 490,
    "Белые": 550,
    "Черные": 550,
    "Розовые": 550,
    "Весовые (круглые и овальные)": 4320,
    "Белые весовые": 5740,
    "Весовые": 4320,
}

special_prices = {
    "0.3": 360,
    "0.4": 450,
    "0.45": 405,
    "Белые": 495,
    "Черные": 495,
    "Розовые": 495,
    "Белые весовые": 5600,
    "Весовые (круглые и овальные)": 4200,
    "Весовые": 4200,
}

def aggregate_vesovye(summary):
    total_vesovye = 0
    # Суммируем основные категории, которые попадают под "Весовые"
    total_vesovye += summary.get("Весовые", 0)
    total_vesovye += summary.get("Весовые (круглые и овальные)", 0)
    total_vesovye += summary.get("Весовые круглые", 0)
    total_vesovye += summary.get("Весовые овальные", 0)
    # Если есть ещё какие-то веса, добавляй сюда
    return total_vesovye

# ------------- Парсер заявки ------------------
def parse_order(text):
    lines = text.lower().splitlines()
    detailed, summary = {}, {}

    for line in lines:
        line = line.strip()
        if not line:
            continue

        tokens = re.findall(r'\S+', line)
        i = 0
        while i < len(tokens):
            token = tokens[i]

            # Определяем количество и название
            if token.isdigit():
                qty = int(token)
                i += 1
                if i < len(tokens):
                    name_part = tokens[i]
                    i += 1
                else:
                    break
            else:
                name_part = token
                qty = 1
                if i + 1 < len(tokens) and tokens[i + 1].isdigit():
                    qty = int(tokens[i + 1])
                    i += 2
                else:
                    i += 1

            name_part = name_part.strip()

            # Обработка весовых — сначала уточнённые, потом просто вес
            if "вес" in name_part:
                matched_weight = False

                if "овальн" in name_part or "овал" in name_part:
                    name = "Весовые овальные"
                    cat = "Весовые (круглые и овальные)"
                    matched_weight = True
                elif "кругл" in name_part:
                    name = "Весовые круглые"
                    cat = "Весовые (круглые и овальные)"
                    matched_weight = True
                elif name_part.strip() in ["вес", "весовые", "весовый"]:
                    name = "Весовые"
                    cat = "Весовые"
                    matched_weight = True

                if matched_weight:
                    detailed[name] = detailed.get(name, 0) + qty
                    summary[cat] = summary.get(cat, 0) + qty
                    continue  # Пропускаем fuzzy matching для весовых

            # Fuzzy Matching по остальным
            best_match = None
            best_score = 0

            for item in pryaniki_items:
                for alias in item['aliases']:
                    score = fuzz.partial_ratio(name_part, alias)
                    if score > best_score:
                        best_score = score
                        best_match = item

            if best_score >= 70 and best_match:
                name = best_match["name"]
                cat = best_match["category"]
                detailed[name] = detailed.get(name, 0) + qty
                summary[cat] = summary.get(cat, 0) + qty

    return detailed, summary

def calculate_total(summary, prices):
    return sum(summary.get(cat, 0) * prices.get(cat, 0) for cat in summary)

def parse_magazin_and_reason(text: str):
    lines = text.strip().splitlines()
    
    # Если пользователь ввёл несколько строк
    if len(lines) >= 2:
        magazin = lines[0].strip()
        reason_line = lines[1].strip()

        # Попробуем вытащить из скобок, если они есть
        match = re.match(r"^\(?(.+?)\)?$", reason_line)
        if match:
            reason = match.group(1).strip()
        else:
            reason = reason_line

        return magazin, reason

    # Иначе — как раньше, ищем в одной строке
    match = re.match(r"^(.*?)\s*\((.*?)\)\s*$", text)
    if match:
        magazin_name = match.group(1).strip()
        reason = match.group(2).strip()
        return magazin_name, reason

    return text.strip(), ""


# ------------- Обработчики команд ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    markup = ReplyKeyboardMarkup([["Оформить заявку", "Пропуск / Комментарий"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Что вы хотите сделать?", reply_markup=markup)
    return CHOICE

async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if "заявк" in text:
        await update.message.reply_text("Назови, пожалуйста, магазин.", reply_markup=ReplyKeyboardRemove())
        return MAGAZIN
    elif "комментар" in text or "пропуск" in text:
        await update.message.reply_text("Напиши название магазина и причину пропуска (опционально):", reply_markup=ReplyKeyboardRemove())
        return COMMENT
    else:
        await update.message.reply_text("Не понял выбор. Попробуй снова: /start")
        return ConversationHandler.END

async def get_magazin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if any(k in text.lower() for k in ["спец", "спец цена", "спец.цена", "спец цен"]):
        context.user_data['use_special_price'] = True
        clean_name = re.sub(r"\bспец(?:\.| цена| цен)?\b", "", text, flags=re.IGNORECASE).strip()
        context.user_data['magazin'] = f"{clean_name} (спец цена)"
    else:
        context.user_data['use_special_price'] = False
        context.user_data['magazin'] = text

    await update.message.reply_text(
    "Если есть возврат, напиши его, если нет — просто нажми 'Нет'",
    reply_markup=ReplyKeyboardMarkup([["Нет"]], one_time_keyboard=True, resize_keyboard=True)
)
    return RETURN

async def get_return(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data['return_raw'] = text
    d, s = parse_order(text)
    context.user_data['return_detailed'] = d
    context.user_data['return_summary'] = s

    await update.message.reply_text("Что заказал магазин?")
    reply_markup=ReplyKeyboardRemove()
    return ORDER

async def get_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    d, s = parse_order(text)

    prices = special_prices if context.user_data.get('use_special_price') else regular_prices
    total = calculate_total(s, prices)

    context.user_data['order_detailed'] = d
    context.user_data['order_summary'] = s

    ret = context.user_data.get('return_detailed') or {}
    ret_lines = [f"{name}: {qty}" for name, qty in ret.items()] if ret else ["Нет"]

    ord_lines = [f"{name}: {qty}" for name, qty in d.items()] + [f"💰 Сумма: {total} тг"]

    msg = f"""✅ Новая заявка:
📍 Магазин: {context.user_data['magazin']}
↩️ Возврат:
{chr(10).join(ret_lines)}
📦 Заказ:
{chr(10).join(ord_lines)}"""

    await context.bot.send_message(chat_id=TARGET_CHAT_ID, text=msg)
    await update.message.reply_text("Спасибо! Заявка сохранена.")

    markup = ReplyKeyboardMarkup([["Да", "Нет"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Хочешь оформить новую заявку?", reply_markup=markup)

    date = datetime.now().strftime("%d.%m.%Y")
    write_zayavka_to_sheet(
        date=date,
        magazin=context.user_data['magazin'],
        use_special_price=context.user_data.get('use_special_price', False),
        summary=s,
        total=total,
    )

    return RESTART

async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data['comment_magazin'] = text
    await update.message.reply_text(
        "Есть ли возврат? Напиши его или нажми 'Нет'",
        reply_markup=ReplyKeyboardMarkup([["Нет"]], resize_keyboard=True, one_time_keyboard=True)
    )
    return COMMENT_RETURN

async def handle_comment_return(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    d, s = parse_order(text)
    context.user_data['return_detailed'] = d
    context.user_data['return_summary'] = s

    raw_text = context.user_data.get('comment_magazin', 'Не указан')
    magazin, reason = parse_magazin_and_reason(raw_text)

    ret_lines = [f"{name}: {qty}" for name, qty in d.items()] if d else ["Нет"]

    msg = f"""❌ Пропуск
📍 Магазин: {magazin}
📌 Причина: {reason if reason else "Не указана"}
↩️ Возврат:
{chr(10).join(ret_lines)}"""

    await context.bot.send_message(chat_id=TARGET_CHAT_ID, text=msg)
    reply_markup=ReplyKeyboardRemove()
    await update.message.reply_text("Пропуск с возвратом зафиксирован.")

    # Запись в таблицу
    date = datetime.now().strftime("%d.%m.%Y")
    write_skip_to_sheet(date, magazin, reason, s)

    markup = ReplyKeyboardMarkup([["Да", "Нет"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Хочешь оформить новую заявку?", reply_markup=markup)
    return RESTART

async def restart_or_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip().lower() == "да":
        return await start(update, context)
    
    markup = ReplyKeyboardMarkup([["/start"]], resize_keyboard=True)
    await update.message.reply_text("До встречи! Нажми /start, если хочешь начать заново.", reply_markup=markup)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

# ------------- Запуск бота ------------------
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_choice)],
            MAGAZIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_magazin)],
            RETURN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_return)],
            ORDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_order)],
            COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment)],
            COMMENT_RETURN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment_return)],
            RESTART: [MessageHandler(filters.TEXT & ~filters.COMMAND, restart_or_end)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)

    print("Бот запущен...")
    app.run_polling()
