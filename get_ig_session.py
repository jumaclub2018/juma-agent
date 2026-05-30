"""
Получение Instagram сессии для Railway.

Запуск:
    python get_ig_session.py

Если Instagram авторизует не тот аккаунт — используй вход через sessionid из браузера:
    1. Открой instagram.com, войди как нужный аккаунт
    2. DevTools → Application → Cookies → instagram.com → sessionid
    3. Запусти: python get_ig_session.py --sessionid <значение>

После авторизации скопируй JSON в Railway Variables как IG_SESSION.
"""
import json
import os
import sys

try:
    from instagrapi import Client
    from instagrapi.exceptions import TwoFactorRequired, BadPassword, UserNotFound
except ImportError:
    print("Установи библиотеку: pip install instagrapi")
    sys.exit(1)


def verify_account(cl, expected_username=None):
    """Проверяет реальный аккаунт сессии и выводит username."""
    try:
        info = cl.user_info(cl.user_id)
        actual = info.username
    except Exception:
        actual = str(cl.user_id)

    print(f"\n📱 Аккаунт в сессии: @{actual}")

    if expected_username and actual.lower() != expected_username.lower():
        print(f"⚠️  ВНИМАНИЕ: ожидался @{expected_username}, но сессия от @{actual}!")
        confirm = input("Продолжить и сохранить эту сессию? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Отменено.")
            sys.exit(1)

    return actual


def login_by_sessionid(cl, sessionid):
    """Вход через sessionid из браузера — гарантирует нужный аккаунт."""
    try:
        cl.login_by_sessionid(sessionid)
    except Exception as e:
        print(f"❌ Ошибка входа по sessionid: {e}")
        sys.exit(1)


def login_with_2fa(cl, username, password):
    """Вход через логин/пароль с поддержкой 2FA."""
    try:
        cl.login(username, password)
        return

    except TwoFactorRequired:
        two_factor_info = cl.last_json.get("two_factor_info", {})
        totp_on = two_factor_info.get("totp_two_factor_on", False)
        sms_on = two_factor_info.get("sms_two_factor_on", False)
        obfuscated_phone = two_factor_info.get("obfuscated_phone_no", "")

        print()
        if sms_on and obfuscated_phone:
            print(f"📱 SMS с кодом отправлено на номер {obfuscated_phone}")
        elif totp_on:
            print("🔐 Открой приложение-аутентификатор (Google Authenticator / Яндекс Ключ)")
        else:
            print("🔐 Instagram требует 2FA подтверждение")

        for attempt in range(3):
            code = input("Введи 2FA код: ").strip().replace(" ", "")
            if not code:
                print("Код не может быть пустым, попробуй ещё раз.")
                continue
            try:
                cl.two_factor_login(
                    verification_code=code,
                    two_factor_identifier=two_factor_info.get("two_factor_identifier", ""),
                    username=username,
                    identifier_type="1" if totp_on else "0",
                )
                return
            except TwoFactorRequired:
                remaining = 2 - attempt
                if remaining > 0:
                    print(f"❌ Неверный код. Осталось попыток: {remaining}")
                else:
                    print("❌ Код не принят. Запроси новый и запусти скрипт заново.")
                    sys.exit(1)
            except Exception as e:
                print(f"Ошибка 2FA: {e}")
                sys.exit(1)

    except BadPassword:
        print("❌ Неверный пароль.")
        sys.exit(1)

    except UserNotFound:
        print("❌ Пользователь не найден.")
        sys.exit(1)

    except Exception as e:
        print(f"❌ Ошибка входа: {e}")
        sys.exit(1)


def get_session():
    cl = Client()
    cl.delay_range = [1, 3]

    proxy = os.environ.get("IG_PROXY") or input(
        "Прокси (Enter чтобы пропустить) [http://user:pass@host:port]: "
    ).strip()
    if proxy:
        cl.set_proxy(proxy)
        print(f"Прокси установлен: {proxy}")

    # Выбор метода входа
    sessionid = None
    if "--sessionid" in sys.argv:
        idx = sys.argv.index("--sessionid")
        if idx + 1 < len(sys.argv):
            sessionid = sys.argv[idx + 1]

    if not sessionid:
        sessionid = os.environ.get("IG_SESSIONID", "").strip()

    if sessionid:
        print(f"\n🔑 Вход через sessionid из браузера...")
        login_by_sessionid(cl, sessionid)
        actual = verify_account(cl)
    else:
        print("\n💡 Совет: если Instagram авторизует не тот аккаунт,")
        print("   используй --sessionid <куки из браузера>\n")
        username = os.environ.get("IG_USERNAME") or input("Instagram username: ").strip()
        password = os.environ.get("IG_PASSWORD") or input("Instagram password: ").strip()
        login_with_2fa(cl, username, password)
        actual = verify_account(cl, expected_username=username)

    session = cl.get_settings()
    session_str = json.dumps(session)

    print(f"\n✅ Сессия готова! Аккаунт: @{actual}")
    print("\n" + "=" * 60)
    print("Добавь в Railway Variables:")
    print("  Имя переменной : IG_SESSION")
    print("  Значение (скопируй строку целиком):")
    print("=" * 60)
    print(session_str)
    print("=" * 60 + "\n")


if __name__ == "__main__":
    get_session()
