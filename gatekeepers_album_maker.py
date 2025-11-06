import logging
import os
import asyncio
from pathlib import Path
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters
)
from telegram.error import TimedOut, NetworkError, BadRequest

# ========== CONFIG ==========
BOT_TOKEN = "8302726230:AAGL6A89q7VfsQO5ViQKstGsAntL3f5bdRU"  # Replace this with your real token
DATA_DIR = Path("user_data")
DATA_DIR.mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO)

# ========== STATES ==========
FACE, PHOTOS, VIDEOS, NAME, ALIAS, COUNTRY, FAME, SOCIALS, CONFIRM = range(9)
user_data = {}

# ========== HELPERS ==========

def split_evenly(items, max_per_group):
    """Split items into groups that stay close in size and distribute the remainder fairly."""
    if not items:
        return []
    n = len(items)
    num_groups = (n + max_per_group - 1) // max_per_group
    base_size = n // num_groups
    remainder = n % num_groups

    groups = []
    start = 0
    for i in range(num_groups):
        size = base_size + (1 if i < remainder else 0)
        groups.append(items[start:start + size])
        start += size
    return groups

def parse_social_block(text):
    socials = {"youtube": "", "instagram": "", "tiktok": ""}
    lines = text.strip().splitlines()
    for line in lines:
        if "youtube" in line.lower():
            socials["youtube"] = line.strip()
        elif "instagram" in line.lower():
            socials["instagram"] = line.strip()
        elif "tiktok" in line.lower():
            socials["tiktok"] = line.strip()
    return socials

def parse_link_followers(entry):
    parts = entry.split()
    if len(parts) > 1:
        return parts[0], parts[-1]
    elif parts:
        return parts[0], "unknown"
    else:
        return "", "unknown"

def format_social(name, entry):
    if not entry:
        return f"{name} (  -  ) - "
    link, followers = parse_link_followers(entry)
    return f"{name} ( {followers} ) - {link}"

def format_output(data):
    return (
        f"^^^^^^^^^^^^^^^\n\n"
        f"Name: {data.get('name','-')}\n"
        f"Alias: {data.get('alias','-')}\n"
        f"Country: {data.get('country','-')}\n"
        f"Fame: {data.get('fame','-')}\n"
        f"Top socials: \n"
        f"{format_social('YouTube', data.get('youtube',''))}\n"
        f"{format_social('Instagram', data.get('instagram',''))}\n"
        f"{format_social('TikTok', data.get('tiktok',''))}\n\n"
        f"==============="
    )

async def safe_send_media_group(bot, chat_id, media):
    """Safely send media in groups, splitting if Telegram complains."""
    for attempt in range(3):
        try:
            if not media:
                return
            return await bot.send_media_group(chat_id=chat_id, media=media)
        except (TimedOut, NetworkError):
            logging.warning(f"Timeout, retry {attempt+1}/3...")
            await asyncio.sleep(2)
        except BadRequest as e:
            if "Too many" in str(e):
                logging.warning("Album too large, splitting...")
                mid = len(media) // 2
                await safe_send_media_group(bot, chat_id, media[:mid])
                await safe_send_media_group(bot, chat_id, media[mid:])
                return
            else:
                raise
    logging.error("Failed after 3 retries.")

# ========== HANDLERS ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid] = {"photos": [], "videos": []}
    await update.message.reply_text("Welcome to Gatekeepers Album Maker.\n\nStep 1: Send a clear face picture.")
    return FACE

async def face_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        photo = update.message.photo[-1]
        f = await photo.get_file()
        path = DATA_DIR / f"{uid}_face.jpg"
        await f.download_to_drive(path)
        user_data[uid]["face_path"] = path
        await update.message.reply_text("Got it.\n\nStep 2: Send all photos. Type 'next' when done.")
        return PHOTOS
    except Exception as e:
        logging.error(e)
        await update.message.reply_text("Error saving face photo. Try again.")
        return FACE

async def collect_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    photo = update.message.photo[-1]
    f = await photo.get_file()
    path = DATA_DIR / f"{uid}_{os.path.basename(f.file_path)}"
    await f.download_to_drive(path)
    user_data[uid]["photos"].append(path)
    return PHOTOS

