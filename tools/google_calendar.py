import os, json
from datetime import datetime, timedelta

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
