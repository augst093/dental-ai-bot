"""
Правила расписания для записи из бота. Чистые функции, без базы и сети.

Повторяют правила Mini App (dental_miniapp/src/lib/slots.ts и patientAppointments.ts):
- часовой пояс Asia/Tashkent (UTC+5, без перехода на летнее время);
- дни недели по схеме 0=воскресенье ... 6=суббота (как в поле Doctor.workingDays);
- шаг слота из карточки врача; занятыми считаются записи в статусах pending, confirmed, reschedule_requested;
- минимальный запас до визита 2 часа при записи, 3 часа при переносе и отмене пациентом.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, List, Optional, Set, Tuple

TASHKENT = timezone(timedelta(hours=5), name="Asia/Tashkent")
UTC = timezone.utc

BOOKING_LEAD_MINUTES = 120
CHANGE_WINDOW_HOURS = 3
ACTIVE_STATUSES = ("pending", "confirmed", "reschedule_requested")
CHANGEABLE_STATUSES = ("pending", "confirmed", "reschedule_requested")


@dataclass(frozen=True)
class DoctorHours:
    working_days: Set[int]  # 0=Вс ... 6=Сб
    start_minutes: int  # минуты от полуночи, локальное время
    end_minutes: int
    slot_minutes: int


def parse_working_days(csv: str) -> Set[int]:
    days: Set[int] = set()
    for part in (csv or "").split(","):
        part = part.strip()
        if part.isdigit() and 0 <= int(part) <= 6:
            days.add(int(part))
    return days or {1, 2, 3, 4, 5, 6}


def parse_hhmm(value: str, default: int) -> int:
    try:
        h, m = value.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return default


def doctor_hours(row: dict) -> DoctorHours:
    return DoctorHours(
        working_days=parse_working_days(row.get("workingDays") or row.get("working_days") or ""),
        start_minutes=parse_hhmm(row.get("workingHoursStart") or "09:00", 9 * 60),
        end_minutes=parse_hhmm(row.get("workingHoursEnd") or "20:00", 20 * 60),
        slot_minutes=int(row.get("slotDurationMinutes") or 30),
    )


def local_to_utc(date_iso: str, hhmm: str) -> datetime:
    y, m, d = (int(x) for x in date_iso.split("-"))
    h, mi = (int(x) for x in hhmm.split(":"))
    return datetime(y, m, d, h, mi, tzinfo=TASHKENT).astimezone(UTC)


def day_bounds_utc(date_iso: str) -> Tuple[datetime, datetime]:
    start = local_to_utc(date_iso, "00:00")
    return start, start + timedelta(days=1)


def slot_starts(
    date_iso: str,
    hours: DoctorHours,
    busy_utc: Iterable[datetime],
    now_utc: datetime,
    lead_minutes: int = BOOKING_LEAD_MINUTES,
) -> List[Tuple[str, datetime]]:
    """Свободные слоты дня: [(\"09:30\", datetime_utc), ...] по возрастанию времени."""
    d = date.fromisoformat(date_iso)
    js_weekday = (d.weekday() + 1) % 7  # Python: пн=0; здесь: вс=0
    if js_weekday not in hours.working_days:
        return []

    busy = {b if b.tzinfo else b.replace(tzinfo=UTC) for b in busy_utc}
    earliest = now_utc + timedelta(minutes=lead_minutes)
    result: List[Tuple[str, datetime]] = []
    minute = hours.start_minutes
    while minute + hours.slot_minutes <= hours.end_minutes:
        hhmm = f"{minute // 60:02d}:{minute % 60:02d}"
        when = local_to_utc(date_iso, hhmm)
        if when >= earliest and when not in busy:
            result.append((hhmm, when))
        minute += hours.slot_minutes
    return result


def can_change(status: str, visit_utc: datetime, now_utc: datetime, owner_ok: bool) -> Tuple[bool, str]:
    """Может ли пациент перенести или отменить запись. Возвращает (можно, код причины)."""
    if not owner_ok:
        return False, "NOT_OWNER"
    if status not in CHANGEABLE_STATUSES:
        return False, "NOT_CHANGEABLE"
    hours_left = (visit_utc - now_utc).total_seconds() / 3600
    if hours_left < CHANGE_WINDOW_HOURS:
        return False, "TOO_LATE"
    return True, "OK"
