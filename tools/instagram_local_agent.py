import os, json, requests

IG_AGENT_URL = os.environ.get("IG_AGENT_URL", "").rstrip("/")
IG_AGENT_SECRET = os.environ.get("IG_AGENT_SECRET", "")


def publish_photo(image_bytes: bytes, caption: str) -> dict:
    if not IG_AGENT_URL:
        return {"ok": False, "error": "IG_AGENT_URL не задан в Railway Variables."}

    headers = {}
    if IG_AGENT_SECRET:
        headers["X-Agent-Secret"] = IG_AGENT_SECRET

    try:
        resp = requests.post(
            f"{IG_AGENT_URL}/publish",
            files={"photo": ("photo.jpg", image_bytes, "image/jpeg")},
            data={"caption": caption.encode("utf-8")},
            headers=headers,
            timeout=180,
        )
        resp.encoding = "utf-8"
        if resp.status_code >= 400:
            print(f"[ig-client] agent returned HTTP {resp.status_code}: {resp.text[:500]}")
        return resp.json()
    except requests.Timeout:
        return {"ok": False, "error": "Агент не ответил за 3 минуты. Проверь что ig_local_agent.py запущен на Mac."}
    except Exception as e:
        print(f"[ig-client] exception calling agent: {e}")
        return {"ok": False, "error": str(e)}
