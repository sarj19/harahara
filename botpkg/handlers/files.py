"""File transfer handlers: download, upload, file_receive."""
import os
import time

from botpkg import bot, logger, AUTHORIZED_USER_ID
from settings import DOWNLOADS_DIR
from botpkg.utils import send_file_smart

# ─── Pending upload target (chat_id → path or None) ───
_pending_uploads = {}


def handle_download(message, chat_id, text):
    """Send a file from Mac to Telegram."""
    args = text.split(" ", 1)[1].strip() if " " in text else ""
    if not args:
        bot.reply_to(message, "Usage: `/download <path>`\nExample: `/download ~/Documents/report.pdf`", parse_mode="Markdown")
        return
    path = os.path.expanduser(args)
    if not os.path.exists(path):
        bot.reply_to(message, f"❌ File not found: `{args}`", parse_mode="Markdown")
        return
    if os.path.isdir(path):
        bot.reply_to(message, "❌ Path is a directory. Specify a file.")
        return
    try:
        success = send_file_smart(chat_id, path, caption=os.path.basename(path))
        if success:
            bot.reply_to(message, f"📤 Sent: `{args}`", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Failed to send file.")
    except Exception as e:
        bot.reply_to(message, f"❌ Download error: {e}")
        logger.error(f"Download error: {e}")


def handle_upload(message, chat_id, text):
    """Set a target directory for the next incoming file."""
    args = text.split(" ", 1)[1].strip() if " " in text else ""
    if args:
        target = os.path.expanduser(args)
        _pending_uploads[chat_id] = target
        bot.reply_to(message, f"📂 Next file will be saved to: `{args}`\nSend a file now.", parse_mode="Markdown")
    else:
        _pending_uploads[chat_id] = DOWNLOADS_DIR
        home = os.path.expanduser("~")
        display = DOWNLOADS_DIR.replace(home, "~")
        bot.reply_to(message, f"📂 Next file will be saved to: `{display}`\nSend a file now.", parse_mode="Markdown")
    logger.info(f"Upload target set: {_pending_uploads.get(chat_id)}")


def handle_file_receive(message):
    """Save incoming files from Telegram to the downloads directory."""
    if message.from_user.id != AUTHORIZED_USER_ID:
        bot.reply_to(message, "Unauthorized access.")
        return

    import botpkg
    botpkg.last_interaction_time = time.time()

    chat_id = message.chat.id

    try:
        if message.content_type == 'document':
            file_info = bot.get_file(message.document.file_id)
            filename = message.document.file_name or f"file_{int(time.time())}"
        elif message.content_type == 'photo':
            photo = message.photo[-1]
            file_info = bot.get_file(photo.file_id)
            filename = f"photo_{int(time.time())}.jpg"
        elif message.content_type == 'audio':
            file_info = bot.get_file(message.audio.file_id)
            filename = message.audio.file_name or f"audio_{int(time.time())}.mp3"
        elif message.content_type == 'video':
            file_info = bot.get_file(message.video.file_id)
            filename = message.video.file_name or f"video_{int(time.time())}.mp4"
        else:
            return

        save_dir = _pending_uploads.pop(chat_id, None) or DOWNLOADS_DIR
        os.makedirs(save_dir, exist_ok=True)

        save_path = os.path.join(save_dir, filename)
        downloaded = bot.download_file(file_info.file_path)
        with open(save_path, "wb") as f:
            f.write(downloaded)

        home = os.path.expanduser("~")
        display_path = save_path.replace(home, "~") if save_path.startswith(home) else save_path
        bot.reply_to(message, f"📥 Saved: `{display_path}`", parse_mode="Markdown")
        logger.info(f"File received and saved: {save_path}")
    except Exception as e:
        bot.reply_to(message, f"❌ File save error: {e}")
        logger.error(f"File receive error: {e}")
