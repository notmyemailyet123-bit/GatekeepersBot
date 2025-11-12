import os 
import re
import math
import asyncio
import logging
from quart import Quart, request
from telegram import (
    Update,
    InputMediaPhoto,
    InputMediaVideo,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
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
def format_followers(f):
    """Convert numeric follower counts to shorthand (e.g., 5700000 -> 5.7M)."""
    try:
        f = f.replace(",", "").strip().upper()
        if f.endswith(("M", "K")):
            return f
        num = float(f)
        if num >= 1_000_000:
            return f"{num / 1_000_000:.1f}M".rstrip("0").rstrip(".")
        elif num >= 1_000:
            return f"{num / 1_000:.0f}K"
        else:
            return str(int(num)) if num.is_integer() else str(num)
    except Exception:
        return f


def parse_socials(text):
    """Parse social media links and follower counts (any platform)."""
    socials = {}
    lines = re.split(r"[,\n]+", text.strip())

    for line in lines:
        match = re.search(r"(https?://\S+)\s+([\d.,]+[MK]?)", line.strip(), re.IGNORECASE)
        if match:
            url, followers = match.groups()
            url = url.strip()
            followers = format_followers(followers.strip())

            platform = "Other"
            if "instagram" in url.lower():
                platform = "Instagram"
            elif "youtube" in url.lower():
                platform = "YouTube"
            elif "tiktok" in url.lower():
                platform = "TikTok"
            elif "twitter" in url.lower() or "x.com" in url.lower():
                platform = "Twitter"
            elif "facebook" in url.lower():
                platform = "Facebook"
            elif "threads.net" in url.lower():
                platform = "Threads"
            elif "snapchat" in url.lower():
                platform = "Snapchat"
            elif "linkedin" in url.lower():
                platform = "LinkedIn"
            elif "twitch" in url.lower():
                platform = "Twitch"
            elif "pinterest" in url.lower():
                platform = "Pinterest"

            socials[platform] = (url, followers)
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
    """Send a summary safely for both messages and callback queries."""
    message_target = None
    if hasattr(update, "effective_message") and update.effective_message:
        message_target = update.effective_message
    elif hasattr(update, "callback_query") and update.callback_query:
        message_target = update.callback_query.message
    elif hasattr(update, "message") and update.message:
        message_target = update.message

    if not message_target:
        logger.warning("No valid message target for send_summary.")
        return

    socials = parse_socials(data.get("socials", ""))
    social_lines = [f"{p} ({f}) - {u}" for p, (u, f) in socials.items() if u and f]
    social_text = "\n".join(social_lines)

    if social_text:
        summary = (
            "^^^^^^^^^^^^^^^\n\n"
            f"Name: {data.get('name','-')}\n"
            f"Alias: {data.get('alias','-')}\n"
            f"Country: {data.get('country','-')}\n"
            f"Fame: {data.get('fame','-')}\n"
            f"Top socials:\n{social_text}\n\n"
            "==============="
        )
    else:
        summary = (
            "^^^^^^^^^^^^^^^\n\n"
            f"Name: {data.get('name','-')}\n"
            f"Alias: {data.get('alias','-')}\n"
            f"Country: {data.get('country','-')}\n"
            f"Fame: {data.get('fame','-')}\n"
            f"Top socials:\nNone provided\n\n"
            "==============="
        )

    await message_target.reply_text(summary)


def done_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ Done", callback_data="done")]])


# ========== Bot Logic ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.effective_user.id] = {"step": 1, "photos": [], "videos": []}
    await update.message.reply_text(
        "<b><u>Step 1:</u></b>\nSend a clear, regular face photo of the celebrity.",
        parse_mode=ParseMode.HTML,
    )


async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.effective_user.id] = {"step": 1, "photos": [], "videos": []}
    await update.message.reply_text(
        "Restarted.\n<b><u>Step 1:</u></b>\nSend a clear, regular face photo of the celebrity.",
        parse_mode=ParseMode.HTML,
    )


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
        await update.message.reply_text(
            "<b><u>Step 2:</u></b>\nGot it! Now send all photos only (no videos or GIFs).\n"
            "When you’re finished, either type 'done' or press the ✅ Done button below.",
            parse_mode=ParseMode.HTML,
            reply_markup=done_button(),
        )
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


