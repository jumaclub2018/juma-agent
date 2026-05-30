import os, json, tempfile, time
from pathlib import Path

IG_USERNAME = os.environ.get("IG_USERNAME", "")
IG_PASSWORD = os.environ.get("IG_PASSWORD", "")

COOKIES_FILE = Path("/tmp/ig_playwright_cookies.json")


def _save_cookies(context, cookies):
    try:
        COOKIES_FILE.write_text(json.dumps(cookies))
    except Exception:
        pass


async def _login(page, context):
    await page.goto("https://www.instagram.com/accounts/login/", wait_until="networkidle")
    await page.wait_for_timeout(2000)

    try:
        btn = page.locator("text=Allow all cookies").first
        if await btn.is_visible(timeout=3000):
            await btn.click()
            await page.wait_for_timeout(1000)
    except Exception:
        pass

    await page.fill('input[name="username"]', IG_USERNAME)
    await page.fill('input[name="password"]', IG_PASSWORD)
    await page.click('button[type="submit"]')
    await page.wait_for_url("**/instagram.com/**", timeout=15000)
    await page.wait_for_timeout(3000)

    for label in ("Not now", "Not Now"):
        try:
            btn = page.locator(f"text={label}").first
            if await btn.is_visible(timeout=2000):
                await btn.click()
                await page.wait_for_timeout(1000)
        except Exception:
            pass

    _save_cookies(context, await context.cookies())


async def _publish(image_bytes: bytes, caption: str) -> dict:
    from playwright.async_api import async_playwright

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(image_bytes)
        tmp_path = f.name

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            logged_in = False
            if COOKIES_FILE.exists():
                try:
                    await context.add_cookies(json.loads(COOKIES_FILE.read_text()))
                    await page.goto("https://www.instagram.com/", wait_until="networkidle")
                    await page.wait_for_timeout(2000)
                    if "login" not in page.url:
                        logged_in = True
                except Exception:
                    COOKIES_FILE.unlink(missing_ok=True)

            if not logged_in:
                await _login(page, context)
                await page.goto("https://www.instagram.com/", wait_until="networkidle")
                await page.wait_for_timeout(2000)

            # Кнопка создания поста
            create_btn = page.locator('[aria-label="New post"]').first
            await create_btn.wait_for(timeout=10000)
            await create_btn.click()
            await page.wait_for_timeout(1000)

            try:
                post_option = page.locator("text=Post").first
                if await post_option.is_visible(timeout=3000):
                    await post_option.click()
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            # Загрузка файла
            async with page.expect_file_chooser() as fc_info:
                await page.locator('[aria-label="New post"]').first.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(tmp_path)
            await page.wait_for_timeout(2000)

            try:
                ok_btn = page.locator("text=OK").first
                if await ok_btn.is_visible(timeout=2000):
                    await ok_btn.click()
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            # Next → Next
            for _ in range(2):
                next_btn = page.locator("text=Next").first
                await next_btn.wait_for(timeout=10000)
                await next_btn.click()
                await page.wait_for_timeout(1000)

            # Caption
            caption_box = page.locator('div[aria-label="Write a caption..."]').first
            await caption_box.wait_for(timeout=10000)
            await caption_box.click()
            await caption_box.type(caption, delay=30)
            await page.wait_for_timeout(1000)

            # Share
            share_btn = page.locator("text=Share").first
            await share_btn.wait_for(timeout=10000)
            await share_btn.click()
            await page.wait_for_selector("text=Your post has been shared", timeout=60000)
            await page.wait_for_timeout(2000)

            _save_cookies(context, await context.cookies())
            await browser.close()

        return {"ok": True, "url": f"https://www.instagram.com/{IG_USERNAME}/"}

    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def publish_photo(image_bytes: bytes, caption: str) -> dict:
    if not IG_USERNAME or not IG_PASSWORD:
        return {"ok": False, "error": "IG_USERNAME и IG_PASSWORD не заданы в переменных окружения."}
    try:
        from playwright.async_api import async_playwright  # noqa: проверка установки
    except ImportError:
        return {"ok": False, "error": "Playwright не установлен. Добавь playwright в requirements.txt и запусти playwright install chromium."}
    return await _publish(image_bytes, caption)
