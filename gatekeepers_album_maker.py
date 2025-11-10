import os
import re
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# ---- Bot states ----
FACE, PHOTOS, VIDEOS, NAME, ALIAS, COUNTRY, FAME, SOCIALS, DONE = range(9)

# ---- Temporary storage per user ----
user_data_store = {}

# ---- Helper functions ----
def split_albums(media_list, face_photo):
    """Split list into Telegram albums (~10 per album), starting with face photo."""
    albums = []
    total = len(media_list)
    if total == 0:
        return [[face_photo]]
    chunk_size = max(1, total // ((total // 10) + 1))
    chunks = [media_list[i:i+chunk_size] for i in range(0, total, chunk_size)]
    for chunk in chunks:
        albums.append([face_photo] + chunk)
    return albums

def parse_social_link(link):
    """Identify social media site and follower count if in the link."""
    social_sites = ["youtube", "instagram", "tiktok"]
    site = None
    followers = None
    for s in social_sites:
        if s in link.lower():
            site = s.capitalize()
            break
    # Look for a follower count in parentheses at end of link
    match = re.search(r'\((\d+)\)$', link)
    if match:
        followers = match.group(1)
        link = re.sub(r'\(\d+\)$', '', link).strip()
    return site, link, followers

# ---- Handlers ----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id] = {
        "face": None,
        "photos": [],
        "videos": [],
        "name": "",
        "alias": "",
        "country": "",
        "fame": "",
        "socials": {}
    }
    await update.message.reply_text("Send a normal face picture of the celebrity.")
    return FACE

async def face(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        user_data_store[user_id]["face"] = file.file_id
        await update.message.reply_text("Now send all pictures you want to post. Send 'Done' when finished.")
        return PHOTOS
    else:
        await update.message.reply_text("Please send a photo of the celebrity's face.")
        return FACE

async def photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if text and text.lower() == "done":
        await update.message.reply_text("Photos saved. Now send all videos and GIFs you want to add. Send 'Done' when finished.")
        return VIDEOS
    elif update.message.photo:
        file = await update.message.photo[-1].get_file()
        user_data_store[user_id]["photos"].append(file.file_id)
    return PHOTOS

async def videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if text and text.lower() == "done":
        await update.message.reply_text("Videos saved. Send the celebrity's full name.")
        return NAME
    elif update.message.video or update.message.animation:
        file_id = update.message.video.file_id if update.message.video else update.message.animation.file_id
        user_data_store[user_id]["videos"].append(file_id)
    return VIDEOS

async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id]["name"] = update.message.text
    await update.message.reply_text("Send the celebrity's alias/social media handles (or '-' if none).")
    return ALIAS

async def alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id]["alias"] = update.message.text
    await update.message.reply_text("Send the celebrity's country of origin.")
    return COUNTRY

async def country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id]["country"] = update.message.text
    await update.message.reply_text("Send why the celebrity is famous.")
    return FAME

async def fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id]["fame"] = update.message.text
    await update.message.reply_text(
        "Send celebrity's social media links (YouTube, Instagram, TikTok) one at a time. Send 'Done' when finished."
    )
    return SOCIALS

async def socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if text.lower() == "done":
        await update.message.reply_text("All done! Compiling album...")
        return await compile_album(update, context)
    else:
        site, link, followers = parse_social_link(text)
        if site:
            user_data_store[user_id]["socials"][site] = (link, followers)
        return SOCIALS

async def compile_album(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_data_store[user_id]
    face = data["face"]
    photos = data["photos"]
    videos = data["videos"]

    # Prepare albums
    albums = []
    media_list = photos + videos
    albums = split_albums(media_list, face)

    # Send albums
    for album in albums:
        media_group = []
        for f in album:
            if f in photos or f == face:
                media_group.append(InputMediaPhoto(f))
            elif f in videos:
                media_group.append(InputMediaVideo(f))
        await update.message.reply_media_group(media_group)

    # Prepare summary
    summary = f"^^^^^^^^^^^^^^^\n\nName: {data['name']}\nAlias: {data['alias']}\nCountry: {data['country']}\nFame: {data['fame']}\nTop socials:"
    for site, (link, followers) in data["socials"].items():
        count = f"({followers})" if followers else ""
        summary += f"\n{site} {count} - {link}"
    summary += "\n\n==============="
    await update.message.reply_text(summary)

    return ConversationHandler.END

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

# ---- Setup bot ----
app = ApplicationBuilder().token("YOUR_BOT_TOKEN_HERE").build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        FACE: [MessageHandler(filters.PHOTO, face)],
        PHOTOS: [MessageHandler(filters.PHOTO | filters.TEXT & ~filters.COMMAND, photos)],
        VIDEOS: [MessageHandler(filters.VIDEO | filters.ANIMATION | (filters.TEXT & ~filters.COMMAND), videos)],
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
        ALIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, alias)],
        COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country)],
        FAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, fame)],
        SOCIALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, socials)],
    },
    fallbacks=[CommandHandler('restart', restart)]
)

app.add_handler(conv_handler)

# ---- Dummy server for Render ----
from flask import Flask as FApp
from threading import Thread

dummy_server = FApp(__name__)

@dummy_server.route("/")
def home():
    return "Bot is running!"

def run_dummy():
    port = int(os.environ.get("PORT", 10000))
    dummy_server.run(host="0.0.0.0", port=port)

Thread(target=run_dummy).start()

# ---- Start bot ----
app.run_polling()
