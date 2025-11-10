import os
import re
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# User sessions storage
user_sessions = {}

STEPS = [
    "face_photo", "pictures", "videos_gifs", "full_name",
    "alias", "country", "fame", "socials", "done"
]

SOCIAL_PATTERNS = {
    "youtube": r"(?:https?://)?(?:www\.)?youtube\.com/.*",
    "instagram": r"(?:https?://)?(?:www\.)?instagram\.com/.*",
    "tiktok": r"(?:https?://)?(?:www\.)?tiktok\.com/.*"
}

# Start/restart command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_sessions[user_id] = {
        "step": 0,
        "face_photo": None,
        "pictures": [],
        "videos_gifs": [],
        "full_name": "",
        "alias": "",
        "country": "",
        "fame": "",
        "socials": {}
    }
    await update.message.reply_text("Welcome to Gatekeepers Album Maker! Send celebrity's normal face photo to start.")

# Handle messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await start(update, context)
        return

    session = user_sessions[user_id]
    step = STEPS[session["step"]]

    # Step 1: Face photo
    if step == "face_photo" and update.message.photo:
        session["face_photo"] = update.message.photo[-1].file_id
        session["step"] += 1
        await update.message.reply_text("Face photo saved. Now send pictures to include in the album. Send 'Done' when finished.")
        return

    # Step 2: Pictures
    if step == "pictures":
        if update.message.text and update.message.text.lower() == "done":
            session["step"] += 1
            await update.message.reply_text("Pictures saved. Now send videos and GIFs. Send 'Done' when finished.")
            return
        elif update.message.photo:
            session["pictures"].append(update.message.photo[-1].file_id)
            return  # stay quiet while receiving
        else:
            return

    # Step 3: Videos/GIFs
    if step == "videos_gifs":
        if update.message.text and update.message.text.lower() == "done":
            session["step"] += 1
            await update.message.reply_text("Videos/GIFs saved. Send celebrity's full name.")
            return
        elif update.message.video or update.message.animation:
            file_id = update.message.video.file_id if update.message.video else update.message.animation.file_id
            session["videos_gifs"].append(file_id)
            return
        else:
            return

    # Step 4: Full name
    if step == "full_name" and update.message.text:
        session["full_name"] = update.message.text.strip()
        session["step"] += 1
        await update.message.reply_text("Send celebrity's alias/social media handles (or '-' if none).")
        return

    # Step 5: Alias
    if step == "alias" and update.message.text:
        session["alias"] = update.message.text.strip()
        session["step"] += 1
        await update.message.reply_text("Send celebrity's country of origin.")
        return

    # Step 6: Country
    if step == "country" and update.message.text:
        session["country"] = update.message.text.strip()
        session["step"] += 1
        await update.message.reply_text("Send why the celebrity is famous.")
        return

    # Step 7: Fame
    if step == "fame" and update.message.text:
        session["fame"] = update.message.text.strip()
        session["step"] += 1
        await update.message.reply_text(
            "Send celebrity's social media links (YouTube, Instagram, TikTok) one at a time. Send 'Done' when finished."
        )
        return

    # Step 8: Socials
    if step == "socials" and update.message.text:
        text = update.message.text.strip()
        if text.lower() == "done":
            session["step"] += 1
            await generate_summary(update, context)
            return

        if text == "-":
            await update.message.reply_text("Skipped.")
            return

        # Extract follower number if provided in parentheses
        follower_match = re.search(r"\((\d+)\)$", text)
        followers = None
        if follower_match:
            followers = follower_match.group(1)
            text = text[:follower_match.start()].strip()

        # Detect platform automatically
        platform_name = None
        for name, pattern in SOCIAL_PATTERNS.items():
            if re.match(pattern, text, re.IGNORECASE):
                platform_name = name.capitalize()
                break
        if not platform_name:
            domain_match = re.search(r"https?://(?:www\.)?([^/]+)", text)
            if domain_match:
                platform_name = domain_match.group(1).split('.')[0].capitalize()
            else:
                platform_name = "Other"

        session["socials"][platform_name] = {"link": text, "followers": followers or "x"}
        await update.message.reply_text(f"{platform_name} link saved.")
        return

# Generate summary and albums
async def generate_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = user_sessions[user_id]

    summary = f"""^^^^^^^^^^^^^^^

Name: {session['full_name']}
Alias: {session['alias']}
Country: {session['country']}
Fame: {session['fame']}
Top socials:"""

    for platform, info in session["socials"].items():
        if info["link"] == "-":
            continue
        summary += f"\n{platform} ({info['followers']}) - {info['link']}"

    summary += "\n\n==============="
    await update.message.reply_text(summary)

    # Send albums (face photo first in each)
    all_files = [session["face_photo"]] + session["pictures"] + session["videos_gifs"]
    max_per_album = 10

    # Split into chunks evenly
    chunks = []
    n = len(all_files)
    if n <= max_per_album:
        chunks = [all_files]
    else:
        chunk_size = n // ((n + max_per_album - 1) // max_per_album)
        chunks = [all_files[i:i+chunk_size] for i in range(0, n, chunk_size)]

    for chunk in chunks:
        media_group = []
        for file_id in chunk:
            # Assume video if in videos_gifs, else photo
            if file_id in session["videos_gifs"]:
                media_group.append(InputMediaVideo(media=file_id))
            else:
                media_group.append(InputMediaPhoto(media=file_id))
        await context.bot.send_media_group(chat_id=update.effective_chat.id, media=media_group)

    await update.message.reply_text("Albums sent. You can /restart anytime to create another.")

# Main
def main():
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        raise ValueError("No TELEGRAM_BOT_TOKEN found in environment variables.")

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("restart", start))
    app.add_handler(MessageHandler(filters.ALL, handle_message))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
