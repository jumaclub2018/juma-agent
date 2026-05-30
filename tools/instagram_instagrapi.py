import os, json, tempfile, time
from pathlib import Path
from typing import Optional

IG_USERNAME = os.environ.get("IG_USERNAME", "")
IG_PASSWORD = os.environ.get("IG_PASSWORD", "")
IG_SESSION = os.environ.get("IG_SESSION", "")
IG_TOTP_SECRET = os.environ.get("IG_TOTP_SECRET", "")  # TOTP секрет для авто-2FA

SESSION_FILE = Path("/tmp/ig_session_cache.json")

_client = None

LOGIN_REQUIRED_MARKERS = ("login_required", "LoginRequired", "login required", "Not authorized")


def _save_session(cl):
    try:
        SESSION_FILE.write_text(json.dumps(cl.get_settings()))
    except Exception:
        pass


def _load_settings():
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
            "Запусти get_ig_session.py заново."
        )


def _totp_code():
    """Генерирует TOTP код если задан IG_TOTP_SECRET."""
    if not IG_TOTP_SECRET:
        return None
    try:
        import pyotp
        return pyotp.TOTP(IG_TOTP_SECRET).now()
    except ImportError:
        return None


def _do_login(cl):
    """Полный логин с поддержкой 2FA через TOTP."""
    from instagrapi.exceptions import TwoFactorRequired

    if not IG_USERNAME or not IG_PASSWORD:
        raise RuntimeError(
            "Для авто-перелогина нужны IG_USERNAME и IG_PASSWORD в Railway Variables."
        )

    try:
        cl.login(IG_USERNAME, IG_PASSWORD)
    except TwoFactorRequired:
        code = _totp_code()
        if not code:
            raise RuntimeError(
                "Сессия истекла, Instagram требует 2FA, но IG_TOTP_SECRET не задан.\n"
                "Добавь TOTP секрет в Railway Variables или пересоздай сессию вручную."
            )
        two_factor_info = cl.last_json.get("two_factor_info", {})
        cl.two_factor_login(
            verification_code=code,
            two_factor_identifier=two_factor_info.get("two_factor_identifier", ""),
            username=IG_USERNAME,
            identifier_type="1",
        )


def _build_client():
    from instagrapi import Client
    cl = Client()
    cl.delay_range = [1, 3]

    try:
        cl.set_settings(_load_settings())
        cl.get_timeline_feed()
    except Exception as e:
        if any(m in str(e) for m in LOGIN_REQUIRED_MARKERS):
            # Сессия истекла — перелогиниваемся
            SESSION_FILE.unlink(missing_ok=True)
            cl = Client()
            cl.delay_range = [1, 3]
            _do_login(cl)
        else:
            raise RuntimeError(f"Не удалось инициализировать Instagram клиент: {e}")

    _save_session(cl)
    return cl


def get_client():
    global _client
    if _client is None:
        _client = _build_client()
    return _client


def _reset_client():
    global _client
    _client = None
    SESSION_FILE.unlink(missing_ok=True)


def _handle_error(e, cl):
    """Возвращает True если стоит повторить попытку после сброса сессии."""
    if any(m in str(e) for m in LOGIN_REQUIRED_MARKERS):
        _reset_client()
        try:
            globals()["_client"] = _build_client()
        except Exception:
            pass
        return True
    return False


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
                if _handle_error(e, cl):
                    cl = get_client()
                elif "succeeded without media payload" in str(e):
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
