"""
Анализ посещаемости по группам YClients за период.
Запуск: python3 analytics_attendance.py [start_date] [end_date]
По умолчанию: 2026-04-01 – 2026-05-31
"""

import os, sys, time
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Загружаем .env.test если запускаем локально
_env = Path(__file__).parent.parent / "judo_bot" / ".env.test"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).parent))
from tools.yclients import _get, COMPANY_ID

START = sys.argv[1] if len(sys.argv) > 1 else "2026-04-01"
END   = sys.argv[2] if len(sys.argv) > 2 else "2026-05-31"


def fetch_records(start: str, end: str) -> list:
    """Собирает все записи за период постраничной прокруткой."""
    all_records = []
    for page in range(1, 50):
        time.sleep(0.3)
        res = _get(f"/records/{COMPANY_ID}", params={"count": 200, "page": page})
        data = res.get("data") or []
        if not data:
            break
        in_range = [r for r in data if start <= r["date"][:10] <= end]
        all_records.extend(in_range)
        oldest = min(r["date"][:10] for r in data)
        if oldest < start:
            break
    return all_records


def parse_records(records: list) -> dict:
    """
    Возвращает структуру:
    { group_title: { client_id: {"name": str, "attended": int, "total": int} } }
    """
    groups: dict = defaultdict(lambda: defaultdict(lambda: {"name": "", "attended": 0, "total": 0}))

    for r in records:
        group = (r.get("services") or [{}])[0].get("title", "Без группы")
        client = r.get("client") or {}
        cid    = client.get("id", 0)
        cname  = client.get("name") or client.get("display_name") or "—"
        att    = r.get("attendance", 0)   # 1=пришёл, 0=не отмечен/-1=отмена

        entry = groups[group][cid]
        entry["name"] = cname
        entry["total"] += 1
        if att == 1:
            entry["attended"] += 1

    return groups


def months_in_range(start: str, end: str) -> float:
    d0 = datetime.strptime(start, "%Y-%m-%d")
    d1 = datetime.strptime(end,   "%Y-%m-%d")
    return max((d1 - d0).days / 30.44, 1.0)


def print_report(groups: dict, start: str, end: str, total_records: int):
    months = months_in_range(start, end)

    print("=" * 60)
    print(f"  ПОСЕЩАЕМОСТЬ ПО ГРУППАМ  {start} – {end}")
    print("=" * 60)
    print(f"  Всего записей в базе:  {total_records}")
    print(f"  Расчётный период:      {months:.1f} мес.\n")

    for group in sorted(groups.keys()):
        clients = groups[group]
        if not clients:
            continue

        attended_list = [c["attended"] for c in clients.values()]
        total_list    = [c["total"]    for c in clients.values()]

        # Считаем только клиентов у кого есть хоть одна запись
        rates = [
            c["attended"] / c["total"]
            for c in clients.values()
            if c["total"] > 0
        ]
        monthly = [c["attended"] / months for c in clients.values()]

        avg_rate    = sum(rates)    / len(rates)    if rates    else 0
        avg_monthly = sum(monthly)  / len(monthly)  if monthly  else 0
        min_att     = min(attended_list)
        max_att     = max(attended_list)
        total_att   = sum(attended_list)
        total_sched = sum(total_list)

        print(f"┌─ {group}")
        print(f"│  Детей в группе:        {len(clients)}")
        print(f"│  Всего назначено:        {total_sched}")
        print(f"│  Всего пришли:           {total_att}")
        print(f"│  Средняя посещаемость:   {avg_rate * 100:.0f}%")
        print(f"│  Среднее занятий/мес:    {avg_monthly:.1f}")
        print(f"│  Разброс (мин–макс):     {min_att}–{max_att} занятий за период")

        # Топ-3 активных и 3 пропускающих
        by_rate = sorted(clients.values(), key=lambda c: c["attended"] / max(c["total"], 1))
        skippers = [c for c in by_rate[:3]  if c["attended"] / max(c["total"], 1) < 0.5]
        leaders  = [c for c in by_rate[-3:] if c["total"] > 1]

        if skippers:
            names = ", ".join(f"{c['name']} ({c['attended']}/{c['total']})" for c in skippers)
            print(f"│  Пропускают >50%:        {names}")
        if leaders:
            names = ", ".join(f"{c['name']} ({c['attended']}/{c['total']})" for c in reversed(leaders))
            print(f"│  Самые стабильные:       {names}")

        print("│")

    print("└─ конец отчёта")


def main():
    print(f"Загружаем записи {START} – {END}…")
    records = fetch_records(START, END)
    print(f"Получено: {len(records)} записей\n")

    if not records:
        print("Нет данных за указанный период.")
        return

    # Показываем реальный диапазон дат в базе
    actual_start = min(r["date"][:10] for r in records)
    actual_end   = max(r["date"][:10] for r in records)
    print(f"Реальный диапазон данных: {actual_start} – {actual_end}\n")

    groups = parse_records(records)
    print_report(groups, actual_start, actual_end, len(records))


if __name__ == "__main__":
    main()
