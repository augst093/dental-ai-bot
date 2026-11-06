"""
Запись на приём, «Мои записи» и каталог из общей базы: обработчики aiogram.

Подключаются из bot.py вызовом register_booking_handlers(dp), ДО общего обработчика текста.
Правила времени и переноса — в services/schedule.py, тексты и клавиатуры — в services/bot_screens.py.
Записи создаются через database.book_slot / reschedule_slot, которые проверяют занятость слота
под блокировкой, поэтому два пациента не займут одно время.
"""

import re
import uuid
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from aiogram import Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from database import db
from keyboards import get_back_home_keyboard, get_services_catalog_keyboard
from services import bot_screens as bs
from templates import SERVICES_CATALOG_INTRO
from services.schedule import (
    TASHKENT,
    UTC,
    can_change,
    day_bounds_utc,
    doctor_hours,
    local_to_utc,
    slot_starts,
)

logger = logging.getLogger("dental_bot.booking")

PHONE_RE = re.compile(r"^\+?\d[\d\s()\-]{8,18}\d$")
REMINDER_OFFSETS = (("reminder_24h", timedelta(hours=24)), ("reminder_2h", timedelta(hours=2)))


class BookingFlow(StatesGroup):
    phone = State()


async def _lang(user_id: int) -> str:
    lang = await db.get_user_language(user_id)
    return lang if lang in ("ru", "uz", "en") else "ru"


def _now() -> datetime:
    return datetime.now(UTC)


def _today_tashkent():
    return _now().astimezone(TASHKENT).date()


def _visit_text(lang: str, visit_utc: datetime) -> str:
    local = visit_utc.astimezone(TASHKENT)
    return f"{bs.long_day(lang, local.date().isoformat())}, {local.strftime('%H:%M')}"


async def _catalog() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    return await db.fetch_active_doctors(), await db.fetch_active_services()


async def _day_slots(
    doctors: List[Dict[str, Any]], date_iso: str, only_doctor_id: Optional[str]
) -> Dict[str, List[Tuple[Dict[str, Any], datetime]]]:
    """Свободные времена дня: время -> список (врач, момент UTC), где врач свободен."""
    result: Dict[str, List[Tuple[Dict[str, Any], datetime]]] = {}
    now = _now()
    start, end = day_bounds_utc(date_iso)
    for doc in doctors:
        if only_doctor_id and doc["id"] != only_doctor_id:
            continue
        busy = await db.fetch_busy_utc(doc["id"], start, end)
        for hhmm, when in slot_starts(date_iso, doctor_hours(doc), busy, now):
            result.setdefault(hhmm, []).append((doc, when))
    return dict(sorted(result.items()))


async def _schedule_reminders(appointment_id: str, visit_utc: datetime) -> None:
    now = _now()
    for kind, delta in REMINDER_OFFSETS:
        due = visit_utc - delta
        if due > now:
            await db.schedule_reminder(appointment_id, kind, due.astimezone(TASHKENT).isoformat())


async def _alert_staff(data: Dict[str, Any], visit: datetime, name: str, phone: str, username: Optional[str]) -> None:
    """Карточка новой записи в группу администраторов (через очередь отправки)."""
    try:
        from services.outbox_worker import enqueue_staff_alert
        local = visit.astimezone(TASHKENT)
        text = (
            "🆕 <b>Запись из бота</b>\n"
            f"👤 {name}" + (f" (@{username})" if username else "") + "\n"
            f"📱 {phone}\n"
            f"🦷 {data['service_title']}\n"
            f"👨‍⚕️ {data['doctor_name']}\n"
            f"🕒 {local.strftime('%d.%m.%Y %H:%M')}"
        )
        await enqueue_staff_alert(text)
    except Exception:
        logger.exception("Не удалось поставить в очередь алерт администраторам о записи из бота")


async def _edit_or_send(callback: types.CallbackQuery, text: str, markup) -> None:
    try:
        await callback.message.edit_text(text=text, parse_mode=ParseMode.HTML, reply_markup=markup)
    except Exception:
        await callback.message.answer(text=text, parse_mode=ParseMode.HTML, reply_markup=markup)
    await callback.answer()


