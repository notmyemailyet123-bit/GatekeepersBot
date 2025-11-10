import os
from flask import Flask, request
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackContext
from urllib.parse import urlparse

# Environment variables
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Flask app for webhook
flask_app = Flask(__name__)

# Store user sessions
sessions = {}

# Steps
STEPS = [
    "face_photo",
    "pics",
    "videos",
    "full_name",
    "alias",
    "country",
    "fame",
    "socials",
    "done"
]

# Helper: split items evenly into albums
def split_evenly(items, max_per_album=10):
    n = len(items)
    num_albums = (n + max_per_album - 1) // max_per_album
    base_size = n // num_albums
    remainder = n % num_albums

    albums = []
    start = 0
    for i in range(num_albums):
        end = start + base_size + (1 if i < remainder else 0)
        albums.append(items[start:end])
        start = end
    return albums

# Restart command
async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    sessions[chat_id] = {
        "step": 0,
        "face_photo": None,
        "pics": [],
        "videos": [],
        "full_name": "",
        "alias": "",
        "country": "",
        "fame": "",
        "socials": {}
    }
    await context.bot.send_message(chat_id=chat_id, text="Session restarted. Send the celebrity's face photo first.")

# Process messages
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = sessions.setdefault(chat_id, {
        "step": 0,
        "face_photo": None,
        "pics": [],
        "videos": [],
        "full_name": "",
        "alias": "",
        "country": "",
        "fame": "",
        "socials": {}
    })
    step = user["step"]

    # Step 0: face photo
    if step == 0 and update.message.photo:
        user["face_photo"] = update.message.photo[-1].file_id
        user["step"] += 1
        await context.bot.send_message(chat_id=chat_id, text="Face photo saved. Now send all other pictures. Send /next when done.")
        return

    # Step 1: pictures
    if step == 1:
        if update.message.photo:
            user["pics"].append(update.message.photo[-1].file_id)
            return
        elif update.message.text and update.message.text.lower() == "/next":
            user["step"] += 1
            await context.bot.send_message(chat_id=chat_id, text="Pictures saved. Now send all videos/gifs. Send /next when done.")
            return
        else:
            return

    # Step 2: videos/gifs
    if step == 2:
        if update.message.video or update.message.animation:
            file_id = update.message.video.file_id if update.message.video else update.message.animation.file_id
            user["videos"].append(file_id)
            return
        elif update.message.text and update.message.text.lower() == "/next":
            user["step"] += 1
            await context.bot.send_message(chat_id=chat_id, text="Videos saved. Send full name of the celebrity.")
            return
        else:
            return

    # Step 3: full name
    if step == 3:
        user["full_name"] = update.message.text
        user["step"] += 1
        await context.bot.send_message(chat_id=chat_id, text="Send alias/social media handles.")
        return

    # Step 4: alias
    if step == 4:
        user["alias"] = update.message.text
        user["step"] += 1
        await context.bot.send_message(chat_id=chat_id, text="Send country of origin.")
        return

    # Step 5: country
    if step == 5:
        user["country"] = update.message.text
        user["step"] += 1
        await context.bot.send_message(chat_id=chat_id, text="Send why the celebrity is famous.")
        return

    # Step 6: fame
    if step == 6:
        user["fame"] = update.message.text
        user["step"] += 1
        await context.bot.send_message(chat_id=chat_id, text="Send social media links (YouTube, Instagram, TikTok). Send /done when finished.")
        return

    # Step 7: socials
    if step == 7:
        if update.message.text and update.message.text.lower() == "/done":
            user["step"] += 1
        else:
            text = update.message.text
            if "youtube.com" in text:
                user["socials"]["YouTube"] = text
            elif "instagram.com" in text:
                user["socials"]["Instagram"] = text
            elif "tiktok.com" in text:
                user["socials"]["TikTok"] = text
            return

    # Step 8: done -> output albums & summary
    if step == 8:
        await send_summary_and_albums(chat_id, user, context)
        sessions.pop(chat_id)  # reset session
        return

# Send summary and albums
async def send_summary_and_albums(chat_id, user, context):
    # Format summary
    summary = f"""^^^^^^^^^^^^^^^

Name: {user['full_name']}
Alias: {user['alias']}
Country: {user['country']}
Fame: {user['fame']}
Top socials:
YouTube - {user['socials'].get('YouTube','-')}
Instagram - {user['socials'].get('Instagram','-')}
TikTok - {user['socials'].get('TikTok','-')}

==============="""
    await context.bot.send_message(chat_id=chat_id, text=summary)

    # Combine all media
    all_media = [user["face_photo"]] + user["pics"] + user["videos"]
    albums = split_evenly(all_media, max_per_album=10)

    for album in albums:
        media_group = []
        for file_id in album:
            if file_id in user["videos"]:
                media_group.append(InputMediaVideo(file_id))
            else:
                media_group.append(InputMediaPhoto(file_id))
        await context.bot.send_media_group(chat_id=chat_id, media=media_group)

# Flask route
@flask_app.route('/', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put(update)
    return 'OK'

# Set webhook
async def set_webhook():
    await application.bot.set_webhook(WEBHOOK_URL)

# Main
application = ApplicationBuilder().token(TOKEN).build()
application.add_handler(CommandHandler("restart", restart))
application.add_handler(MessageHandler(filters.ALL, message_handler))

if __name__ == "__main__":
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(set_webhook())
    flask_app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
