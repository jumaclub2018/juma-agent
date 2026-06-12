import os, json
from datetime import datetime, timedelta, timezone

GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
GOOGLE_TOKEN_JSON = os.environ.get("GOOGLE_TOKEN_JSON", "")
CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")


def _get_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    if not GOOGLE_TOKEN_JSON:
        raise RuntimeError(
            "GOOGLE_TOKEN_JSON не задан. Запусти get_google_token.py и добавь результат в переменные окружения."
        )

    token_data = json.loads(GOOGLE_TOKEN_JSON)
    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=token_data.get("scopes", ["https://www.googleapis.com/auth/calendar"]),
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build("calendar", "v3", credentials=creds)


def create_event(
    title: str,
    date: str,
    time: str,
    duration_minutes: int = 60,
    description: str = "",
) -> dict:
    """
    date: YYYY-MM-DD
    time: HH:MM
    """
    try:
        service = _get_service()

        start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        # Часовой пояс Москвы
        tz = "Europe/Moscow"

        event = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": tz},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": tz},
        }

        created = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        return {
            "ok": True,
            "event_id": created["id"],
            "url": created.get("htmlLink", ""),
            "start": start_dt.strftime("%d.%m.%Y %H:%M"),
            "end": end_dt.strftime("%H:%M"),
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_events(date_from: str, date_to: str) -> dict:
    """
    Список событий за период.
    date_from, date_to: YYYY-MM-DD
    Возвращает список {"id", "title", "date", "time_start", "time_end"}.
    """
    try:
        service = _get_service()

        # Google Calendar API требует RFC3339 с часовым поясом
        time_min = f"{date_from}T00:00:00+03:00"
        time_max = f"{date_to}T23:59:59+03:00"

        result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            maxResults=50,
        ).execute()

        events = []
        for e in result.get("items", []):
            start = e.get("start", {})
            end   = e.get("end", {})
            # Событие может быть весь день (date) или конкретное время (dateTime)
            if "dateTime" in start:
                dt_start = datetime.fromisoformat(start["dateTime"])
                dt_end   = datetime.fromisoformat(end["dateTime"])
                time_start = dt_start.strftime("%H:%M")
                time_end   = dt_end.strftime("%H:%M")
                date_str   = dt_start.strftime("%d.%m.%Y")
            else:
                date_str   = start.get("date", "")
                time_start = "весь день"
                time_end   = ""

            events.append({
                "id":         e["id"],
                "title":      e.get("summary", "(без названия)"),
                "date":       date_str,
                "time_start": time_start,
                "time_end":   time_end,
            })

        return {"ok": True, "events": events}

    except Exception as e:
        return {"ok": False, "error": str(e)}


def delete_event(event_id: str) -> dict:
    """Удаляет событие по id. Возвращает {"ok": True} или {"ok": False, "error": ...}."""
    try:
        service = _get_service()
        service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
