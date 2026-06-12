"""
Получение OAuth2 токена Google Calendar.

1. Создай проект в https://console.cloud.google.com/
2. Включи Google Calendar API
3. Создай OAuth2 credentials (Desktop app) → скачай credentials.json
4. Запусти: python3 get_google_token.py --credentials путь/к/credentials.json
5. Скопируй GOOGLE_TOKEN_JSON и GOOGLE_CREDENTIALS_JSON в Railway Variables
"""
import json, argparse, sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", default="credentials.json", help="Путь к credentials.json от Google")
    args = parser.parse_args()

    creds_path = Path(args.credentials)
    if not creds_path.exists():
        print(f"Файл {creds_path} не найден.")
        print("Скачай credentials.json из Google Cloud Console → APIs & Services → Credentials")
        sys.exit(1)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
    except ImportError:
        print("Установи зависимости: pip3 install google-auth-oauthlib google-api-python-client")
        sys.exit(1)

    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }

    token_json = json.dumps(token_data, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("Добавь в Railway Variables:")
    print("=" * 60)
    print(f"\nGOOGLE_TOKEN_JSON={token_json}")
    print(f"\nGOOGLE_CALENDAR_ID=primary")
    print("\n" + "=" * 60)

    Path("google_token.json").write_text(token_json)
    print("Токен также сохранён в google_token.json")


if __name__ == "__main__":
    main()
