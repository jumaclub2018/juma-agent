import os, json, anthropic
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters
from tools.analytics import get_attendance_report, get_finance_report, get_leads_report, get_students_list
from tools.instagram_playwright import publish_photo
from tools.broadcast import send_broadcast

TELEGRAM_TOKEN = os.environ.get("AGENT_BOT_TOKEN", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")
OWNER_ID = int(os.environ.get("ADMIN_ID", "0"))

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# Фото ожидающее публикации: {uid: bytes}
pending_photos: dict = {}

TOOLS = [
    {
        "name": "get_analytics",
        "description": "Анализ посещаемости учеников: кто не ходит, кто регулярный, у кого кончаются занятия.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "За сколько дней анализировать (по умолчанию 30)"}
            }
        }
    },
    {
        "name": "get_finances",
        "description": "Финансовый отчёт: сколько денег пришло, по залам, список последних платежей.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "За сколько дней (по умолчанию 30)"}
            }
        }
    },
    {
        "name": "get_leads",
        "description": "Статус заявок с сайта Tilda: новые, записанные на пробное, пришедшие.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_students",
        "description": "Полный список учеников по залам с остатком занятий и поясом.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "publish_instagram",
        "description": (
            "ОБЯЗАТЕЛЬНО вызывать этот инструмент когда пользователь просит опубликовать фото в Instagram. "
            "Инструмент публикует фото напрямую в аккаунт @jumaclub. "
            "Сам составь caption — живой текст с эмодзи и хэштегами #JumaClub #дзюдо #самбо — и передай его сюда. "
            "НЕ отправляй текст поста пользователю отдельным сообщением — только вызывай этот инструмент."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "caption": {"type": "string", "description": "Текст поста с эмодзи и хэштегами"},
            },
            "required": ["caption"]
        }
    },
    {
        "name": "send_broadcast",
        "description": "Отправить сообщение родителям через бот.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Текст сообщения"},
                "hall": {"type": "string", "description": "Зал (ЖК Весна / Селятино / Эко Бунино) или пустая строка — всем"}
            },
            "required": ["message"]
        }
    },
]

SYSTEM = """Ты личный ИИ-агент владельца клуба дзюдо и самбо Juma Club (Подмосковье).
Три зала: ЖК Весна, Селятино, Эко Бунино.
Отвечай коротко и по делу. Используй инструменты когда нужны данные или действия.

Правило публикации в Instagram:
- Когда пользователь просит опубликовать фото — ВСЕГДА вызывай инструмент publish_instagram.
- Составь caption внутри вызова инструмента, не отправляй его отдельным сообщением.
- Не спрашивай подтверждения — публикуй сразу.

Язык: русский."""


async def run_agent(update: Update, user_text: str):
    uid = update.message.chat_id
    photo_bytes = pending_photos.get(uid)
    messages = [{"role": "user", "content": user_text}]
    await update.message.reply_text("⏳")

    while True:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2048,
            system=SYSTEM,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if hasattr(b, "text")), "—")
            await update.message.reply_text(text)
            break

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                name = block.name
                inp = block.input

                if name == "get_analytics":
                    result = get_attendance_report(inp.get("days", 30))

                elif name == "get_finances":
                    result = get_finance_report(inp.get("days", 30))

                elif name == "get_leads":
                    result = get_leads_report()

                elif name == "get_students":
                    result = get_students_list()

                elif name == "publish_instagram":
                    caption = inp["caption"]
                    if not photo_bytes:
                        result = "❌ Нет фото для публикации. Отправь фото вместе с запросом."
                    else:
                        pending_photos.pop(uid, None)
                        pub = await publish_photo(photo_bytes, caption)
                        if pub["ok"]:
                            result = f"✅ Опубликовано!\n{pub['url']}"
                        else:
                            result = f"❌ Ошибка: {pub['error']}"

                elif name == "send_broadcast":
                    hall = inp.get("hall") or None
                    result = await send_broadcast(inp["message"], hall)

                else:
                    result = "Инструмент не найден."

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

            messages.append({"role": "user", "content": tool_results})


async def handle_text(update: Update, context):
    if update.message.chat_id != OWNER_ID:
        return

    uid = update.message.chat_id
    text = update.message.text.strip()

    await run_agent(update, text)


async def handle_photo(update: Update, context):
    if update.message.chat_id != OWNER_ID:
        return

    uid = update.message.chat_id
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    photo_bytes = await file.download_as_bytearray()
    pending_photos[uid] = bytes(photo_bytes)

    caption = update.message.caption
    if caption:
        await run_agent(update, caption)
    else:
        await update.message.reply_text(
            "📸 Фото сохранено. Напиши что с ним сделать — например:\n"
            "«опубликуй в Instagram про победу Матвея»"
        )


async def start(update: Update, context):
    if update.message.chat_id != OWNER_ID:
        return
    await update.message.reply_text(
        "👋 Juma Agent на связи!\n\n"
        "Что могу:\n"
        "• Аналитика посещаемости и денег\n"
        "• Статус заявок с сайта\n"
        "• Публикация в Instagram (отправь фото + скажи что написать)\n"
        "• Рассылка родителям\n\n"
        "Просто пиши что нужно."
    )


app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

print("Juma Agent запущен!")
app.run_polling()
