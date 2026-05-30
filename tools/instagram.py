import os, requests, base64
from typing import Optional

SMMPLANNER_TOKEN = os.environ.get("SMMPLANNER_TOKEN", "")
SMMPLANNER_ACCOUNT_ID = os.environ.get("SMMPLANNER_ACCOUNT_ID", "")

API_URL = "https://api.smmplanner.com/api2"


def _headers():
    return {"Authorization": f"Bearer {SMMPLANNER_TOKEN}"}


def upload_image(image_bytes: bytes) -> Optional[str]:
    """Загружаем фото в SMMplanner, получаем ID файла."""
    resp = requests.post(
        f"{API_URL}/file",
        headers=_headers(),
        files={"file": ("photo.jpg", image_bytes, "image/jpeg")}
    )
    if resp.status_code == 200:
        data = resp.json()
        return data.get("data", {}).get("id")
    return None


def publish_photo(image_bytes: bytes, caption: str, schedule_time: Optional[str] = None) -> dict:
    """
    Публикуем фото в Instagram через SMMplanner.
    schedule_time — ISO строка '2025-06-01 18:00' для отложенной публикации.
    Если None — публикуем сразу (nearest slot).
    """
    file_id = upload_image(image_bytes)
    if not file_id:
        return {"ok": False, "error": "Не удалось загрузить фото в SMMplanner"}

    payload = {
        "account_ids": [SMMPLANNER_ACCOUNT_ID],
        "text": caption,
        "img_ids": [file_id],
    }
    if schedule_time:
        payload["planned_time"] = schedule_time
    else:
        payload["planned_time"] = "now"

    resp = requests.post(
        f"{API_URL}/post",
        headers=_headers(),
        json=payload
    )

    if resp.status_code == 200:
        data = resp.json()
        post_id = data.get("data", {}).get("id", "")
        return {"ok": True, "post_id": post_id}
    else:
        return {"ok": False, "error": resp.text}


def get_accounts() -> list:
    """Список подключённых аккаунтов (для проверки)."""
    resp = requests.get(f"{API_URL}/account", headers=_headers())
    if resp.status_code == 200:
        return resp.json().get("data", [])
    return []
