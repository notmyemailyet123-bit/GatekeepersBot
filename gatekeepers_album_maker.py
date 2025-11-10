import logging
from quart import Quart, request, jsonify
from telegram import Bot
from telegram.error import TelegramError
import asyncio

# -----------------------------
# CONFIG
# -----------------------------
TOKEN = "YOUR_BOT_TOKEN"  # Replace with your bot token
WEBHOOK_URL = "https://gatekeepersbot.onrender.com/webhook"

# -----------------------------
# SETUP
# -----------------------------
logging.basicConfig(level=logging.INFO)
app = Quart(__name__)
bot = Bot(token=TOKEN)

# -----------------------------
# WEBHOOK ROUTE
# -----------------------------
@app.route('/webhook', methods=['POST'])
async def webhook():
    try:
        data = await request.get_json()  # Quart allows 'await'
        logging.info(f"Incoming update: {data}")

        # Handle messages
        if "message" in data:
            chat_id = data["message"]["chat"]["id"]
            text = data["message"].get("text", "")
            if text:
                await bot.send_message(chat_id=chat_id, text=f"You said: {text}")

        # Respond OK to Telegram
        return jsonify({"status": "ok"}), 200

    except TelegramError as te:
        logging.error(f"Telegram error: {te}")
        return jsonify({"status": "error", "error": str(te)}), 500
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
