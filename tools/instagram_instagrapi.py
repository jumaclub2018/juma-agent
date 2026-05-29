import os, json, tempfile
from pathlib import Path

IG_USERNAME = os.environ.get("IG_USERNAME", "")
IG_SESSION = os.environ.get("IG_SESSION", "")  # JSON сессии из Railway

_client = None


def get_client():
    global _client
    if _client is not None:
        return _client
    from instagrapi import Client
    cl = Client()
    if IG_SESSION:
        # Грузим сохранённую сессию — не нужен пароль и новый логин
        settings = json.loads(IG_SESSION)
        cl.set_settings(settings)
        cl.login(IG_USERNAME, "")  # переавторизация по сессии
    else:
        raise RuntimeError("IG_SESSION не задан. Запусти get_ig_session.py локально.")
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
