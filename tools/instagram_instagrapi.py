import os, json, tempfile, time
from pathlib import Path
from typing import Optional

IG_USERNAME = os.environ.get("IG_USERNAME", "")
IG_SESSION = os.environ.get("IG_SESSION", "")

_client = None


def get_client():
    global _client
    if _client is not None:
        return _client

    if not IG_SESSION:
        raise RuntimeError("IG_SESSION не задан. Запусти get_ig_session.py локально.")

    try:
        settings = json.loads(IG_SESSION)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"IG_SESSION содержит невалидный JSON: '{IG_SESSION[:40]}...'\n"
            "Запусти get_ig_session.py и вставь полученный JSON в Railway Variables."
        )

    from instagrapi import Client
    cl = Client()
    cl.set_settings(settings)

    # Проверяем сессию без пароля — если токен живой, этого достаточно
    try:
        cl.get_timeline_feed()
    except Exception as e:
        raise RuntimeError(
            f"Сессия устарела или невалидна: {e}\n"
            "Запусти get_ig_session.py заново и обнови IG_SESSION в Railway Variables."
        )

    _client = cl
    return cl


def publish_photo(image_bytes: bytes, caption: str) -> dict:
    try:
        cl = get_client()
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(image_bytes)
            tmp_path = Path(f.name)

        last_error = None
        for attempt in range(3):
            try:
                if attempt > 0:
                    time.sleep(5 * attempt)
                media = cl.photo_upload(tmp_path, caption=caption)
                tmp_path.unlink(missing_ok=True)
                return {
                    "ok": True,
                    "media_id": str(media.id),
                    "url": f"https://instagram.com/p/{media.code}/"
                }
            except Exception as e:
                last_error = e
                error_str = str(e)
                # Фото иногда всё-таки публикуется — проверяем ленту
                if "succeeded without media payload" in error_str:
                    try:
                        recent = cl.user_medias(cl.user_id, 1)
                        if recent:
                            m = recent[0]
                            tmp_path.unlink(missing_ok=True)
                            return {
                                "ok": True,
                                "media_id": str(m.id),
                                "url": f"https://instagram.com/p/{m.code}/",
                                "note": "опубликовано (подтверждено через ленту)"
                            }
                    except Exception:
                        pass

        tmp_path.unlink(missing_ok=True)
        return {"ok": False, "error": str(last_error)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def publish_video(video_bytes: bytes, caption: str, thumbnail_bytes: Optional[bytes] = None) -> dict:
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
