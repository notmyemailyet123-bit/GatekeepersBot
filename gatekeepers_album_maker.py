import os
from dotenv import load_dotenv
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Conversation states
FACE, PHOTOS, VIDEOS, FULL_NAME, ALIAS, COUNTRY, FAME, SOCIALS, DONE = range(9)

# Temporary storage
user_data_store = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id] = {
        "face": None,
        "photos": [],
        "videos": [],
        "full_name": "",
        "alias": "",
        "country": "",
        "fame": "",
        "socials": {}
    }
    await update.message.reply_text("Send a normal face picture of the celebrity.")
    return FACE

# Step 1: Face
async def face(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not update.message.photo:
        await update.message.reply_text("Please send a photo.")
        return FACE
    user_data_store[user_id]["face"] = update.message.photo[-1].file_id
    await update.message.reply_text("Now send all photos you want to post. Send 'Done' when finished.")
    return PHOTOS

# Step 2: Photos
async def photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.text and update.message.text.lower() == "done":
        await update.message.reply_text("Photos saved. Now send all videos and gifs. Send 'Done' when finished.")
        return VIDEOS
    if update.message.photo:
        user_data_store[user_id]["photos"].append(update.message.photo[-1].file_id)
        return PHOTOS
    return PHOTOS

# Step 3: Videos
async def videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.text and update.message.text.lower() == "done":
        await update.message.reply_text("Videos saved. Send celebrity's full name.")
        return FULL_NAME
    if update.message.video or update.message.document and (update.message.document.mime_type.startswith("video") or update.message.document.mime_type in ["image/gif", "video/mp4"]):
        file_id = update.message.video.file_id if update.message.video else update.message.document.file_id
        user_data_store[user_id]["videos"].append(file_id)
        return VIDEOS
    return VIDEOS

# Step 4: Full Name
async def full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id]["full_name"] = update.message.text
    await update.message.reply_text("Send celebrity's alias/social media handles if they have one (or '-' if none).")
    return ALIAS

# Step 5: Alias
async def alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id]["alias"] = update.message.text
    await update.message.reply_text("Send celebrity's country of origin.")
    return COUNTRY

# Step 6: Country
async def country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id]["country"] = update.message.text
    await update.message.reply_text("Send why the person is famous.")
    return FAME

# Step 7: Fame
async def fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_store[user_id]["fame"] = update.message.text
    await update.message.reply_text(
        "Send celebrity's social media links (YouTube, Instagram, TikTok) one at a time. Send 'Done' when finished. "
        "If they don't have a platform, send '-' for that."
    )
    return SOCIALS

# Step 8: Socials
async def socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if text.lower() == "done":
        await update.message.reply_text("All data collected. Generating album and summary...")
        return await generate_summary(update, context)
    
    # Identify social platform by URL or name
    platform = None
    if "youtube.com" in text.lower():
        platform = "YouTube"
    elif "instagram.com" in text.lower():
        platform = "Instagram"
    elif "tiktok.com" in text.lower():
        platform = "TikTok"
    else:
        # For any other, just use the domain name
        platform = text.split("/")[2] if "/" in text else text

    if text != "-":
        user_data_store[user_id]["socials"][platform] = text
    return SOCIALS

# Generate album & summary
async def generate_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_data_store[user_id]

    # Assemble text summary
    summary_lines = [
        f"Name: {data['full_name']}",
    ]
    if data["alias"] != "-":
        summary_lines.append(f"Alias: {data['alias']}")
    summary_lines.append(f"Country: {data['country']}")
    summary_lines.append(f"Fame: {data['fame']}")
    if data["socials"]:
        summary_lines.append("Top socials:")
        for platform, link in data["socials"].items():
            summary_lines.append(f"{platform} - {link}")
    summary = "\n".join(summary_lines)
    await update.message.reply_text(summary)

    # Send albums in batches of 10 (face photo first)
    all_media = [InputMediaPhoto(media=data["face"])] + \
                [InputMediaPhoto(media=p) for p in data["photos"]] + \
                [InputMediaVideo(media=v) for v in data["videos"]]
    batch_size = 10
    for i in range(0, len(all_media), batch_size):
        await update.message.reply_media_group(all_media[i:i+batch_size])

    await update.message.reply_text("Album and summary completed. Use /restart to start again.")
    return ConversationHandler.END

# Restart
async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

# Cancel
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Process canceled. Use /start to begin again.")
    return ConversationHandler.END

# Set up ConversationHandler
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        FACE: [MessageHandler(filters.PHOTO, face)],
        PHOTOS: [MessageHandler(filters.PHOTO | filters.TEXT, photos)],
        VIDEOS: [MessageHandler(filters.VIDEO | filters.Document.ALL | filters.TEXT, videos)],
        FULL_NAME: [MessageHandler(filters.TEXT, full_name)],
        ALIAS: [MessageHandler(filters.TEXT, alias)],
        COUNTRY: [MessageHandler(filters.TEXT, country)],
        FAME: [MessageHandler(filters.TEXT, fame)],
        SOCIALS: [MessageHandler(filters.TEXT, socials)],
    },
    fallbacks=[CommandHandler("restart", restart), CommandHandler("cancel", cancel)],
)

# Build app
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(conv_handler)
app.add_handler(CommandHandler("restart", restart))
app.add_handler(CommandHandler("cancel", cancel))

if __name__ == "__main__":
    app.run_polling()
