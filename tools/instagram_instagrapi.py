import os, json, tempfile, time
from pathlib import Path
from typing import Optional

IG_USERNAME = os.environ.get("IG_USERNAME", "")
IG_SESSION = os.environ.get("IG_SESSION", "")

# Локальный файл для сохранения обновлённой сессии внутри контейнера Railway.
# Переживает перезапуски кода, но не передеплои.
SESSION_FILE = Path("/tmp/ig_session_cache.json")

_client = None


def _save_session(cl):
    """Сохраняет обновлённую сессию в файл — токены обновляются после каждого запроса."""
    try:
        SESSION_FILE.write_text(json.dumps(cl.get_settings()))
    except Exception:
        pass


def _load_settings():
    """Загружает сессию: сначала из файла (свежее), потом из env."""
    if SESSION_FILE.exists():
        try:
            return json.loads(SESSION_FILE.read_text())
        except Exception:
            SESSION_FILE.unlink(missing_ok=True)

    if not IG_SESSION:
        raise RuntimeError(
            "IG_SESSION не задан. Запусти get_ig_session.py и добавь JSON в Railway Variables."
        )
    try:
        return json.loads(IG_SESSION)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"IG_SESSION содержит невалидный JSON: '{IG_SESSION[:40]}...'\n"
            "Запусти get_ig_session.py заново и обнови IG_SESSION в Railway Variables."
        )


def _build_client():
    from instagrapi import Client
    cl = Client()
    cl.delay_range = [1, 3]
    cl.set_settings(_load_settings())
    try:
        cl.get_timeline_feed()
    except Exception as e:
        raise RuntimeError(
            f"Сессия устарела или невалидна: {e}\n"
            "Запусти get_ig_session.py заново и обнови IG_SESSION в Railway Variables."
        )
    _save_session(cl)
    return cl


def get_client():
    global _client
    if _client is None:
        _client = _build_client()
    return _client


def _reset_client():
    """Сбрасывает кэш клиента — следующий вызов get_client() пересоздаст сессию."""
    global _client
    _client = None
    SESSION_FILE.unlink(missing_ok=True)


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
                _save_session(cl)
                return {
                    "ok": True,
                    "media_id": str(media.id),
                    "url": f"https://instagram.com/p/{media.code}/"
                }
            except Exception as e:
                last_error = e
                error_str = str(e)

                # Сессия истекла — сбрасываем и пробуем переподключиться
                if any(x in error_str for x in ("login_required", "LoginRequired", "login required")):
                    _reset_client()
                    try:
                        cl = get_client()
                    except Exception:
                        break

                # Фото иногда всё-таки публикуется несмотря на ошибку — проверяем ленту
                elif "succeeded without media payload" in error_str:
                    try:
                        recent = cl.user_medias(cl.user_id, 1)
                        if recent:
                            m = recent[0]
                            tmp_path.unlink(missing_ok=True)
                            _save_session(cl)
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
        _save_session(cl)
        return {
            "ok": True,
            "media_id": str(media.id),
            "url": f"https://instagram.com/p/{media.code}/"
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
