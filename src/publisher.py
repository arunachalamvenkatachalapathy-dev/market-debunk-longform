"""
Publisher — Uploads videos to YouTube (English + Tamil) and sends links via Telegram.
"""
import os
import logging
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)


def _get_secret(name):
    """Get a secret from environment variables."""
    value = os.environ.get(name, "")
    if not value:
        logger.warning(f"Secret '{name}' is not set")
    return value


def _upload_to_youtube(video_path, title, description, tags, client_id_key, client_secret_key, refresh_token_key):
    """
    Upload a video to YouTube using OAuth2 refresh tokens.
    This is a regular upload (NOT a Short).
    """
    try:
        refresh_token = _get_secret(refresh_token_key)
        client_id = _get_secret(client_id_key)
        client_secret = _get_secret(client_secret_key)

        if not all([refresh_token, client_id, client_secret]):
            logger.error(f"Missing YouTube credentials for {client_id_key}")
            return {"success": False, "error": "Missing credentials"}

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
        )

        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags[:15],
                "categoryId": "27",  # Education
            },
            "status": {
                "privacyStatus": "public",
            },
        }

        logger.info(f"📤 Uploading to YouTube: '{title[:50]}...'")
        media = MediaFileUpload(
            video_path, chunksize=1024 * 1024, resumable=True, mimetype="video/mp4"
        )

        request = youtube.videos().insert(
            part="snippet,status", body=body, media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                if progress % 25 == 0:  # Log every 25%
                    logger.info(f"   Upload progress: {progress}%")

        video_id = response.get("id")
        logger.info(f"✅ YouTube upload complete. Video ID: {video_id}")
        return {"success": True, "video_id": video_id}

    except Exception as e:
        logger.error(f"YouTube upload failed: {e}")
        return {"success": False, "error": str(e)}


def upload_english(video_path, script_data):
    """Upload video to the English YouTube channel."""
    title = script_data.get("title", "Market Analysis")
    description = script_data.get("description", "")
    keywords = script_data.get("visual_keywords", [])
    tags = ["finance", "stockmarket", "investing", "podcast", "analysis"] + keywords[:10]

    return _upload_to_youtube(
        video_path=video_path,
        title=title,
        description=description,
        tags=tags,
        client_id_key="YT_CLIENT_ID",
        client_secret_key="YT_CLIENT_SECRET",
        refresh_token_key="YT_REFRESH_TOKEN",
    )


def upload_tamil(video_path, script_data):
    """Upload video to the Tamil YouTube channel."""
    title = script_data.get("title", "சந்தை பகுப்பாய்வு")
    description = script_data.get("description", "")
    keywords = script_data.get("visual_keywords", [])
    tags = ["finance", "stockmarket", "investing", "podcast", "tamil"] + keywords[:10]

    return _upload_to_youtube(
        video_path=video_path,
        title=title,
        description=description,
        tags=tags,
        client_id_key="YT_TAMIL_CLIENT_ID",
        client_secret_key="YT_TAMIL_CLIENT_SECRET",
        refresh_token_key="YT_TAMIL_REFRESH_TOKEN",
    )


def send_telegram_links(en_result, ta_result):
    """
    Send a Telegram message with YouTube video links.
    Does NOT upload any video — just shares the links.
    """
    token = _get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = _get_secret("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.error("Telegram credentials not set. Skipping.")
        return {"success": False, "error": "Missing Telegram credentials"}

    # Build message
    lines = ["🎙️ *New Podcast Video Published!*", ""]

    if en_result and en_result.get("success"):
        en_id = en_result["video_id"]
        lines.append(f"🇬🇧 English: https://youtube.com/watch?v={en_id}")

    if ta_result and ta_result.get("success"):
        ta_id = ta_result["video_id"]
        lines.append(f"🇮🇳 Tamil: https://youtube.com/watch?v={ta_id}")

    if len(lines) <= 2:
        logger.warning("No successful uploads to share on Telegram")
        return {"success": False, "error": "No videos to share"}

    message = "\n".join(lines)

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }
        response = requests.post(url, data=payload, timeout=30)
        response.raise_for_status()
        logger.info("✅ Telegram notification sent successfully")
        return {"success": True}

    except Exception as e:
        logger.error(f"Telegram notification failed: {e}")
        return {"success": False, "error": str(e)}
