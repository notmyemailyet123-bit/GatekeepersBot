import os
import re
from math import ceil
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)

# Conversation steps
FACE, PHOTOS, VIDEOS, NAME, ALIAS, COUNTRY, FAME, SOCIALS, DONE = range(9)
user_data_store = {}

# Split albums evenly if >10 items
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

# Start or restart bot
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

# Step 2: Other photos
async def photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.photo:
        user_data_store[user_id]["photos"].append(update.message.photo[-1].file_id)
    return PHOTOS

async def photos_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Photos saved. Now send **videos or GIFs**. Send /done when finished.")
    return VIDEOS

# Step 3: Videos
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

# Step 4: Name
async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["name"] = update.message.text
    await update.message.reply_text("Send the celebrity’s **aliases or handles** (comma-separated).")
    return ALIAS

# Step 5: Alias
async def alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["alias"] = update.message.text
    await update.message.reply_text("Send the celebrity’s **country of origin**.")
    return COUNTRY

# Step 6: Country
async def country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["country"] = update.message.text
    await update.message.reply_text("What is the celebrity famous for?")
    return FAME

# Step 7: Fame
async def fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["fame"] = update.message.text
    await update.message.reply_text(
        "Now send **social media links** with follower counts.\n\n"
        "Example:\nhttps://www.instagram.com/nicholasgalitzine 5.7M, "
        "https://youtube.com/@nicholasgalitzineofficial 118K, "
        "https://www.tiktok.com/@nicholasgalitzine 3.1M"
    )
    return SOCIALS

# Step 8: Social links + follower parsing
async def socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    socials = {"YouTube": ("", ""), "Instagram": ("", ""), "TikTok": ("", "")}

    # Split by comma
    for entry in text.split(','):
        entry = entry.strip()
        # Regex to match follower count (like 5.7M or 118K)
        match = re.search(r'([\d\.]+[MK]?)', entry)
        followers = match.group(1) if match else "x"

        if "instagram.com" in entry:
            socials["Instagram"] = (entry.split()[0], followers)
        elif "youtube.com" in entry:
            socials["YouTube"] = (entry.split()[0], followers)
        elif "tiktok.com" in entry:
            socials["TikTok"] = (entry.split()[0], followers)

    user_data_store[user_id]["socials"] = socials
    await update.message.reply_text("All info saved. Send /done to generate albums and summary.")
    return DONE

# Step 9: Generate albums and summary
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_data_store[user_id]

    all_media = [data["face"]] + data["photos"] + data["videos"]
    albums = split_albums(all_media)

    for album in albums:
        media_group = []
        for fid in album:
            if fid == data["face"] or fid in data["photos"]:
                media_group.append(InputMediaPhoto(fid))
            else:
                media_group.append(InputMediaVideo(fid))
        await update.message.reply_media_group(media_group)

    s = f"""^^^^^^^^^^^^^^^

Name: {data['name']}
Alias: {data['alias']}
Country: {data['country']}
Fame: {data['fame']}
Top socials:
YouTube ({data['socials']['YouTube'][1]}) - {data['socials']['YouTube'][0]}
Instagram ({data['socials']['Instagram'][1]}) - {data['socials']['Instagram'][0]}
TikTok ({data['socials']['TikTok'][1]}) - {data['socials']['TikTok'][0]}

==============="""
    await update.message.reply_text(s)
    return ConversationHandler.END

# Restart
async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

# Main function
def main():
    bot_token = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(bot_token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler(['start', 'restart'], start)],
        states={
            FACE: [MessageHandler(filters.PHOTO, face_photo)],
            PHOTOS: [
                MessageHandler(filters.PHOTO, photos),
                CommandHandler('done', photos_done)
            ],
            VIDEOS: [
                MessageHandler(filters.VIDEO | filters.ANIMATION, videos),
                CommandHandler('done', videos_done)
            ],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
            ALIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, alias)],
            COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country)],
            FAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, fame)],
            SOCIALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, socials)],
            DONE: [CommandHandler('done', done)]
        },
        fallbacks=[CommandHandler('restart', restart)]
    )

    app.add_handler(conv_handler)
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        webhook_url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/"
    )

if __name__ == "__main__":
    main()
