"""
Экраны бота, которые строятся из данных клиники (каталог, врачи, записи, слоты).
Чистые функции: текст в HTML и клавиатуры. Без базы и сети, поэтому их легко проверить тестами.
"""

from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

CLINIC_PHONES = ("+998 71 200 44 88", "+998 90 999 44 88")
CLINIC_ADDRESS = {
    "ru": "г. Ташкент, Мирабадский район, ул. Афросиёб, 12Б (метро «Ойбек»)",
    "uz": "Toshkent, Mirobod tumani, Afrosiyob ko'chasi, 12B («Oybek» metro)",
    "en": "12B Afrosiyob St, Mirabad district, Tashkent (Oybek metro)",
}

WEEKDAYS = {
    "ru": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
    "uz": ["Du", "Se", "Cho", "Pa", "Ju", "Sha", "Ya"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
}
MONTHS = {
    "ru": ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
    "uz": ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}

T = {
    "ru": {
        "services_title": "🦷 <b>Услуги и цены</b>",
        "services_note": "Цены ориентировочные, точную стоимость уточняет врач на осмотре.",
        "doctors_title": "👨‍⚕️ <b>Врачи клиники</b>",
        "exp": "стаж {n} лет",
        "book": "📅 Записаться на приём",
        "my_title": "📋 <b>Мои записи</b>",
        "my_empty": "У вас нет предстоящих записей.",
        "reschedule": "🔄 Перенести",
        "cancel": "❌ Отменить",
        "pick_service": "Выберите услугу:",
        "pick_doctor": "Выберите врача:",
        "any_doctor": "Любой свободный врач",
        "pick_day": "Выберите день:",
        "pick_time": "Свободное время на {day}:",
        "no_slots": "На этот день свободного времени нет. Выберите другой день.",
        "confirm_title": "Проверьте запись:",
        "confirm_btn": "✅ Подтвердить",
        "consent": "Нажимая «Подтвердить», вы соглашаетесь на обработку персональных данных для записи.",
        "ask_phone": "Отправьте номер телефона кнопкой ниже или напишите в формате +998…",
        "send_phone": "📱 Отправить мой номер",
        "booked": "✅ <b>Вы записаны!</b>\nМы свяжемся с вами для подтверждения за 24 часа до визита.",
        "taken": "Это время уже занято. Выберите другое.",
        "changed": "✅ Запись перенесена на {when}. Ожидайте подтверждения.",
        "cancelled": "Запись отменена. Если захотите вернуться, мы всегда рады вас видеть.",
        "too_late": "Изменить запись можно не позже чем за 3 часа до визита. Позвоните в клинику: {phone}",
        "not_changeable": "Эту запись уже нельзя изменить. Позвоните в клинику: {phone}",
        "not_found": "Запись не найдена.",
        "back": "◀️ В главное меню",
        "cancel_flow": "✖️ Отмена",
        "no_catalog": "Каталог обновляется. Пока можно посмотреть цены в прайсе ниже.",
        "error": "Что-то пошло не так. Попробуйте ещё раз или позвоните в клинику: {phone}",
    },
    "uz": {
        "services_title": "🦷 <b>Xizmatlar va narxlar</b>",
        "services_note": "Narxlar taxminiy, aniq narxni shifokor ko'rikda aytadi.",
        "doctors_title": "👨‍⚕️ <b>Klinika shifokorlari</b>",
        "exp": "{n} yil tajriba",
        "book": "📅 Qabulga yozilish",
        "my_title": "📋 <b>Mening yozuvlarim</b>",
        "my_empty": "Sizda kelgusi yozuvlar yo'q.",
        "reschedule": "🔄 Ko'chirish",
        "cancel": "❌ Bekor qilish",
        "pick_service": "Xizmatni tanlang:",
        "pick_doctor": "Shifokorni tanlang:",
        "any_doctor": "Istalgan bo'sh shifokor",
        "pick_day": "Kunni tanlang:",
        "pick_time": "{day} kuni bo'sh vaqt:",
        "no_slots": "Bu kunda bo'sh vaqt yo'q. Boshqa kunni tanlang.",
        "confirm_title": "Yozuvni tekshiring:",
        "confirm_btn": "✅ Tasdiqlash",
        "consent": "«Tasdiqlash» tugmasini bosib, yozilish uchun shaxsiy ma'lumotlarni qayta ishlashga rozilik bildirasiz.",
        "ask_phone": "Telefon raqamingizni pastdagi tugma orqali yuboring yoki +998… shaklida yozing.",
        "send_phone": "📱 Raqamimni yuborish",
        "booked": "✅ <b>Siz yozildingiz!</b>\nTashrifdan 24 soat oldin tasdiqlash uchun bog'lanamiz.",
        "taken": "Bu vaqt band. Boshqasini tanlang.",
        "changed": "✅ Yozuv {when} ga ko'chirildi. Tasdiqlashni kuting.",
        "cancelled": "Yozuv bekor qilindi. Yana kutib qolamiz.",
        "too_late": "Yozuvni tashrifdan kamida 3 soat oldin o'zgartirish mumkin. Qo'ng'iroq qiling: {phone}",
        "not_changeable": "Bu yozuvni endi o'zgartirib bo'lmaydi. Qo'ng'iroq qiling: {phone}",
        "not_found": "Yozuv topilmadi.",
        "back": "◀️ Bosh menyuga",
        "cancel_flow": "✖️ Bekor qilish",
        "no_catalog": "Katalog yangilanmoqda. Hozircha narxlarni quyida ko'rishingiz mumkin.",
        "error": "Xatolik yuz berdi. Qayta urinib ko'ring yoki qo'ng'iroq qiling: {phone}",
    },
    "en": {
        "services_title": "🦷 <b>Services & Prices</b>",
        "services_note": "Prices are approximate; the doctor confirms the exact cost at the visit.",
        "doctors_title": "👨‍⚕️ <b>Our doctors</b>",
        "exp": "{n} years of experience",
        "book": "📅 Book an appointment",
        "my_title": "📋 <b>My appointments</b>",
        "my_empty": "You have no upcoming appointments.",
        "reschedule": "🔄 Reschedule",
        "cancel": "❌ Cancel",
        "pick_service": "Choose a service:",
        "pick_doctor": "Choose a doctor:",
        "any_doctor": "Any available doctor",
        "pick_day": "Choose a day:",
        "pick_time": "Free times on {day}:",
        "no_slots": "No free times on this day. Please choose another day.",
        "confirm_title": "Please check your booking:",
        "confirm_btn": "✅ Confirm",
        "consent": "By pressing “Confirm” you agree to the processing of your personal data for this booking.",
        "ask_phone": "Send your phone number with the button below, or type it as +998…",
        "send_phone": "📱 Send my number",
        "booked": "✅ <b>You are booked!</b>\nWe will confirm with you 24 hours before the visit.",
        "taken": "This time is already taken. Please choose another.",
        "changed": "✅ Appointment moved to {when}. Waiting for confirmation.",
        "cancelled": "Your appointment is cancelled. We are always glad to see you again.",
        "too_late": "Changes are possible no later than 3 hours before the visit. Please call: {phone}",
        "not_changeable": "This appointment can no longer be changed. Please call: {phone}",
        "not_found": "Appointment not found.",
        "back": "◀️ Back to menu",
        "cancel_flow": "✖️ Cancel",
        "no_catalog": "The catalog is being updated. Meanwhile, see the price list below.",
        "error": "Something went wrong. Please try again or call: {phone}",
    },
}


def tr(lang: str) -> Dict[str, str]:
    return T.get(lang, T["ru"])


def format_sum(value: Optional[int]) -> str:
    if value is None:
        return ""
    return f"{value:,}".replace(",", " ") + " сум"


def day_label(lang: str, day: date) -> str:
    return f"{WEEKDAYS.get(lang, WEEKDAYS['ru'])[day.weekday()]} {day.day} {MONTHS.get(lang, MONTHS['ru'])[day.month - 1]}"


def long_day(lang: str, iso: str) -> str:
    return day_label(lang, date.fromisoformat(iso))


def services_text(lang: str, services: List[Dict[str, Any]]) -> str:
    """Каталог услуг из базы, сгруппированный по категориям."""
    t = tr(lang)
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for s in services:
        groups.setdefault(s["category"], []).append(s)
    lines = [t["services_title"], f"<i>{t['services_note']}</i>", ""]
    for category, items in groups.items():
        lines.append(f"<b>{category}</b>")
        for s in items:
            lines.append(f"• {s['title']} — от {format_sum(s['price_uzs'])}")
        lines.append("")
    return "\n".join(lines).rstrip()


def doctors_text(lang: str, doctors: List[Dict[str, Any]]) -> str:
    t = tr(lang)
    lines = [t["doctors_title"], ""]
    for d in doctors:
        block = [f"<b>{d['name']}</b>", d["specialty"]]
        if d.get("experience_years"):
            block.append(t["exp"].format(n=d["experience_years"]))
        lines.append("\n".join(block))
        lines.append("")
    return "\n".join(lines).rstrip()


def day_options(today_tashkent: date, days: int = 10) -> List[str]:
    return [(today_tashkent + timedelta(days=i)).isoformat() for i in range(days)]


def _grid(buttons: List[InlineKeyboardButton], per_row: int) -> List[List[InlineKeyboardButton]]:
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


def services_keyboard(lang: str, services: Iterable[Dict[str, Any]], prefix: str) -> InlineKeyboardMarkup:
    """prefix: 'bk:svc' для выбора услуги при записи, 'dbsvc' для карточки услуги в каталоге."""
    t = tr(lang)
    rows = [[InlineKeyboardButton(text=s["title"][:60], callback_data=f"{prefix}:{s['id']}")] for s in services]
    rows.append([InlineKeyboardButton(text=t["back"], callback_data="nav:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def service_card_keyboard(lang: str, service_id: str) -> InlineKeyboardMarkup:
    t = tr(lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t["book"], callback_data="bk:start")],
            [InlineKeyboardButton(text=t["back"], callback_data="catalog_db")],
        ]
    )


def doctors_choice_keyboard(lang: str, doctors: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    t = tr(lang)
    rows = [[InlineKeyboardButton(text=t["any_doctor"], callback_data="bk:doc:any")]]
    rows += [[InlineKeyboardButton(text=d["name"][:60], callback_data=f"bk:doc:{d['id']}")] for d in doctors]
    rows.append([InlineKeyboardButton(text=t["cancel_flow"], callback_data="nav:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def days_keyboard(lang: str, days: List[str], callback_prefix: str) -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(text=day_label(lang, date.fromisoformat(d)), callback_data=f"{callback_prefix}:{d}") for d in days]
    rows = _grid(buttons, 2)
    rows.append([InlineKeyboardButton(text=tr(lang)["cancel_flow"], callback_data="nav:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def times_keyboard(lang: str, times: List[str], callback_prefix: str, back_callback: str) -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(text=hhmm, callback_data=f"{callback_prefix}:{hhmm}") for hhmm in times]
    rows = _grid(buttons, 4)
    rows.append([InlineKeyboardButton(text=tr(lang)["back"], callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_keyboard(lang: str) -> InlineKeyboardMarkup:
    t = tr(lang)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t["confirm_btn"], callback_data="bk:ok")],
            [InlineKeyboardButton(text=t["cancel_flow"], callback_data="nav:home")],
        ]
    )


def my_appointments_text(lang: str, items: List[Dict[str, Any]], tashkent_text) -> str:
    t = tr(lang)
    if not items:
        return f"{t['my_title']}\n\n{t['my_empty']}"
    lines = [t["my_title"], ""]
    for it in items:
        lines.append(f"<b>{tashkent_text(it['visit_utc'], lang)}</b>")
        lines.append(f"{it['service']} · {it['doctor']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def my_appointments_keyboard(lang: str, items: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    t = tr(lang)
    rows = []
    for it in items:
        rows.append([
            InlineKeyboardButton(text=t["reschedule"], callback_data=f"my:r:{it['id']}"),
            InlineKeyboardButton(text=t["cancel"], callback_data=f"my:c:{it['id']}"),
        ])
    rows.append([InlineKeyboardButton(text=t["back"], callback_data="nav:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
