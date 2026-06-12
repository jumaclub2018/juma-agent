import os, json, anthropic
from datetime import date
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters
from tools.analytics import get_attendance_report, get_finance_report, get_leads_report, get_students_list
from tools.instagram_local_agent import publish_photo
from tools.broadcast import send_broadcast
from tools.google_calendar import (
    create_event as calendar_create_event,
    list_events as calendar_list_events,
    delete_event as calendar_delete_event,
)
from tools.yclients import get_clients as yc_get_clients, get_records as yc_get_records

TELEGRAM_TOKEN = os.environ.get("AGENT_BOT_TOKEN", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")
OWNER_ID = int(os.environ.get("ADMIN_ID", "0"))

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# Фото ожидающее публикации: {uid: bytes}
pending_photos: dict = {}
# История диалога per-user для многошаговых сценариев (подтверждение удаления и т.п.)
conversations: dict = {}

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
        "name": "create_calendar_event",
        "description": "Создать событие в Google Calendar. Используй когда пользователь говорит 'добавь', 'запланируй', 'поставь' тренировку или событие.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":            {"type": "string",  "description": "Название события"},
                "date":             {"type": "string",  "description": "Дата в формате YYYY-MM-DD"},
                "time":             {"type": "string",  "description": "Время начала HH:MM"},
                "duration_minutes": {"type": "integer", "description": "Длительность в минутах (по умолчанию 60)"},
                "description":      {"type": "string",  "description": "Описание события (необязательно)"},
            },
            "required": ["title", "date", "time"]
        }
    },
    {
        "name": "list_calendar_events",
        "description": (
            "Показать события Google Calendar за период. "
            "Используй ПЕРЕД удалением — чтобы найти нужное событие и показать пользователю."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "Начало периода YYYY-MM-DD"},
                "date_to":   {"type": "string", "description": "Конец периода YYYY-MM-DD"},
            },
            "required": ["date_from", "date_to"]
        }
    },
    {
        "name": "delete_calendar_event",
        "description": (
            "Удалить событие из Google Calendar по его id. "
            "НИКОГДА не вызывай без явного подтверждения пользователя ('да', 'удали', 'подтверждаю')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "ID события из list_calendar_events"},
            },
            "required": ["event_id"]
        }
    },
    {
        "name": "get_yclients_clients",
        "description": (
            "Список клиентов из YClients CRM: количество, имена, телефоны. "
            "Используй когда спрашивают про клиентскую базу, сколько человек занимается, или нужно найти конкретного клиента."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "Сколько клиентов запросить (по умолчанию 200)"}
            }
        }
    },
    {
        "name": "get_yclients_records",
        "description": (
            "Записи (расписание) из YClients на указанную дату. "
            "Используй когда спрашивают кто записан на тренировку, сколько записей сегодня/завтра/на конкретный день."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Дата в формате YYYY-MM-DD. Если не указана — берётся сегодня."}
            }
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

def _build_system() -> str:
    today = date.today().strftime("%Y-%m-%d")
    return f"""Ты личный ИИ-агент владельца клуба дзюдо и самбо Juma Club (Подмосковье).
Три зала: ЖК Весна, Селятино, Эко Бунино.
Отвечай коротко и по делу. Используй инструменты когда нужны данные или действия.

Сегодня: {today} (используй для вычисления дат — «завтра», «в пятницу» и т.д.)

Правило публикации в Instagram:
- Когда пользователь просит опубликовать фото — ВСЕГДА вызывай инструмент publish_instagram.
- Составь caption внутри вызова инструмента, не отправляй его отдельным сообщением.
- Не спрашивай подтверждения — публикуй сразу.

Правило удаления событий Calendar:
- При запросе на удаление: сначала вызови list_calendar_events, найди подходящее событие.
- Покажи пользователю: название, дата, время — и спроси подтверждение.
- Если подходит несколько событий — покажи список и спроси какое именно.
- delete_calendar_event вызывай ТОЛЬКО после явного "да" / "удали" / "подтверждаю".

Язык: русский."""


async def run_agent(update: Update, user_text: str):
    uid = update.message.chat_id
    photo_bytes = pending_photos.get(uid)

    # Сохраняем историю для многошаговых сценариев (подтверждение удаления и т.п.)
    history = conversations.setdefault(uid, [])
    history.append({"role": "user", "content": user_text})
    if len(history) > 20:
        history[:] = history[-20:]
    messages = list(history)

    await update.message.reply_text("⏳")

    while True:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2048,
            system=_build_system(),
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if hasattr(b, "text")), "—")
            await update.message.reply_text(text)
            history.append({"role": "assistant", "content": text})
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
                        pub = publish_photo(photo_bytes, caption)
                        if pub["ok"]:
                            result = f"✅ Опубликовано!\n{pub['url']}"
                        else:
                            result = f"❌ Ошибка: {pub['error']}"

                elif name == "create_calendar_event":
                    ev = calendar_create_event(
                        title=inp["title"],
                        date=inp["date"],
                        time=inp["time"],
                        duration_minutes=inp.get("duration_minutes", 60),
                        description=inp.get("description", ""),
                    )
                    if ev["ok"]:
                        result = f"✅ Событие создано: {ev['start']}–{ev['end']}\n{ev['url']}"
                    else:
                        result = f"❌ Ошибка: {ev['error']}"

                elif name == "list_calendar_events":
                    ev = calendar_list_events(
                        date_from=inp["date_from"],
                        date_to=inp["date_to"],
                    )
                    if ev["ok"]:
                        events = ev["events"]
                        if not events:
                            result = "Событий за этот период не найдено."
                        else:
                            lines = [f"{e['date']} {e['time_start']}–{e['time_end']}  {e['title']}  (id: {e['id']})" for e in events]
                            result = "Найдены события:\n" + "\n".join(lines)
                    else:
                        result = f"❌ Ошибка: {ev['error']}"

                elif name == "delete_calendar_event":
                    ev = calendar_delete_event(event_id=inp["event_id"])
                    if ev["ok"]:
                        result = "✅ Событие удалено."
                    else:
                        result = f"❌ Ошибка удаления: {ev['error']}"

                elif name == "get_yclients_clients":
                    res = yc_get_clients(count=inp.get("count", 200))
                    if res.get("ok"):
                        clients = res["data"]
                        lines = [
                            f"• {c.get('name', '—')} | {c.get('phone', '—')}"
                            for c in clients[:50]
                        ]
                        tail = f"\n…и ещё {len(clients) - 50}" if len(clients) > 50 else ""
                        result = f"Клиентов в YClients: {len(clients)}\n" + "\n".join(lines) + tail
                    else:
                        result = f"❌ {res.get('error')}"

                elif name == "get_yclients_records":
                    target_date = inp.get("date") or date.today().isoformat()
                    res = yc_get_records(target_date)
                    if res.get("ok"):
                        records = res["data"]
                        if not records:
                            result = f"Записей на {target_date} нет."
                        else:
                            lines = []
                            for r in records[:30]:
                                client_name = (r.get("client") or {}).get("name", "—")
                                staff_name  = (r.get("staff")  or {}).get("name", "—")
                                dt = r.get("datetime", "—")
                                lines.append(f"• {dt} | {client_name} → {staff_name}")
                            tail = f"\n…и ещё {len(records) - 30}" if len(records) > 30 else ""
                            result = f"Записей на {target_date}: {len(records)}\n" + "\n".join(lines) + tail
                    else:
                        result = f"❌ {res.get('error')}"

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