def register_booking_handlers(dp: Dispatcher) -> None:
    # ---------------------------------------------------------------
    # Каталог и врачи из базы
    # ---------------------------------------------------------------

    @dp.callback_query(F.data == "nav:doctors")
    async def cb_doctors(callback: types.CallbackQuery):
        lang = await _lang(callback.from_user.id)
        doctors, _ = await _catalog()
        if not doctors:
            await callback.answer(bs.tr(lang)["no_catalog"], show_alert=True)
            return
        await _edit_or_send(callback, bs.doctors_text(lang, doctors), get_back_home_keyboard(lang))

    @dp.callback_query(F.data == "catalog_db")
    async def cb_catalog_db(callback: types.CallbackQuery):
        """Каталог услуг: из базы, если там есть активные услуги; иначе прежний прайс из шаблонов."""
        lang = await _lang(callback.from_user.id)
        _, services = await _catalog()
        if not services:
            await _edit_or_send(callback, SERVICES_CATALOG_INTRO.get(lang, SERVICES_CATALOG_INTRO["ru"]),
                                get_services_catalog_keyboard(lang))
            return
        await _edit_or_send(callback, bs.services_text(lang, services), bs.services_keyboard(lang, services, "dbsvc"))

    @dp.callback_query(F.data.startswith("dbsvc:"))
    async def cb_db_service(callback: types.CallbackQuery):
        lang = await _lang(callback.from_user.id)
        service_id = callback.data.split(":", 1)[1]
        _, services = await _catalog()
        s = next((x for x in services if x["id"] == service_id), None)
        if s is None:
            await callback.answer(bs.tr(lang)["not_found"], show_alert=True)
            return
        lines = [f"<b>{s['title']}</b>", f"<i>{s['category']}</i>", "",
                 f"💰 от {bs.format_sum(s['price_uzs'])}", f"⏱ {s['duration_minutes']} мин"]
        if s.get("description"):
            lines += ["", s["description"]]
        kb = bs.service_card_keyboard(lang, service_id)
        await _edit_or_send(callback, "\n".join(lines), kb)

    # ---------------------------------------------------------------
    # Запись: услуга -> врач -> день -> время -> телефон -> подтверждение
    # ---------------------------------------------------------------

    async def start_booking(callback: types.CallbackQuery, state: FSMContext) -> None:
        lang = await _lang(callback.from_user.id)
        await state.clear()
        _, services = await _catalog()
        if not services:
            await callback.answer(bs.tr(lang)["no_catalog"], show_alert=True)
            return
        await _edit_or_send(callback, bs.tr(lang)["pick_service"], bs.services_keyboard(lang, services, "bk:svc"))

    @dp.callback_query(F.data == "bk:start")
    async def cb_booking_start(callback: types.CallbackQuery, state: FSMContext):
        await start_booking(callback, state)

    @dp.callback_query(F.data.startswith("bk:svc:"))
    async def cb_booking_service(callback: types.CallbackQuery, state: FSMContext):
        lang = await _lang(callback.from_user.id)
        service_id = callback.data.split(":", 2)[2]
        doctors, services = await _catalog()
        if not any(s["id"] == service_id for s in services):
            await callback.answer(bs.tr(lang)["not_found"], show_alert=True)
            return
        await state.update_data(service_id=service_id)
        await _edit_or_send(callback, bs.tr(lang)["pick_doctor"], bs.doctors_choice_keyboard(lang, doctors))

    @dp.callback_query(F.data.startswith("bk:doc:"))
    async def cb_booking_doctor(callback: types.CallbackQuery, state: FSMContext):
        lang = await _lang(callback.from_user.id)
        choice = callback.data.split(":", 2)[2]
        await state.update_data(doctor_pref=None if choice == "any" else choice)
        await _edit_or_send(callback, bs.tr(lang)["pick_day"], bs.days_keyboard(lang, bs.day_options(_today_tashkent()), "bk:day"))

    @dp.callback_query(F.data.startswith("bk:day:"))
    async def cb_booking_day(callback: types.CallbackQuery, state: FSMContext):
        lang = await _lang(callback.from_user.id)
        date_iso = callback.data.split(":", 2)[2]
        data = await state.get_data()
        doctors, _ = await _catalog()
        slots = await _day_slots(doctors, date_iso, data.get("doctor_pref"))
        await state.update_data(date_iso=date_iso)
        if not slots:
            await _edit_or_send(callback, bs.tr(lang)["no_slots"], bs.days_keyboard(lang, bs.day_options(_today_tashkent()), "bk:day"))
            return
        times = list(slots.keys())
        await _edit_or_send(
            callback,
            bs.tr(lang)["pick_time"].format(day=bs.long_day(lang, date_iso)),
            bs.times_keyboard(lang, times, "bk:t", "bk:start"),
        )

    @dp.callback_query(F.data.startswith("bk:t:"))
    async def cb_booking_time(callback: types.CallbackQuery, state: FSMContext):
        lang = await _lang(callback.from_user.id)
        hhmm = callback.data.split(":", 2)[2]
        data = await state.get_data()
        date_iso = data.get("date_iso")
        if not date_iso or not data.get("service_id"):
            await callback.answer(bs.tr(lang)["error"].format(phone=bs.CLINIC_PHONES[0]), show_alert=True)
            return
        doctors, services = await _catalog()
        slots = await _day_slots(doctors, date_iso, data.get("doctor_pref"))
        candidates = slots.get(hhmm)
        if not candidates:
            await callback.answer(bs.tr(lang)["taken"], show_alert=True)
            return
        doc, when = candidates[0]
        service = next(s for s in services if s["id"] == data["service_id"])
        await state.update_data(doctor_id=doc["id"], visit_iso=when.isoformat())
        await state.set_state(BookingFlow.phone)
        await state.update_data(service_title=service["title"], doctor_name=doc["name"], price=service["price_uzs"],
                                duration=service["duration_minutes"], service_db_id=service["id"])
        phone_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=bs.tr(lang)["send_phone"], request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await callback.message.answer(text=bs.tr(lang)["ask_phone"], reply_markup=phone_kb)
        await callback.answer()

    @dp.message(BookingFlow.phone, F.contact)
    async def msg_booking_contact(message: types.Message, state: FSMContext):
        await _after_phone(message, state, message.contact.phone_number)

    @dp.message(BookingFlow.phone, F.text)
    async def msg_booking_phone_text(message: types.Message, state: FSMContext):
        lang = await _lang(message.from_user.id)
        raw = (message.text or "").strip()
        if raw.lower() in (bs.tr(lang)["cancel_flow"].lower(), "/cancel"):
            await state.clear()
            await message.answer(bs.tr(lang)["cancelled"])
            return
        if not PHONE_RE.match(raw):
            await message.answer(bs.tr(lang)["ask_phone"])
            return
        await _after_phone(message, state, raw)

    async def _after_phone(message: types.Message, state: FSMContext, phone: str) -> None:
        lang = await _lang(message.from_user.id)
        data = await state.get_data()
        visit = datetime.fromisoformat(data["visit_iso"])
        text = (
            f"<b>{bs.tr(lang)['confirm_title']}</b>\n\n"
            f"🦷 {data['service_title']}\n"
            f"👨‍⚕️ {data['doctor_name']}\n"
            f"🕒 {_visit_text(lang, visit)}\n"
            f"📱 {phone}\n\n"
            f"<i>{bs.tr(lang)['consent']}</i>"
        )
        await state.update_data(phone=phone)
        await message.answer(text=text, parse_mode=ParseMode.HTML, reply_markup=bs.confirm_keyboard(lang))

    @dp.callback_query(F.data == "bk:ok")
    async def cb_booking_confirm(callback: types.CallbackQuery, state: FSMContext):
        lang = await _lang(callback.from_user.id)
        data = await state.get_data()
        required = ("doctor_id", "visit_iso", "phone", "service_title", "doctor_name", "service_db_id")
        if not all(data.get(k) for k in required):
            await callback.answer(bs.tr(lang)["error"].format(phone=bs.CLINIC_PHONES[0]), show_alert=True)
            return
        visit = datetime.fromisoformat(data["visit_iso"])
        if visit <= _now() + timedelta(minutes=120):
            await state.clear()
            await _edit_or_send(callback, bs.tr(lang)["taken"], bs.days_keyboard(lang, bs.day_options(_today_tashkent()), "bk:day"))
            return
        user = callback.from_user
        appointment_id = str(uuid.uuid4())
        result = await db.book_slot(
            appointment_id=appointment_id,
            telegram_id=user.id,
            client_name=user.full_name or user.first_name or "Пациент",
            phone=data["phone"],
            doctor_id=data["doctor_id"],
            doctor_name=data["doctor_name"],
            service_id=data["service_db_id"],
            service_title=data["service_title"],
            price_uzs=data.get("price"),
            duration_minutes=data.get("duration") or 30,
            visit_utc=visit,
        )
        if result == "taken":
            await state.update_data(visit_iso=None)
            await _edit_or_send(callback, bs.tr(lang)["taken"], bs.days_keyboard(lang, bs.day_options(_today_tashkent()), "bk:day"))
            return
        await _schedule_reminders(appointment_id, visit)
        await _alert_staff(data, visit, user.full_name or "Пациент", data["phone"], user.username)
        await state.clear()
        await _edit_or_send(callback, bs.tr(lang)["booked"], get_back_home_keyboard(lang))

    # ---------------------------------------------------------------
    # Мои записи: список, перенос, отмена
    # ---------------------------------------------------------------

    async def show_my(callback_or_message, user_id: int, edit: bool) -> None:
        lang = await _lang(user_id)
        items = await db.list_my_appointments(user_id)
        text = bs.my_appointments_text(lang, items, _visit_text)
        markup = bs.my_appointments_keyboard(lang, items)
        if isinstance(callback_or_message, types.CallbackQuery):
            await _edit_or_send(callback_or_message, text, markup)
        else:
            await callback_or_message.answer(text=text, parse_mode=ParseMode.HTML, reply_markup=markup)

    @dp.callback_query(F.data == "nav:my")
    async def cb_my(callback: types.CallbackQuery):
        await show_my(callback, callback.from_user.id, edit=True)

    @dp.message(Command("my", "mybookings", "записи"))
    async def cmd_my(message: types.Message):
        await show_my(message, message.from_user.id, edit=False)

    async def _owned(user_id: int, appointment_id: str) -> Optional[Dict[str, Any]]:
        for item in await db.list_my_appointments(user_id):
            if item["id"] == appointment_id:
                return item
        return None

    @dp.callback_query(F.data.startswith("my:c:"))
    async def cb_my_cancel(callback: types.CallbackQuery):
        lang = await _lang(callback.from_user.id)
        appointment_id = callback.data.split(":", 2)[2]
        item = await _owned(callback.from_user.id, appointment_id)
        if item is None:
            await callback.answer(bs.tr(lang)["not_found"], show_alert=True)
            return
        ok, code = can_change(item["status"], item["visit_utc"], _now(), owner_ok=True)
        if not ok:
            key = "too_late" if code == "TOO_LATE" else "not_changeable"
            await callback.answer(bs.tr(lang)[key].format(phone=bs.CLINIC_PHONES[0]), show_alert=True)
            return
        await db.update_appointment_status(appointment_id, "cancelled")
        await _edit_or_send(callback, bs.tr(lang)["cancelled"], _back_home(lang))

    @dp.callback_query(F.data.startswith("my:r:"))
    async def cb_my_reschedule(callback: types.CallbackQuery):
        lang = await _lang(callback.from_user.id)
        appointment_id = callback.data.split(":", 2)[2]
        item = await _owned(callback.from_user.id, appointment_id)
        if item is None:
            await callback.answer(bs.tr(lang)["not_found"], show_alert=True)
            return
        ok, code = can_change(item["status"], item["visit_utc"], _now(), owner_ok=True)
        if not ok or not item.get("doctor_id"):
            key = "too_late" if code == "TOO_LATE" else "not_changeable"
            await callback.answer(bs.tr(lang)[key].format(phone=bs.CLINIC_PHONES[0]), show_alert=True)
            return
        days = [d for d in bs.day_options(_today_tashkent(), 10)]
        buttons = bs.days_keyboard(lang, days, f"rs:d:{appointment_id}")
        await _edit_or_send(callback, bs.tr(lang)["pick_day"], buttons)

    @dp.callback_query(F.data.startswith("rs:d:"))
    async def cb_reschedule_day(callback: types.CallbackQuery):
        lang = await _lang(callback.from_user.id)
        _, _, appointment_id, date_iso = callback.data.split(":", 3)
        item = await _owned(callback.from_user.id, appointment_id)
        if item is None or not item.get("doctor_id"):
            await callback.answer(bs.tr(lang)["not_found"], show_alert=True)
            return
        doctors, _ = await _catalog()
        slots = await _day_slots(doctors, date_iso, item["doctor_id"])
        if not slots:
            await callback.answer(bs.tr(lang)["no_slots"], show_alert=True)
            return
        await _edit_or_send(
            callback,
            bs.tr(lang)["pick_time"].format(day=bs.long_day(lang, date_iso)),
            bs.times_keyboard(lang, list(slots.keys()), f"rs:t:{appointment_id}:{date_iso}", "nav:my"),
        )

    @dp.callback_query(F.data.startswith("rs:t:"))
    async def cb_reschedule_time(callback: types.CallbackQuery):
        lang = await _lang(callback.from_user.id)
        _, _, appointment_id, date_iso, hhmm = callback.data.split(":", 4)
        item = await _owned(callback.from_user.id, appointment_id)
        if item is None or not item.get("doctor_id"):
            await callback.answer(bs.tr(lang)["not_found"], show_alert=True)
            return
        doctors, _ = await _catalog()
        slots = await _day_slots(doctors, date_iso, item["doctor_id"])
        candidates = slots.get(hhmm)
        if not candidates:
            await callback.answer(bs.tr(lang)["taken"], show_alert=True)
            return
        _, when = candidates[0]
        result = await db.reschedule_slot(appointment_id=appointment_id, telegram_id=callback.from_user.id, new_visit_utc=when)
        if result != "ok":
            await callback.answer(bs.tr(lang)["taken"], show_alert=True)
            return
        await _schedule_reminders(appointment_id, when)
        await _edit_or_send(callback, bs.tr(lang)["changed"].format(when=_visit_text(lang, when)), _back_home(lang))
