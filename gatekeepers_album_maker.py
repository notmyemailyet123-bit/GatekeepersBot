import os
import re
import logging
from flask import Flask, request
from telegram import (
    Update, InputMediaPhoto, InputMediaVideo, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
    ConversationHandler
)
import requests
import asyncio

logging.basicConfig(level=logging.INFO)

# --- Environment Variables ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# --- Conversation Steps ---
(
    STATE_FACE,
    STATE_PHOTOS,
    STATE_VIDEOS,
    STATE_NAME,
    STATE_ALIAS,
    STATE_COUNTRY,
    STATE_FAME,
    STATE_SOCIALS,
    STATE_FINAL_CONFIRM,
) = range(9)

# --- Step Buttons ---
BTN_NEXT = "Next Step"
BTN_DONE = "Done"

# --- User data storage ---
user_data_store = {}

# --- Helper Functions ---
def get_user_data(context: ContextTypes.DEFAULT_TYPE):
    return user_data_store.setdefault(context._user_id, {
        "face": None,
        "photos": [],
        "videos": [],
        "name": None,
        "alias": None,
        "country": None,
        "fame": None,
        "socials": {},
    })

def format_output(data):
    socials_text = ""
    for site, info in data["socials"].items():
        socials_text += f"{site.capitalize()} ({info.get('followers','x')}) - {info.get('link','')}\n"

    return (
        "^^^^^^^^^^^^^^^\n\n"
        f"Name: {data['name']}\n"
        f"Alias: {data['alias']}\n"
        f"Country: {data['country']}\n"
        f"Fame: {data['fame']}\n"
        f"Top socials:\n{socials_text}\n"
        "===============\n"
    )

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store.pop(update.effective_user.id, None)
    user_data_store[update.effective_user.id] = {
        "face": None,
        "photos": [],
        "videos": [],
        "name": None,
        "alias": None,
        "country": None,
        "fame": None,
        "socials": {},
    }
    await update.message.reply_text("Step 1: Send a normal face picture of the celebrity.")
    return STATE_FACE

async def face_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_id = update.message.photo[-1].file_id
    get_user_data(context)["face"] = file_id
    await update.message.reply_text("Got it. Now send all the pictures you want to post. When done, press or type 'Next Step'.")
    return STATE_PHOTOS

async def photos_collector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_user_data(context)
    if update.message.photo:
        data["photos"].append(update.message.photo[-1].file_id)
    return STATE_PHOTOS

async def photos_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Now send all videos or GIFs you want to include. When done, press or type 'Next Step'.")
    return STATE_VIDEOS

async def videos_collector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_user_data(context)
    message = update.message

    if message.video:
        data["videos"].append(message.video.file_id)
    elif message.animation:
        data["videos"].append(message.animation.file_id)
    elif message.document and "video" in (message.document.mime_type or ""):
        data["videos"].append(message.document.file_id)

    return STATE_VIDEOS

async def videos_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Step 4: Send the person’s full name.")
    return STATE_NAME

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user_data(context)["name"] = update.message.text
    await update.message.reply_text("Step 5: Send the person’s alias or social media handles.")
    return STATE_ALIAS

async def receive_alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user_data(context)["alias"] = update.message.text
    await update.message.reply_text("Step 6: Send the person’s country of origin.")
    return STATE_COUNTRY

async def receive_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user_data(context)["country"] = update.message.text
    await update.message.reply_text("Step 7: Why is this person famous?")
    return STATE_FAME

async def receive_fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    get_user_data(context)["fame"] = update.message.text
    await update.message.reply_text("Step 8: Send the celebrity’s social media links (YouTube, Instagram, TikTok).")
    return STATE_SOCIALS

def extract_followers(url):
    # Fake placeholder follower counter for now (API integration can be added later)
    return "x"

async def socials_collector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    data = get_user_data(context)

    for platform in ["youtube", "instagram", "tiktok"]:
        if platform in text.lower():
            data["socials"][platform] = {
                "link": text,
                "followers": extract_followers(text)
            }

    await update.message.reply_text("Got it. When done sending all social links, type or click 'Done'.")
    return STATE_FINAL_CONFIRM

async def finalize_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = get_user_data(context)
    summary = format_output(data)
    await update.message.reply_text(summary)

    # Send albums back
    all_media = data["photos"]
    face_id = data["face"]

    if all_media:
        groups = []
        total = len(all_media)
        split_size = max(1, total // ((total + 9) // 10))

        for i in range(0, total, split_size):
            batch = all_media[i:i + split_size]
            group = [InputMediaPhoto(face_id)] + [InputMediaPhoto(pid) for pid in batch]
            groups.append(group)

        for g in groups:
            await update.message.reply_media_group(g)

    await update.message.reply_text("All done! You can forward this summary now or use /restart to start over.")
    return ConversationHandler.END

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

# --- Flask + Telegram Integration ---
def create_app():
    app = Flask(__name__)

    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            STATE_FACE: [
                MessageHandler(filters.PHOTO & ~filters.COMMAND, face_photo_handler),
                CommandHandler("restart", restart),
            ],
            STATE_PHOTOS: [
                MessageHandler(filters.TEXT & filters.Regex(re.compile(f'^{re.escape(BTN_NEXT)}$', re.I)), photos_next),
                MessageHandler(filters.PHOTO & ~filters.COMMAND, photos_collector),
                CommandHandler("restart", restart),
            ],
            STATE_VIDEOS: [
                MessageHandler(filters.TEXT & filters.Regex(re.compile(f'^{re.escape(BTN_NEXT)}$', re.I)), videos_next),
                MessageHandler(
                    (filters.VIDEO | filters.ANIMATION | (filters.Document.ALL & filters.Regex("video"))),
                    videos_collector,
                ),
                CommandHandler("restart", restart),
            ],
            STATE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name),
                CommandHandler("restart", restart),
            ],
            STATE_ALIAS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_alias),
                CommandHandler("restart", restart),
            ],
            STATE_COUNTRY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_country),
                CommandHandler("restart", restart),
            ],
            STATE_FAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_fame),
                CommandHandler("restart", restart),
            ],
            STATE_SOCIALS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, socials_collector),
                CommandHandler("restart", restart),
            ],
            STATE_FINAL_CONFIRM: [
                MessageHandler(filters.TEXT & filters.Regex(re.compile(f'^{re.escape(BTN_DONE)}$', re.I)), finalize_and_send),
                CommandHandler("restart", restart),
            ],
        },
        fallbacks=[CommandHandler("restart", restart)],
        allow_reentry=True,
    )

    application.add_handler(conv_handler)

    async def process_update(request_data):
        update = Update.de_json(request_data, application.bot)
        await application.process_update(update)

    @app.route("/webhook", methods=["POST"])
    def webhook():
        asyncio.run(process_update(request.get_json(force=True)))
        return "ok"

    async def set_hook():
        await application.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")

    asyncio.get_event_loop().run_until_complete(set_hook())
    return app

app_obj = create_app()

if __name__ == "__main__":
    app_obj.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
