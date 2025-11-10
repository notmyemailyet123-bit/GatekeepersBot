# gatekeepers_album_maker.py
import os
import asyncio
from quart import Quart, request
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("TELEGRAM_TOKEN")  # Put your bot token in Render env variables
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://yourbot.onrender.com/

app = Quart(__name__)

# In-memory user data storage
user_data = {}

# Steps
STEPS = [
    "face_photo",
    "content_photos",
    "content_videos",
    "full_name",
    "alias",
    "country",
    "fame",
    "social_links",
    "done"
]

# --- BOT LOGIC ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data[chat_id] = {
        "step": 0,
        "face_photo": None,
        "content_photos": [],
        "content_videos": [],
        "full_name": "",
        "alias": "",
        "country": "",
        "fame": "",
        "social_links": {}
    }
    await context.bot.send_message(chat_id, "Welcome to Gatekeepers Album Maker! Please send a normal face picture of the celebrity to start.")

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data.pop(chat_id, None)
    await start(update, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in user_data:
        await start(update, context)
        return

    step = user_data[chat_id]["step"]

    # Step 1: face photo
    if step == 0:
        if update.message.photo:
            user_data[chat_id]["face_photo"] = update.message.photo[-1].file_id
            user_data[chat_id]["step"] += 1
            await context.bot.send_message(chat_id, "Face photo received. Now send all pictures you want to post. When done, type 'next'.")
        else:
            await context.bot.send_message(chat_id, "Please send a normal face photo.")

    # Step 2: content photos
    elif step == 1:
        if update.message.photo:
            user_data[chat_id]["content_photos"].append(update.message.photo[-1].file_id)
        elif update.message.text and update.message.text.lower() == "next":
            user_data[chat_id]["step"] += 1
            await context.bot.send_message(chat_id, f"{len(user_data[chat_id]['content_photos'])} photos saved. Now send all videos/GIFs. Type 'next' when done.")
        else:
            await context.bot.send_message(chat_id, "Send photos or 'next' to continue.")

    # Step 3: content videos
    elif step == 2:
        if update.message.video or update.message.animation:
            file_id = update.message.video.file_id if update.message.video else update.message.animation.file_id
            user_data[chat_id]["content_videos"].append(file_id)
        elif update.message.text and update.message.text.lower() == "next":
            user_data[chat_id]["step"] += 1
            await context.bot.send_message(chat_id, "Videos/GIFs saved. Send the celebrity's full name.")
        else:
            await context.bot.send_message(chat_id, "Send videos/GIFs or 'next' to continue.")

    # Step 4: full name
    elif step == 3:
        if update.message.text:
            user_data[chat_id]["full_name"] = update.message.text
            user_data[chat_id]["step"] += 1
            await context.bot.send_message(chat_id, "Send alias or social media handles (or 'none').")
        else:
            await context.bot.send_message(chat_id, "Please send text.")

    # Step 5: alias
    elif step == 4:
        user_data[chat_id]["alias"] = update.message.text
        user_data[chat_id]["step"] += 1
        await context.bot.send_message(chat_id, "Send the country of origin.")

    # Step 6: country
    elif step == 5:
        user_data[chat_id]["country"] = update.message.text
        user_data[chat_id]["step"] += 1
        await context.bot.send_message(chat_id, "Send why the person is famous.")

    # Step 7: fame
    elif step == 6:
        user_data[chat_id]["fame"] = update.message.text
        user_data[chat_id]["step"] += 1
        await context.bot.send_message(chat_id, "Send social media links (YouTube, Instagram, TikTok).")

    # Step 8: social links
    elif step == 7:
        links = update.message.text.splitlines()
        for link in links:
            if "youtube.com" in link:
                user_data[chat_id]["social_links"]["YouTube"] = link
            elif "instagram.com" in link:
                user_data[chat_id]["social_links"]["Instagram"] = link
            elif "tiktok.com" in link:
                user_data[chat_id]["social_links"]["TikTok"] = link
        user_data[chat_id]["step"] += 1
        await context.bot.send_message(chat_id, "All info saved. Type 'done' when ready to receive album and summary.")

    # Step 9: done
    elif step == 8:
        if update.message.text.lower() == "done":
            await send_summary_and_albums(chat_id, context)
            user_data[chat_id]["step"] = 0
        else:
            await context.bot.send_message(chat_id, "Type 'done' when ready.")

# --- SEND ALBUM AND SUMMARY ---
async def send_summary_and_albums(chat_id, context):
    data = user_data[chat_id]

    # 1. Build summary text
    summary = f"""
^^^^^^^^^^^^^^^

Name: {data['full_name']}
Alias: {data['alias']}
Country: {data['country']}
Fame: {data['fame']}
Top socials: 
YouTube ( x ) - {data['social_links'].get('YouTube','')}
Instagram ( x ) - {data['social_links'].get('Instagram','')}
TikTok ( x ) - {data['social_links'].get('TikTok','')}

===============
"""
    await context.bot.send_message(chat_id, summary)

    # 2. Build albums
    media_files = [data['face_photo']] + data['content_photos'] + data['content_videos']
    album_size = 10
    albums = [media_files[i:i+album_size] for i in range(0, len(media_files), album_size)]

    for album in albums:
        media_group = []
        for f in album:
            if f in data['content_videos']:
                media_group.append(InputMediaVideo(f))
            else:
                media_group.append(InputMediaPhoto(f))
        await context.bot.send_media_group(chat_id, media_group)

# --- WEBHOOK ROUTE ---
application = ApplicationBuilder().token(TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("restart", restart))
application.add_handler(MessageHandler(filters.ALL, handle_message))

@app.route("/", methods=["POST"])
async def webhook():
    data = await request.get_json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return "ok"

# --- START QUART APP ---
if __name__ == "__main__":
    async def main():
        await application.initialize()
        await application.start()
        # Set webhook
        await application.bot.set_webhook(WEBHOOK_URL)
        print(f"Webhook set to {WEBHOOK_URL}")
        await app.run_task(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
        await application.stop()
    asyncio.run(main())
