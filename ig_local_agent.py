"""
Локальный HTTP-агент для публикации в Instagram.
Запускается на Mac, принимает запросы от Railway бота.

Запуск:
    python3 ig_local_agent.py

Туннель (постоянный URL, бесплатно):
    cloudflared tunnel --url http://localhost:8765
"""
import os, json, hmac, hashlib
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
    """Парсит multipart/form-data вручную через cgi."""
    import cgi, io
    content_type = handler.headers.get("Content-Type", "")
    length = int(handler.headers.get("Content-Length", 0))
    body = handler.rfile.read(length)
    environ = {
        "REQUEST_METHOD": "POST",
        "CONTENT_TYPE": content_type,
        "CONTENT_LENGTH": str(length),
    }
    form = cgi.FieldStorage(
        fp=io.BytesIO(body),
        environ=environ,
        keep_blank_values=True,
    )
    photo = form["photo"].file.read() if "photo" in form else None
    caption = form["caption"].value if "caption" in form else ""
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
            self._respond(500, {"ok": False, "error": str(e)})


if __name__ == "__main__":
    print(f"[ig-agent] Запуск на порту {PORT}")
    if SECRET:
        print(f"[ig-agent] Защита токеном: включена")
    else:
        print(f"[ig-agent] ВНИМАНИЕ: IG_AGENT_SECRET не задан, запросы не проверяются")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
