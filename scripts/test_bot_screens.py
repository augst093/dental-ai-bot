"""Проверка экранов бота: тексты, длина callback_data (лимит Telegram 64 байта). Запуск: python scripts/test_bot_screens.py"""

import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import bot_screens as bs  # noqa: E402

FAILURES = []


def check(name, ok):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        FAILURES.append(name)


def all_callbacks(markup):
    return [b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data]


def main() -> int:
    services = [
        {"id": str(uuid.uuid4()), "title": "Damon Q2", "category": "Прикус", "price_uzs": 7_500_000, "duration_minutes": 60, "description": None},
        {"id": str(uuid.uuid4()), "title": "Чистка", "category": "Гигиена", "price_uzs": 550_000, "duration_minutes": 45, "description": None},
    ]
    text = bs.services_text("ru", services)
    check("services text groups by category", "<b>Прикус</b>" in text and "<b>Гигиена</b>" in text)
    check("price shown with spaces and 'от'", "от 7 500 000 сум" in text)

    doctors = [{"id": str(uuid.uuid4()), "name": "Сардор Каримов", "specialty": "Имплантолог", "experience_years": 16}]
    dtext = bs.doctors_text("ru", doctors)
    check("doctor card has name and experience", "<b>Сардор Каримов</b>" in dtext and "стаж 16 лет" in dtext)

    days = bs.day_options(date(2026, 11, 6), 10)
    check("10 day options", len(days) == 10 and days[0] == "2026-11-06")

    # Худший случай: uuid в каждом callback
    appt = str(uuid.uuid4())
    items = [{"id": appt, "visit_utc": None, "service": "x", "doctor": "y"}]
    cbs = all_callbacks(bs.my_appointments_keyboard("ru", items))
    cbs += all_callbacks(bs.days_keyboard("ru", days, f"rs:d:{appt}"))
    cbs += all_callbacks(bs.times_keyboard("ru", ["09:00"], f"rs:t:{appt}:2026-11-06", "nav:my"))
    cbs += all_callbacks(bs.services_keyboard("ru", services, "bk:svc"))
    longest = max(len(c.encode()) for c in cbs)
    check(f"all callback_data <= 64 bytes (longest {longest})", longest <= 64)

    print(f"\n{'OK' if not FAILURES else 'FAILED'}: {len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
