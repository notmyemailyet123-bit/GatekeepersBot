import os
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)
from math import ceil

# Steps
FACE, PHOTOS, VIDEOS, NAME, ALIAS, COUNTRY, FAME, SOCIALS, DONE = range(9)

# Data storage for each user
user_data_store = {}

# Helper function to split media evenly
def split_albums(media_list):
    n = len(media_list)
    if n <= 10:
        return [media_list]
    # Determine number of albums
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

# Start / restart command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id] = {
        "face": None, "photos": [], "videos": [],
        "name": "", "alias": "", "country": "",
        "fame": "", "socials": {}
    }
    await update.message.reply_text("Welcome to Gatekeepers Album Maker! Send the celebrity's **face photo** to start.")
    return FACE

# Step 1: Face photo
async def face_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        user_data_store[user_id]["face"] = file_id
        await update.message.reply_text("Face photo saved. Now send all **other photos** you want included. Send /done when finished.")
        return PHOTOS
    await update.message.reply_text("Please send a photo of the celebrity's face.")
    return FACE

# Step 2: Other photos
async def photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        user_data_store[user_id]["photos"].append(file_id)
    return PHOTOS

# Step 2 done
async def photos_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Photos saved. Now send all **videos and GIFs**. Send /done when finished.")
    return VIDEOS

# Step 3: Videos/GIFs
async def videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.video:
        user_data_store[user_id]["videos"].append(update.message.video.file_id)
    elif update.message.animation:
        user_data_store[user_id]["videos"].append(update.message.animation.file_id)
    return VIDEOS

# Step 3 done
async def videos_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Videos/GIFs saved. Send the celebrity's full name.")
    return NAME

# Step 4: Name
async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["name"] = update.message.text
    await update.message.reply_text("Send the celebrity's alias/social media handles (comma-separated if multiple).")
    return ALIAS

# Step 5: Alias
async def alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["alias"] = update.message.text
    await update.message.reply_text("Send the celebrity's country of origin.")
    return COUNTRY

# Step 6: Country
async def country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["country"] = update.message.text
    await update.message.reply_text("Why is the celebrity famous?")
    return FAME

# Step 7: Fame
async def fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data_store[update.effective_user.id]["fame"] = update.message.text
    await update.message.reply_text("Send social media links (Instagram, YouTube, TikTok). Separate with commas.")
    return SOCIALS

# Step 8: Social links
async def socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    links = update.message.text.split(',')
    socials = {"YouTube": ("", ""), "Instagram": ("", ""), "TikTok": ("", "")}
    for link in links:
        link = link.strip()
        if "instagram.com" in link:
            socials["Instagram"] = (link, "x")  # Placeholder x
        elif "youtube.com" in link:
            socials["YouTube"] = (link, "x")
        elif "tiktok.com" in link:
            socials["TikTok"] = (link, "x")
    user_data_store[user_id]["socials"] = socials
    await update.message.reply_text("All information saved. Send /done to generate albums and summary.")
    return DONE

# Step 9/10: Generate albums and summary
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_data_store[user_id]

    # Combine all media with face photo first
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
        await update.message.reply_media_group(media_group)

    # Build summary
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

# /restart command
async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

# Set up the bot application
def main():
    bot_token = os.getenv("BOT_TOKEN")  # Put your token in Render env vars
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
