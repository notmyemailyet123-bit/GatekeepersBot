import os
import re
import asyncio
import httpx
from quart import Quart, request
from dotenv import load_dotenv
from telegram import Update, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from hypercorn.config import Config
from hypercorn.asyncio import serve

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Initialize Telegram bot
bot_app = Application.builder().token(TELEGRAM_TOKEN).build()

# Initialize Quart app
app = Quart(__name__)

# ------------------------- Helper Functions ----------------------------

def extract_socials(text: str):
    """
    Extracts social media URLs and follower counts from the user's message.
    Example input:
        https://www.instagram.com/nicholasgalitzine 5.7M
        https://youtube.com/@nicholasgalitzineofficial 118K
        https://www.tiktok.com/@nicholasgalitzine 3.1M
    """
    socials = {}
    pattern = r"(https?://[^\s]+)\s+([\d\.]+[KkMm]?)"
    matches = re.findall(pattern, text)

    for url, count in matches:
        if "instagram" in url.lower():
            socials["Instagram"] = (count, url)
        elif "youtube" in url.lower():
            socials["YouTube"] = (count, url)
        elif "tiktok" in url.lower():
            socials["TikTok"] = (count, url)

    return socials


def evenly_split_photos(photo_urls, group_count=3):
    """
    Evenly split the list of photos into N groups (albums) as balanced as possible.
    Example: 26 photos → [8, 9, 9]
    """
    total = len(photo_urls)
    base = total // group_count
    remainder = total % group_count

    sizes = [base + (1 if i < remainder else 0) for i in range(group_count)]

    albums = []
    idx = 0
    for size in sizes:
        albums.append(photo_urls[idx: idx + size])
        idx += size
    return albums


async def generate_summary(name, socials):
    """
    Generate a formatted text summary for the celebrity/person.
    """
    instagram = socials.get("Instagram", ("x", ""))
    youtube = socials.get("YouTube", ("x", ""))
    tiktok = socials.get("TikTok", ("x", ""))

    summary = (
        f"^^^^^^^^^^^^^^^^\n\n"
        f"Name: {name}\n"
        f"Alias: {name.replace(' ', '')}, {name.lower()}\n"
        f"Country: UK\n"
        f"Fame: Actor\n"
        f"Top socials:\n"
        f"YouTube ({youtube[0]}) - {youtube[1]}\n"
        f"Instagram ({instagram[0]}) - {instagram[1]}\n"
        f"TikTok ({tiktok[0]}) - {tiktok[1]}\n\n"
        f"===============\n"
    )
    return summary


# ------------------------- Telegram Bot Logic ----------------------------

@bot_app.message(filters.COMMAND & filters.Regex(r"^/start"))
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hey! Send me social media links and follower counts (one per line).")


@bot_app.message(filters.TEXT & ~filters.COMMAND)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    socials = extract_socials(text)
    name = "Nicholas Galitzine"  # for example, you could add name parsing later

    summary = await generate_summary(name, socials)
    await update.message.reply_text(summary)

    # Example placeholder photos (in a real version you’d get these dynamically)
    photos = [
        "https://picsum.photos/400/400?random=1",
        "https://picsum.photos/400/400?random=2",
        "https://picsum.photos/400/400?random=3",
        "https://picsum.photos/400/400?random=4",
        "https://picsum.photos/400/400?random=5",
        "https://picsum.photos/400/400?random=6",
        "https://picsum.photos/400/400?random=7",
        "https://picsum.photos/400/400?random=8",
        "https://picsum.photos/400/400?random=9"
    ]

    albums = evenly_split_photos(photos, 3)

    for album in albums:
        media_group = [InputMediaPhoto(url) for url in album]
        await context.bot.send_media_group(chat_id=update.message.chat_id, media=media_group)


# ------------------------- Quart Webhook ----------------------------

@app.route("/", methods=["GET"])
async def home():
    return "Bot is running!", 200


@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
async def telegram_webhook():
    data = await request.get_json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return "OK", 200


# ------------------------- Combined Async Runner ----------------------------

async def start_bot():
    print("Starting Telegram bot...")
    await bot_app.initialize()
    await bot_app.start()
    print("Telegram bot is live.")
    await bot_app.updater.start_polling()
    await bot_app.updater.wait_for_stop()
    await bot_app.stop()
    await bot_app.shutdown()


async def start_web():
    print("Starting Quart web server...")
    config = Config()
    config.bind = ["0.0.0.0:10000"]
    await serve(app, config)


async def main():
    await asyncio.gather(start_bot(), start_web())


if __name__ == "__main__":
    asyncio.run(main())
