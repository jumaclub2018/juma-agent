import os, psycopg2
from psycopg2.extras import RealDictCursor
from telegram import Bot

PARENT_BOT_TOKEN = os.environ.get("PARENT_BOT_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")


def get_conn():
    return psycopg2.connect(DATABASE_URL)


async def send_broadcast(message: str, hall: str | None = None) -> str:
    """Рассылка родителям. hall=None — всем, иначе только зала."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM parents")
    all_parents = cur.fetchall()

    if hall:
        filtered = []
        for p in all_parents:
            cur.execute("SELECT child_name FROM parent_children WHERE uid=%s", (p["uid"],))
            children = [r["child_name"] for r in cur.fetchall()]
            for child in children:
                cur.execute("SELECT hall FROM students WHERE name=%s", (child,))
                row = cur.fetchone()
                if row and row["hall"] == hall:
                    filtered.append(p)
                    break
        parents = filtered
    else:
        parents = all_parents

    cur.close()
    conn.close()

    bot = Bot(token=PARENT_BOT_TOKEN)
    sent, failed = 0, 0
    full_msg = "📢 Juma Club:\n\n" + message
    for p in parents:
        try:
            await bot.send_message(chat_id=p["uid"], text=full_msg)
            sent += 1
        except Exception:
            failed += 1

    target = f"зала {hall}" if hall else "всем родителям"
    return f"✅ Рассылка {target}: отправлено {sent}, не доставлено {failed}."
