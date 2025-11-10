import os
import math
import logging
from flask import Flask, request
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask app
flask_app = Flask(__name__)

# Telegram bot token and webhook URL
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # e.g., https://gatekeepersbot.onrender.com/

# Conversation states
(
    FACE, PHOTOS, VIDEOS, NAME, ALIAS, COUNTRY, FAME, SOCIALS, DONE
) = range(9)

# Temporary storage
user_data_store = {}

# --- Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data_store[chat_id] = {
        "face": None,
        "photos": [],
        "videos": [],
        "name": None,
        "alias": None,
        "country": None,
        "fame": None,
        "socials": {}
    }
    await update.message.reply_text("Send a normal face picture of the celebrity to start.")
    return FACE

async def face(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.message.photo:
        user_data_store[chat_id]["face"] = update.message.photo[-1].file_id
        await update.message.reply_text(
            "Great! Now send all other pictures you want to include. Send 'done' when finished."
        )
        return PHOTOS
    await update.message.reply_text("Please send a valid photo.")
    return FACE

async def photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    if text and text.lower() == "done":
        await update.message.reply_text(
            "Photos saved! Now send all videos or GIFs. Send 'done' when finished."
        )
        return VIDEOS

    if update.message.photo:
        user_data_store[chat_id]["photos"].append(update.message.photo[-1].file_id)
    return PHOTOS

async def videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    if text and text.lower() == "done":
        await update.message.reply_text("Videos saved! Now send the celebrity's full name.")
        return NAME

    if update.message.video:
        user_data_store[chat_id]["videos"].append(update.message.video.file_id)
    if update.message.animation:  # GIFs
        user_data_store[chat_id]["videos"].append(update.message.animation.file_id)
    return VIDEOS

async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data_store[chat_id]["name"] = update.message.text
    await update.message.reply_text("Send the alias or social media handles (if any).")
    return ALIAS

async def alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data_store[chat_id]["alias"] = update.message.text
    await update.message.reply_text("Send the country of origin.")
    return COUNTRY

async def country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data_store[chat_id]["country"] = update.message.text
    await update.message.reply_text("Why is this person famous?")
    return FAME

async def fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data_store[chat_id]["fame"] = update.message.text
    await update.message.reply_text(
        "Send celebrity's social links (YouTube, Instagram, TikTok) in one message, separated by commas."
    )
    return SOCIALS

async def socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    socials = {}
    for link in text.split(","):
        link = link.strip()
        if "youtube.com" in link:
            socials["YouTube"] = f"{link} (x)"
        elif "instagram.com" in link:
            socials["Instagram"] = f"{link} (x)"
        elif "tiktok.com" in link:
            socials["TikTok"] = f"{link} (x)"
    user_data_store[chat_id]["socials"] = socials
    await update.message.reply_text("All done! Send 'done' to generate the album and summary.")
    return DONE

# Helper to split list into N nearly equal parts
def split_list_evenly(lst, n):
    k, m = divmod(len(lst), n)
    return [lst[i*k + min(i, m):(i+1)*k + min(i+1, m)] for i in range(n)]

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = user_data_store[chat_id]

    # Generate summary
    summary = f"""^^^^^^^^^^^^^^^

Name: {data['name']}
Alias: {data['alias']}
Country: {data['country']}
Fame: {data['fame']}
Top socials:
YouTube {data['socials'].get('YouTube','-')}
Instagram {data['socials'].get('Instagram','-')}
TikTok {data['socials'].get('TikTok','-')}

==============="""
    await update.message.reply_text(summary)

    # Prepare all photos
    all_photos = [data['face']] + data['photos']
    num_photos = len(all_photos)
    num_albums = math.ceil(num_photos / 10)  # Target 10 max per album
    albums = split_list_evenly(all_photos, num_albums)

    # Send albums
    for album in albums:
        media = [InputMediaPhoto(media=file_id) for file_id in album]
        await context.bot.send_media_group(chat_id=chat_id, media=media)

    # Send videos
    for vid_id in data['videos']:
        await context.bot.send_video(chat_id=chat_id, video=vid_id)

    await update.message.reply_text("Process complete! You can /restart anytime.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Process cancelled. You can /start to restart anytime.")
    return ConversationHandler.END

# --- Conversation Handler ---
conv_handler = ConversationHandler(
    entry_points=[CommandHandler(['start', 'restart'], start)],
    states={
        FACE: [MessageHandler(filters.PHOTO, face)],
        PHOTOS: [MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, photos)],
        VIDEOS: [MessageHandler(filters.VIDEO | filters.ANIMATION | (filters.TEXT & ~filters.COMMAND), videos)],
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
        ALIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, alias)],
        COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country)],
        FAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, fame)],
        SOCIALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, socials)],
        DONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, done)],
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_message=False
)

# --- Telegram app ---
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(conv_handler)

# --- Webhook endpoint ---
@flask_app.route('/', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), app.bot)
    app.update_queue.put(update)
    return "ok"

# --- Run Flask with webhook setup ---
if __name__ == '__main__':
    import asyncio
    asyncio.run(app.initialize())
    # Automatically set webhook
    asyncio.run(app.bot.set_webhook(WEBHOOK_URL))
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
