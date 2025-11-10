import os
import re
import math
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

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Telegram bot
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")  # from Render environment variable

bot_app = Application.builder().token(TOKEN).build()
web_app = Quart(__name__)

# In-memory storage
user_data = {}

# ========== Helper Functions ==========

def parse_socials(text):
    """Parse social media URLs and follower counts."""
    socials = {"YouTube": ("", ""), "Instagram": ("", ""), "TikTok": ("", "")}
    lines = re.split(r"[,\\n]+", text)
    for line in lines:
        match = re.search(r"(https?://\\S+)\s+([\\d\\.]+[MK]?)", line.strip())
        if match:
            url, followers = match.groups()
            if "instagram" in url:
                socials["Instagram"] = (url, followers)
            elif "youtube" in url:
                socials["YouTube"] = (url, followers)
            elif "tiktok" in url:
                socials["TikTok"] = (url, followers)
    return socials


def split_evenly(files, max_per_album=10):
    """Evenly split files into albums of ≤10 items."""
    if len(files) <= max_per_album:
        return [files]
    total = len(files)
    num_albums = math.ceil(total / max_per_album)
    base_size = total // num_albums
    remainder = total % num_albums
    albums = []
    start = 0
    for i in range(num_albums):
        end = start + base_size + (1 if i < remainder else 0)
        albums.append(files[start:end])
        start = end
    return albums


async def send_summary(update, data):
    """Send final summary in the custom format."""
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


# ========== Bot Step Logic ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.effective_user.id] = {"step": 1, "photos": [], "videos": []}
    await update.message.reply_text("Step 1: Send a clear face photo of the celebrity.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = user_data.get(uid)
    if not data:
        return
    step = data.get("step")

    photo_file = update.message.photo[-1].file_id
    if step == 1:
        data["face_photo"] = photo_file
        data["step"] = 2
        await update.message.reply_text("Got it! Now send all the pictures you want to post. Type 'done' when finished.")
    elif step == 2:
        data["photos"].append(photo_file)
    else:
        await update.message.reply_text("Not expecting photos right now.")


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = user_data.get(uid)
    if not data:
        return
    step = data.get("step")

    file_id = update.message.video.file_id
    if step == 3:
        data["videos"].append(file_id)
    else:
        await update.message.reply_text("Not expecting videos right now.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip().lower()
    data = user_data.get(uid)
    if not data:
        return

    step = data.get("step")

    if text == "done":
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
                        media.append(InputMediaVideo(media=fid))
                    else:
                        media.append(InputMediaPhoto(media=fid))
                await update.message.reply_media_group(media)
            await update.message.reply_text("All done!")
        return

    if step == 4:
        data["name"] = update.message.text.strip()
        data["step"] = 5
        await update.message.reply_text("Step 5: Send the alias/social media handles.")
    elif step == 5:
        data["alias"] = update.message.text.strip()
        data["step"] = 6
        await update.message.reply_text("Step 6: Send the country of origin.")
    elif step == 6:
        data["country"] = update.message.text.strip()
        data["step"] = 7
        await update.message.reply_text("Step 7: Send why this person is famous.")
    elif step == 7:
        data["fame"] = update.message.text.strip()
        data["step"] = 8
        await update.message.reply_text("Step 8: Send the celebrity’s social media links and follower counts.")
    elif step == 8:
        data["socials"] = update.message.text.strip()
        data["step"] = 9
        await update.message.reply_text("Step 9: Type 'done' when you’re finished.")


async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.effective_user.id] = {"step": 1, "photos": [], "videos": []}
    await update.message.reply_text("Restarted. Step 1: Send a clear face photo.")


# ========== Handlers ==========
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("restart", restart))
bot_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
bot_app.add_handler(MessageHandler(filters.VIDEO, handle_video))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# ========== Quart Webhook Setup ==========

@web_app.post("/webhook")
async def webhook():
    data = await request.get_json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return "OK", 200


@web_app.get("/")
async def index():
    return "Gatekeepers Album Maker is live!", 200


async def main():
    await bot_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    logger.info(f"Webhook set to {WEBHOOK_URL}/webhook")


if __name__ == "__main__":
    import asyncio
    asyncio.get_event_loop().run_until_complete(main())
    web_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
