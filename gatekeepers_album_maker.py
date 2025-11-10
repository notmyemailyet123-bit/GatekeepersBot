# bot.py
"""
Gatekeepers Album Maker
Python 3.14
python-telegram-bot==20.3

How to run on Render (summary):
- Set environment variables:
    BOT_TOKEN = "1234:..."
    WEBHOOK_URL = "https://<your-service>.onrender.com/webhook"
- Deploy to Render as a web service that runs: python bot.py
- Render must allow port 8443 or change the port below to what Render exposes.
"""

import os
import asyncio
import logging
import math
import re
from typing import List, Dict, Any, Optional

import requests  # used for social scraping best-effort
from flask import Flask, request

from telegram import (
    Update, InputMediaPhoto, InputMediaVideo,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes,
    ConversationHandler, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # e.g. https://yourapp.onrender.com/webhook
if not BOT_TOKEN:
    raise RuntimeError("Please set BOT_TOKEN environment variable")

# Conversation states
(
    STATE_FACE,
    STATE_PHOTOS,
    STATE_VIDEOS,
    STATE_NAME,
    STATE_ALIAS,
    STATE_COUNTRY,
    STATE_FAME,
    STATE_SOCIALS,
    STATE_FINAL_CONFIRM,
) = range(9)

# Keyboard buttons
BTN_NEXT = "✅ Next"
BTN_DONE = "✅ Done"
BTN_RESTART = "/restart"

# Utility functions --------------------------------------------------------------------------------

def reset_user_data(user_data: Dict[str, Any]):
    user_data.clear()
    user_data.update({
        "face_file_id": None,
        "photos": [],     # list of file_ids for photos (other than face)
        "videos": [],     # list of file_ids for videos/gifs
        "name": None,
        "alias": None,
        "country": None,
        "fame": None,
        "social_links": [],  # list of urls
        "socials_parsed": {},  # map of platform -> (url, follower_count or None)
    })

def try_parse_social_followers(url: str, timeout: int = 6) -> Optional[int]:
    """
    Best-effort scraping to find follower counts on common social pages.
    Returns integer follower count if found; else None.
    NOTE: This is fragile. For production, use official APIs.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; GatekeepersAlbumMaker/1.0; +https://example.com/bot)"
        }
        resp = requests.get(url, headers=headers, timeout=timeout)
        text = resp.text

        # YouTube channel page (simple approaches)
        m = re.search(r'\"subscriberCountText\".*?\"simpleText\":\"([\d,\.KMB]+)', text)
        if m:
            return parse_shorthand_number(m.group(1))

        # Instagram: look for "edge_followed_by":{"count":12345}
        m = re.search(r'"edge_followed_by":\s*\{\s*"count":\s*([0-9]+)\s*\}', text)
        if m:
            return int(m.group(1))

        # TikTok: look for follower count in meta or JSON: "fans":1234
        m = re.search(r'"fans":\s*"?([0-9,]+)"?', text)
        if m:
            return int(m.group(1).replace(",", ""))

        # Generic appearance e.g. "1.2M followers" or "Followers: 123,456"
        m = re.search(r'([\d\.,]+)\s*(?:Followers|followers)', text)
        if m:
            return parse_shorthand_number(m.group(1))

    except Exception as e:
        logger.info("Error parsing followers for %s: %s", url, e)
    return None

def parse_shorthand_number(s: str) -> int:
    """
    Convert formats like '1.2M', '3,456' -> int.
    """
    s = s.strip().replace(",", "")
    m = re.match(r'^([\d\.]+)\s*([KkMmBb])?$', s)
    if not m:
        try:
            return int(s)
        except:
            return 0
    num = float(m.group(1))
    suffix = m.group(2)
    if not suffix:
        return int(num)
    if suffix.lower() == "k":
        return int(num * 1_000)
    if suffix.lower() == "m":
        return int(num * 1_000_000)
    if suffix.lower() == "b":
        return int(num * 1_000_000_000)
    return int(num)

def split_photos_into_albums(face_file_id: str, other_file_ids: List[str]) -> List[List[Dict[str, Any]]]:
    """
    Build albums such that:
    - Each album contains the face photo as the first item (duplicated across albums)
    - Telegram album max size = 10
    - Therefore each album may contain up to 9 other photos/videos after the face
    - Distribute other_file_ids evenly across albums (as evenly as possible)
    Returns list of albums; each album is list of media dicts: {"type":"photo"|"video", "file_id":...}
    NOTE: videos/gifs will be included where present in the 'other_file_ids' order.
    """
    if face_file_id is None:
        raise ValueError("face_file_id must be provided")

    # other_file_ids is presumed to be *only pictures* for the albums (we will include videos separately if desired)
    others = other_file_ids[:]
    # capacity per album for others (excluding face) = 9
    cap = 9
    if not others:
        # still create one album with only face
        return [[{"type": "photo", "file_id": face_file_id}]]

    n_albums = math.ceil(len(others) / cap)
    # even distribution: floor/ceil
    base = len(others) // n_albums
    remainder = len(others) % n_albums
    albums = []
    idx = 0
    for i in range(n_albums):
        count = base + (1 if i < remainder else 0)
        chunk = others[idx: idx + count]
        idx += count
        album = [{"type": "photo", "file_id": face_file_id}]
        for fid in chunk:
            album.append({"type": "photo", "file_id": fid})
        albums.append(album)
    return albums

def build_summary_text(user_data: Dict[str, Any]) -> str:
    """
    Produce exact output template:
    ^^^^^^^^^^^^^^^
    
    Name: -
    Alias: -
    Country: -
    Fame: -
    Top socials: 
    YouTube ( x ) - 
    Instagram ( x ) - 
    TikTok ( x ) -
    
    ===============
    """
    name = user_data.get("name") or "-"
    alias = user_data.get("alias") or "-"
    country = user_data.get("country") or "-"
    fame = user_data.get("fame") or "-"
    socials = user_data.get("socials_parsed", {})

    def social_line(platform: str):
        entry = socials.get(platform.lower())
        if entry:
            url, count = entry
            count_str = f"({count})" if (count is not None) else "( - )"
            return f"{platform} {count_str} - {url}"
        else:
            return f"{platform} ( - ) - "

    lines = [
        "^" * 15,
        "",
        f"Name: {name}",
        f"Alias: {alias}",
        f"Country: {country}",
        f"Fame: {fame}",
        "Top socials: ",
        f"YouTube {format_count_for_template(socials.get('youtube'))} -",
        f"Instagram {format_count_for_template(socials.get('instagram'))} -",
        f"TikTok {format_count_for_template(socials.get('tiktok'))} -",
        "",
        "=" * 15,
    ]
    # The user asked for exact format. To match their structure:
    # They wrote:
    # Name: -
    # Alias: -
    # Country: -
    # Fame: -
    # Top socials: 
    # YouTube ( x ) - 
    # Instagram ( x ) - 
    # TikTok ( x ) -
    #
    # We'll produce the same.
    return "\n".join(lines)

def format_count_for_template(entry):
    # entry is (url, count) or None
    if not entry:
        return "( x )"
    url, count = entry
    if count is None:
        return "( x )"
    return f"({count})"

# Bot handlers --------------------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start or restart the conversation."""
    reset_user_data(context.user_data)
    await update.message.reply_text(
        "Welcome to Gatekeepers Album Maker.\n\nStep 1: Send a normal face photo of the celebrity.",
        reply_markup=ReplyKeyboardMarkup([[BTN_RESTART]], one_time_keyboard=False, resize_keyboard=True)
    )
    return STATE_FACE

async def restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_user_data(context.user_data)
    await update.message.reply_text(
        "Restarting. Send the celebrity face photo to begin again.",
        reply_markup=ReplyKeyboardMarkup([[BTN_RESTART]], one_time_keyboard=False, resize_keyboard=True)
    )
    return STATE_FACE

async def face_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the face photo (single). Move to photo collection."""
    msg = update.message
    if not msg.photo:
        await msg.reply_text("Please send a photo (as a regular image).")
        return STATE_FACE
    # use the highest-resolution photo
    file_id = msg.photo[-1].file_id
    context.user_data.setdefault("face_file_id", file_id)
    await msg.reply_text(
        "Face photo saved. Now send all pictures you want to post (send as many as you like). "
        "When you're done sending pictures, click '✅ Next'.",
        reply_markup=ReplyKeyboardMarkup([[BTN_NEXT, BTN_RESTART]], one_time_keyboard=False, resize_keyboard=True)
    )
    # initialize lists if not present
    context.user_data.setdefault("photos", [])
    context.user_data.setdefault("videos", [])
    return STATE_PHOTOS

# PHOTOS COLLECTION
async def photos_collector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    While in photos collection state, silently save any photo messages.
    Do NOT reply to each image. Only when user sends BTN_NEXT do we confirm.
    """
    msg = update.message
    if msg.photo:
        file_id = msg.photo[-1].file_id
        context.user_data.setdefault("photos", []).append(file_id)
        # stay silent (no reply)
        return STATE_PHOTOS
    # If user sends other things (e.g., text), pass to text handler
    return STATE_PHOTOS

async def photos_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Confirm photos saved and move to videos stage
    n = len(context.user_data.get("photos", []))
    await update.message.reply_text(
        f"Saved {n} photo(s). Now send all videos/gifs you want to add. When you're done, click '✅ Next'.",
        reply_markup=ReplyKeyboardMarkup([[BTN_NEXT, BTN_RESTART]], one_time_keyboard=False, resize_keyboard=True)
    )
    return STATE_VIDEOS

# VIDEOS COLLECTION
async def videos_collector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Silently collect videos/gifs."""
    msg = update.message
    if msg.video or msg.document and msg.document.mime_type and "video" in msg.document.mime_type:
        # get video file_id
        if msg.video:
            fid = msg.video.file_id
        else:
            fid = msg.document.file_id
        context.user_data.setdefault("videos", []).append(fid)
        return STATE_VIDEOS
    if msg.animation:
        # GIFs (animation)
        fid = msg.animation.file_id
        context.user_data.setdefault("videos", []).append(fid)
        return STATE_VIDEOS
    return STATE_VIDEOS

async def videos_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    n = len(context.user_data.get("videos", []))
    await update.message.reply_text(
        f"Saved {n} video(s)/gif(s). Now send the person's full name (Step 4).",
        reply_markup=ReplyKeyboardMarkup([[BTN_RESTART]], one_time_keyboard=False, resize_keyboard=True)
    )
    return STATE_NAME

# Text input states
async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Got it. Now send alias / social handles (or '-' if none).")
    return STATE_ALIAS

async def receive_alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["alias"] = update.message.text.strip()
    await update.message.reply_text("Now send the person's country of origin.")
    return STATE_COUNTRY

async def receive_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["country"] = update.message.text.strip()
    await update.message.reply_text("Now send why the person is famous (a short phrase).")
    return STATE_FAME

async def receive_fame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fame"] = update.message.text.strip()
    await update.message.reply_text(
        "Now send the celebrity's social links (YouTube, Instagram, TikTok). Send each link as a separate message. "
        "When done, click '✅ Done'.",
        reply_markup=ReplyKeyboardMarkup([[BTN_DONE, BTN_RESTART]], one_time_keyboard=False, resize_keyboard=True)
    )
    context.user_data.setdefault("social_links", [])
    return STATE_SOCIALS

async def socials_collector(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt.lower() in {BTN_DONE.lower()}:
        # move to finalization
        return await socials_done(update, context)
    # simple validation of URLs
    if not (txt.startswith("http://") or txt.startswith("https://")):
        await update.message.reply_text("Please send a full link starting with http:// or https:// (or send '✅ Done').")
        return STATE_SOCIALS
    context.user_data.setdefault("social_links", []).append(txt)
    # stay silent while collecting (no confirmation on each link)
    return STATE_SOCIALS

async def socials_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    links: List[str] = context.user_data.get("social_links", [])
    parsed = {}
    # best-effort parsing
    for url in links:
        platform = identify_platform(url)
        count = None
        try:
            count = try_parse_social_followers(url)
        except Exception as e:
            logger.info("Failed parsing followers for %s: %s", url, e)
        parsed[platform] = (url, count)
    context.user_data["socials_parsed"] = parsed
    await update.message.reply_text("Social links saved. When you're ready, click '✅ Done' to finalize and create albums.",
                                   reply_markup=ReplyKeyboardMarkup([[BTN_DONE, BTN_RESTART]], one_time_keyboard=False, resize_keyboard=True))
    return STATE_FINAL_CONFIRM

async def finalize_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Assemble summary, send it, then send media albums (face at start of each)."""
    # Build summary exactly in required format
    summary = build_summary_text(context.user_data)
    # Send summary
    await update.message.reply_text(summary)

    # Prepare albums:
    face = context.user_data.get("face_file_id")
    photos = context.user_data.get("photos", [])
    videos = context.user_data.get("videos", [])

    # For albums we will use photos list; videos can be appended at end of albums or grouped separately.
    # For simplicity: include photos albums as requested (face first), then send videos as separate albums if any (also with face at start).
    albums = split_photos_into_albums(face, photos)

    # Send each album as a MediaGroup (only photos here)
    app = context.application
    chat_id = update.effective_chat.id

    for album in albums:
        media_group = []
        for i, item in enumerate(album):
            if item["type"] == "photo":
                media_group.append(InputMediaPhoto(media=item["file_id"]))
            else:
                media_group.append(InputMediaVideo(media=item["file_id"]))
        try:
            await app.bot.send_media_group(chat_id=chat_id, media=media_group)
        except Exception as e:
            logger.exception("Failed to send photo album: %s", e)
            # fallback: send individually
            for m in media_group:
                if isinstance(m, InputMediaPhoto):
                    await app.bot.send_photo(chat_id=chat_id, photo=m.media)
                else:
                    await app.bot.send_video(chat_id=chat_id, video=m.media)

    # If there are videos/gifs, create albums for them too (face first)
    if videos:
        # treat each video list similarly with face first (note that media types may mix)
        # We will group videos into albums up to 10 items (face + up to 9 videos)
        cap = 9
        n_albums = math.ceil(len(videos) / cap)
        idx = 0
        for i in range(n_albums):
            chunk = videos[idx: idx + cap]; idx += cap
            media_group = [InputMediaPhoto(media=face)]  # face as photo at start
            for fid in chunk:
                # assume video
                media_group.append(InputMediaVideo(media=fid))
            try:
                await app.bot.send_media_group(chat_id=chat_id, media=media_group)
            except Exception:
                # fallback
                for m in media_group:
                    if isinstance(m, InputMediaPhoto):
                        await app.bot.send_photo(chat_id=chat_id, photo=m.media)
                    else:
                        await app.bot.send_video(chat_id=chat_id, video=m.media)

    await update.message.reply_text("All done. You can forward the summary. Send /restart to create another album.")
    # Reset user_data to allow new session in same chat
    reset_user_data(context.user_data)
    return ConversationHandler.END

# Helpers --------------------------------------------------------------------------------------------
def identify_platform(url: str) -> str:
    url_l = url.lower()
    if "youtube.com" in url_l or "youtu.be" in url_l:
        return "youtube"
    if "instagram.com" in url_l:
        return "instagram"
    if "tiktok.com" in url_l:
        return "tiktok"
    # default to 'other'
    return "other"

# A simple message handler for unexpected text during flows
async def fallback_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Sorry, I didn't understand that. Use /restart to start over or follow the prompts.")
    return

# Entry point and webhook setup -----------------------------------------------------------------------
def create_app():
    # Build bot application
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            STATE_FACE: [
                MessageHandler(filters.PHOTO & ~filters.COMMAND, face_photo_handler),
                CommandHandler("restart", restart),
            ],
            STATE_PHOTOS: [
                MessageHandler(filters.TEXT & filters.Regex(f'^{re.escape(BTN_NEXT)}$', flags=re.I), photos_next),
                MessageHandler(filters.PHOTO & ~filters.COMMAND, photos_collector),
                CommandHandler("restart", restart),
            ],
            STATE_VIDEOS: [
                MessageHandler(filters.TEXT & filters.Regex(f'^{re.escape(BTN_NEXT)}$', flags=re.I), videos_next),
                MessageHandler(filters.VIDEO | filters.ANIMATION | (filters.Document.ATTR("mime_type") & filters.Regex("video")), videos_collector),
                CommandHandler("restart", restart),
            ],
            STATE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name),
                CommandHandler("restart", restart),
            ],
            STATE_ALIAS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_alias),
                CommandHandler("restart", restart),
            ],
            STATE_COUNTRY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_country),
                CommandHandler("restart", restart),
            ],
            STATE_FAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_fame),
                CommandHandler("restart", restart),
            ],
            STATE_SOCIALS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, socials_collector),
                CommandHandler("restart", restart),
            ],
            STATE_FINAL_CONFIRM: [
                MessageHandler(filters.TEXT & filters.Regex(f'^{re.escape(BTN_DONE)}$', flags=re.I), finalize_and_send),
                CommandHandler("restart", restart),
            ],
        },
        fallbacks=[CommandHandler("restart", restart)],
        allow_reentry=True,
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("restart", restart))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, fallback_text))

    return application

