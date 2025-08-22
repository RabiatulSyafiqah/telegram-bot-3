# bot.py
import asyncio
from flask import Flask, request
from dotenv import load_dotenv
import os
import logging

from telegram import Bot, Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ConversationHandler, ContextTypes
)

from sheet import (
    is_slot_available,
    save_booking,
    is_valid_date,
    is_weekend,
    get_available_slots,
    sheet,
    get_available_slots_for_officer
)

# Load environment variables
load_dotenv()

# Telegram bot setup
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

# Flask app setup
app = Flask(__name__)

# Conversation states
CHOOSING_OFFICER, GET_NAME, GET_PHONE, GET_EMAIL, GET_PURPOSE, GET_DATE, GET_TIME = range(7)

# Global application instance
application = None

# === Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Selamat datang ke Sistem Temu Janji Pejabat Daerah Keningau! 🏛️\n"
        "Taip /book untuk menempah janji temu."
    )

async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Sila pilih pegawai yang ingin anda temui:\n"
        "1. Pegawai Daerah (DO)\n"
        "2. Penolong Pegawai Daerah (ADO)\n"
        "3. Penolong Pegawai Daerah (Pembangunan)"
    )
    return CHOOSING_OFFICER

async def choose_officer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.strip()
    if choice == "1":
        officer = "DO"
    elif choice == "2":
        officer = "ADO"
    elif choice == "3":
        officer = "ADO_PEMBANGUNAN"
    else:
        await update.message.reply_text("Sila pilih 1, 2 atau 3.")
        return CHOOSING_OFFICER

    context.user_data["officer"] = officer
    await update.message.reply_text("Masukkan nama penuh anda:")
    return GET_NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Masukkan nombor telefon anda (cth: 0134567890):")
    return GET_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["phone"] = update.message.text.strip()
    await update.message.reply_text("Masukkan alamat emel anda:")
    return GET_EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["email"] = update.message.text.strip()
    await update.message.reply_text("Nyatakan tujuan janji temu:")
    return GET_PURPOSE

async def get_purpose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["purpose"] = update.message.text.strip()
    await update.message.reply_text("Masukkan tarikh pilihan (DD/MM/YYYY):")
    return GET_DATE

async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date = update.message.text.strip()

    if not is_valid_date(date):
        await update.message.reply_text("⚠️ Tarikh tidak sah! Sila masukkan tarikh akan datang (DD/MM/YYYY).")
        return GET_DATE

    if is_weekend(date):
        await update.message.reply_text("⛔ Tempahan tidak boleh dibuat pada hujung minggu. Sila pilih tarikh bekerja.")
        return GET_DATE

    officer = context.user_data.get("officer")
    available_slots = get_available_slots_for_officer(date, officer) if officer else get_available_slots(date)
    if not available_slots:
        await update.message.reply_text("⛔ Tiada slot tersedia pada tarikh ini. Sila cuba tarikh lain:")
        return GET_DATE

    context.user_data.update({"date": date, "available_slots": available_slots})
    keyboard = [[slot] for slot in available_slots]
    await update.message.reply_text("⏰ Sila pilih masa temu janji:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return GET_TIME

async def get_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = context.user_data
        chosen_time = update.message.text.strip()
        available_slots = data["available_slots"]
        date = data["date"]
        officer = data["officer"]
    except KeyError:
        await update.message.reply_text("⚠️ Sesi dibatalkan. Sila cuba lagi dengan /book", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    if chosen_time not in available_slots:
        await update.message.reply_text("⛔ Masa tidak sah. Sila pilih masa dari senarai yang diberikan.")
        return GET_TIME

    if not is_slot_available(date, chosen_time, officer):
        # Recompute available slots to reflect latest calendar updates
        available_slots = get_available_slots_for_officer(date, officer)
        await update.message.reply_text("⛔ Slot ini tidak tersedia (bertembung dengan jadual). Sila pilih masa lain.", reply_markup=ReplyKeyboardMarkup([[slot] for slot in available_slots], one_time_keyboard=True))
        return GET_TIME

    save_booking(update.message.from_user.id, data["name"], data["phone"], data["email"], officer, data["purpose"], date, chosen_time)
    await update.message.reply_text(f"✅ Tempahan berjaya!\nTarikh: {date}\nMasa: {chosen_time}\nPegawai: {officer}", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Tempahan dibatalkan.")
    return ConversationHandler.END

# === Setup Application ===
async def setup_application():
    global application
    application = Application.builder().token(TOKEN).build()
    
    # Initialize the application
    await application.initialize()
    
    # === Register handlers ===
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("book", book)],
        states={
            CHOOSING_OFFICER: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_officer)],
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            GET_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            GET_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            GET_PURPOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_purpose)],
            GET_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
            GET_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_time)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    
    return application

# === Global event loop for the application ===
bot_loop = None
bot_thread = None

def run_bot_loop():
    """Run the bot's event loop in a dedicated thread"""
    global bot_loop
    bot_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(bot_loop)
    
    # Initialize the application in this thread
    asyncio.run_coroutine_threadsafe(setup_application(), bot_loop)
    
    # Run the event loop forever
    bot_loop.run_forever()

import threading

# === Webhook routes ===
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    
    # Schedule the update processing in the bot's event loop
    if bot_loop and not bot_loop.is_closed():
        future = asyncio.run_coroutine_threadsafe(application.process_update(update), bot_loop)
        try:
            # Wait for completion with a timeout
            future.result(timeout=30)
        except Exception as e:
            print(f"Error processing update: {e}")
            return "error", 500
    else:
        print("Bot loop not available")
        return "error", 500
    
    return "ok", 200

@app.route("/")
def index():
    return "Bot is live!", 200

@app.route("/", methods=["POST"])
def webhook_root():
    # Redirect POST requests to root to the proper webhook endpoint
    return webhook()

# === Run the app ===
if __name__ == "__main__":
    # Start the bot in a separate thread with its own event loop
    import threading
    bot_thread = threading.Thread(target=run_bot_loop, daemon=True)
    bot_thread.start()
    
    # Give the bot thread time to initialize
    import time
    time.sleep(2)
    
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
