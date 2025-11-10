import asyncio
from quart import Quart, request, jsonify
from telegram import Update, InputMediaPhoto, InputMediaVideo, Bot
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, ConversationHandler
)
import re
from urllib.parse import urlparse

TOKEN = "YOUR_BOT_TOKEN"
WEBHOOK_URL = "https://gatekeepersbot.onrender.com/"  # Replace with your HTTPS URL

app = Quart(__name__)

# Step states
(
    FACE,
    PHOTOS,
    VIDEOS,
    FULLNAME,
    ALIAS,
    COUNTRY,
    FAME,
    SOCIALS,
    DONE,
) = range(9)

# User data store
user_data_store = {}

# Utilities

def split_albums(items):
    """
    Split items into 3 albums evenly, largest last if needed.
    """
    if not items:
        return []
    n = len(items)
    base = n // 3
    extra = n % 3
    splits = [base] * 3
    for i in range(extra):
        splits[i] += 1
    result = []
    idx = 0
    for size in splits:
        if size > 0:
            result.append(items[idx:idx + size])
        idx += size
    return result

def validate_social(url):
    """
    Simple validation for social links.
    """
    try:
        result = urlparse(url)
        if result.scheme not in ("http", "https"):
            return False
        if not result.netloc:
            return False
        return True
    except:
        return False

# Handlers

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id] = {
        "face": None, "photos": [], "videos": [], "fullname": "", "alias": "",
        "country": "", "fame": "", "socials": []
    }
    await update.message.reply_text("Welcome to Gatekeepers Album Maker!\nStep 1: Send a normal face photo of the celebrity.")
    return FACE

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id] = {
        "face": None, "photos": [], "videos": [], "fullname": "", "alias": "",
        "country": "", "fame": "", "socials": []
    }
    await update.message.reply_text("Process restarted. Step 1: Send a normal face photo of the celebrity.")
    return FACE

async def face_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Please send a photo.")
        return FACE
    user_data_store[update.effective_user.id]["face"] = update.message.photo[-1].file_id
    await update.message.reply_text("Face photo received.\nStep 2: Send all pictures you want to post. Send /next when done.")
    return PHOTOS

async def photos_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "/next":
        await update.message.reply_text(f"{len(user_data_store[update.effective_user.id]['photos'])} photos saved.\nStep 3: Send all videos/gifs. Send /next when done.")
        return VIDEOS
    if update.message.photo:
        user_data_store[update.effective_user.id]["photos"].append(update.message.photo[-1].file_id)
    return PHOTOS

async def videos_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "/next":
        await update.message.reply_text(f"{len(user_data_store[update.effective_user.id]['videos'])} videos/gifs saved.\nStep 4: Send the person's full name.")
        return FULLNAME
    if update.message.video or update.message.document:
        file_id = update.message.video.file_id if update.message.video else update.message.document.file_id
        user_data_store[update.effective_user.id]["videos"].append(file_id)
    return VIDEOS

async def fullname_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["fullname"] = update.message.text
    await update.message.reply_text("Step 5: Send alias/social media handles (or '-' if none).")
    return ALIAS

async def alias_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["alias"] = update.message.text
    await update.message.reply_text("Step 6: Send the person's country of origin.")
    return COUNTRY

async def country_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["country"] = update.message.text
    await update.message.reply_text("Step 7: Why is this person famous?")
    return FAME

async def fame_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["fame"] = update.message.text
    await update.message.reply_text("Step 8: Send social media links separated by space.")
    return SOCIALS

async def socials_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    urls = update.message.text.split()
    valid_urls = [url for url in urls if validate_social(url)]
    user_data_store[update.effective_user.id]["socials"] = valid_urls
    await update.message.reply_text("Step 9: Type /done when ready to assemble album and summary.")
    return DONE

async def done_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = user_data_store[update.effective_user.id]

    # Build summary
    summary = (
        f"^^^^^^^^^^^^^^^\n\n"
        f"Name: {data['fullname']}\n"
        f"Alias: {data['alias']}\n"
        f"Country: {data['country']}\n"
        f"Fame: {data['fame']}\n"
        f"Top socials:\n"
    )
    for url in data["socials"]:
        summary += f"{url}\n"
    summary += "\n===============\n"

    await update.message.reply_text(summary)

    # Assemble albums
    all_photos = [data["face"]] + data["photos"]
    albums = split_albums(all_photos)
    bot: Bot = context.bot

    for album in albums:
        media_group = [InputMediaPhoto(media=file_id) for file_id in album]
        await bot.send_media_group(chat_id=update.effective_chat.id, media=media_group)

    await update.message.reply_text("All albums sent. You can restart anytime with /restart.")
    return ConversationHandler.END

# Conversation handler
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        FACE: [MessageHandler(filters.PHOTO, face_handler)],
        PHOTOS: [
            MessageHandler(filters.PHOTO, photos_handler),
            CommandHandler("next", photos_handler),
        ],
        VIDEOS: [
            MessageHandler(filters.VIDEO | filters.Document.ALL, videos_handler),
            CommandHandler("next", videos_handler),
        ],
        FULLNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, fullname_handler)],
        ALIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, alias_handler)],
        COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country_handler)],
        FAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, fame_handler)],
        SOCIALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, socials_handler)],
        DONE: [CommandHandler("done", done_handler)],
    },
    fallbacks=[CommandHandler("restart", restart)],
)

bot_app = ApplicationBuilder().token(TOKEN).build()
bot_app.add_handler(conv_handler)
bot_app.add_handler(CommandHandler("restart", restart))

# Quart webhook endpoint
@app.route("/", methods=["POST"])
async def webhook():
    data = await request.get_json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.update_queue.put(update)
    return jsonify({"status": "ok"})

# Run webhook
async def main():
    # Set Telegram webhook
    await bot_app.bot.set_webhook(WEBHOOK_URL)
    print(f"Webhook set to {WEBHOOK_URL}")
    # Start Quart server
    await app.run_task(host="0.0.0.0", port=10000)

if __name__ == "__main__":
    asyncio.run(main())
