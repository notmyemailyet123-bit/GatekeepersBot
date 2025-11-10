import os
import asyncio
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
)
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler,
    ConversationHandler, CallbackQueryHandler, filters
)
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
URL = os.getenv("WEBHOOK_URL")  # e.g., https://gatekeepersbot.onrender.com/

# Steps
(
    FACE, PICS, VIDEOS,
    NAME, ALIAS, COUNTRY,
    FAME, SOCIALS, DONE
) = range(9)

user_data_dict = {}

# Flask app
flask_app = Flask(__name__)

def split_albums(items, max_per_album=10):
    """Split list into roughly equal albums."""
    n = len(items)
    if n <= max_per_album:
        return [items]
    num_albums = (n + max_per_album - 1) // max_per_album
    avg = n // num_albums
    remainder = n % num_albums
    albums = []
    start = 0
    for i in range(num_albums):
        end = start + avg + (1 if i < remainder else 0)
        albums.append(items[start:end])
        start = end
    return albums

# ---- Handlers ----

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_dict[update.effective_user.id] = {
        "face": None, "pics": [], "videos": [],
        "name": "", "alias": "", "country": "",
        "fame": "", "socials": {}
    }
    await update.message.reply_text(
        "Welcome to Gatekeepers Album Maker!\n"
        "Step 1: Please send a **clear face photo** of the celebrity.",
        parse_mode=ParseMode.MARKDOWN
    )
    return FACE

async def face_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photo_file = await update.message.photo[-1].get_file()
    path = f"temp_{user_id}_face.jpg"
    await photo_file.download_to_drive(path)
    user_data_dict[user_id]["face"] = path
    keyboard = [[InlineKeyboardButton("Next", callback_data="next")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Face photo received.", reply_markup=reply_markup)
    return PICS

async def pics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    media_files = []
    if update.message.photo:
        for photo in update.message.photo:
            file = await photo.get_file()
            path = f"temp_{user_id}_pic_{len(user_data_dict[user_id]['pics'])}.jpg"
            await file.download_to_drive(path)
            user_data_dict[user_id]['pics'].append(path)
    keyboard = [[InlineKeyboardButton("Next", callback_data="next")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Pictures saved. Press Next when done uploading more.", reply_markup=reply_markup)
    return VIDEOS

async def videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.video:
        file = await update.message.video.get_file()
        path = f"temp_{user_id}_video_{len(user_data_dict[user_id]['videos'])}.mp4"
        await file.download_to_drive(path)
        user_data_dict[user_id]['videos'].append(path)
    elif update.message.animation:
        file = await update.message.animation.get_file()
        path = f"temp_{user_id}_video_{len(user_data_dict[user_id]['videos'])}.mp4"
        await file.download_to_drive(path)
        user_data_dict[user_id]['videos'].append(path)
    keyboard = [[InlineKeyboardButton("Next", callback_data="next")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Videos saved. Press Next when done uploading more.", reply_markup=reply_markup)
    return NAME

async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_dict[update.effective_user.id]["name"] = update.message.text
    await update.message.reply_text("Step 5: Send the celebrity's alias or social handles (if any).")
    return ALIAS

async def alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_dict[update.effective_user.id]["alias"] = update.message.text
    await update.message.reply_text("Step 6: Send the celebrity's country of origin.")
    return COUNTRY

async def country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_dict[update.effective_user.id]["country"] = update.message.text
    await update.message.reply_text("Step 7: Why is this person famous?")
    return FAME

async def fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_dict[update.effective_user.id]["fame"] = update.message.text
    await update.message.reply_text("Step 8: Send their social media links.")
    return SOCIALS

async def socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Simple validation: only accept URLs with https
    links = update.message.text.split()
    socials = {}
    for link in links:
        if "youtube.com" in link:
            socials["YouTube"] = link
        elif "instagram.com" in link:
            socials["Instagram"] = link
        elif "tiktok.com" in link:
            socials["TikTok"] = link
    user_data_dict[user_id]["socials"] = socials
    keyboard = [[InlineKeyboardButton("Finish", callback_data="finish")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Press Finish when done.", reply_markup=reply_markup)
    return DONE

async def finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = user_data_dict[user_id]

    # Assemble summary
    summary = (
        f"^^^^^^^^^^^^^^^\n\n"
        f"Name: {escape_markdown(data['name'], version=2)}\n"
        f"Alias: {escape_markdown(data['alias'], version=2)}\n"
        f"Country: {escape_markdown(data['country'], version=2)}\n"
        f"Fame: {escape_markdown(data['fame'], version=2)}\n"
        f"Top socials:\n"
    )
    for platform, link in data['socials'].items():
        summary += f"{platform} - {link}\n"
    summary += "\n==============="

    await query.message.reply_text(summary, parse_mode=ParseMode.MARKDOWN_V2)

    # Prepare media albums
    all_media = [data['face']] + data['pics'] + data['videos']
    albums = split_albums(all_media, max_per_album=10)

    for album in albums:
        media_group = []
        for file_path in album:
            if file_path.endswith(".jpg"):
                media_group.append(InputMediaPhoto(open(file_path, "rb")))
            else:
                media_group.append(InputMediaVideo(open(file_path, "rb")))
        await query.message.reply_media_group(media_group)

    return ConversationHandler.END

async def next_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if context.user_data.get("step") == FACE:
        await query.message.reply_text("Step 2: Send all the pictures you want to add.")
        context.user_data["step"] = PICS
        return PICS
    elif context.user_data.get("step") == PICS:
        await query.message.reply_text("Step 3: Send all the videos or GIFs you want to add.")
        context.user_data["step"] = VIDEOS
        return VIDEOS
    elif context.user_data.get("step") == VIDEOS:
        await query.message.reply_text("Step 4: Send the celebrity's full name.")
        context.user_data["step"] = NAME
        return NAME

# ---- Flask route ----
@flask_app.route("/", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), app.bot)
    asyncio.run(app.update_queue.put(update))
    return "OK"

# ---- Main ----
app = ApplicationBuilder().token(TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        FACE: [MessageHandler(filters.PHOTO, face_photo)],
        PICS: [MessageHandler(filters.PHOTO, pics)],
        VIDEOS: [MessageHandler(filters.VIDEO | filters.ANIMATION, videos)],
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
        ALIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, alias)],
        COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country)],
        FAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, fame)],
        SOCIALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, socials)],
        DONE: [CallbackQueryHandler(finish, pattern="finish")],
    },
    fallbacks=[CommandHandler("restart", start)],
    per_message=False
)

app.add_handler(conv_handler)
app.add_handler(CallbackQueryHandler(next_step, pattern="next"))

# Set webhook automatically
async def set_hook():
    await app.bot.set_webhook(URL)

asyncio.run(set_hook())

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
