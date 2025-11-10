import os
import re
import math
import asyncio
import logging
from quart import Quart, request
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv

load_dotenv()

# ========== Logging ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gatekeepers_album_maker")

# ========== Setup ==========
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")
PORT = int(os.getenv("PORT", 10000))

bot_app = Application.builder().token(TOKEN).build()
web_app = Quart(__name__)

# In-memory user session
user_data = {}

# ========== Helper Functions ==========

def parse_socials(text):
    """Parse social media links and follower counts."""
    socials = {"YouTube": ("", ""), "Instagram": ("", ""), "TikTok": ("", "")}
    lines = re.split(r"[,\n]+", text.strip())

    for line in lines:
        match = re.search(r"(https?://\S+)\s+([\d.,]+[MK]?)", line.strip(), re.IGNORECASE)
        if match:
            url, followers = match.groups()
            url = url.strip()
            followers = followers.strip()
            if "instagram" in url.lower():
                socials["Instagram"] = (url, followers)
            elif "youtube" in url.lower():
                socials["YouTube"] = (url, followers)
            elif "tiktok" in url.lower():
                socials["TikTok"] = (url, followers)
    return socials


def split_evenly(files, max_per_album=10):
    """Evenly split files into albums (max 10 each)."""
    if len(files) <= max_per_album:
        return [files]
    total = len(files)
    num_albums = math.ceil(total / max_per_album)
    base_size = total // num_albums
    remainder = total % num_albums
    albums, start = [], 0
    for i in range(num_albums):
        end = start + base_size + (1 if i < remainder else 0)
        albums.append(files[start:end])
        start = end
    return albums


async def send_summary(update, data):
    socials = parse_socials(data.get("socials", ""))
    summary = (
        "^^^^^^^^^^^^^^^\n\n"
        f"Name: {data.get('name','-')}\n"
        f"Alias: {data.get('alias','-')}\n"
        f"Country: {data.get('country','-')}\n"
        f"Fame: {data.get('fame','-')}\n"
        "Top socials:\n"
        f"YouTube ({socials['YouTube'][1] or 'x'}) - {socials['YouTube'][0]}\n"
        f"Instagram ({socials['Instagram'][1] or 'x'}) - {socials['Instagram'][0]}\n"
        f"TikTok ({socials['TikTok'][1] or 'x'}) - {socials['TikTok'][0]}\n\n"
        "==============="
    )
    await update.message.reply_text(summary)


# ========== Bot Logic ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.effective_user.id] = {"step": 1, "photos": [], "videos": []}
    await update.message.reply_text("Step 1: Send a clear face photo of the celebrity.")


async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.effective_user.id] = {"step": 1, "photos": [], "videos": []}
    await update.message.reply_text("Restarted. Step 1: Send a clear face photo.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = user_data.get(uid)
    if not data:
        return
    step = data["step"]

    photo_id = update.message.photo[-1].file_id
    if step == 1:
        data["face_photo"] = photo_id
        data["step"] = 2
        await update.message.reply_text("Got it! Now send all other images. Type 'done' when finished.")
    elif step == 2:
        data["photos"].append(photo_id)
    else:
        await update.message.reply_text("Not expecting photos right now.")


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = user_data.get(uid)
    if not data:
        return
    step = data["step"]
    if step == 3:
        data["videos"].append(update.message.video.file_id)
    else:
        await update.message.reply_text("Not expecting videos right now.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()
    lower_text = text.lower()
    data = user_data.get(uid)
    if not data:
        return
    step = data["step"]

    if lower_text == "done":
        if step == 2:
            data["step"] = 3
            await update.message.reply_text("Step 3: Send all videos and GIFs. Type 'done' when finished.")
        elif step == 3:
            data["step"] = 4
            await update.message.reply_text("Step 4: Send the person’s full name.")
        elif step == 9:
            await send_summary(update, data)
            all_files = [data.get("face_photo")] + data["photos"] + data["videos"]
            albums = split_evenly(all_files)
            for album in albums:
                media = []
                for fid in album:
                    if fid in data["videos"]:
                        media.append(InputMediaVideo(fid))
                    else:
                        media.append(InputMediaPhoto(fid))
                await update.message.reply_media_group(media)
            await update.message.reply_text("All done!")
        return

    # Step logic
    if step == 4:
        data["name"] = text
        data["step"] = 5
        await update.message.reply_text("Step 5: Send aliases or handles.")
    elif step == 5:
        data["alias"] = text
        data["step"] = 6
        await update.message.reply_text("Step 6: Send country of origin.")
    elif step == 6:
        data["country"] = text
        data["step"] = 7
        await update.message.reply_text("Step 7: Why is this person famous?")
    elif step == 7:
        data["fame"] = text
        data["step"] = 8
        await update.message.reply_text("Step 8: Send social links with follower counts (e.g. 'https://instagram.com/... 5.7M').")
    elif step == 8:
        data["socials"] = text
        data["step"] = 9
        await update.message.reply_text("Step 9: Type 'done' when finished.")


# ========== Register Handlers ==========
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("restart", restart))
bot_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
bot_app.add_handler(MessageHandler(filters.VIDEO, handle_video))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# ========== Quart Webhook ==========
@web_app.post("/webhook")
async def webhook():
    data = await request.get_json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return "OK", 200


@web_app.get("/")
async def index():
    return "✅ Gatekeepers Album Maker is live!", 200


# ========== Startup ==========
async def init_bot():
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    logger.info(f"Webhook set to {WEBHOOK_URL}/webhook")


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(init_bot())
    web_app.run(host="0.0.0.0", port=PORT)
