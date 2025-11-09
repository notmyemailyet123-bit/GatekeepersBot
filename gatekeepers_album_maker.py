import os
import logging
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)
from pathlib import Path

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 10000))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("Set BOT_TOKEN and WEBHOOK_URL environment variables.")

DATA_DIR = Path("user_data")
DATA_DIR.mkdir(exist_ok=True)

# Conversation states
FACE, PHOTOS, VIDEOS, NAME, ALIAS, COUNTRY, FAME, SOCIALS, CONFIRM = range(9)
user_data = {}

# ======== HANDLERS =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid] = {"photos": [], "videos": []}
    await update.message.reply_text("Send a face picture to start.")
    return FACE

async def face_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    photo = update.message.photo[-1]
    f = await photo.get_file()
    path = DATA_DIR / f"{uid}_face.jpg"
    await f.download_to_drive(path)
    user_data[uid]["face_path"] = path
    await update.message.reply_text("Face saved. Now send all photos. Type 'next' when done.")
    return PHOTOS

async def collect_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if update.message.text and update.message.text.lower() == "next":
        await update.message.reply_text("Now send videos. Type 'next' when done.")
        return VIDEOS
    photo = update.message.photo[-1]
    f = await photo.get_file()
    path = DATA_DIR / f"{uid}_{os.path.basename(f.file_path)}"
    await f.download_to_drive(path)
    user_data[uid]["photos"].append(path)
    return PHOTOS

async def collect_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if update.message.text and update.message.text.lower() == "next":
        await update.message.reply_text("Send full name:")
        return NAME
    file = update.message.video or update.message.animation
    if file:
        f = await file.get_file()
        path = DATA_DIR / f"{uid}_{os.path.basename(f.file_path)}"
        await f.download_to_drive(path)
        user_data[uid]["videos"].append(path)
    return VIDEOS

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid]["name"] = update.message.text
    await update.message.reply_text("Send alias/handle:")
    return ALIAS

async def get_alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid]["alias"] = update.message.text
    await update.message.reply_text("Send country:")
    return COUNTRY

async def get_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid]["country"] = update.message.text
    await update.message.reply_text("Why are they famous?")
    return FAME

async def get_fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid]["fame"] = update.message.text
    await update.message.reply_text("Send socials (YouTube/Instagram/TikTok) in one message.")
    return SOCIALS

async def get_socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lines = update.message.text.splitlines()
    socials = {}
    for line in lines:
        if "youtube" in line.lower(): socials["youtube"] = line.strip()
        if "instagram" in line.lower(): socials["instagram"] = line.strip()
        if "tiktok" in line.lower(): socials["tiktok"] = line.strip()
    user_data[uid].update(socials)
    await update.message.reply_text("Type 'done' to finish.")
    return CONFIRM

async def finalize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = user_data[uid]
    msg = f"Name: {data.get('name')}\nAlias: {data.get('alias')}\nCountry: {data.get('country')}\nFame: {data.get('fame')}\nSocials: {data.get('youtube','')}, {data.get('instagram','')}, {data.get('tiktok','')}"
    await update.message.reply_text(msg)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END

# ======== BOT SETUP =========
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        FACE: [MessageHandler(filters.PHOTO, face_photo)],
        PHOTOS: [MessageHandler(filters.PHOTO | filters.TEXT, collect_photos)],
        VIDEOS: [MessageHandler(filters.VIDEO | filters.ANIMATION | filters.TEXT, collect_videos)],
        NAME: [MessageHandler(filters.TEXT, get_name)],
        ALIAS: [MessageHandler(filters.TEXT, get_alias)],
        COUNTRY: [MessageHandler(filters.TEXT, get_country)],
        FAME: [MessageHandler(filters.TEXT, get_fame)],
        SOCIALS: [MessageHandler(filters.TEXT, get_socials)],
        CONFIRM: [MessageHandler(filters.Regex("^(done|Done|DONE)$"), finalize)],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
)

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(conv_handler)

if __name__ == "__main__":
    # Run webhook server directly (production-ready)
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
        webhook_cert=None,
        key=None,
    )
