import os
import time
from typing import Any, Dict, List, Optional

import requests

PARTNER_TOKEN = os.environ.get("YCLIENTS_PARTNER_TOKEN", "")
USER_TOKEN    = os.environ.get("YCLIENTS_USER_TOKEN", "")
COMPANY_ID    = os.environ.get("YCLIENTS_COMPANY_ID", "")

BASE_URL = "https://api.yclients.com/api/v1"

# Минимальная пауза между запросами (YClients: не более 5 req/s)
_THROTTLE_SECONDS = 0.25
_last_request_at: float = 0.0


def _clean(token: Optional[str]) -> str:
    if not token:
        return ""
    return token.encode("ascii", errors="ignore").decode("ascii").strip()


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_clean(PARTNER_TOKEN)}, User {_clean(USER_TOKEN)}",
        "Accept": "application/vnd.yclients.v2+json",
    }


def _get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Выполняет GET-запрос с троттлингом и обработкой ошибок."""
    global _last_request_at

    if not PARTNER_TOKEN or not USER_TOKEN:
        return {
            "ok": False,
            "error": "Токены не заданы. Добавь YCLIENTS_PARTNER_TOKEN и YCLIENTS_USER_TOKEN в переменные окружения.",
        }
    if not COMPANY_ID and "/company/" in path:
        return {"ok": False, "error": "YCLIENTS_COMPANY_ID не задан в переменных окружения."}

    elapsed = time.monotonic() - _last_request_at
    if elapsed < _THROTTLE_SECONDS:
        time.sleep(_THROTTLE_SECONDS - elapsed)

    url = BASE_URL + path
    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=15)
        _last_request_at = time.monotonic()
    except requests.Timeout:
        return {"ok": False, "error": "YClients API не ответил за 15 секунд."}
    except requests.ConnectionError as e:
        return {"ok": False, "error": f"Ошибка соединения с YClients: {e}"}

    if resp.status_code == 401:
        return {"ok": False, "error": "YClients: неверный PARTNER_TOKEN или USER_TOKEN (401 Unauthorized)."}
    if resp.status_code == 403:
        return {"ok": False, "error": "YClients: нет доступа к ресурсу (403 Forbidden). Проверь права токена."}
    if resp.status_code == 429:
        return {"ok": False, "error": "YClients: превышен лимит запросов (429 Too Many Requests). Подожди немного."}
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("meta", {}).get("message", resp.text[:200])
        except Exception:
            detail = resp.text[:200]
        return {"ok": False, "error": f"YClients вернул {resp.status_code}: {detail}"}

    try:
        data = resp.json()
    except Exception:
        return {"ok": False, "error": f"YClients вернул не-JSON ответ: {resp.text[:200]}"}

    if not data.get("success", True):
        msg = data.get("meta", {}).get("message", "Неизвестная ошибка YClients")
        return {"ok": False, "error": msg}

    return {"ok": True, "data": data.get("data", data)}


# ── Публичные функции ──────────────────────────────────────────────────────────

def test_connection() -> Dict[str, Any]:
    """Проверяет что токены рабочие. Возвращает {"ok": True} или {"ok": False, "error": ...}."""
    result = _get(f"/company/{COMPANY_ID}")
    if result["ok"]:
        name = result["data"].get("title", "")
        return {"ok": True, "company": name}
    return result


def get_clients(page: int = 1, count: int = 200) -> Dict[str, Any]:
    """
    Список клиентов компании.
    Возвращает {"ok": True, "data": [...]} или {"ok": False, "error": "..."}.
    """
    return _get(
        f"/clients/{COMPANY_ID}",
        params={"page": page, "count": count},
    )


def get_client_abonements(client_id: int) -> Dict[str, Any]:
    """
    Абонементы клиента и остаток посещений.
    Возвращает {"ok": True, "data": [...]} или {"ok": False, "error": "..."}.
    """
    return _get(f"/loyalty/abonements/{COMPANY_ID}", params={"client_id": client_id})


def get_client_visits(client_id: int, page: int = 1, count: int = 100) -> Dict[str, Any]:
    """
    История посещений клиента.
    Возвращает {"ok": True, "data": [...]} или {"ok": False, "error": "..."}.
    """
    return _get(
        f"/records/{COMPANY_ID}",
        params={"client_id": client_id, "page": page, "count": count},
    )


def get_records(date: str) -> Dict[str, Any]:
    """
    Записи на конкретную дату.
    date: строка в формате YYYY-MM-DD.
    Возвращает {"ok": True, "data": [...]} или {"ok": False, "error": "..."}.
    """
    return _get(
        f"/records/{COMPANY_ID}",
        params={"start_date": date, "end_date": date},
    )
