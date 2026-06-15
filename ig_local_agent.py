"""
Локальный HTTP-агент для публикации в Instagram.
Запускается на Mac, принимает запросы от Railway бота.

Запуск:
    python3 ig_local_agent.py

Туннель (постоянный URL, бесплатно):
    cloudflared tunnel --url http://localhost:8765
"""
import os, json, hmac, hashlib, re, traceback, tempfile, threading
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── STT (Whisper) — грузится лениво при первом запросе ────────────────────────
_stt_model = None
_stt_lock  = threading.Lock()
STT_MODEL  = os.environ.get("STT_MODEL", "small")

def _get_stt_model():
    global _stt_model
    if _stt_model is None:
        with _stt_lock:
            if _stt_model is None:
                print(f"[ig-agent] Загружаю STT-модель '{STT_MODEL}'…")
                from faster_whisper import WhisperModel
                _stt_model = WhisperModel(STT_MODEL, compute_type="int8", device="cpu")
                print(f"[ig-agent] STT-модель '{STT_MODEL}' загружена.")
    return _stt_model


def _load_dotenv():
    """Загружает .env из папки скрипта, не перезаписывая уже выставленные переменные."""
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        return
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = val.strip()


_load_dotenv()

from tools.instagram_instagrapi import publish_photo  # импорт после загрузки .env

PORT = int(os.environ.get("IG_AGENT_PORT", 8765))
SECRET = os.environ.get("IG_AGENT_SECRET", "")


def _check_auth(handler) -> bool:
    if not SECRET:
        return True
    token = handler.headers.get("X-Agent-Secret", "")
    return hmac.compare_digest(token, SECRET)


def _parse_multipart(handler):
    """Парсит multipart/form-data без cgi — работает с бинарными данными."""
    content_type = handler.headers.get("Content-Type", "")
    length = int(handler.headers.get("Content-Length", 0))
    body = handler.rfile.read(length)

    # Извлекаем boundary
    m = re.search(r'boundary=([^\s;]+)', content_type)
    if not m:
        raise ValueError(f"boundary не найден в Content-Type: {content_type}")
    boundary = ("--" + m.group(1)).encode()

    photo = None
    caption = ""

    for part in body.split(boundary):
        if b"Content-Disposition" not in part:
            continue
        # Разделяем заголовки и тело части двойным CRLF
        if b"\r\n\r\n" in part:
            headers_raw, _, value = part.partition(b"\r\n\r\n")
        else:
            continue
        value = value.rstrip(b"\r\n--")
        headers_raw = headers_raw.decode("utf-8", errors="replace")

        name_m = re.search(r'name="([^"]+)"', headers_raw)
        if not name_m:
            continue
        name = name_m.group(1)

        if name == "photo":
            photo = value
        elif name == "caption":
            caption = value.decode("utf-8", errors="replace")

    return photo, caption


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[ig-agent] {fmt % args}")

    def _respond(self, code: int, data: dict):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"ok": True, "status": "running"})
        else:
            self._respond(404, {"ok": False})

    def do_POST(self):
        if not _check_auth(self):
            self._respond(401, {"ok": False, "error": "Unauthorized"})
            return

        if self.path == "/publish":
            self._handle_publish()
        elif self.path == "/transcribe":
            self._handle_transcribe()
        else:
            self._respond(404, {"ok": False, "error": "Not found"})

    def _handle_publish(self):
        try:
            photo_bytes, caption = _parse_multipart(self)
            if not photo_bytes:
                self._respond(400, {"ok": False, "error": "Нет фото"})
                return

            print(f"[ig-agent] caption ({len(caption)} chars): {caption[:120]!r}")
            result = publish_photo(photo_bytes, caption)
            if not result.get("ok"):
                print(f"[ig-agent] publish_photo returned error: {result}")
            self._respond(200 if result["ok"] else 500, result)

        except Exception as e:
            traceback.print_exc()
            self._respond(500, {"ok": False, "error": str(e)})

    def _handle_transcribe(self):
        tmp = None
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 180 * 16_000:  # ~180 сек
                self._respond(413, {"ok": False, "error": "Аудио слишком длинное (лимит 180 сек)"})
                return

            audio_bytes = self.rfile.read(length)

            with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
                f.write(audio_bytes)
                tmp = f.name

            model = _get_stt_model()
            segments, info = model.transcribe(
                tmp,
                language="ru",
                beam_size=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
            )
            text = " ".join(s.text.strip() for s in segments).strip()
            print(f"[ig-agent] STT ({info.duration:.1f}s): {text[:120]!r}")
            self._respond(200, {"ok": True, "text": text})

        except Exception as e:
            traceback.print_exc()
            self._respond(500, {"ok": False, "error": str(e)})
        finally:
            if tmp:
                Path(tmp).unlink(missing_ok=True)


if __name__ == "__main__":
    print(f"[ig-agent] Запуск на порту {PORT}")
    if SECRET:
        print(f"[ig-agent] Защита токеном: включена")
    else:
        print(f"[ig-agent] ВНИМАНИЕ: IG_AGENT_SECRET не задан, запросы не проверяются")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
