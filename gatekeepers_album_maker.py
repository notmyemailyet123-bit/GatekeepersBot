import os
import math
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ConversationHandler

# Environment variables
TOKEN = os.environ.get("BOT_TOKEN")
URL = os.environ.get("URL")  # Webhook URL, e.g., https://yourapp.onrender.com

# Steps
FACE, PICTURES, VIDEOS, NAME, ALIAS, COUNTRY, FAME, SOCIALS, DONE = range(9)

# In-memory user data
user_data = {}

# Helper to create Next button
def create_next_button(text="Next"):
    keyboard = [[InlineKeyboardButton(text, callback_data="next")]]
    return InlineKeyboardMarkup(keyboard)

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id] = {
        "face": None,
        "pictures": [],
        "videos": [],
        "name": "",
        "alias": "",
        "country": "",
        "fame": "",
        "socials": {}
    }
    await update.message.reply_text(
        "Welcome! Step 1: Please send a clear face picture of the celebrity."
    )
    return FACE

# Handle face photo
async def face(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.photo:
        user_data[user_id]["face"] = update.message.photo[-1].file_id
        await update.message.reply_text(
            "Face photo received. Step 2: Send all pictures you want to post. Press 'Next' when done.",
            reply_markup=create_next_button()
        )
        return PICTURES
    await update.message.reply_text("Please send a valid photo.")
    return FACE

# Handle pictures step
async def pictures(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.text and update.message.text.lower() == "next":
        await update.message.reply_text(
            "Step 3: Send all videos/gifs. Press 'Next' when done.",
            reply_markup=create_next_button()
        )
        return VIDEOS
    if update.message.photo:
        user_data[user_id]["pictures"].append(update.message.photo[-1].file_id)
    return PICTURES

# Handle videos/gifs step
async def videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.text and update.message.text.lower() == "next":
        await update.message.reply_text("Step 4: Send the celebrity's full name.")
        return NAME
    if update.message.video:
        user_data[user_id]["videos"].append(update.message.video.file_id)
    elif update.message.document:
        user_data[user_id]["videos"].append(update.message.document.file_id)
    return VIDEOS

# Text input handlers
async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.effective_user.id]["name"] = update.message.text
    await update.message.reply_text("Step 5: Send the alias/social media handles (or type 'None').")
    return ALIAS

async def alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.effective_user.id]["alias"] = update.message.text
    await update.message.reply_text("Step 6: Send the celebrity's country of origin.")
    return COUNTRY

async def country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.effective_user.id]["country"] = update.message.text
    await update.message.reply_text("Step 7: Why is this person famous?")
    return FAME

async def fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.effective_user.id]["fame"] = update.message.text
    await update.message.reply_text("Step 8: Send social media links (YouTube, Instagram, TikTok).")
    return SOCIALS

# Handle social links
async def socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    for platform in ["youtube", "instagram", "tiktok"]:
        if platform in text.lower():
            user_data[user_id]["socials"][platform] = text
    await update.message.reply_text("All info received! Press 'Next' to finish.", reply_markup=create_next_button())
    return DONE

# Split items evenly across albums
def split_evenly(items, max_per_album=10):
    total = len(items)
    n_albums = math.ceil(total / max_per_album)
    base_size = total // n_albums
    remainder = total % n_albums
    splits = []
    start = 0
    for i in range(n_albums):
        extra = 1 if i < remainder else 0
        end = start + base_size + extra
        splits.append(items[start:end])
        start = end
    return splits

# Final step: assemble albums and send info
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_data[user_id]

    # Create media items list
    media_items = [data["face"]] + data["pictures"] + data["videos"]
    albums = split_evenly(media_items, max_per_album=10)

    for i, album in enumerate(albums):
        media_group = []
        for file_id in album:
            if file_id == data["face"] or file_id in data["pictures"]:
                media_group.append(InputMediaPhoto(file_id))
            else:
                media_group.append(InputMediaVideo(file_id))
        await context.bot.send_media_group(chat_id=user_id, media=media_group)

    # Send summary info
    summary = f"""
^^^^^^^^^^^^^^^

Name: {data['name']}
Alias: {data['alias']}
Country: {data['country']}
Fame: {data['fame']}
Top socials: 
YouTube - {data['socials'].get('youtube', 'N/A')}
Instagram - {data['socials'].get('instagram', 'N/A')}
TikTok - {data['socials'].get('tiktok', 'N/A')}

===============
"""
    await context.bot.send_message(chat_id=user_id, text=summary)
    return ConversationHandler.END

# Restart handler
async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

# CallbackQuery for buttons
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    step = context.user_data.get("current_step", PICTURES)
    if step == PICTURES:
        return await videos(update, context)
    if step == VIDEOS:
        return await name(update, context)
    if step == DONE:
        return await done(update, context)
    return step

# ConversationHandler
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        FACE: [MessageHandler(filters.PHOTO, face)],
        PICTURES: [
            MessageHandler(filters.PHOTO | filters.TEXT, pictures),
            CallbackQueryHandler(button)
        ],
        VIDEOS: [
            MessageHandler(filters.VIDEO | filters.Document.ALL | filters.TEXT, videos),
            CallbackQueryHandler(button)
        ],
        NAME: [MessageHandler(filters.TEXT, name)],
        ALIAS: [MessageHandler(filters.TEXT, alias)],
        COUNTRY: [MessageHandler(filters.TEXT, country)],
        FAME: [MessageHandler(filters.TEXT, fame)],
        SOCIALS: [MessageHandler(filters.TEXT, socials)],
        DONE: [CallbackQueryHandler(button)]
    },
    fallbacks=[CommandHandler("restart", restart)]
)

# Build application
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(conv_handler)

# Flask webhook
from flask import Flask, request
flask_app = Flask(__name__)

@flask_app.route("/", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), app.bot)
    asyncio.run(app.update_queue.put(update))
    return "OK"

if __name__ == "__main__":
    async def main():
        await app.bot.set_webhook(URL)
        flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
    asyncio.run(main())
