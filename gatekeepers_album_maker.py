import os
import math
import asyncio
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from flask import Flask, request

# ===============================
# STEP ENUMS
# ===============================
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

# ===============================
# FLASK APP
# ===============================
flask_app = Flask(__name__)

# ===============================
# TELEGRAM BOT SETUP
# ===============================
TOKEN = os.getenv("BOT_TOKEN")
application = ApplicationBuilder().token(TOKEN).build()

# ===============================
# USER DATA HANDLING
# ===============================
users_data = {}

# ===============================
# HELPER FUNCTIONS
# ===============================

def split_evenly(lst, n):
    """Split a list into n roughly equal parts."""
    k, m = divmod(len(lst), n)
    return [lst[i*k + min(i, m):(i+1)*k + min(i+1, m)] for i in range(n)]

async def assemble_albums(chat_id, context: ContextTypes.DEFAULT_TYPE):
    data = users_data.get(chat_id)
    if not data:
        return

    media = [data['face']] + data['images'] + data['videos']
    total_files = len(media)
    # Split into roughly equal albums, max 10 per album
    num_albums = math.ceil(total_files / 10)
    albums = split_evenly(media, num_albums)

    for album in albums:
        input_media = []
        for item in album:
            if item['type'] == 'photo':
                input_media.append(InputMediaPhoto(item['file_id']))
            else:
                input_media.append(InputMediaVideo(item['file_id']))
        await context.bot.send_media_group(chat_id=chat_id, media=input_media)

async def send_summary(chat_id, context: ContextTypes.DEFAULT_TYPE):
    data = users_data.get(chat_id)
    if not data:
        return
    summary = f"""
^^^^^^^^^^^^^^^

Name: {data.get('name','-')}
Alias: {data.get('alias','-')}
Country: {data.get('country','-')}
Fame: {data.get('fame','-')}
Top socials:
YouTube ({data.get('youtube','x')})
Instagram ({data.get('instagram','x')})
TikTok ({data.get('tiktok','x')})

===============
"""
    await context.bot.send_message(chat_id=chat_id, text=summary)

# ===============================
# COMMANDS
# ===============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    users_data[chat_id] = {
        'images': [],
        'videos': [],
    }
    await update.message.reply_text("Send the celebrity's face photo first.")
    return STEP_FACE

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

# ===============================
# MESSAGE HANDLERS
# ===============================
async def handle_face(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    photo = update.message.photo[-1]  # best quality
    users_data[chat_id]['face'] = {'type':'photo','file_id':photo.file_id}
    await update.message.reply_text("Face received. Send the images you want to add. Send /next when done.")
    return STEP_IMAGES

async def handle_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.message.photo:
        photo = update.message.photo[-1]
        users_data[chat_id]['images'].append({'type':'photo','file_id':photo.file_id})
    return STEP_IMAGES

async def next_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Images saved. Now send videos or GIFs. Send /next when done.")
    return STEP_VIDEOS

async def handle_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.message.video:
        users_data[chat_id]['videos'].append({'type':'video','file_id':update.message.video.file_id})
    elif update.message.animation:
        users_data[chat_id]['videos'].append({'type':'video','file_id':update.message.animation.file_id})
    return STEP_VIDEOS

async def next_videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Videos saved. Send celebrity's full name.")
    return STEP_NAME

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    users_data[chat_id]['name'] = update.message.text
    await update.message.reply_text("Send alias/social media handles.")
    return STEP_ALIAS

async def handle_alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    users_data[chat_id]['alias'] = update.message.text
    await update.message.reply_text("Send country of origin.")
    return STEP_COUNTRY

async def handle_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    users_data[chat_id]['country'] = update.message.text
    await update.message.reply_text("Send why the person is famous.")
    return STEP_FAME

async def handle_fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    users_data[chat_id]['fame'] = update.message.text
    await update.message.reply_text("Send social media links in format: YouTube Instagram TikTok")
    return STEP_SOCIALS

async def handle_socials(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    # Simple parser: split by spaces
    links = update.message.text.split()
    users_data[chat_id]['youtube'] = links[0] if len(links) > 0 else 'x'
    users_data[chat_id]['instagram'] = links[1] if len(links) > 1 else 'x'
    users_data[chat_id]['tiktok'] = links[2] if len(links) > 2 else 'x'
    await update.message.reply_text("All done! Sending albums and summary...")
    await send_summary(chat_id, context)
    await assemble_albums(chat_id, context)
    return ConversationHandler.END

# ===============================
# CONVERSATION HANDLER
# ===============================
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        STEP_FACE: [MessageHandler(filters.PHOTO, handle_face)],
        STEP_IMAGES: [
            MessageHandler(filters.PHOTO, handle_images),
            CommandHandler("next", next_images),
        ],
        STEP_VIDEOS: [
            MessageHandler(filters.VIDEO | filters.ANIMATION, handle_videos),
            CommandHandler("next", next_videos),
        ],
        STEP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
        STEP_ALIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_alias)],
        STEP_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_country)],
        STEP_FAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_fame)],
        STEP_SOCIALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_socials)],
    },
    fallbacks=[CommandHandler("restart", restart)],
)

application.add_handler(conv_handler)

# ===============================
# FLASK WEBHOOK
# ===============================
@flask_app.route("/", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)
    asyncio.create_task(application.update_queue.put(update))
    return "OK"

# ===============================
# RUN FLASK
# ===============================
if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
