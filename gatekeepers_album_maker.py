import math
from telegram import Update, ReplyKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Conversation states
FACE, PICTURES, VIDEOS, NAME, ALIAS, COUNTRY, FAME, SOCIALS, CONFIRM = range(9)

# Split media into albums evenly, with face photo first only in the first album
def split_albums(face_id, media_list):
    total_items = len(media_list)
    if total_items == 0:
        return [[face_id]]

    # Calculate how many albums needed to keep each album <= 10
    max_per_album = 10
    num_albums = math.ceil((total_items + 1) / max_per_album)  # +1 for face
    chunk_sizes = []

    base = total_items // num_albums
    extra = total_items % num_albums
    for i in range(num_albums):
        chunk_sizes.append(base + (1 if i < extra else 0))

    albums = []
    start_idx = 0
    for i, size in enumerate(chunk_sizes):
        if i == 0:
            # First album starts with face
            albums.append([face_id] + media_list[start_idx:start_idx + size])
        else:
            albums.append(media_list[start_idx:start_idx + size])
        start_idx += size
    return albums

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data['current_state'] = FACE
    await update.message.reply_text("Welcome to Gatekeepers Album Maker!\nSend a clear face picture of the celebrity first.")
    return FACE

# Handle face photo
async def handle_face(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data['face'] = update.message.photo[-1].file_id
        context.user_data['pictures'] = []
        context.user_data['videos'] = []
        context.user_data['current_state'] = PICTURES
        await update.message.reply_text("Face received! Now send all the pictures you want to post. When done, type /next.")
        return PICTURES
    await update.message.reply_text("Please send a face photo.")
    return FACE

# Handle pictures
async def handle_pictures(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        context.user_data['pictures'].append(update.message.photo[-1].file_id)
    return PICTURES

# Handle videos and GIFs
async def handle_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.video or update.message.animation:
        file_id = update.message.video.file_id if update.message.video else update.message.animation.file_id
        context.user_data['videos'].append(file_id)
    return VIDEOS

# Move to next step command
async def next_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_state = context.user_data.get('current_state')
    if current_state == PICTURES:
        context.user_data['current_state'] = VIDEOS
        await update.message.reply_text("All pictures received! Now send all videos or GIFs. Type /next when done.")
        return VIDEOS
    elif current_state == VIDEOS:
        context.user_data['current_state'] = NAME
        await update.message.reply_text("Videos received! Now send the celebrity's full name.")
        return NAME
    return ConversationHandler.END

# Text info handlers
async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Send the celebrity's alias or social handles (or type '-' if none).")
    return ALIAS

async def handle_alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['alias'] = update.message.text
    await update.message.reply_text("Send the celebrity's country of origin.")
    return COUNTRY

async def handle_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['country'] = update.message.text
    await update.message.reply_text("Why is this person famous?")
    return FAME

async def handle_fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['fame'] = update.message.text
    await update.message.reply_text("Send celebrity social links (YouTube, Instagram, TikTok), separated by space or newline.")
    return SOCIALS

# Social links handler
async def handle_socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    socials = {'YouTube': '-', 'Instagram': '-', 'TikTok': '-'}
    for line in text.split():
        if 'youtube' in line.lower():
            socials['YouTube'] = line + " (x)"
        elif 'instagram' in line.lower():
            socials['Instagram'] = line + " (x)"
        elif 'tiktok' in line.lower():
            socials['TikTok'] = line + " (x)"
    context.user_data['socials'] = socials

    keyboard = [["Done"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("All info collected! Press 'Done' to finish and receive the album.", reply_markup=reply_markup)
    return CONFIRM

# Send final album and summary
async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    face_id = context.user_data['face']
    media_list = context.user_data['pictures'] + context.user_data['videos']

    albums = split_albums(face_id, media_list)

    # Send albums
    for album in albums:
        media_group = []
        for item in album:
            if item in context.user_data['pictures']:
                media_group.append(InputMediaPhoto(item))
            else:
                media_group.append(InputMediaVideo(item))
        await update.message.reply_media_group(media_group)

    # Send summary
    summary = f"""
^^^^^^^^^^^^^^^

Name: {context.user_data['name']}
Alias: {context.user_data['alias']}
Country: {context.user_data['country']}
Fame: {context.user_data['fame']}
Top socials: 
YouTube {context.user_data['socials']['YouTube']}
Instagram {context.user_data['socials']['Instagram']}
TikTok {context.user_data['socials']['TikTok']}

===============
"""
    await update.message.reply_text(summary)
    context.user_data.clear()
    return ConversationHandler.END

# Restart command
async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

# Cancel command
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Process canceled. You can start again with /start.")
    context.user_data.clear()
    return ConversationHandler.END

# Conversation handler
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        FACE: [MessageHandler(filters.PHOTO, handle_face)],
        PICTURES: [
            MessageHandler(filters.PHOTO, handle_pictures),
            CommandHandler('next', next_step)
        ],
        VIDEOS: [
            MessageHandler(filters.VIDEO | filters.ANIMATION, handle_videos),
            CommandHandler('next', next_step)
        ],
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
        ALIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_alias)],
        COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_country)],
        FAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_fame)],
        SOCIALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_socials)],
        CONFIRM: [MessageHandler(filters.Regex('^Done$'), handle_confirm)],
    },
    fallbacks=[CommandHandler('restart', restart), CommandHandler('cancel', cancel)],
)

# Application setup
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(conv_handler)

if __name__ == "__main__":
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", "8443")),
        webhook_url=f"https://yourapp.onrender.com/{BOT_TOKEN}"
    )
