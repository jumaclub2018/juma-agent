import os, json, tempfile, time
from pathlib import Path

IG_USERNAME = os.environ.get("IG_USERNAME", "")
IG_PASSWORD = os.environ.get("IG_PASSWORD", "")

COOKIES_FILE = Path("/tmp/ig_playwright_cookies.json")


def _save_cookies(context):
    try:
        COOKIES_FILE.write_text(json.dumps(context.cookies()))
    except Exception:
        pass


def _load_cookies(context):
    if COOKIES_FILE.exists():
        try:
            context.add_cookies(json.loads(COOKIES_FILE.read_text()))
            return True
        except Exception:
            COOKIES_FILE.unlink(missing_ok=True)
    return False


def _login(page, context):
    page.goto("https://www.instagram.com/accounts/login/", wait_until="networkidle")
    time.sleep(2)

    # Принять cookies если появится баннер
    try:
        btn = page.locator("text=Allow all cookies").first
        if btn.is_visible(timeout=3000):
            btn.click()
            time.sleep(1)
    except Exception:
        pass

    page.fill('input[name="username"]', IG_USERNAME)
    page.fill('input[name="password"]', IG_PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_url("**/instagram.com/**", timeout=15000)
    time.sleep(3)

    # Закрыть попап "Save login info?"
    try:
        btn = page.locator("text=Not now").first
        if btn.is_visible(timeout=3000):
            btn.click()
            time.sleep(1)
    except Exception:
        pass

    # Закрыть попап уведомлений
    try:
        btn = page.locator("text=Not Now").first
        if btn.is_visible(timeout=3000):
            btn.click()
            time.sleep(1)
    except Exception:
        pass

    _save_cookies(context)


def publish_photo(image_bytes: bytes, caption: str) -> dict:
    if not IG_USERNAME or not IG_PASSWORD:
        return {"ok": False, "error": "IG_USERNAME и IG_PASSWORD не заданы в переменных окружения."}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "error": "Playwright не установлен. Добавь playwright в requirements.txt и запусти playwright install chromium."}

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(image_bytes)
        tmp_path = f.name

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()

            # Попробовать войти через сохранённые cookies
            logged_in = False
            if _load_cookies(context):
                page.goto("https://www.instagram.com/", wait_until="networkidle")
                time.sleep(2)
                if "login" not in page.url:
                    logged_in = True

            if not logged_in:
                _login(page, context)

            # Открыть диалог создания поста
            page.goto("https://www.instagram.com/", wait_until="networkidle")
            time.sleep(2)

            # Кликнуть кнопку "New post" (иконка +)
            create_btn = page.locator('[aria-label="New post"]').first
            create_btn.wait_for(timeout=10000)
            create_btn.click()
            time.sleep(1)

            # Выбрать "Post"
            try:
                post_option = page.locator("text=Post").first
                if post_option.is_visible(timeout=3000):
                    post_option.click()
                    time.sleep(1)
            except Exception:
                pass

            # Загрузить файл
            with page.expect_file_chooser() as fc_info:
                page.locator('[aria-label="New post"]').first.click()
            file_chooser = fc_info.value
            file_chooser.set_files(tmp_path)
            time.sleep(2)

            # Если появился выбор соотношения — пропустить
            try:
                ok_btn = page.locator("text=OK").first
                if ok_btn.is_visible(timeout=2000):
                    ok_btn.click()
                    time.sleep(1)
            except Exception:
                pass

            # Next → Next → написать caption → Share
            for _ in range(2):
                next_btn = page.locator("text=Next").first
                next_btn.wait_for(timeout=10000)
                next_btn.click()
                time.sleep(1)

            # Caption
            caption_box = page.locator('div[aria-label="Write a caption..."]').first
            caption_box.wait_for(timeout=10000)
            caption_box.click()
            caption_box.type(caption, delay=30)
            time.sleep(1)

            # Share
            share_btn = page.locator("text=Share").first
            share_btn.wait_for(timeout=10000)
            share_btn.click()

            # Ждать завершения публикации
            page.wait_for_selector("text=Your post has been shared", timeout=60000)
            time.sleep(2)

            _save_cookies(context)
            browser.close()

        return {"ok": True, "url": f"https://www.instagram.com/{IG_USERNAME}/"}

    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)
