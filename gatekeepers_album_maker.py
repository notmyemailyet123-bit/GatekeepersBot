import os
import re
import math
import logging
import asyncio
import requests
from flask import Flask, request
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

# ============ CONFIG ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", "10000"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")  # Your Render URL + /webhook

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ BOT STATES ============
(
    FACE_PHOTO,
    CONTENT_PHOTOS,
    CONTENT_VIDEOS,
    NAME,
    ALIAS,
    COUNTRY,
    FAME,
    SOCIALS,
    DONE
) = range(9)

# ============ USER DATA STORAGE ============
user_data_store = {}


# ============ STEP HANDLERS ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id] = {
        "face": None,
        "photos": [],
        "videos": [],
        "name": "",
        "alias": "",
        "country": "",
        "fame": "",
        "socials": {}
    }
    await update.message.reply_text("Step 1: Please send a clear face picture of the celebrity.")
    return FACE_PHOTO


async def handle_face(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        user_data_store[user_id]["face"] = file_id
        await update.message.reply_text(
            "Step 2: Send all pictures you want to include.\n"
            "When finished, type or click 'next'."
        )
        return CONTENT_PHOTOS
    await update.message.reply_text("Please send a photo, not text.")
    return FACE_PHOTO


async def handle_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.photo:
        user_data_store[user_id]["photos"].append(update.message.photo[-1].file_id)
        return CONTENT_PHOTOS
    elif update.message.text and update.message.text.lower() == "next":
        await update.message.reply_text(
            "Step 3: Send all videos or gifs you want to include.\n"
            "When finished, type or click 'next'."
        )
        return CONTENT_VIDEOS
    return CONTENT_PHOTOS


async def handle_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.video or update.message.animation:
        file_id = update.message.video.file_id if update.message.video else update.message.animation.file_id
        user_data_store[user_id]["videos"].append(file_id)
        return CONTENT_VIDEOS
    elif update.message.text and update.message.text.lower() == "next":
        await update.message.reply_text("Step 4: Send the person’s full name.")
        return NAME
    return CONTENT_VIDEOS


async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["name"] = update.message.text
    await update.message.reply_text("Step 5: Send their alias or social media handle (if any).")
    return ALIAS


async def handle_alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["alias"] = update.message.text
    await update.message.reply_text("Step 6: Send their country of origin.")
    return COUNTRY


async def handle_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["country"] = update.message.text
    await update.message.reply_text("Step 7: Why is this person famous?")
    return FAME


async def handle_fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["fame"] = update.message.text
    await update.message.reply_text("Step 8: Send their top social media links.")
    return SOCIALS


def extract_follower_count(url: str):
    try:
        if "instagram" in url:
            resp = requests.get(f"https://www.instagram.com/{url.split('/')[-2]}/?__a=1&__d=dis", timeout=5)
            data = resp.json()
            return data.get("graphql", {}).get("user", {}).get("edge_followed_by", {}).get("count", 0)
        elif "tiktok" in url:
            resp = requests.get(url, timeout=5)
            match = re.search(r'\"followerCount\":(\d+)', resp.text)
            return int(match.group(1)) if match else 0
        elif "youtube" in url:
            return 0  # Placeholder (YouTube requires API key)
        else:
            return 0
    except Exception:
        return 0


async def handle_socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == "done":
        await update.message.reply_text("Step 9: Type or click 'done' when ready.")
        return DONE

    user_id = update.effective_user.id
    socials = user_data_store[user_id]["socials"]
    followers = extract_follower_count(text)
    if "instagram" in text:
        socials["Instagram"] = (text, followers)
    elif "youtube" in text:
        socials["YouTube"] = (text, followers)
    elif "tiktok" in text:
        socials["TikTok"] = (text, followers)
    else:
        await update.message.reply_text("Link noted (unknown platform).")
        return SOCIALS

    await update.message.reply_text("Saved! Send another or type 'done'.")
    return SOCIALS


async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_data_store[user_id]

    socials_text = ""
    for name, (url, followers) in data["socials"].items():
        socials_text += f"{name} ({followers}) - {url}\n"

    summary = (
        f"^^^^^^^^^^^^^^^\n\n"
        f"Name: {data['name']}\n"
        f"Alias: {data['alias']}\n"
        f"Country: {data['country']}\n"
        f"Fame: {data['fame']}\n"
        f"Top socials:\n{socials_text}\n===============\n"
    )

    await update.message.reply_text(summary)

    # Album grouping
    all_photos = [data["face"]] + data["photos"]
    group_size = math.ceil(len(all_photos) / math.ceil(len(all_photos) / 10))
    for i in range(0, len(all_photos), group_size):
        chunk = all_photos[i:i + group_size]
        media = [InputMediaPhoto(media=chunk[0])] + [InputMediaPhoto(media=pid) for pid in chunk[1:]]
        await context.bot.send_media_group(chat_id=user_id, media=media)

    await update.message.reply_text("All albums and data have been sent successfully!")
    return ConversationHandler.END


async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)


# ============ CONVERSATION HANDLER ============
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        FACE_PHOTO: [MessageHandler(filters.PHOTO, handle_face)],
        CONTENT_PHOTOS: [MessageHandler(filters.PHOTO | filters.TEXT, handle_photos)],
        CONTENT_VIDEOS: [MessageHandler(filters.VIDEO | filters.ANIMATION | filters.TEXT, handle_videos)],
        NAME: [MessageHandler(filters.TEXT, handle_name)],
        ALIAS: [MessageHandler(filters.TEXT, handle_alias)],
        COUNTRY: [MessageHandler(filters.TEXT, handle_country)],
        FAME: [MessageHandler(filters.TEXT, handle_fame)],
        SOCIALS: [MessageHandler(filters.TEXT, handle_socials)],
        DONE: [MessageHandler(filters.TEXT, finish)],
    },
    fallbacks=[CommandHandler("restart", restart)],
)

# ============ BOT INITIALIZATION ============
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(conv_handler)
application.add_handler(CommandHandler("restart", restart))

_bot_initialized = False  # guard flag


@app.before_request
def setup_bot_once():
    """Initialize the Telegram bot once, since Flask 3.0 removed before_first_request."""
    global _bot_initialized
    if not _bot_initialized:
        asyncio.get_event_loop().run_until_complete(initialize_app())
        _bot_initialized = True


async def initialize_app():
    if not application._initialized:
        await application.initialize()
        await application.start()
        logger.info("Telegram bot initialized and started.")


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        update_data = request.get_json(force=True)
        update = Update.de_json(update_data, application.bot)
        asyncio.get_event_loop().create_task(application.process_update(update))
        return "OK", 200
    except Exception as e:
        logger.exception("Error handling webhook: %s", e)
        return "Internal Server Error", 500


@app.route("/")
def home():
    return "Gatekeepers Album Maker bot is running.", 200


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(initialize_app())
    if WEBHOOK_URL:
        asyncio.get_event_loop().run_until_complete(
            application.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        )
    app.run(host="0.0.0.0", port=PORT)
