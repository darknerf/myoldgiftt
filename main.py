import os
import json
import logging
import asyncio
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler
from telegram.constants import ParseMode

# lol
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("Переменная окружения TOKEN не задана!")

GIFT_IDS = {
    "heart_14feb": 5801108895304779062,
    "newyear_bear": 5956217000635139069,
    "bear_14feb": 5800655655995968830,
}

GIFT_NAMES = {
    "heart_14feb": "❤️ Сердечко на 14 февраля",
    "newyear_bear": "🎄 Новогодний мишка",
    "bear_14feb": "🧸 Мишка на 14 февраля",
}

DATA_FILE = "user_data.json"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

def load_data():
    if Path(DATA_FILE).exists():
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

user_data = load_data()

def update_user_data(user_id, name=None):
    user_id = str(user_id)
    if user_id not in user_data:
        user_data[user_id] = {"name": name, "operations": 0}
    elif name:
        user_data[user_id]["name"] = name
    save_data(user_data)

def main_keyboard():
    keyboard = [[KeyboardButton("👤 Профиль"), KeyboardButton("🎁 Купить подарок")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def gifts_keyboard():
    keyboard = []
    for key, name in GIFT_NAMES.items():
        keyboard.append([InlineKeyboardButton(name, callback_data=f"gift_{key}")])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    update_user_data(user.id, user.full_name)
    await update.message.reply_text(
        f"Привет, {user.first_name}!\nЭто бот для покупки гифтов в Telegram (через API), которые больше не активны и не покупаются через дефолтный магазин.",
        reply_markup=main_keyboard()
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    data = user_data.get(uid, {"name": user.full_name, "operations": 0})
    text = f"👤 Твоё имя: {data['name']}\n🆔 Твой ID: {user.id}\n📊 Твои операции: {data['operations']}"
    keyboard = [[KeyboardButton("🔙 Назад")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(text, reply_markup=reply_markup)

async def back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Главное меню:", reply_markup=main_keyboard())

async def buy_gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выбери подарок:", reply_markup=gifts_keyboard())

async def gift_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gift_key = query.data.replace("gift_", "")
    if gift_key not in GIFT_IDS:
        await query.edit_message_text("Неизвестный подарок.")
        return
    context.user_data["selected_gift"] = gift_key
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Без описания", callback_data="no_text")]])
    await query.edit_message_text(
        "Какую надпись вы хотите добавить?\nНапиши текст или нажми кнопку «Без описания».",
        reply_markup=keyboard
    )

async def no_text_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Хорошо, отправляю счёт без подписи...")
    await send_invoice(update, context, text=None)

async def handle_gift_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "selected_gift" not in context.user_data:
        return
    text = update.message.text
    await send_invoice(update, context, text)

async def send_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE, text=None):
    user = update.effective_user
    gift_key = context.user_data.get("selected_gift")
    if not gift_key:
        await update.message.reply_text("Ошибка: подарок не выбран.")
        return
    gift_name = GIFT_NAMES[gift_key]
    payload = json.dumps({"user_id": user.id, "gift_key": gift_key, "text": text})
    await context.bot.send_invoice(
        chat_id=user.id,
        title=f"Покупка подарка: {gift_name}",
        description="Подарок в Telegram за 50 звёзд",
        payload=payload,
        provider_token="",
        currency="XTR",
        prices=[{"label": "Подарок", "amount": 50}],
        start_parameter="gift_payment"
    )

async def pre_checkout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = message.from_user
    payload_str = message.successful_payment.invoice_payload
    try:
        payload = json.loads(payload_str)
    except:
        await message.reply_text("Ошибка обработки платежа.")
        return
    user_id = payload["user_id"]
    gift_key = payload["gift_key"]
    text = payload.get("text")
    if user_id != user.id:
        await message.reply_text("Ошибка: несоответствие пользователя.")
        return
    gift_id = GIFT_IDS[gift_key]
    try:
        await context.bot.send_gift(user_id=user_id, gift_id=gift_id, text=text)
        uid = str(user.id)
        if uid in user_data:
            user_data[uid]["operations"] += 1
        else:
            user_data[uid] = {"name": user.full_name, "operations": 1}
        save_data(user_data)
        await message.reply_text(f"✅ Подарок успешно отправлен!\nТвои операции: {user_data[uid]['operations']}", reply_markup=main_keyboard())
    except Exception as e:
        logger.error(f"Ошибка отправки подарка: {e}")
        await message.reply_text("❌ Не удалось отправить подарок. Попробуй позже.")
    context.user_data.pop("selected_gift", None)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "👤 Профиль":
        await profile(update, context)
    elif text == "🎁 Купить подарок":
        await buy_gift(update, context)
    elif text == "🔙 Назад":
        await back(update, context)
    elif "selected_gift" in context.user_data:
        await handle_gift_text(update, context)
    else:
        await update.message.reply_text("Используй кнопки меню.", reply_markup=main_keyboard())

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(gift_callback, pattern="^gift_"))
    app.add_handler(CallbackQueryHandler(no_text_callback, pattern="^no_text$"))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    print("Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
