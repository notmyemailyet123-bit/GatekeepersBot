import os
import logging
from dotenv import load_dotenv
from quart import Quart, request, jsonify
from telegram import Bot
from telegram.error import TelegramError

# Load environment variables from .env
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN found in .env file!")

# Setup logging
logging.basicConfig(level=logging.INFO)

# Initialize Quart app
app = Quart(__name__)

# Initialize Telegram bot
bot = Bot(token=TOKEN)

@app.route("/")
async def index():
    return "Gatekeepers Album Maker Bot is running!"

@app.route("/webhook", methods=["POST"])
async def webhook():
    data = await request.get_json()
    logging.info(f"Incoming update: {data}")

    try:
        if "message" in data:
            chat_id = data["message"]["chat"]["id"]
            text = data["message"].get("text", "")

            if text.startswith("/start"):
                await bot.send_message(chat_id=chat_id, text="Hello! Bot is working.")
            else:
                await bot.send_message(chat_id=chat_id, text=f"You said: {text}")
        return jsonify({"status": "ok"})
    except TelegramError as e:
        logging.error(f"Telegram error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    import hypercorn.asyncio
    import asyncio
    from hypercorn.config import Config

    config = Config()
    config.bind = ["0.0.0.0:10000"]
    asyncio.run(hypercorn.asyncio.serve(app, config))
