"""
Получение Instagram сессии для Railway.

Запуск:
    python get_ig_session.py

После успешной авторизации скопируй выведенный JSON в Railway Variables
как переменную IG_SESSION.
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


def login_with_2fa(cl, username, password):
    """Вход с поддержкой 2FA через SMS или TOTP-приложение."""
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
                # Используем two_factor_login — работает с внутренним состоянием
                # сохранённым после первой попытки входа
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
    username = os.environ.get("IG_USERNAME") or input("Instagram username: ").strip()
    password = os.environ.get("IG_PASSWORD") or input("Instagram password: ").strip()

    cl = Client()
    cl.delay_range = [1, 3]

    # Прокси: из env или ввод вручную
    # Форматы: http://user:pass@host:port  или  socks5://host:port
    proxy = os.environ.get("IG_PROXY") or input(
        "Прокси (Enter чтобы пропустить) [http://user:pass@host:port]: "
    ).strip()
    if proxy:
        cl.set_proxy(proxy)
        print(f"Прокси установлен: {proxy}")

    login_with_2fa(cl, username, password)

    session = cl.get_settings()
    session_str = json.dumps(session)

    print(f"\n✅ Авторизация успешна! Аккаунт: @{username}")
    print("\n" + "=" * 60)
    print("Добавь в Railway Variables:")
    print("  Имя переменной : IG_SESSION")
    print("  Значение (скопируй строку целиком):")
    print("=" * 60)
    print(session_str)
    print("=" * 60 + "\n")


if __name__ == "__main__":
    get_session()
