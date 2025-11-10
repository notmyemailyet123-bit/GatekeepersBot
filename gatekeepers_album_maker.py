import os
import asyncio
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from quart import Quart

# Store user data in memory
user_data = {}

# Restart command
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
        "social_links": {}  # Store as {"platform": {"count": "", "url": ""}}
    }
    await update.message.reply_text("Process restarted. Send a normal face picture of the celebrity to begin.")

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await restart(update, context)

# Handle messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in user_data:
        await restart(update, context)
    data = user_data[chat_id]
    step = data["step"]

    # Step 1: Face image
    if step == 0:
        if update.message.photo:
            data["face_image"] = update.message.photo[-1].file_id
            data["step"] += 1
            await update.message.reply_text("Face image received. Send all images you want to post. Type 'done' when finished.")
        else:
            await update.message.reply_text("Please send a face picture to begin.")

    # Step 2: Content images
    elif step == 1:
        if update.message.text and update.message.text.lower() == "done":
            data["step"] += 1
            await update.message.reply_text("All images saved. Send all videos and GIFs now. Type 'done' when finished.")
        elif update.message.photo:
            data["images"].append(update.message.photo[-1].file_id)

    # Step 3: Videos and GIFs
    elif step == 2:
        if update.message.text and update.message.text.lower() == "done":
            data["step"] += 1
            await update.message.reply_text("All videos/GIFs saved. Send the celebrity's full name.")
        elif update.message.video or update.message.animation:
            file_id = update.message.video.file_id if update.message.video else update.message.animation.file_id
            data["videos"].append(file_id)

    # Step 4: Full name
    elif step == 3:
        data["full_name"] = update.message.text
        data["step"] += 1
        await update.message.reply_text("Send the celebrity's alias/social media handles if any.")

    # Step 5: Alias
    elif step == 4:
        data["alias"] = update.message.text
        data["step"] += 1
        await update.message.reply_text("Send the celebrity's country of origin.")

    # Step 6: Country
    elif step == 5:
        data["country"] = update.message.text
        data["step"] += 1
        await update.message.reply_text("Why is this person famous?")

    # Step 7: Fame
    elif step == 6:
        data["fame"] = update.message.text
        data["step"] += 1
        await update.message.reply_text("Send social media links with follower counts (one per line, e.g., 'URL 1.2M').")

    # Step 8: Social media links
    elif step == 7:
        lines = update.message.text.splitlines()
        for line in lines:
            parts = line.split()
            if not parts:
                continue
            url = parts[0]
            followers = " ".join(parts[1:]) if len(parts) > 1 else ""
            if "youtube.com" in url.lower():
                data["social_links"]["YouTube"] = {"count": followers, "url": url}
            elif "instagram.com" in url.lower():
                data["social_links"]["Instagram"] = {"count": followers, "url": url}
            elif "tiktok.com" in url.lower():
                data["social_links"]["TikTok"] = {"count": followers, "url": url}
        data["step"] += 1
        await update.message.reply_text("All social info saved. Type 'done' when ready to receive album and summary.")

    # Step 9: Done
    elif step == 8:
        if update.message.text.lower() == "done":
            # Create summary
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

            # Prepare albums
            media_files = [data["face_image"]] + data["images"] + data["videos"]
            max_per_album = 10
            total = len(media_files)
            chunk_size = max_per_album if total <= max_per_album else (total + 1) // ((total + max_per_album - 1) // max_per_album)
            albums = [media_files[i:i + chunk_size] for i in range(0, total, chunk_size)]

            # Send albums
            for album in albums:
                media_group = []
                for file_id in album:
                    if file_id in data["videos"]:
                        media_group.append(InputMediaVideo(file_id))
                    else:
                        media_group.append(InputMediaPhoto(file_id))
                await context.bot.send_media_group(chat_id, media_group)

            data["step"] += 1
        else:
            await update.message.reply_text("Type 'done' when you are ready to finish and get the summary and albums.")

# Quart web server
app = Quart(__name__)

@app.route("/")
async def index():
    return "Gatekeepers Telegram Bot is running!"

# Start Telegram bot in the background
async def start_bot():
    token = os.getenv("TELEGRAM_TOKEN")
    bot_app = ApplicationBuilder().token(token).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("restart", restart))
    bot_app.add_handler(MessageHandler(filters.ALL, handle_message))
    print("Telegram bot is running...")
    await bot_app.run_polling()

# Run both Quart and Telegram bot
def main():
    port = int(os.environ.get("PORT", 10000))
    loop = asyncio.get_event_loop()
    loop.create_task(start_bot())
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
