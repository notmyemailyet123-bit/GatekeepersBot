import os
import asyncio
from quart import Quart, request, jsonify
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# Quart app
app = Quart(__name__)

# Bot token
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Step states
(
    STEP_FACE,
    STEP_IMAGES,
    STEP_VIDEOS,
    STEP_NAME,
    STEP_ALIAS,
    STEP_COUNTRY,
    STEP_FAME,
    STEP_SOCIALS,
    STEP_CONFIRM,
) = range(9)

# Store user data in memory
user_sessions = {}

# Function to split media into balanced albums
def split_albums(face, images, max_per_album=10):
    all_photos = [face] + images
    n = len(all_photos)
    # calculate balanced split
    k = n // max_per_album
    rem = n % max_per_album
    albums = []
    start = 0
    for i in range(max_per_album if k==0 else k + (1 if rem > 0 else 0)):
        end = start + (n // k if k else n) + (1 if rem > 0 else 0)
        albums.append(all_photos[start:end])
        start = end
        rem -= 1
        if start >= n:
            break
    return albums

# Helper to reset user session
def reset_session(user_id):
    user_sessions[user_id] = {
        "face": None,
        "images": [],
        "videos": [],
        "name": "",
        "alias": "",
        "country": "",
        "fame": "",
        "socials": [],
    }

# /start and /restart handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_session(update.effective_user.id)
    await update.message.reply_text("Welcome! Step 1: Send a normal face picture of the celebrity.")
    return STEP_FACE

# Step 1: face photo
async def handle_face(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.photo:
        user_sessions[user_id]["face"] = update.message.photo[-1].file_id
        await update.message.reply_text("Got it! Step 2: Send all images you want to include. Type 'done' when finished.")
        return STEP_IMAGES
    else:
        await update.message.reply_text("Please send a photo of the celebrity's face.")
        return STEP_FACE

# Step 2: images
async def handle_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.text and update.message.text.lower() == "done":
        await update.message.reply_text("Step 3: Send all videos/GIFs. Type 'done' when finished.")
        return STEP_VIDEOS
    elif update.message.photo:
        user_sessions[user_id]["images"].append(update.message.photo[-1].file_id)
        return STEP_IMAGES  # stay silent while collecting
    else:
        return STEP_IMAGES

# Step 3: videos/gifs
async def handle_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.text and update.message.text.lower() == "done":
        await update.message.reply_text("Step 4: Send the celebrity's full name.")
        return STEP_NAME
    elif update.message.video or update.message.animation:
        if update.message.video:
            user_sessions[user_id]["videos"].append(update.message.video.file_id)
        else:
            user_sessions[user_id]["videos"].append(update.message.animation.file_id)
        return STEP_VIDEOS
    else:
        return STEP_VIDEOS

# Step 4: full name
async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_sessions[update.effective_user.id]["name"] = update.message.text
    await update.message.reply_text("Step 5: Send the celebrity's alias or social media handles (or type '-' if none).")
    return STEP_ALIAS

# Step 5: alias
async def handle_alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_sessions[update.effective_user.id]["alias"] = update.message.text
    await update.message.reply_text("Step 6: Send the celebrity's country of origin.")
    return STEP_COUNTRY

# Step 6: country
async def handle_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_sessions[update.effective_user.id]["country"] = update.message.text
    await update.message.reply_text("Step 7: Why is the celebrity famous?")
    return STEP_FAME

# Step 7: fame
async def handle_fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_sessions[update.effective_user.id]["fame"] = update.message.text
    await update.message.reply_text("Step 8: Send social links (YouTube, Instagram, TikTok). Separate by newlines.")
    return STEP_SOCIALS

# Step 8: socials
async def handle_socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_sessions[update.effective_user.id]["socials"] = update.message.text.split("\n")
    await update.message.reply_text("Step 9: Type 'done' when you are finished with socials.")
    return STEP_CONFIRM

# Step 9: confirm
async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() == "done":
        user_id = update.effective_user.id
        data = user_sessions[user_id]

        # Step 10: assemble albums
        albums = split_albums(data["face"], data["images"], max_per_album=10)

        # Send summary
        summary_text = f"""^^^^^^^^^^^^^^^

Name: {data['name']}
Alias: {data['alias']}
Country: {data['country']}
Fame: {data['fame']}
Top socials:
"""
        for link in data["socials"]:
            summary_text += f"{link}\n"
        summary_text += "\n==============="
        await update.message.reply_text(summary_text)

        # Send albums
        for album in albums:
            media = [InputMediaPhoto(file_id) for file_id in album]
            if media:
                await context.bot.send_media_group(chat_id=user_id, media=media)

        await update.message.reply_text("All done! You can /restart anytime to create another album.")
        return ConversationHandler.END
    else:
        await update.message.reply_text("Please type 'done' when finished with socials.")
        return STEP_CONFIRM

# Conversation handler
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start), CommandHandler("restart", start)],
    states={
        STEP_FACE: [MessageHandler(filters.PHOTO, handle_face)],
        STEP_IMAGES: [MessageHandler(filters.PHOTO | filters.TEXT, handle_images)],
        STEP_VIDEOS: [MessageHandler(filters.VIDEO | filters.ANIMATION | filters.TEXT, handle_videos)],
        STEP_NAME: [MessageHandler(filters.TEXT, handle_name)],
        STEP_ALIAS: [MessageHandler(filters.TEXT, handle_alias)],
        STEP_COUNTRY: [MessageHandler(filters.TEXT, handle_country)],
        STEP_FAME: [MessageHandler(filters.TEXT, handle_fame)],
        STEP_SOCIALS: [MessageHandler(filters.TEXT, handle_socials)],
        STEP_CONFIRM: [MessageHandler(filters.TEXT, handle_confirm)],
    },
    fallbacks=[CommandHandler("restart", start)],
)

# Telegram bot app
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
telegram_app.add_handler(conv_handler)

# Quart webhook route
@app.route("/", methods=["POST"])
async def webhook():
    data = await request.get_json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.update_queue.put(update)
    return jsonify({"status": "ok"})

# Run on Render
if __name__ == "__main__":
    import hypercorn.asyncio
    import hypercorn.config
    config = hypercorn.config.Config()
    config.bind = ["0.0.0.0:10000"]
    asyncio.run(hypercorn.asyncio.serve(app, config))