# Flask to accept webhook requests and pass to telegram Application
flask_app = Flask(__name__)
app_obj = create_app()

@flask_app.route("/webhook", methods=["POST"])
def webhook():
    # telegram will post updates here
    update = Update.de_json(request.get_json(force=True), app_obj.bot)
    # process update in asyncio loop
    asyncio.get_event_loop().create_task(app_obj.update_queue.put(update))
    return "", 200

if __name__ == "__main__":
    # set webhook on startup
    if not WEBHOOK_URL:
        raise RuntimeError("Please set WEBHOOK_URL environment variable (e.g. https://<your-app>.onrender.com/webhook)")

    # set webhook with Telegram
    import asyncio
    async def _run():
        await app_obj.bot.set_webhook(WEBHOOK_URL)
        logger.info("Webhook set to %s", WEBHOOK_URL)
        # start the application's internal run_polling to handle updates from queue
        await app_obj.start()
        # keep Flask running (we still need the WSGI server to forward POSTs to /webhook)
    loop = asyncio.get_event_loop()
    loop.create_task(_run())

    # Run Flask (on Render use port from environment, otherwise 8443)
    port = int(os.environ.get("PORT", "8443"))
    # Note: In production, Render will run this with a WSGI server like gunicorn. For local quick tests:
    flask_app.run(host="0.0.0.0", port=port)
