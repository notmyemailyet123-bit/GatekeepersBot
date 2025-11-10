import os
import math
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, CallbackQueryHandler, ConversationHandler,
    filters
)

# -------------------------------
# Constants for conversation steps
# -------------------------------
(
    FACE_PHOTO, PICTURES, VIDEOS,
    NAME, ALIAS, COUNTRY, FAME,
    SOCIALS, CONFIRM
) = range(9)

# -------------------------------
# Flask app
# -------------------------------
app = Flask(__name__)
BOT_TOKEN = os.environ['BOT_TOKEN']
URL = f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/{BOT_TOKEN}"

# -------------------------------
# Telegram application
# -------------------------------
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

# -------------------------------
# In-memory user storage
# -------------------------------
user_data = {}

# -------------------------------
# Helper functions
# -------------------------------
def create_next_button(text="Next"):
    keyboard = [[InlineKeyboardButton(text, callback_data="next")]]
    return InlineKeyboardMarkup(keyboard)

def split_into_albums(items, face_photo=None):
    # Calculate split sizes
    total = len(items)
    num_albums = math.ceil(total / 10)
    base_size = total // num_albums
    remainder = total % num_albums

    albums = []
    idx = 0
    for i in range(num_albums):
        size = base_size + (1 if i < remainder else 0)
        album = items[idx:idx+size]
        if i == 0 and face_photo:
            album = [face_photo] + album
        albums.append(album)
        idx += size
    return albums

def format_summary(data):
    return f"""^^^^^^^^^^^^^^^

Name: {data.get('name','-')}
Alias: {data.get('alias','-')}
Country: {data.get('country','-')}
Fame: {data.get('fame','-')}
Top socials:
YouTube ({data.get('youtube','-')})
Instagram ({data.get('instagram','-')})
TikTok ({data.get('tiktok','-')})

=============== """

# -------------------------------
# Handlers
# -------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id] = {
        "face": None,
        "pictures": [],
        "videos": [],
        "info": {}
    }
    await update.message.reply_text("Welcome to Gatekeepers Album Maker!\nPlease send a clear face photo of the celebrity.")
    return FACE_PHOTO

# Step 1: Face photo
async def face_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not update.message.photo:
        await update.message.reply_text("Please send a valid photo.")
        return FACE_PHOTO
    file_id = update.message.photo[-1].file_id
    user_data[user_id]["face"] = file_id
    await update.message.reply_text("Face photo received! Now send all the pictures you want to add. Press 'Next' when done.", reply_markup=create_next_button())
    return PICTURES

# Step 2: Pictures
async def pictures(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.text and update.message.text.lower() == "next":
        await update.message.reply_text("Moving to videos step. Send all videos/gifs. Press 'Next' when done.", reply_markup=create_next_button())
        return VIDEOS
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        user_data[user_id]["pictures"].append(file_id)
    return PICTURES

# Step 3: Videos
async def videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.text and update.message.text.lower() == "next":
        await update.message.reply_text("Now, send the celebrity's full name.")
        return NAME
    if update.message.video or update.message.animation:
        file_id = update.message.video.file_id if update.message.video else update.message.animation.file_id
        user_data[user_id]["videos"].append(file_id)
    return VIDEOS

# Step 4-8: Info
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id]["info"]["name"] = update.message.text
    await update.message.reply_text("Send the celebrity's alias/social handles (or '-' if none).")
    return ALIAS

async def get_alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id]["info"]["alias"] = update.message.text
    await update.message.reply_text("Send the celebrity's country of origin.")
    return COUNTRY

async def get_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id]["info"]["country"] = update.message.text
    await update.message.reply_text("Send why the celebrity is famous.")
    return FAME

async def get_fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id]["info"]["fame"] = update.message.text
    await update.message.reply_text("Send the celebrity's socials in format: YouTube followers, Instagram followers, TikTok followers.\nExample: 1000,2000,3000")
    return SOCIALS

async def get_socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    parts = [p.strip() for p in update.message.text.split(",")]
    if len(parts) != 3:
        await update.message.reply_text("Please provide exactly 3 numbers separated by commas.")
        return SOCIALS
    user_data[user_id]["info"]["youtube"] = parts[0]
    user_data[user_id]["info"]["instagram"] = parts[1]
    user_data[user_id]["info"]["tiktok"] = parts[2]

    # Confirm button
    await update.message.reply_text("All done! Press 'Finish' to generate albums and summary.", reply_markup=create_next_button("Finish"))
    return CONFIRM

# Step 9: Finish
async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_data[user_id]

    # Assemble summary
    summary_text = format_summary(data["info"])
    await update.message.reply_text(summary_text)

    # Prepare albums
    all_media = data["pictures"] + data["videos"]
    albums = split_into_albums(all_media, face_photo=data["face"])

    for album in albums:
        media_group = []
        for file_id in album:
            # Decide photo/video
            media_group.append(InputMediaPhoto(file_id) if file_id in data["pictures"] or file_id==data["face"] else InputMediaVideo(file_id))
        await context.bot.send_media_group(chat_id=update.effective_chat.id, media=media_group)

    await update.message.reply_text("Process complete! You can /start again anytime.")
    return ConversationHandler.END

# Restart at any time
async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

# -------------------------------
# Conversation Handler
# -------------------------------
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        FACE_PHOTO: [MessageHandler(filters.PHOTO, face_photo)],
        PICTURES: [
            MessageHandler(filters.PHOTO, pictures),
            MessageHandler(filters.TEXT & ~filters.COMMAND, pictures)
        ],
        VIDEOS: [
            MessageHandler(filters.VIDEO | filters.ANIMATION, videos),
            MessageHandler(filters.TEXT & ~filters.COMMAND, videos)
        ],
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
        ALIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_alias)],
        COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_country)],
        FAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fame)],
        SOCIALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_socials)],
        CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, finish)]
    },
    fallbacks=[CommandHandler('restart', restart)]
)

telegram_app.add_handler(conv_handler)

# -------------------------------
# Flask webhook route
# -------------------------------
@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    telegram_app.update_queue.put(update)
    return "OK"

# -------------------------------
# Run Flask app
# -------------------------------
if __name__ == "__main__":
    telegram_app.bot.set_webhook(URL)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
