import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import os
import re

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

# Global storage for user sessions
user_sessions = {}

# Steps
STEPS = [
    "face_photo",
    "content_photos",
    "content_videos",
    "full_name",
    "alias",
    "country",
    "fame",
    "socials",
    "confirmation",
    "finished",
]

SOCIAL_PATTERNS = {
    "YouTube": r"(?:https?://)?(?:www\.)?youtube\.com/.*",
    "Instagram": r"(?:https?://)?(?:www\.)?instagram\.com/.*",
    "TikTok": r"(?:https?://)?(?:www\.)?tiktok\.com/.*"
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_sessions[user_id] = {
        "step": 0,
        "face_photo": None,
        "content_photos": [],
        "content_videos": [],
        "full_name": "",
        "alias": "",
        "country": "",
        "fame": "",
        "socials": {},
    }
    await update.message.reply_text("Welcome! Please send a normal face picture of the celebrity to start.")


async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_sessions:
        del user_sessions[user_id]
    await start(update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        await start(update, context)
        return

    session = user_sessions[user_id]
    step = STEPS[session["step"]]

    # Step 1: Face photo
    if step == "face_photo":
        if update.message.photo:
            session["face_photo"] = update.message.photo[-1].file_id
            session["step"] += 1
            await update.message.reply_text("Face photo saved! Now send all content photos. When done, send 'Done'.")
        else:
            await update.message.reply_text("Please send a photo of the celebrity's face.")

    # Step 2: Content photos
    elif step == "content_photos":
        if update.message.photo:
            session["content_photos"].append(update.message.photo[-1].file_id)
        elif update.message.text and update.message.text.lower() == "done":
            session["step"] += 1
            await update.message.reply_text("Photos saved! Now send all videos and gifs. Send 'Done' when finished.")
        else:
            await update.message.reply_text("Send photos or 'Done' when finished.")

    # Step 3: Videos & GIFs
    elif step == "content_videos":
        if update.message.video or update.message.animation:
            file_id = update.message.video.file_id if update.message.video else update.message.animation.file_id
            session["content_videos"].append(file_id)
        elif update.message.text and update.message.text.lower() == "done":
            session["step"] += 1
            await update.message.reply_text("Videos saved! Now send the celebrity's full name.")
        else:
            await update.message.reply_text("Send videos/gifs or 'Done' when finished.")

    # Step 4: Full name
    elif step == "full_name":
        session["full_name"] = update.message.text
        session["step"] += 1
        await update.message.reply_text("Got it! Now send the celebrity's alias or social media handles if any.")

    # Step 5: Alias
    elif step == "alias":
        session["alias"] = update.message.text
        session["step"] += 1
        await update.message.reply_text("Next, send the celebrity's country of origin.")

    # Step 6: Country
    elif step == "country":
        session["country"] = update.message.text
        session["step"] += 1
        await update.message.reply_text("Why is this person famous?")

    # Step 7: Fame
    elif step == "fame":
        session["fame"] = update.message.text
        session["step"] += 1
        await update.message.reply_text("Send celebrity's social media links (YouTube, Instagram, TikTok). Send 'Done' when finished.")

    # Step 8: Socials
    elif step == "socials":
        if update.message.text and update.message.text.lower() == "done":
            session["step"] += 1
            await generate_summary(update, context)
        else:
            for name, pattern in SOCIAL_PATTERNS.items():
                if re.match(pattern, update.message.text):
                    session["socials"][name] = update.message.text
                    await update.message.reply_text(f"{name} link saved.")
                    break

    # Step 9/10 handled in generate_summary
    else:
        await update.message.reply_text("Process complete. Use /restart to start over.")


async def generate_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session = user_sessions[user_id]

    summary = f"""^^^^^^^^^^^^^^^

Name: {session['full_name']}
Alias: {session['alias']}
Country: {session['country']}
Fame: {session['fame']}
Top socials:"""
    for platform in ["YouTube", "Instagram", "TikTok"]:
        link = session["socials"].get(platform, "-")
        followers = "x"  # Placeholder, implement scraping/parsing for real counts
        summary += f"\n{platform} ({followers}) - {link}"

    summary += "\n\n==============="

    await update.message.reply_text(summary)

    # Prepare media albums (photos + videos)
    face = session["face_photo"]
    photos = session["content_photos"]
    videos = session["content_videos"]

    all_media = [face] + photos + videos
    albums = []
    album_size = max(1, len(all_media) // ((len(all_media) - 1) // 10 + 1))  # Even split

    for i in range(0, len(all_media), album_size):
        media_group = []
        for m in all_media[i:i + album_size]:
            if m in photos or m == face:
                media_group.append(InputMediaPhoto(m))
            else:
                media_group.append(InputMediaVideo(m))
        albums.append(media_group)

    for album in albums:
        await context.bot.send_media_group(chat_id=update.effective_chat.id, media=album)

    session["step"] = len(STEPS) - 1  # Mark finished


if __name__ == "__main__":
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        raise ValueError("No TELEGRAM_BOT_TOKEN found in environment variables!")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("restart", restart))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO | filters.ANIMATION, handle_message))

    print("Bot is running...")
    app.run_polling()
