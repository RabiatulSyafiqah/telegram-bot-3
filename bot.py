# bot.py
from flask import Flask, request
from dotenv import load_dotenv
import os
import logging
from queue import Queue

from telegram import Bot, Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Dispatcher, CommandHandler, MessageHandler, Filters,
    ConversationHandler, CallbackContext
)

from sheet import (
    is_slot_available,
    save_booking,
    get_alternative_times,
    is_valid_date,
    is_weekend,
    get_available_slots,
    sheet
)

# Load environment variables
load_dotenv()

# Telegram bot setup
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
bot = Bot(token=TOKEN)
app = Flask(__name__)

# Dispatcher setup for python-telegram-bot v13.15
update_queue = Queue()
dispatcher = Dispatcher(bot, update_queue, workers=0, use_context=True)

# Conversation states
CHOOSING_OFFICER, GET_NAME, GET_PHONE, GET_EMAIL, GET_PURPOSE, GET_DATE, GET_TIME = range(7)

# === Handlers ===
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Selamat datang ke Sistem Temu Janji Pejabat Daerah Keningau! 🏛️\n"
        "Taip /book untuk menempah janji temu."
    )

def book(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Sila pilih pegawai yang ingin anda temui:\n"
        "1. Pegawai Daerah (DO)\n"
        "2. Penolong Pegawai Daerah (ADO)"
    )
    return CHOOSING_OFFICER

def choose_officer(update: Update, context: CallbackContext):
    choice = update.message.text.strip()
    if choice == "1":
        officer = "DO"
    elif choice == "2":
        officer = "ADO"
    else:
        update.message.reply_text("Sila pilih 1 atau 2.")
        return CHOOSING_OFFICER

    context.user_data["officer"] = officer
    update.message.reply_text("Masukkan nama penuh anda:")
    return GET_NAME

def get_name(update: Update, context: CallbackContext):
    context.user_data["name"] = update.message.text.strip()
    update.message.reply_text("Masukkan nombor telefon anda (cth: 0134567890):")
    return GET_PHONE

def get_phone(update: Update, context: CallbackContext):
    context.user_data["phone"] = update.message.text.strip()
    update.message.reply_text("Masukkan alamat emel anda:")
    return GET_EMAIL

def get_email(update: Update, context: CallbackContext):
    context.user_data["email"] = update.message.text.strip()
    update.message.reply_text("Nyatakan tujuan janji temu:")
    return GET_PURPOSE

def get_purpose(update: Update, context: CallbackContext):
    context.user_data["purpose"] = update.message.text.strip()
    update.message.reply_text("Masukkan tarikh pilihan (DD/MM/YYYY):")
    return GET_DATE

def get_date(update: Update, context: CallbackContext):
    date = update.message.text.strip()

    if not is_valid_date(date):
        update.message.reply_text("⚠️ Tarikh tidak sah! Sila masukkan tarikh akan datang (DD/MM/YYYY).")
        return GET_DATE

    if is_weekend(date):
        update.message.reply_text("⛔ Tempahan tidak boleh dibuat pada hujung minggu. Sila pilih tarikh bekerja.")
        return GET_DATE

    available_slots = get_available_slots(date)
    if not available_slots:
        update.message.reply_text("⛔ Tiada slot tersedia pada tarikh ini. Sila cuba tarikh lain:")
        return GET_DATE

    context.user_data.update({"date": date, "available_slots": available_slots})
    keyboard = [[slot] for slot in available_slots]
    update.message.reply_text("⏰ Sila pilih masa temu janji:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return GET_TIME

def get_time(update: Update, context: CallbackContext):
    try:
        data = context.user_data
        chosen_time = update.message.text.strip()
        available_slots = data["available_slots"]
        date = data["date"]
        officer = data["officer"]
    except KeyError:
        update.message.reply_text("⚠️ Sesi dibatalkan. Sila cuba lagi dengan /book", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    if chosen_time not in available_slots:
        update.message.reply_text("⛔ Masa tidak sah. Sila pilih masa dari senarai yang diberikan.")
        return GET_TIME

    if not is_slot_available(date, chosen_time, officer):
        update.message.reply_text("⛔ Slot ini telah ditempah. Sila pilih masa lain.", reply_markup=ReplyKeyboardMarkup([[slot] for slot in available_slots if is_slot_available(date, slot, officer)], one_time_keyboard=True))
        return GET_TIME

    save_booking(update.message.from_user.id, data["name"], data["phone"], data["email"], officer, data["purpose"], date, chosen_time)
    update.message.reply_text(f"✅ Tempahan berjaya!\nTarikh: {date}\nMasa: {chosen_time}\nPegawai: {officer}", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("Tempahan dibatalkan.")
    return ConversationHandler.END

# === Register handlers ===
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("book", book)],
    states={
        CHOOSING_OFFICER: [MessageHandler(Filters.text & ~Filters.command, choose_officer)],
        GET_NAME: [MessageHandler(Filters.text & ~Filters.command, get_name)],
        GET_PHONE: [MessageHandler(Filters.text & ~Filters.command, get_phone)],
        GET_EMAIL: [MessageHandler(Filters.text & ~Filters.command, get_email)],
        GET_PURPOSE: [MessageHandler(Filters.text & ~Filters.command, get_purpose)],
        GET_DATE: [MessageHandler(Filters.text & ~Filters.command, get_date)],
        GET_TIME: [MessageHandler(Filters.text & ~Filters.command, get_time)],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(conv_handler)

# === Webhook route ===
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok", 200

@app.route("/")
def index():
    return "Bot is live!", 200

# === Run the app ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))