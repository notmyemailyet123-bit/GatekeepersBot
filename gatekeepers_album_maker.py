import os
import logging
from telegram import Update, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# -----------------------------
# States for ConversationHandler
# -----------------------------
STEP_FACE, STEP_PHOTOS, STEP_VIDEOS, STEP_NAME, STEP_ALIAS, STEP_COUNTRY, STEP_FAME, STEP_SOCIALS, STEP_DONE = range(9)

# -----------------------------
# Helper Functions
# -----------------------------
def split_into_albums(items, max_per_album=10):
    """Split a list into multiple lists with roughly even number of items."""
    if not items:
        return []
    total = len(items)
    num_albums = (total + max_per_album - 1) // max_per_album  # ceil division
    base_size = total // num_albums
    remainder = total % num_albums
    albums = []
    index = 0
    for i in range(num_albums):
        size = base_size + (1 if i < remainder else 0)
        albums.append(items[index:index + size])
        index += size
    return albums

def format_output(user_data):
    """Return the formatted output template"""
    return f"""^^^^^^^^^^^^^^^

Name: {user_data.get('name', '-')}
Alias: {user_data.get('alias', '-')}
Country: {user_data.get('country', '-')}
Fame: {user_data.get('fame', '-')}

Top socials:
YouTube ({user_data.get('youtube_followers', '-')}) - {user_data.get('youtube', '-')}
Instagram ({user_data.get('instagram_followers', '-')}) - {user_data.get('instagram', '-')}
TikTok ({user_data.get('tiktok_followers', '-')}) - {user_data.get('tiktok', '-')}

===============
"""

# -----------------------------
# Handlers
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start / restart"""
    context.user_data.clear()
    context.user_data['photos'] = []
    context.user_data['videos'] = []
    await update.message.reply_text("Welcome! Step 1: Send a normal face picture of the celebrity.")
    return STEP_FACE

async def face_picture(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 1: Save the face photo"""
    if not update.message.photo:
        await update.message.reply_text("Please send a photo (not text).")
        return STEP_FACE
    file = await update.message.photo[-1].get_file()
    path = f"temp_face_{update.effective_user.id}.jpg"
    await file.download_to_drive(path)
    context.user_data['face'] = path
    await update.message.reply_text("Face photo received! Step 2: Send all other pictures. Send /next when done.")
    return STEP_PHOTOS

async def photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 2: Save additional photos"""
    if update.message.text == "/next":
        await update.message.reply_text(f"Received {len(context.user_data['photos'])} photos. Step 3: Send all videos and gifs. Send /next when done.")
        return STEP_VIDEOS
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        path = f"photo_{len(context.user_data['photos'])}_{update.effective_user.id}.jpg"
        await file.download_to_drive(path)
        context.user_data['photos'].append(path)
    return STEP_PHOTOS

async def videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 3: Save videos/gifs"""
    if update.message.text == "/next":
        await update.message.reply_text("Step 4: Send the celebrity's full name.")
        return STEP_NAME
    if update.message.video or update.message.animation:
        file = update.message.video or update.message.animation
        file_obj = await file.get_file()
        path = f"video_{len(context.user_data['videos'])}_{update.effective_user.id}.mp4"
        await file_obj.download_to_drive(path)
        context.user_data['videos'].append(path)
    return STEP_VIDEOS

async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 4: Save full name"""
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Step 5: Send the celebrity's alias/social media handles (or type '-' if none).")
    return STEP_ALIAS

async def alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 5: Save alias"""
    context.user_data['alias'] = update.message.text
    await update.message.reply_text("Step 6: Send the celebrity's country of origin.")
    return STEP_COUNTRY

async def country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 6: Save country"""
    context.user_data['country'] = update.message.text
    await update.message.reply_text("Step 7: Send why the person is famous.")
    return STEP_FAME

async def fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 7: Save fame reason"""
    context.user_data['fame'] = update.message.text
    await update.message.reply_text("Step 8: Send social links (YouTube, Instagram, TikTok). Separate by commas. Type '-' if none.")
    return STEP_SOCIALS

async def socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 8: Save socials"""
    text = update.message.text.split(",")
    context.user_data['youtube'] = text[0].strip() if len(text) > 0 else '-'
    context.user_data['instagram'] = text[1].strip() if len(text) > 1 else '-'
    context.user_data['tiktok'] = text[2].strip() if len(text) > 2 else '-'

    # For now, placeholder follower counts
    context.user_data['youtube_followers'] = 'x'
    context.user_data['instagram_followers'] = 'x'
    context.user_data['tiktok_followers'] = 'x'

    await update.message.reply_text("All info received. Step 9: Type /done when you are ready to assemble the album.")
    return STEP_DONE

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 9 & 10: Assemble album and send"""
    user_data = context.user_data
    media = [user_data['face']] + user_data.get('photos', [])

    albums = split_into_albums(media, 10)

    # Send summary first
    await update.message.reply_text(format_output(user_data))

    # Send albums
    for album in albums:
        media_group = [InputMediaPhoto(open(photo, "rb")) for photo in album]
        await update.message.reply_media_group(media_group)

    await update.message.reply_text("Album creation complete! You can /restart anytime to make another album.")
    return ConversationHandler.END

# -----------------------------
# Conversation Handler
# -----------------------------
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        STEP_FACE: [MessageHandler(filters.PHOTO, face_picture)],
        STEP_PHOTOS: [
            MessageHandler(filters.PHOTO, photos),
            CommandHandler('next', photos)
        ],
        STEP_VIDEOS: [
            MessageHandler(filters.VIDEO | filters.ANIMATION, videos),
            CommandHandler('next', videos)
        ],
        STEP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name)],
        STEP_ALIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, alias)],
        STEP_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country)],
        STEP_FAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, fame)],
        STEP_SOCIALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, socials)],
        STEP_DONE: [CommandHandler('done', done)]
    },
    fallbacks=[CommandHandler('restart', start)]
)

# -----------------------------
# Application
# -----------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN not set in environment variables!")
    exit(1)

application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(conv_handler)

PORT = int(os.environ.get("PORT", 10000))
WEBHOOK_URL = f"https://gatekeepersbot.onrender.com/"

logger.info(f"Starting Gatekeepers Album Maker on webhook {WEBHOOK_URL}")

application.run_webhook(
    listen="0.0.0.0",
    port=PORT,
    url_path="",
    webhook_url=WEBHOOK_URL
)
