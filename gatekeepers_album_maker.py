import os
import re
from math import ceil
from urllib.parse import urlparse
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)

# Conversation states
FACE, PHOTOS, VIDEOS, NAME, ALIAS, COUNTRY, FAME, SOCIALS, DONE = range(9)
user_data_store = {}

# Helper to split media into evenly sized albums
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

# /start or /restart
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
        await update.message.reply_text("Face photo saved. Now send all **other photos**. Send /done when finished.")
        return PHOTOS
    await update.message.reply_text("Please send a valid face photo.")
    return FACE

# Step 2: Additional photos
async def photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.photo:
        user_data_store[user_id]["photos"].append(update.message.photo[-1].file_id)
    return PHOTOS

async def photos_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Photos saved. Now send **videos or GIFs**. Send /done when finished.")
    return VIDEOS

# Step 3: Videos or GIFs
async def videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.video:
        user_data_store[user_id]["videos"].append(update.message.video.file_id)
    elif update.message.animation:
        user_data_store[user_id]["videos"].append(update.message.animation.file_id)
    return VIDEOS

async def videos_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Videos saved. Now send the celebrity’s **full name**.")
    return NAME

# Step 4–7: Text info
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

# Step 8: Parse ANY social site
async def socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    socials_dict = {}

    # Split input by commas or newlines
    entries = re.split(r'[,\n]', text)
    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue

        parts = entry.split()
        if len(parts) >= 2:
            link = parts[0].strip()
            followers = parts[1].strip()
        else:
            link = parts[0].strip()
            followers = "x"

        # Extract domain name for labeling
        try:
            parsed = urlparse(link)
            domain = parsed.netloc.lower()
            platform = domain.replace("www.", "").split(".")[0].capitalize()
        except Exception:
            platform = "Unknown"

        socials_dict[platform] = (link, followers)

    user_data_store[user_id]["socials"] = socials_dict
    await update.message.reply_text("Socials saved. Send /done to generate albums and summary.")
    return DONE

# Step 9: Final output + albums
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_data_store[user_id]

    all_media = [data["face"]] + data["photos"] + data["videos"]
    albums = split_albums(all_media)

    # Send albums evenly split
    for album in albums:
        media_group = []
        for fid in album:
            if fid == data["face"] or fid in data["photos"]:
                media_group.append(InputMediaPhoto(fid))
            else:
                media_group.append(InputMediaVideo(fid))
        await update.message.reply_media_group(media_group)

    # Format dynamic socials
    socials_text = ""
    for platform, (link, followers) in data["socials"].items():
        socials_text += f"{platform} ({followers}) - {link}\n"

    # Summary message
    summary = f"""^^^^^^^^^^^^^^^

Name: {data['name']}
Alias: {data['alias']}
Country: {data['country']}
Fame: {data['fame']}
Top socials:
{socials_text}
==============="""
    await update.message.reply_text(summary)
    return ConversationHandler.END

# Restart
async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

# Main bot setup
def main():
    bot_token = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(bot_token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler(["start", "restart"], start)],
        states={
            FACE: [MessageHandler(filters.PHOTO, face_photo)],
            PHOTOS: [
                MessageHandler(filters.PHOTO, photos),
                CommandHandler("done", photos_done)
            ],
            VIDEOS: [
                MessageHandler(filters.VIDEO | filters.ANIMATION, videos),
                CommandHandler("done", videos_done)
            ],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
            ALIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, alias)],
            COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country)],
            FAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, fame)],
            SOCIALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, socials)],
            DONE: [CommandHandler("done", done)]
        },
        fallbacks=[CommandHandler("restart", restart)]
    )

    app.add_handler(conv_handler)

    # Webhook setup for Render
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        webhook_url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/"
    )

if __name__ == "__main__":
    main()
