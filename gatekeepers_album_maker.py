import os
import re
from math import ceil
from urllib.parse import urlparse
from telegram import (
    Update, InputMediaPhoto, InputMediaVideo,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes, ConversationHandler
)

# Conversation states
FACE, PHOTOS, VIDEOS, NAME, ALIAS, COUNTRY, FAME, SOCIALS, DONE = range(9)
user_data_store = {}

# Split media into even albums
def split_albums(media_list):
    n = len(media_list)
    if n <= 10:
        return [media_list]
    num_albums = ceil(n / 10)
    per_album = n // num_albums
    remainder = n % num_albums
    albums = []
    start = 0
    for i in range(num_albums):
        end = start + per_album + (1 if i < remainder else 0)
        albums.append(media_list[start:end])
        start = end
    return albums

# Start or restart
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id] = {
        "face": None, "photos": [], "videos": [],
        "name": "", "alias": "", "country": "",
        "fame": "", "socials": {}
    }
    await update.message.reply_text("Welcome to Gatekeepers Album Maker! Send the celebrity’s **face photo** to start.")
    return FACE

# Step 1: Face photo
async def face_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.photo:
        user_data_store[user_id]["face"] = update.message.photo[-1].file_id
        keyboard = [[InlineKeyboardButton("Next ➡️", callback_data="done_photos")]]
        await update.message.reply_text("Face photo saved. Now send all **other photos**, then tap 'Next' when finished.", reply_markup=InlineKeyboardMarkup(keyboard))
        return PHOTOS
    await update.message.reply_text("Please send a valid face photo.")
    return FACE

# Step 2: Additional photos
async def photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        user_data_store[update.effective_user.id]["photos"].append(update.message.photo[-1].file_id)
    return PHOTOS

async def done_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("Next ➡️", callback_data="done_videos")]]
    await query.edit_message_text("Photos saved. Now send **videos or GIFs**, then tap 'Next' when finished.", reply_markup=InlineKeyboardMarkup(keyboard))
    return VIDEOS

# Step 3: Videos
async def videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.video:
        user_data_store[user_id]["videos"].append(update.message.video.file_id)
    elif update.message.animation:
        user_data_store[user_id]["videos"].append(update.message.animation.file_id)
    return VIDEOS

async def done_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Videos saved. Now send the celebrity’s **full name**.")
    return NAME

# Step 4–8: Text info
async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["name"] = update.message.text
    await update.message.reply_text("Send the celebrity’s **aliases or handles** (comma-separated).")
    return ALIAS

async def alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["alias"] = update.message.text
    await update.message.reply_text("Send the celebrity’s **country of origin**.")
    return COUNTRY

async def country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["country"] = update.message.text
    await update.message.reply_text("What is the celebrity famous for?")
    return FAME

async def fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["fame"] = update.message.text
    await update.message.reply_text(
        "Now send **social media links** with follower counts.\n\n"
        "Example:\n"
        "https://www.instagram.com/example 5.7M,\n"
        "https://youtube.com/@example 118K,\n"
        "https://www.tiktok.com/@example 3.1M,\n"
        "https://twitter.com/example 420K"
    )
    return SOCIALS

# Step 9: Parse socials automatically
async def socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    socials_dict = {}

    entries = re.split(r'[,\n]', text)
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split()
        if len(parts) >= 2:
            link, followers = parts[0].strip(), parts[1].strip()
        else:
            link, followers = parts[0].strip(), "x"
        try:
            parsed = urlparse(link)
            domain = parsed.netloc.lower()
            platform = domain.replace("www.", "").split(".")[0].capitalize()
        except Exception:
            platform = "Unknown"
        socials_dict[platform] = (link, followers)

    user_data_store[user_id]["socials"] = socials_dict
    keyboard = [[InlineKeyboardButton("Done ✅", callback_data="finalize")]]
    await update.message.reply_text("Socials saved. Tap **Done ✅** to generate albums and summary.", reply_markup=InlineKeyboardMarkup(keyboard))
    return DONE

# Step 10: Finalize
async def finalize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = user_data_store[user_id]
    all_media = [data["face"]] + data["photos"] + data["videos"]
    albums = split_albums(all_media)

    # Send albums
    for album in albums:
        media_group = []
        for fid in album:
            if fid == data["face"] or fid in data["photos"]:
                media_group.append(InputMediaPhoto(fid))
            else:
                media_group.append(InputMediaVideo(fid))
        await query.message.reply_media_group(media_group)

    # Prepare socials
    socials_text = ""
    for platform, (link, followers) in sorted(data["socials"].items()):
        socials_text += f"{platform} ({followers}) - {link}\n"

    summary = f"""^^^^^^^^^^^^^^^

Name: {data['name']}
Alias: {data['alias']}
Country: {data['country']}
Fame: {data['fame']}
Top socials:
{socials_text}
==============="""

    # Ask to restart
    keyboard = [
        [InlineKeyboardButton("Restart 🔁", callback_data="restart"),
         InlineKeyboardButton("Exit 🚪", callback_data="exit")]
    ]
    await query.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# Restart button callback
async def restart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Restarting bot...")
    return await start(update, context)

# Exit button callback
async def exit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Thanks for using Gatekeepers Album Maker! 👋")
    return ConversationHandler.END

# Main app
def main():
    bot_token = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(bot_token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler(["start", "restart"], start)],
        states={
            FACE: [MessageHandler(filters.PHOTO, face_photo)],
            PHOTOS: [
                MessageHandler(filters.PHOTO, photos),
                CallbackQueryHandler(done_photos, pattern="^done_photos$")
            ],
            VIDEOS: [
                MessageHandler(filters.VIDEO | filters.ANIMATION, videos),
                CallbackQueryHandler(done_videos, pattern="^done_videos$")
            ],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
            ALIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, alias)],
            COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country)],
            FAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, fame)],
            SOCIALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, socials)],
            DONE: [CallbackQueryHandler(finalize, pattern="^finalize$")]
        },
        fallbacks=[
            CommandHandler("restart", start),
            CallbackQueryHandler(restart_callback, pattern="^restart$"),
            CallbackQueryHandler(exit_callback, pattern="^exit$")
        ]
    )

    app.add_handler(conv_handler)
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        webhook_url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/"
    )

if __name__ == "__main__":
    main()