async def process_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = user_data.get(uid)
    if not data:
        return

    step = data["step"]
    message_target = update.callback_query.message if update.callback_query else update.message

    if step == 2:
        data["step"] = 3
        await message_target.reply_text(
            "<b><u>Step 3:</u></b>\nGot it! Now send all videos and GIFs.\n"
            "When you’re finished, either type 'done' or press the ✅ Done button below.",
            parse_mode=ParseMode.HTML,
            reply_markup=done_button(),
        )
    elif step == 3:
        data["step"] = 4
        await message_target.reply_text(
            "<b><u>Step 4:</u></b>\nGot it! Please send the person’s full name.",
            parse_mode=ParseMode.HTML,
        )
    elif step == 5:
        data["step"] = 6
        await message_target.reply_text(
            "<b><u>Step 6:</u></b>\nGot it! Send their country of origin.",
            parse_mode=ParseMode.HTML,
        )
    elif step in [1, 4, 6, 7, 8]:
        await message_target.reply_text(
            "This step is required. Please provide the requested information before continuing.",
            parse_mode=ParseMode.HTML,
        )
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
            await message_target.reply_media_group(media)
        await message_target.reply_text("All done!")

    if update.callback_query:
        await update.callback_query.answer()


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    lower_text = text.lower()
    uid = update.effective_user.id
    data = user_data.get(uid)
    if not data:
        return

    if lower_text == "done":
        await process_done(update, context)
        return

    step = data["step"]
    if step == 4:
        data["name"] = text
        data["step"] = 5
        await update.message.reply_text(
            "<b><u>Step 5:</u></b>\nGot it! Send all aliases and/or handles.\n"
            "❌ Don’t send links here.\n"
            "✅ Only write the handles without the @.\n"
            "Example: Tom Holland , tomholland2013 , TomHolland1996\n"
            "When you’re finished, either type 'done' or press the ✅ Done button below.",
            parse_mode=ParseMode.HTML,
            reply_markup=done_button(),
        )
    elif step == 5:
        data["alias"] = text
        data["step"] = 6
        await update.message.reply_text(
            "<b><u>Step 6:</u></b>\nGot it! Send their country of origin.",
            parse_mode=ParseMode.HTML,
        )
    elif step == 6:
        data["country"] = text
        data["step"] = 7
        await update.message.reply_text(
            "<b><u>Step 7:</u></b>\nGot it! Why is this person famous?",
            parse_mode=ParseMode.HTML,
        )
    elif step == 7:
        data["fame"] = text
        data["step"] = 8
        await update.message.reply_text(
            "<b><u>Step 8:</u></b>\nGot it! Now send all social media links with follower counts, one per line.\n"
            "Example:\n"
            "https://www.instagram.com/example 5.7M\n"
            "https://youtube.com/@example 118K\n"
            "https://www.tiktok.com/@example 3.1M\n"
            "https://twitter.com/example 420K\n\n"
            "When you’re finished, either type 'done' or press the ✅ Done button below.",
            parse_mode=ParseMode.HTML,
            reply_markup=done_button(),
        )
    elif step == 8:
        data["socials"] = text
        data["step"] = 9
        await update.message.reply_text(
            "<b><u>Step 9:</u></b>\nGot it! When you’re ready, either type 'done' or press the ✅ Done button below.",
            parse_mode=ParseMode.HTML,
            reply_markup=done_button(),
        )


# ========== Register Handlers ==========
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("restart", restart))
bot_app.add_handler(CallbackQueryHandler(process_done, pattern="^done$"))
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
    import hypercorn.asyncio
    from hypercorn.config import Config

    asyncio.run(init_bot())

    config = Config()
    config.bind = [f"0.0.0.0:{PORT}"]
    asyncio.run(hypercorn.asyncio.serve(web_app, config))
