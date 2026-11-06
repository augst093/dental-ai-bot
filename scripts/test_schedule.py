"""Проверка правил расписания для записи из бота (без базы). Запуск: python scripts/test_schedule.py"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.schedule import (  # noqa: E402
    UTC,
    can_change,
    doctor_hours,
    local_to_utc,
    slot_starts,
)

WEEKDAY_ROW = {"workingDays": "1,2,3,4,5,6", "workingHoursStart": "09:00", "workingHoursEnd": "20:00", "slotDurationMinutes": 30}
EARLY_NOW = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)  # далеко в прошлом относительно тестовых дат


def check(name, condition, failures):
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    if not condition:
        failures.append(name)


def main() -> int:
    failures: list = []
    hours = doctor_hours(WEEKDAY_ROW)

    # Понедельник 2 ноября 2026
    monday = "2026-11-02"
    slots = slot_starts(monday, hours, [], EARLY_NOW)
    check("full working day has 22 half-hour slots", len(slots) == 22, failures)
    check("first slot is 09:00 Tashkent", slots[0][0] == "09:00", failures)
    check("last slot is 19:30 Tashkent", slots[-1][0] == "19:30", failures)
    check("09:00 Tashkent is 04:00 UTC", slots[0][1] == datetime(2026, 11, 2, 4, 0, tzinfo=UTC), failures)

    busy = [local_to_utc(monday, "10:00")]
    slots_busy = slot_starts(monday, hours, busy, EARLY_NOW)
    check("busy slot is removed", all(t != "10:00" for t, _ in slots_busy), failures)
    check("busy removes exactly one slot", len(slots_busy) == 21, failures)

    # Лead time: сейчас 10:00 по Ташкенту, слоты раньше 12:00 недоступны
    now_tashkent_10 = local_to_utc(monday, "10:00")
    slots_soon = slot_starts(monday, hours, [], now_tashkent_10)
    check("no slot earlier than now + 2 hours", slots_soon[0][0] == "12:00", failures)

    # Воскресенье закрыто по умолчанию
    sunday = "2026-11-08"
    check("sunday has no slots by default", slot_starts(sunday, hours, [], EARLY_NOW) == [], failures)

    # Правила переноса и отмены
    visit = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
    check("pending far ahead can change", can_change("pending", visit, visit - timedelta(days=2), True)[0], failures)
    check("not owner cannot change", can_change("pending", visit, visit - timedelta(days=2), False) == (False, "NOT_OWNER"), failures)
    check("completed cannot change", can_change("completed", visit, visit - timedelta(days=2), True) == (False, "NOT_CHANGEABLE"), failures)
    check("less than 3 hours is too late", can_change("confirmed", visit, visit - timedelta(hours=2), True) == (False, "TOO_LATE"), failures)

    print(f"\n{'OK' if not failures else 'FAILED'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
