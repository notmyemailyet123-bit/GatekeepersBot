import os
import asyncio
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from flask import Flask, request

# ----------------------------
# Constants for conversation
# ----------------------------
(
    FACE,
    PHOTOS,
    VIDEOS,
    FULL_NAME,
    ALIAS,
    COUNTRY,
    FAME,
    SOCIALS,
    CONFIRM,
) = range(9)

PORT = int(os.environ.get("PORT", 10000))
BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBHOOK_URL = os.environ["WEBHOOK_URL"]

# ----------------------------
# Storage for user sessions
# ----------------------------
user_data_store = {}

# ----------------------------
# Telegram Handlers
# ----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data_store[chat_id] = {
        "face": None,
        "photos": [],
        "videos": [],
        "full_name": "",
        "alias": "",
        "country": "",
        "fame": "",
        "socials": {},
    }
    await update.message.reply_text("Welcome! Step 1: Send a clear face picture of the celebrity.")
    return FACE

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

# Step 1: face photo
async def face(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    photo = update.message.photo[-1]
    user_data_store[chat_id]["face"] = photo.file_id
    await update.message.reply_text("Got it! Step 2: Send all pictures you want to include. Send /next when done.")
    return PHOTOS

# Step 2: multiple photos
async def photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.message.text and update.message.text.lower() == "/next":
        await update.message.reply_text(f"Saved {len(user_data_store[chat_id]['photos'])} photos. Step 3: Send all videos/GIFs. Send /next when done.")
        return VIDEOS
    if update.message.photo:
        user_data_store[chat_id]["photos"].append(update.message.photo[-1].file_id)
    return PHOTOS

# Step 3: videos/gifs
async def videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.message.text and update.message.text.lower() == "/next":
        await update.message.reply_text("Step 4: Send the celebrity's full name.")
        return FULL_NAME
    if update.message.video:
        user_data_store[chat_id]["videos"].append(update.message.video.file_id)
    if update.message.document and update.message.document.mime_type.startswith("video"):
        user_data_store[chat_id]["videos"].append(update.message.document.file_id)
    return VIDEOS

# Step 4: full name
async def full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data_store[chat_id]["full_name"] = update.message.text
    await update.message.reply_text("Step 5: Send the celebrity's alias/social handles.")
    return ALIAS

# Step 5: alias
async def alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data_store[chat_id]["alias"] = update.message.text
    await update.message.reply_text("Step 6: Send the celebrity's country of origin.")
    return COUNTRY

# Step 6: country
async def country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data_store[chat_id]["country"] = update.message.text
    await update.message.reply_text("Step 7: Why is this person famous?")
    return FAME

# Step 7: fame
async def fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data_store[chat_id]["fame"] = update.message.text
    await update.message.reply_text("Step 8: Send the celebrity's social links (YouTube, Instagram, TikTok). One per message. Send /done when finished.")
    return SOCIALS

# Step 8: socials
async def socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    if text.lower() == "/done":
        await update.message.reply_text("All info received. Step 9: Confirm with /confirm")
        return CONFIRM
    # basic validation
    if "youtube.com" in text:
        user_data_store[chat_id]["socials"]["YouTube"] = text
    elif "instagram.com" in text:
        user_data_store[chat_id]["socials"]["Instagram"] = text
    elif "tiktok.com" in text:
        user_data_store[chat_id]["socials"]["TikTok"] = text
    else:
        await update.message.reply_text("Unrecognized link, please send a valid YouTube, Instagram, or TikTok URL.")
    return SOCIALS

# Step 9/10: final confirmation & album
async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = user_data_store[chat_id]

    # Summary
    summary = f"""
^^^^^^^^^^^^^^^

Name: {data['full_name']}
Alias: {data['alias']}
Country: {data['country']}
Fame: {data['fame']}
Top socials:
YouTube - {data['socials'].get('YouTube','-')}
Instagram - {data['socials'].get('Instagram','-')}
TikTok - {data['socials'].get('TikTok','-')}
===============
"""
    await update.message.reply_text(summary)

    # Assemble albums
    all_media = data["photos"] + data["videos"]
    albums = []
    total = len(all_media)
    face = data["face"]
    num_albums = (total + 9) // 10 or 1
    chunk_size = (total + num_albums - 1) // num_albums

    for i in range(0, total, chunk_size):
        chunk = all_media[i:i+chunk_size]
        media_group = [InputMediaPhoto(face)]
        for file_id in chunk:
            if file_id in data["photos"]:
                media_group.append(InputMediaPhoto(file_id))
            else:
                media_group.append(InputMediaVideo(file_id))
        await context.bot.send_media_group(chat_id=chat_id, media=media_group)

    await update.message.reply_text("All albums sent! You can /restart anytime.")
    return ConversationHandler.END

# ----------------------------
# Flask Webhook Setup
# ----------------------------
flask_app = Flask(__name__)
app = ApplicationBuilder().token(BOT_TOKEN).build()

# Add handlers
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        FACE: [MessageHandler(filters.PHOTO, face)],
        PHOTOS: [MessageHandler(filters.PHOTO | filters.TEXT, photos)],
        VIDEOS: [MessageHandler(filters.VIDEO | filters.Document.VIDEO | filters.TEXT, videos)],
        FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, full_name)],
        ALIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, alias)],
        COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country)],
        FAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, fame)],
        SOCIALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, socials)],
        CONFIRM: [CommandHandler("confirm", confirm)],
    },
    fallbacks=[CommandHandler("restart", restart)],
)

app.add_handler(conv_handler)
app.add_handler(CommandHandler("restart", restart))

@flask_app.route("/", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), app.bot)
    app.update_queue.put_nowait(update)
    return "OK"

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=PORT)