async def photos_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() in ["next", "done", "finish"]:
        await update.message.reply_text("Got it.\n\nStep 3: Send videos now. Type 'next' when done.")
        return VIDEOS
    return PHOTOS

async def collect_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    file = update.message.video or update.message.animation
    if file:
        f = await file.get_file()
        path = DATA_DIR / f"{uid}_{os.path.basename(f.file_path)}"
        await f.download_to_drive(path)
        user_data[uid]["videos"].append(path)
    return VIDEOS

async def videos_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() in ["next", "done", "finish"]:
        await update.message.reply_text("Step 4: Full name?")
        return NAME
    return VIDEOS

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid]["name"] = update.message.text.strip()
    await update.message.reply_text("Step 5: Alias or handle?")
    return ALIAS

async def get_alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid]["alias"] = update.message.text.strip()
    await update.message.reply_text("Step 6: Country?")
    return COUNTRY

async def get_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid]["country"] = update.message.text.strip()
    await update.message.reply_text("Step 7: Why are they famous?")
    return FAME

async def get_fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_data[uid]["fame"] = update.message.text.strip()
    await update.message.reply_text(
        "Step 8: Send all social links in one message.\n\n"
        "Example:\nYouTube: https://youtube.com/... 2M\n"
        "Instagram: https://instagram.com/... 150k\n"
        "TikTok: https://tiktok.com/... 500k"
    )
    return SOCIALS

async def get_socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    socials = parse_social_block(update.message.text)
    user_data[uid].update(socials)
    await update.message.reply_text("Step 9: Type 'done' to assemble.")
    return CONFIRM

async def finalize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = user_data[uid]
    await update.message.reply_text("Assembling albums... please wait.")

    face_path = data.get("face_path")
    photos = data.get("photos", [])
    videos = data.get("videos", [])

    # Create media objects
    media_photos = [InputMediaPhoto(open(p, "rb")) for p in photos]
    media_videos = [InputMediaVideo(open(v, "rb")) for v in videos]

    # Add face picture only once at start
    if face_path and face_path.exists():
        media_photos.insert(0, InputMediaPhoto(open(face_path, "rb")))

    # Combine all media, ensuring videos always go last
    combined_media = media_photos + media_videos

    # Split evenly, max 10 per group
    albums = split_evenly(combined_media, 10)

    # Send albums
    for i, album in enumerate(albums, 1):
        try:
            await safe_send_media_group(context.bot, update.effective_chat.id, album)
        except Exception as e:
            logging.error(f"Album {i} failed: {e}")
            await update.message.reply_text(f"⚠️ Album {i} failed. Skipping...")

    await update.message.reply_text(format_output(data))
    await update.message.reply_text("✅ Done! Type /restart to start over.")
    return ConversationHandler.END

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data.pop(update.effective_user.id, None)
    await update.message.reply_text("Restarted. Send a face picture to begin.")
    return FACE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled. Type /start to begin again.")
    return ConversationHandler.END

# ========== BUILD APP ==========
def main():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            FACE: [MessageHandler(filters.PHOTO, face_photo)],
            PHOTOS: [
                MessageHandler(filters.PHOTO, collect_photos),
                MessageHandler(filters.TEXT, photos_next),
            ],
            VIDEOS: [
                MessageHandler(filters.VIDEO | filters.ANIMATION, collect_videos),
                MessageHandler(filters.TEXT, videos_next),
            ],
            NAME: [MessageHandler(filters.TEXT, get_name)],
            ALIAS: [MessageHandler(filters.TEXT, get_alias)],
            COUNTRY: [MessageHandler(filters.TEXT, get_country)],
            FAME: [MessageHandler(filters.TEXT, get_fame)],
            SOCIALS: [MessageHandler(filters.TEXT, get_socials)],
            CONFIRM: [MessageHandler(filters.Regex("^(done|Done|DONE)$"), finalize)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("restart", restart)],
    )

    app.add_handler(conv)
    logging.info("Bot started.")
    app.run_polling()

if __name__ == "__main__":
    main()
