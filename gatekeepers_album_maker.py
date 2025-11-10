import os
import asyncio
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from quart import Quart

# ------------------------
# Telegram Bot Logic
# ------------------------
user_data = {}

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_data[chat_id] = {
        "step": 0,
        "face_image": None,
        "images": [],
        "videos": [],
        "full_name": "",
        "alias": "",
        "country": "",
        "fame": "",
        "social_links": {}
    }
    await update.message.reply_text("Process restarted. Send a normal face picture of the celebrity to begin.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await restart(update, context)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in user_data:
        await restart(update, context)
    data = user_data[chat_id]
    step = data["step"]

    # Face image
    if step == 0 and update.message.photo:
        data["face_image"] = update.message.photo[-1].file_id
        data["step"] += 1
        await update.message.reply_text("Face image received. Send all images you want to post. Type 'done' when finished.")
        return
    elif step == 0:
        await update.message.reply_text("Please send a face picture to begin.")
        return

    # Content images
    if step == 1:
        if update.message.text and update.message.text.lower() == "done":
            data["step"] += 1
            await update.message.reply_text("All images saved. Send all videos and GIFs now. Type 'done' when finished.")
        elif update.message.photo:
            data["images"].append(update.message.photo[-1].file_id)
        return

    # Videos/GIFs
    if step == 2:
        if update.message.text and update.message.text.lower() == "done":
            data["step"] += 1
            await update.message.reply_text("All videos/GIFs saved. Send the celebrity's full name.")
        elif update.message.video or update.message.animation:
            file_id = update.message.video.file_id if update.message.video else update.message.animation.file_id
            data["videos"].append(file_id)
        return

    # Full name
    if step == 3:
        data["full_name"] = update.message.text
        data["step"] += 1
        await update.message.reply_text("Send the celebrity's alias/social media handles if any.")
        return

    # Alias
    if step == 4:
        data["alias"] = update.message.text
        data["step"] += 1
        await update.message.reply_text("Send the celebrity's country of origin.")
        return

    # Country
    if step == 5:
        data["country"] = update.message.text
        data["step"] += 1
        await update.message.reply_text("Why is this person famous?")
        return

    # Fame
    if step == 6:
        data["fame"] = update.message.text
        data["step"] += 1
        await update.message.reply_text("Send social media links with follower counts (one per line, e.g., 'URL 1.2M').")
        return

    # Social links
    if step == 7 and update.message.text:
        for line in update.message.text.splitlines():
            parts = line.split()
            if not parts: continue
            url, count = parts[0], " ".join(parts[1:]) if len(parts) > 1 else ""
            if "youtube.com" in url.lower():
                data["social_links"]["YouTube"] = {"count": count, "url": url}
            elif "instagram.com" in url.lower():
                data["social_links"]["Instagram"] = {"count": count, "url": url}
            elif "tiktok.com" in url.lower():
                data["social_links"]["TikTok"] = {"count": count, "url": url}
        data["step"] += 1
        await update.message.reply_text("All social info saved. Type 'done' when ready to receive album and summary.")
        return

    # Done & send summary
    if step == 8 and update.message.text and update.message.text.lower() == "done":
        summary = f"""
^^^^^^^^^^^^^^^

Name: {data['full_name']}
Alias: {data['alias']}
Country: {data['country']}
Fame: {data['fame']}
Top socials: 
YouTube ({data['social_links'].get('YouTube', {}).get('count','')}) - {data['social_links'].get('YouTube', {}).get('url','')}
Instagram ({data['social_links'].get('Instagram', {}).get('count','')}) - {data['social_links'].get('Instagram', {}).get('url','')}
TikTok ({data['social_links'].get('TikTok', {}).get('count','')}) - {data['social_links'].get('TikTok', {}).get('url','')}

===============
"""
        await update.message.reply_text(summary)

        media_files = [data["face_image"]] + data["images"] + data["videos"]
        chunk_size = 10
        for i in range(0, len(media_files), chunk_size):
            media_group = []
            for file_id in media_files[i:i+chunk_size]:
                if file_id in data["videos"]:
                    media_group.append(InputMediaVideo(file_id))
                else:
                    media_group.append(InputMediaPhoto(file_id))
            await context.bot.send_media_group(chat_id, media_group)
        data["step"] += 1
        return

# ------------------------
# Quart web server
# ------------------------
app = Quart(__name__)

@app.route("/")
async def index():
    return "Gatekeepers Telegram Bot is running!"

# ------------------------
# Run bot + Quart with Hypercorn
# ------------------------
async def start_bot():
    token = os.environ["TELEGRAM_TOKEN"]
    bot_app = ApplicationBuilder().token(token).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("restart", restart))
    bot_app.add_handler(MessageHandler(filters.ALL, handle_message))
    print("Telegram bot is running...")
    await bot_app.run_polling()

if __name__ == "__main__":
    import hypercorn.asyncio
    from hypercorn.config import Config

    port = int(os.environ.get("PORT", 10000))
    config = Config()
    config.bind = [f"0.0.0.0:{port}"]

    # Run both asynchronously
    asyncio.run(asyncio.gather(start_bot(), hypercorn.asyncio.serve(app, config)))
