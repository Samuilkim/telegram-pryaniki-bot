import logging
import re
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
from rapidfuzz import process, fuzz

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

# Состояния
CHOICE, MAGAZIN, ORDER, RETURN, RESTART, COMMENT, COMMENT_EXCHANGE = range(7)

# Токен и чат
TOKEN = "7749753466:AAEkq87KxBo8rko4fuyDl-5RIL64nxpMbos"
TARGET_CHAT_ID = -1002805411399

# Пряники
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
    {"name": "Белые весовые", "category": "Белые весовые", "aliases": ["бел весовые", "бел вес", "вес бел"]},
    {"name": "Весовые круглые", "category": "Весовые (круглые и овальные)", "aliases": ["круглые", "кругл", "вес кругл"]},
    {"name": "Весовые овальные", "category": "Весовые (круглые и овальные)", "aliases": ["овал", "вес овал"]},
    {"name": "0.3", "category": "0.3", "aliases": ["0.3", "0,3"]},
    {"name": "0.4", "category": "0.4", "aliases": ["0.4", "0,4"]},
    {"name": "0.45", "category": "0.45", "aliases": ["0.45", "0,45"]},
    {"name": "Весовые", "category": "Весовые", "aliases": ["весовые", "вес", "весовое"]},
]

# Цены
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

# Парсинг заявки
def parse_order(text):
    text = text.lower()
    pairs = re.findall(r"([\d\w.,]+)[\s\-:]*?(\d+)", text)  # старый шаблон: слово + число
    reverse_pairs = re.findall(r"(\d+)[\s\-:]*?([\d\w.,]+)", text)  # новый: число + слово
    all_pairs = pairs + [(b, a) for a, b in reverse_pairs]  # объединяем

    detailed, summary = {}, {}

    for name_part, qty_str in all_pairs:
        qty = int(qty_str)
        name_part_cleaned = name_part.strip().replace(",", ".")

        best_match = None
        best_score = 0
        for item in pryaniki_items:
            match, score, _ = process.extractOne(name_part_cleaned, item["aliases"], scorer=fuzz.ratio)
            if score > best_score:
                best_score = score
                best_match = item

        if best_score >= 80 and best_match:
            name = best_match["name"]
            cat = best_match["category"]
            detailed[name] = detailed.get(name, 0) + qty
            summary[cat] = summary.get(cat, 0) + qty

    return detailed, summary

def calculate_total(summary, prices):
    return sum(summary.get(cat, 0) * prices.get(cat, 0) for cat in summary)

# Старт
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    markup = ReplyKeyboardMarkup([["Оформить заявку", "Пропуск / Комментарий"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Что вы хотите сделать?", reply_markup=markup)
    return CHOICE

# Выбор
async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip().lower()
    if "заявк" in t:
        await update.message.reply_text("Назови, пожалуйста, магазин.", reply_markup=ReplyKeyboardRemove())
        return MAGAZIN
    elif "комментар" in t or "пропуск" in t:
        await update.message.reply_text("Напиши название магазина и причину пропуска (опционально):", reply_markup=ReplyKeyboardRemove())
        return COMMENT
    else:
        await update.message.reply_text("Не понял выбор. Попробуй снова: /start")
        return ConversationHandler.END

# Комментарий / пропуск
async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    parts = t.split(maxsplit=1)
    magazin = parts[0]
    reason = parts[1] if len(parts) > 1 else None
    context.user_data['comment_result'] = f"🚫 {magazin} — Пропуск" + (f" ({reason})" if reason else "")
    markup = ReplyKeyboardMarkup([["❌ Нет обмена"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Если есть обмен — напиши его. Если нет — нажми ❌", reply_markup=markup)
    return COMMENT_EXCHANGE

async def handle_comment_exchange(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    base = context.user_data['comment_result']
    if "нет" in text.lower() or "❌" in text:
        result = base
    else:
        detailed, _ = parse_order(text)
        lines = [f"{name}: {qty}" for name, qty in detailed.items()]
        result = base + ("\n🔄 Обмен:\n" + "\n".join(lines) if lines else f"\n🔄 Обмен: {text}")
    await context.bot.send_message(chat_id=TARGET_CHAT_ID, text=result)
    await update.message.reply_text("Информация сохранена ✅", reply_markup=ReplyKeyboardMarkup([["/start"]], one_time_keyboard=True))
    return ConversationHandler.END

# Название магазина
async def get_magazin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # Проверяем спеццену
    if any(key in text.lower() for key in ["спец", "спец цена", "спец.цена", "спец цен"]):
        context.user_data['use_special_price'] = True
        # Удаляем слово "спец" и варианты из текста
        clean_name = re.sub(r"\bспец(?:\.| цена| цен)?\b", "", text, flags=re.IGNORECASE).strip()
        context.user_data['magazin'] = f"{clean_name} (спец цена)"
    else:
        context.user_data['use_special_price'] = False
        context.user_data['magazin'] = text

    reply_keyboard = [["Нет"]]
    markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Есть ли возврат? Напиши или нажми 'Нет'", reply_markup=markup)
    return RETURN

# Возврат
async def get_return(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    context.user_data['return_raw'] = txt
    d, s = parse_order(txt)
    context.user_data['return_detailed'] = d
    context.user_data['return_summary'] = s
    await update.message.reply_text("Что заказал магазин?")
    return ORDER

# Заказ
async def get_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    d, s = parse_order(txt)
    prices = special_prices if context.user_data.get('use_special_price') else regular_prices
    total = calculate_total(s, prices)
    context.user_data['order_detailed'] = d
    context.user_data['order_summary'] = s
    ret = context.user_data.get('return_detailed') or {}
    ret_lines = [f"{name}: {qty}" for name, qty in ret.items()] if ret else [context.user_data.get('return_raw', 'нет')]
    ord_lines = [f"{name}: {qty}" for name, qty in d.items()] + [f"💰 Сумма: {total} тг"]
    msg = f"""✅ Новая заявка:
📍 Магазин: {context.user_data['magazin']}
↩️ Возврат:
{chr(10).join(ret_lines)}
📦 Заказ:
{chr(10).join(ord_lines)}"""
    await update.message.reply_text("Спасибо! Заявка сохранена.")
    await context.bot.send_message(chat_id=TARGET_CHAT_ID, text=msg)
    markup = ReplyKeyboardMarkup([["Да", "Нет"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Хочешь оформить новую заявку?", reply_markup=markup)
    return RESTART

async def restart_or_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip().lower() == "да":
        return await start(update, context)
    markup = ReplyKeyboardMarkup([["/start"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Хорошо! Если захочешь снова — просто нажми /start 👇", reply_markup=markup)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена.")
    return ConversationHandler.END

# Запуск
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_choice)],
            COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment)],
            COMMENT_EXCHANGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment_exchange)],
            MAGAZIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_magazin)],
            RETURN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_return)],
            ORDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_order)],
            RESTART: [MessageHandler(filters.TEXT & ~filters.COMMAND, restart_or_end)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    app.add_handler(conv_handler)
    print("Бот запущен...")
    app.run_polling()
