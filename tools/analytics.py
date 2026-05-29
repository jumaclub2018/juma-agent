import psycopg2, os
from psycopg2.extras import RealDictCursor
from datetime import date, timedelta

DATABASE_URL = os.environ.get("DATABASE_URL", "")


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def get_attendance_report(days: int = 30) -> str:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM students ORDER BY name")
    students = cur.fetchall()

    at_risk, no_lessons, low, regular = [], [], [], []
    today = date.today()

    for s in students:
        cur.execute(
            "SELECT COUNT(*) as cnt FROM attendance WHERE child_name=%s AND visit_date >= %s",
            (s["name"], today - timedelta(days=days))
        )
        visits = cur.fetchone()["cnt"]
        cur.execute(
            "SELECT MAX(visit_date) as last FROM attendance WHERE child_name=%s", (s["name"],)
        )
        last = cur.fetchone()["last"]
        days_absent = (today - last).days if last else 999

        entry = {"name": s["name"], "hall": s["hall"], "visits": visits,
                 "left": s["left_count"], "days_absent": days_absent}
        if s["left_count"] <= 0:
            no_lessons.append(entry)
        elif days_absent >= 14:
            at_risk.append(entry)
        elif visits <= 2:
            low.append(entry)
        elif visits >= 6:
            regular.append(entry)

    cur.close()
    conn.close()

    lines = [f"Период: {days} дней. Всего учеников: {len(students)}\n"]
    if no_lessons:
        lines.append("❌ Закончились занятия: " + ", ".join(f"{e['name']} ({e['hall']})" for e in no_lessons))
    if at_risk:
        lines.append("⚠️ Не приходили 14+ дней: " + ", ".join(f"{e['name']} ({e['days_absent']} дн.)" for e in at_risk))
    if low:
        lines.append("😔 Мало ходят: " + ", ".join(f"{e['name']} ({e['visits']} раз)" for e in low))
    if regular:
        lines.append("🔥 Регулярные: " + ", ".join(f"{e['name']} ({e['visits']} раз)" for e in regular))
    return "\n".join(lines)


def get_finance_report(days: int = 30) -> str:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        "SELECT * FROM payments WHERE paid_date >= %s ORDER BY paid_date DESC",
        (date.today() - timedelta(days=days),)
    )
    payments = cur.fetchall()
    cur.close()
    conn.close()

    if not payments:
        return f"За последние {days} дней платежей не найдено."

    total = sum(p["amount"] for p in payments)
    by_hall: dict = {}
    for p in payments:
        h = p["hall"] or "Неизвестно"
        by_hall.setdefault(h, {"count": 0, "sum": 0})
        by_hall[h]["count"] += 1
        by_hall[h]["sum"] += p["amount"]

    lines = [f"💰 Финансы за {days} дней:"]
    lines.append(f"Итого: {total:,} ₽ | Платежей: {len(payments)}".replace(",", " "))
    for hall, info in by_hall.items():
        lines.append(f"  {hall}: {info['count']} абонементов, {info['sum']:,} ₽".replace(",", " "))
    lines.append("\nПоследние платежи:")
    for p in payments[:5]:
        lines.append(f"  {p['paid_date'].strftime('%d.%m')} — {p['student_name']}: {p['amount']} ₽")
    return "\n".join(lines)


def get_leads_report() -> str:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM leads ORDER BY created_date DESC LIMIT 20")
    leads = cur.fetchall()
    cur.close()
    conn.close()

    if not leads:
        return "Заявок нет."

    by_status: dict = {}
    for l in leads:
        by_status.setdefault(l["status"], []).append(l)

    status_labels = {
        "new": "🆕 Новые", "scheduled": "📅 Записаны на пробное",
        "came": "✅ Пришли", "no_show": "❌ Не пришли", "closed": "🚫 Закрытые"
    }
    lines = ["📋 Заявки:"]
    for status, label in status_labels.items():
        if status in by_status:
            lines.append(f"\n{label} ({len(by_status[status])}):")
            for l in by_status[status][:3]:
                lines.append(f"  {l['name']} | {l['phone']} | {l['hall'] or '—'}")
    return "\n".join(lines)


def get_students_list() -> str:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM students ORDER BY hall, name")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    by_hall: dict = {}
    for r in rows:
        by_hall.setdefault(r["hall"], []).append(r)

    lines = [f"👥 Учеников всего: {len(rows)}\n"]
    for hall, students in by_hall.items():
        lines.append(f"🏟 {hall} ({len(students)}):")
        for s in students:
            status = "❌" if s["left_count"] <= 0 else ("⚠️" if s["left_count"] <= 2 else "✅")
            lines.append(f"  {status} {s['name']} | {s['left_count']}/{s['total']} | {s['belt']}")
    return "\n".join(lines)
