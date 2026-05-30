"""
Локальный HTTP-агент для публикации в Instagram.
Запускается на Mac, принимает запросы от Railway бота.

Запуск:
    python3 ig_local_agent.py

Туннель (постоянный URL, бесплатно):
    cloudflared tunnel --url http://localhost:8765
"""
import os, json, hmac, hashlib, re, traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from tools.instagram_instagrapi import publish_photo

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
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"ok": True, "status": "running"})
        else:
            self._respond(404, {"ok": False})

    def do_POST(self):
        if self.path != "/publish":
            self._respond(404, {"ok": False, "error": "Not found"})
            return

        if not _check_auth(self):
            self._respond(401, {"ok": False, "error": "Unauthorized"})
            return

        try:
            photo_bytes, caption = _parse_multipart(self)
            if not photo_bytes:
                self._respond(400, {"ok": False, "error": "Нет фото"})
                return

            result = publish_photo(photo_bytes, caption)
            self._respond(200 if result["ok"] else 500, result)

        except Exception as e:
            traceback.print_exc()
            self._respond(500, {"ok": False, "error": str(e)})


if __name__ == "__main__":
    print(f"[ig-agent] Запуск на порту {PORT}")
    if SECRET:
        print(f"[ig-agent] Защита токеном: включена")
    else:
        print(f"[ig-agent] ВНИМАНИЕ: IG_AGENT_SECRET не задан, запросы не проверяются")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
