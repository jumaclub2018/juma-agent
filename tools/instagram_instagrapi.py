import os
from pathlib import Path
import tempfile

IG_USERNAME = os.environ.get("IG_USERNAME", "")
IG_PASSWORD = os.environ.get("IG_PASSWORD", "")

# Клиент создаётся один раз и переиспользуется
_client = None


def get_client():
    global _client
    if _client is not None:
        return _client
    from instagrapi import Client
    cl = Client()
    # Сохраняем сессию чтобы не логиниться каждый раз
    session_file = Path("ig_session.json")
    if session_file.exists():
        cl.load_settings(session_file)
        cl.login(IG_USERNAME, IG_PASSWORD)
    else:
        cl.login(IG_USERNAME, IG_PASSWORD)
        cl.dump_settings(session_file)
    _client = cl
    return cl


def publish_photo(image_bytes: bytes, caption: str) -> dict:
    """Публикует фото в Instagram через instagrapi."""
    try:
        cl = get_client()
        # Сохраняем байты во временный файл
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(image_bytes)
            tmp_path = Path(f.name)
        media = cl.photo_upload(tmp_path, caption=caption)
        tmp_path.unlink(missing_ok=True)
        return {
            "ok": True,
            "media_id": str(media.id),
            "url": f"https://instagram.com/p/{media.code}/"
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def publish_video(video_bytes: bytes, caption: str, thumbnail_bytes: bytes | None = None) -> dict:
    """Публикует видео/Reels."""
    try:
        cl = get_client()
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(video_bytes)
            tmp_path = Path(f.name)
        thumb_path = None
        if thumbnail_bytes:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
                tf.write(thumbnail_bytes)
                thumb_path = Path(tf.name)
        media = cl.video_upload(tmp_path, caption=caption, thumbnail=thumb_path)
        tmp_path.unlink(missing_ok=True)
        if thumb_path:
            thumb_path.unlink(missing_ok=True)
        return {
            "ok": True,
            "media_id": str(media.id),
            "url": f"https://instagram.com/p/{media.code}/"
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
