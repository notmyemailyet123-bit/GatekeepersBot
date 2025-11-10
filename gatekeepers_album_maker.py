import os
import asyncio
from flask import Flask, request
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN", "8302726230:AAGL6A89q7VfsQO5ViQKstGsAntL3f5bdRU")

# Flask setup
app = Flask(__name__)

# Telegram app setup
telegram_app = Application.builder().token(BOT_TOKEN).build()

# States
NAME, ALIAS, COUNTRY, FAME, SOCIALS, MEDIA, CONFIRM = range(7)

# Temporary storage
user_data = {}

# Helper function to create buttons
def next_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Next ➡️", callback_data="next")]])

def restart_exit_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 Restart", callback_data="restart"),
         InlineKeyboardButton("❌ Exit", callback_data="exit")]
    ])

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.effective_user.id] = {}
    await update.message.reply_text("Let's begin! What's the celebrity's full name?")
    return NAME

async def name_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.effective_user.id]["name"] = update.message.text.strip()
    await update.message.reply_text("Got it. What are their known aliases?", reply_markup=next_button())
    return ALIAS

async def alias_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.effective_user.id]["alias"] = update.message.text.strip()
    await update.message.reply_text("Nice. Which country are they from?", reply_markup=next_button())
    return COUNTRY

async def country_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.effective_user.id]["country"] = update.message.text.strip()
    await update.message.reply_text("Cool. What's their fame or profession?", reply_markup=next_button())
    return FAME

async def fame_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data[update.effective_user.id]["fame"] = update.message.text.strip()
    await update.message.reply_text("Drop their social links and follower counts (example: https://instagram.com/... 5.7M)", reply_markup=next_button())
    return SOCIALS

async def socials_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    socials = {}
    for part in text.split(","):
        part = part.strip()
        if " " in part:
            link, count = part.rsplit(" ", 1)
        else:
            link, count = part, "N/A"

        if "instagram" in link:
            socials["Instagram"] = (link, count)
        elif "tiktok" in link:
            socials["TikTok"] = (link, count)
        elif "youtube" in link:
            socials["YouTube"] = (link, count)
        else:
            socials["Other"] = (link, count)

    user_data[update.effective_user.id]["socials"] = socials
    await update.message.reply_text("Now send all their pictures and videos (up to 30 total).", reply_markup=next_button())
    return MEDIA

async def media_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_data[user_id]
    media_files = context.user_data.get("media_files", [])

    if update.message.photo:
        photo = update.message.photo[-1].file_id
        media_files.append(("photo", photo))
    elif update.message.video:
        video = update.message.video.file_id
        media_files.append(("video", video))
    context.user_data["media_files"] = media_files

    await update.message.reply_text("Received! Press 'Next' when done uploading.", reply_markup=next_button())
    return MEDIA

async def next_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    step_data = user_data.get(user_id, {})

    if "media_files" in context.user_data and "fame" in step_data:
        name = step_data.get("name", "Unknown")
        alias = step_data.get("alias", "N/A")
        country = step_data.get("country", "N/A")
        fame = step_data.get("fame", "N/A")
        socials = step_data.get("socials", {})
        media_files = context.user_data.get("media_files", [])

        socials_text = "\n".join(
            f"{platform} ({count}) - {link}"
            for platform, (link, count) in socials.items()
        )

        output = (
            f"^^^^^^^^^^^^^^^\n\n"
            f"Name: {name}\n"
            f"Alias: {alias}\n"
            f"Country: {country}\n"
            f"Fame: {fame}\n"
            f"Top socials:\n{socials_text}\n\n===============\n"
        )
        await query.message.reply_text(output)

        # Send media in batches of 10 or fewer
        batch = []
        for i, (mtype, fid) in enumerate(media_files):
            if mtype == "photo":
                batch.append(InputMediaPhoto(media=fid))
            else:
                batch.append(InputMediaVideo(media=fid))

            if len(batch) == 10 or i == len(media_files) - 1:
                await query.message.reply_media_group(batch)
                batch = []

        await query.message.reply_text("Would you like to restart or exit?", reply_markup=restart_exit_buttons())
        return CONFIRM
    else:
        await query.message.reply_text("Next question — please reply.", reply_markup=next_button())
        return ConversationHandler.END

async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "restart":
        user_data.pop(user_id, None)
        context.user_data.clear()
        await query.message.reply_text("Restarting the process...", reply_markup=None)
        await query.message.reply_text("Let's begin! What's the celebrity's full name?")
        return NAME
    elif query.data == "exit":
        await query.message.reply_text("Goodbye! 👋")
        user_data.pop(user_id, None)
        context.user_data.clear()
        return ConversationHandler.END

# Conversation handler
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_step)],
        ALIAS: [MessageHandler(filters.TEXT & ~filters.COMMAND, alias_step)],
        COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, country_step)],
        FAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, fame_step)],
        SOCIALS: [MessageHandler(filters.TEXT & ~filters.COMMAND, socials_step)],
        MEDIA: [MessageHandler(filters.ALL & ~filters.COMMAND, media_step)],
        CONFIRM: [CallbackQueryHandler(confirm_callback)],
    },
    fallbacks=[],
)

telegram_app.add_handler(conv_handler)
telegram_app.add_handler(CallbackQueryHandler(next_callback, pattern="^next$"))

# Webhook endpoint
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(), telegram_app.bot)
    telegram_app.update_queue.put_nowait(update)
    return "OK", 200

# Run the bot
if __name__ == "__main__":
    async def main():
        print("Webhook set successfully!")
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling()
        await telegram_app.stop()
    telegram_app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        url_path=BOT_TOKEN,
        webhook_url=f"https://gatekeepersbot.onrender.com/{BOT_TOKEN}"
    )
