import os
import asyncio
from io import BytesIO
from math import ceil
from urllib.parse import urlparse

from flask import Flask, request
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputMediaPhoto, InputMediaVideo
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, ConversationHandler,
    filters
)

# -------------------------
# Configuration
# -------------------------
TOKEN = os.getenv("BOT_TOKEN")  # Your Telegram bot token
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g., https://gatekeepersbot.onrender.com/

# Conversation states
(
    FACE_PHOTO, CONTENT_IMAGES, CONTENT_VIDEOS, FULL_NAME,
    ALIAS, COUNTRY, FAME, SOCIALS, CONFIRM
) = range(9)

# Initialize Flask
flask_app = Flask(__name__)
user_data = {}  # store per-user data

# -------------------------
# Helper functions
# -------------------------
def validate_social_link(url: str):
    """Simple validation for social URLs"""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        if not parsed.netloc:
            return False
        return True
    except Exception:
        return False

def split_into_albums(items, max_per_album=10):
    """Split items into nearly even albums, max 10 per album"""
    n = len(items)
    if n == 0:
        return []
    num_albums = ceil(n / max_per_album)
    per_album = ceil(n / num_albums)
    return [items[i:i + per_album] for i in range(0, n, per_album)]

def format_summary(data):
    """Format user data into your template"""
    socials_text = ""
    for platform, followers in data.get("socials", {}).items():
        socials_text += f"{platform} ({followers}) - \n"
    return (
        "^^^^^^^^^^^^^^^\n\n"
        f"Name: {data.get('full_name','-')}\n"
        f"Alias: {data.get('alias','-')}\n"
        f"Country: {data.get('country','-')}\n"
        f"Fame: {data.get('fame','-')}\n"
        f"Top socials:\n{socials_text}\n"
        "===============\n"
    )

# -------------------------
# Flask webhook route
# -------------------------
@flask_app.route("/", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), app.bot)
    asyncio.run(app.update_queue.put(update))
    return "OK"

# -------------------------
# Command Handlers
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id] = {
        "face_photo": None,
        "images": [],
        "videos": [],
        "full_name": None,
        "alias": None,
        "country": None,
        "fame": None,
        "socials": {}
    }
    await update.message.reply_text("Welcome to Gatekeepers Album Maker!\nSend a **normal face picture of the celebrity** to start.")
    return FACE_PHOTO

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

# -------------------------
# Step Handlers
# -------------------------
async def handle_face_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not update.message.photo:
        await update.message.reply_text("Please send a valid photo.")
        return FACE_PHOTO
    bio = BytesIO()
    await update.message.photo[-1].get_file().download_to_memory(out=bio)
    bio.seek(0)
    user_data[user_id]["face_photo"] = bio
    await update.message.reply_text("Face photo saved! Now send all pictures you want to post. Send /done when finished.")
    return CONTENT_IMAGES

async def handle_content_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.text and update.message.text.lower() == "/done":
        await update.message.reply_text(f"Saved {len(user_data[user_id]['images'])} images. Now send all videos/GIFs. Send /done when finished.")
        return CONTENT_VIDEOS
    elif update.message.photo:
        bio = BytesIO()
        await update.message.photo[-1].get_file().download_to_memory(out=bio)
        bio.seek(0)
        user_data[user_id]["images"].append(bio)
        return CONTENT_IMAGES
    else:
        return CONTENT_IMAGES  # ignore non-photo messages

async def handle_content_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.text and update.message.text.lower() == "/done":
        await update.message.reply_text("Videos/GIFs saved. Send the celebrity's full name.")
        return FULL_NAME
    elif update.message.video or update.message.animation:
        bio = BytesIO()
        file = update.message.video or update.message.animation
        await file.get_file().download_to_memory(out=bio)
        bio.seek(0)
        user_data[user_id]["videos"].append(bio)
        return CONTENT_VIDEOS
    else:
        return CONTENT_VIDEOS  # ignore other messages

async def handle_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id]["full_name"] = update.message.text
    await update.message.reply_text("Send the celebrity's alias or social media handles (or 'None').")
    return ALIAS

async def handle_alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id]["alias"] = update.message.text
    await update.message.reply_text("Send the celebrity's country of origin.")
    return COUNTRY

async def handle_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id]["country"] = update.message.text
    await update.message.reply_text("Send why the celebrity is famous.")
    return FAME

async def handle_fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id]["fame"] = update.message.text
    await update.message.reply_text("Send celebrity social links. Send /done when finished.")
    return SOCIALS

async def handle_socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if text.lower() == "/done":
        await update.message.reply_text("All information collected! Generating albums...")
        return await finalize(update, context)
    if validate_social_link(text):
        platform = urlparse(text).netloc.split('.')[0].capitalize()
        user_data[user_id]["socials"][platform] = "x"  # placeholder for followers
    return SOCIALS

# -------------------------
# Finalize & send albums
# -------------------------
async def finalize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_data[user_id]

    # Send summary
    await update.message.reply_text(format_summary(data))

    # Assemble albums
    all_photos = [data["face_photo"]] + data["images"]
    albums = split_into_albums(all_photos, max_per_album=10)
    for album in albums:
        media = [InputMediaPhoto(photo) for photo in album]
        await context.bot.send_media_group(chat_id=update.effective_chat.id, media=media)

    # Optionally send videos
    videos = data["videos"]
    video_albums = split_into_albums(videos, max_per_album=10)
    for album in video_albums:
        media = [InputMediaVideo(video) for video in album]
        await context.bot.send_media_group(chat_id=update.effective_chat.id, media=media)

    return ConversationHandler.END

# -------------------------
# Add Conversation Handler
# -------------------------
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start), CommandHandler("restart", restart)],
    states={
        FACE_PHOTO: [MessageHandler(filters.PHOTO, handle_face_photo)],
        CONTENT_IMAGES: [MessageHandler(filters.PHOTO | filters.TEXT, handle_content_images)],
        CONTENT_VIDEOS: [MessageHandler(filters.VIDEO | filters.ANIMATION | filters.TEXT, handle_content_videos)],
        FULL_NAME: [MessageHandler(filters.TEXT, handle_full_name)],
        ALIAS: [MessageHandler(filters.TEXT, handle_alias)],
        COUNTRY: [MessageHandler(filters.TEXT, handle_country)],
        FAME: [MessageHandler(filters.TEXT, handle_fame)],
        SOCIALS: [MessageHandler(filters.TEXT, handle_socials)]
    },
    fallbacks=[CommandHandler("restart", restart)],
)

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(conv_handler)

# -------------------------
# Run Flask with webhook
# -------------------------
async def main():
    await app.bot.set_webhook(WEBHOOK_URL)
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    asyncio.run(main())
