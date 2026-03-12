"""Media recording handlers: screen, audio, webcam."""
import os
import subprocess
import threading

from botpkg import bot, logger
from botpkg.utils import parse_duration


# ═══════════════════════════════════════════════════════════════════
# Screen Recording
# ═══════════════════════════════════════════════════════════════════

def handle_record(message, chat_id, text):
    """Record screen video."""
    args = text.split(" ", 1)[1].strip() if " " in text else ""
    if not args:
        args = "15s"  # Smart default

    duration, label = parse_duration(args)
    if duration is None:
        bot.reply_to(message, "❌ Invalid duration. Use: `10s`, `30s`, `1m`, `2m`", parse_mode="Markdown")
        return

    max_duration = 300
    if duration > max_duration:
        bot.reply_to(message, f"❌ Max recording duration is 5 minutes. Got: {label}", parse_mode="Markdown")
        return

    bot.reply_to(message, f"🎬 Recording screen for {label}...")
    recording_path = "/tmp/harahara_bot_recording.mov"

    def do_record():
        try:
            if os.path.exists(recording_path):
                os.remove(recording_path)
            subprocess.run(
                ["screencapture", "-v", "-V", str(duration), recording_path],
                capture_output=True, text=True, timeout=duration + 30,
            )
            if os.path.exists(recording_path):
                file_size = os.path.getsize(recording_path)
                if file_size > 0:
                    with open(recording_path, "rb") as f:
                        bot.send_document(chat_id, f, caption=f"🎬 Screen recording ({label})")
                    os.remove(recording_path)
                    logger.info(f"Screen recording sent ({label})")
                else:
                    bot.send_message(chat_id, "❌ Recording file is empty. Screen Recording permission may be needed.")
            else:
                bot.send_message(chat_id, "❌ Recording was not created.")
        except subprocess.TimeoutExpired:
            bot.send_message(chat_id, "❌ Recording timed out.")
        except Exception as e:
            bot.send_message(chat_id, f"❌ Recording error: {e}")
            logger.error(f"Recording error: {e}")

    threading.Thread(target=do_record, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════
# Audio Recording
# ═══════════════════════════════════════════════════════════════════

def handle_audio(message, chat_id, text):
    """Record audio from mic."""
    args = text.split(" ", 1)[1].strip() if " " in text else ""
    if not args:
        bot.reply_to(message, "Usage: `/audio <duration>`\nExample: `/audio 10s`, `/audio 1m`", parse_mode="Markdown")
        return

    duration, label = parse_duration(args)
    if duration is None:
        bot.reply_to(message, "❌ Invalid duration. Use: `10s`, `30s`, `1m`", parse_mode="Markdown")
        return

    max_duration = 300
    if duration > max_duration:
        bot.reply_to(message, f"❌ Max audio duration is 5 minutes. Got: {label}", parse_mode="Markdown")
        return

    bot.reply_to(message, f"🎙 Recording audio for {label}...")
    audio_path = "/tmp/harahara_bot_audio.mp3"

    def do_audio():
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)

            sox_path = subprocess.run(["which", "sox"], capture_output=True, text=True).stdout.strip()
            ffmpeg_path = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True).stdout.strip()

            if sox_path:
                subprocess.run(
                    ["sox", "-d", audio_path, "trim", "0", str(duration)],
                    capture_output=True, text=True, timeout=duration + 15,
                )
            elif ffmpeg_path:
                subprocess.run(
                    ["ffmpeg", "-y", "-f", "avfoundation", "-i", ":0",
                     "-t", str(duration), audio_path],
                    capture_output=True, text=True, timeout=duration + 15,
                )
            else:
                bot.send_message(chat_id, "❌ Neither `sox` nor `ffmpeg` is installed.\nInstall with: `brew install sox` or `brew install ffmpeg`")
                return

            if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                with open(audio_path, "rb") as f:
                    bot.send_audio(chat_id, f, caption=f"🎙 Audio recording ({label})")
                os.remove(audio_path)
                logger.info(f"Audio recording sent ({label})")
            else:
                bot.send_message(chat_id, "❌ Audio file is empty or was not created.")
        except subprocess.TimeoutExpired:
            bot.send_message(chat_id, "❌ Audio recording timed out.")
        except Exception as e:
            bot.send_message(chat_id, f"❌ Audio error: {e}")
            logger.error(f"Audio error: {e}")

    threading.Thread(target=do_audio, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════
# Webcam Recording
# ═══════════════════════════════════════════════════════════════════

def handle_webcamrecord(message, chat_id, text):
    """Record video from webcam via ffmpeg."""
    args = text.split(" ", 1)[1].strip() if " " in text else ""
    if not args:
        bot.reply_to(message, "Usage: `/webcamrecord <duration>`\nExample: `/webcamrecord 10s`, `/webcamrecord 1m`", parse_mode="Markdown")
        return

    duration, label = parse_duration(args)
    if duration is None:
        bot.reply_to(message, "❌ Invalid duration. Use: `10s`, `30s`, `1m`", parse_mode="Markdown")
        return

    max_duration = 300
    if duration > max_duration:
        bot.reply_to(message, f"❌ Max recording duration is 5 minutes. Got: {label}", parse_mode="Markdown")
        return

    bot.reply_to(message, f"📹 Recording webcam for {label}...")
    video_path = "/tmp/harahara_bot_webcam_video.mp4"

    def do_webcam_record():
        try:
            if os.path.exists(video_path):
                os.remove(video_path)

            ffmpeg_path = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True).stdout.strip()
            if not ffmpeg_path:
                bot.send_message(chat_id, "❌ `ffmpeg` is not installed.\nInstall with: `brew install ffmpeg`")
                return

            subprocess.run(
                ["ffmpeg", "-y", "-f", "avfoundation", "-framerate", "30",
                 "-i", "0", "-t", str(duration), "-pix_fmt", "yuv420p", video_path],
                capture_output=True, text=True, timeout=duration + 30,
            )

            if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                with open(video_path, "rb") as f:
                    bot.send_document(chat_id, f, caption=f"📹 Webcam recording ({label})")
                os.remove(video_path)
                logger.info(f"Webcam recording sent ({label})")
            else:
                bot.send_message(chat_id, "❌ Webcam recording failed. Camera permission may be needed.")
        except subprocess.TimeoutExpired:
            bot.send_message(chat_id, "❌ Webcam recording timed out.")
        except Exception as e:
            bot.send_message(chat_id, f"❌ Webcam recording error: {e}")
            logger.error(f"Webcam recording error: {e}")

    threading.Thread(target=do_webcam_record, daemon=True).start()
