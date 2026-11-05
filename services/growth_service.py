"""
Growth and retention jobs for DentaLux.

- Morning digest for the clinic director (08:00 Tashkent time)
- Review request two hours after a visit
- Recall message 180 days after the last visit
- Daily SQLite backup sent to the admin chat (03:00 Tashkent time)
- Waitlist notifications when a slot is freed
- .ics calendar file for booked visits
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import (

    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from config import config
from keyboards import MINIAPP_URL
from database import db

logger = logging.getLogger("growth_service")

# Uzbekistan has been UTC+5 without daylight saving since 2004
TASHKENT = timezone(timedelta(hours=5))

CLINIC_ADDRESS = os.getenv("CLINIC_ADDRESS", "ул. Шота Руставели, 54, Ташкент")
CLINIC_PHONE = os.getenv("CLINIC_PHONE", "")
REVIEW_URL = os.getenv("REVIEW_URL", "").strip()
# Average administrator hourly cost in UZS; 0 hides the money line
ADMIN_HOURLY_RATE_UZS = int(os.getenv("ADMIN_HOURLY_RATE_UZS", "0") or 0)
MINUTES_SAVED_PER_BOOKING = 4


def now_tashkent() -> datetime:
    return datetime.now(TASHKENT)


def _format_uzs(amount: float) -> str:
    return f"{round(amount):,}".replace(",", " ") + " сум"


# ----------------------------------------------------------------------
# Calendar file
# ----------------------------------------------------------------------

def _ics_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def build_ics(service: str, doctor: str, date_time: str) -> Optional[bytes]:
    """Возвращает .ics файл визита или None, если дата не распознана."""
    try:
        local_start = datetime.strptime(date_time, "%Y-%m-%d %H:%M")
    except ValueError:
        return None

    start_utc = local_start - timedelta(hours=5)
    end_utc = start_utc + timedelta(minutes=45)

    def stamp(value: datetime) -> str:
        return value.strftime("%Y%m%dT%H%M%SZ")

    doctor_line = doctor if doctor and doctor != "Любой специалист" else "врач клиники"
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//DentaLux Tashkent//Booking//RU",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{uuid.uuid4()}@dentalux",
        f"DTSTAMP:{stamp(datetime.now(timezone.utc).replace(tzinfo=None))}",
        f"DTSTART:{stamp(start_utc)}",
        f"DTEND:{stamp(end_utc)}",
        f"SUMMARY:{_ics_escape('DentaLux: ' + (service or 'визит'))}",
        f"LOCATION:{_ics_escape(CLINIC_ADDRESS)}",
        f"DESCRIPTION:{_ics_escape('Врач: ' + doctor_line + '. Возьмите паспорт и приходите за 10 минут.')}",
        "BEGIN:VALARM",
        "TRIGGER:-PT2H",
        "ACTION:DISPLAY",
        "DESCRIPTION:Визит в DentaLux через 2 часа",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


def visit_instructions(lang: str) -> str:
    """Адрес и памятка для пациента, добавляется к подтверждению записи."""
    texts = {
        "ru": (
            f"📍 <b>Адрес:</b> {CLINIC_ADDRESS}\n"
            "🕘 Приходите за 10 минут и возьмите паспорт.\n"
            "📅 Визит можно добавить в календарь файлом ниже."
        ),
        "uz": (
            f"📍 <b>Manzil:</b> {CLINIC_ADDRESS}\n"
            "🕘 10 daqiqa oldin keling va pasportingizni oling.\n"
            "📅 Qabulni kalendarga qo‘shish uchun quyidagi faylni oching."
        ),
        "en": (
            f"📍 <b>Address:</b> {CLINIC_ADDRESS}\n"
            "🕘 Please arrive 10 minutes early and bring your passport.\n"
            "📅 Add the visit to your calendar with the file below."
        ),
    }
    return texts.get(lang, texts["ru"])


# ----------------------------------------------------------------------
# Director digest
# ----------------------------------------------------------------------

async def build_digest_text(days: int, title: str) -> str:
    stats = await db.get_digest_stats(days)
    total = stats["total"]
    if total == 0:
        return (
            f"{title}\n\n"
            "За период записей пока нет. Цифры появятся после первых записей через бота и Mini App."
        )

    confirm_rate = round(100 * stats["confirmed"] / total)
    no_show_rate = round(100 * stats["no_show"] / total)
    hours_saved = round(total * MINUTES_SAVED_PER_BOOKING / 60, 1)

    lines = [
        f"{title}",
        f"<i>Период: последние {days} дн.</i>",
        "",
        f"📥 <b>Записей:</b> {total}",
        f"✅ <b>Подтверждено или пришли:</b> {stats['confirmed']} ({confirm_rate}%)",
        f"🚫 <b>Неявки:</b> {stats['no_show']} ({no_show_rate}%)",
        f"♻️ <b>Отмены, слоты освобождены:</b> {stats['cancelled']}",
        f"⏱ <b>Экономия времени администратора:</b> ~{hours_saved} ч.",
    ]
    if ADMIN_HOURLY_RATE_UZS > 0:
        money = hours_saved * ADMIN_HOURLY_RATE_UZS
        lines.append(f"💰 <b>Экономия в деньгах:</b> ~{_format_uzs(money)}")

    sources = await db.get_sources_breakdown()
    if sources:
        lines.append("")
        lines.append("📊 <b>Откуда пришли пациенты:</b>")
        for row in sources[:6]:
            lines.append(f"• {row['source']}: {row['total']}")

    return "\n".join(lines)


# ----------------------------------------------------------------------
# Notifications to patients
# ----------------------------------------------------------------------

REVIEW_TEXT = {
    "ru": "🙏 Спасибо, что выбрали DentaLux! Будем благодарны за короткий отзыв — это помогает другим пациентам.",
    "uz": "🙏 DentaLux’ni tanlaganingiz uchun rahmat! Qisqa sharh qoldirsangiz, boshqa bemorlarga yordam beradi.",
    "en": "🙏 Thank you for choosing DentaLux! A short review helps other patients find us.",
}

RECALL_TEXT = {
    "ru": (
        "🦷 Прошло полгода с вашего последнего визита. Рекомендуем профилактический осмотр и чистку.\n"
        "Запишитесь через Mini App или нажмите кнопку ниже."
    ),
    "uz": (
        "🦷 Oxirgi tashrifingizdan yarim yil o‘tdi. Profilaktik ko‘rik va tozalashni tavsiya etamiz.\n"
        "Mini App orqali yoziling yoki quyidagi tugmani bosing."
    ),
    "en": (
        "🦷 It has been six months since your last visit. We recommend a check-up and cleaning.\n"
        "Book via the Mini App or tap the button below."
    ),
}


async def _user_lang(telegram_id: int) -> str:
    lang = await db.get_user_language(telegram_id)
    return lang or "ru"


async def send_review_requests(bot: Bot) -> None:
    for row in await db.get_review_candidates():
        if not await db.mark_outreach(f"review:{row['id']}", "review"):
            continue
        lang = await _user_lang(row["telegram_id"])
        markup = None
        if REVIEW_URL:
            markup = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⭐ Оставить отзыв", url=REVIEW_URL)]]
            )
        try:
            await bot.send_message(
                row["telegram_id"], REVIEW_TEXT.get(lang, REVIEW_TEXT["ru"]), reply_markup=markup
            )
        except TelegramForbiddenError:
            logger.info("Пациент заблокировал бота, отзыв не отправлен")
        except Exception:
            logger.exception("Не удалось отправить просьбу об отзыве")


async def send_recalls(bot: Bot) -> None:
    for row in await db.get_recall_candidates():
        key = f"recall:{row['telegram_id']}:{row['last_visit']}"
        if not await db.mark_outreach(key, "recall"):
            continue
        lang = await _user_lang(row["telegram_id"])
        markup = None
        if MINIAPP_URL:
            markup = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="📅 Записаться", url=MINIAPP_URL)]]
            )
        try:
            await bot.send_message(
                row["telegram_id"], RECALL_TEXT.get(lang, RECALL_TEXT["ru"]), reply_markup=markup
            )
        except TelegramForbiddenError:
            logger.info("Пациент заблокировал бота, напоминание о профилактике не отправлено")
        except Exception:
            logger.exception("Не удалось отправить напоминание о профилактике")


async def notify_waitlist(bot: Bot, date_time: str, doctor: str) -> None:
    """Сообщает людям из листа ожидания, что на их дату освободилось окно."""
    if not date_time:
        return
    day = date_time.split(" ")[0]
    for entry in await db.pop_waitlist_for(day, doctor or "any"):
        lang = await _user_lang(entry["telegram_id"])
        text = {
            "ru": f"🔔 Освободилось окно на {day}. Успейте записаться через Mini App.",
            "uz": f"🔔 {day} kuni bo‘sh vaqt paydo bo‘ldi. Mini App orqali tezroq yoziling.",
            "en": f"🔔 A slot opened on {day}. Book quickly via the Mini App.",
        }.get(lang, "")
        try:
            await bot.send_message(entry["telegram_id"], text)
        except Exception:
            logger.exception("Не удалось уведомить лист ожидания")


# ----------------------------------------------------------------------
# Backup
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# Worker
# ----------------------------------------------------------------------

class GrowthWorker:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None

    def start(self, bot: Bot) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(bot))
            logger.info("Growth worker запущен (дайджест, отзывы, возврат, резервные копии)")

    async def _loop(self, bot: Bot) -> None:
        while True:
            try:
                await self._tick(bot)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Ошибка в growth worker")
            await asyncio.sleep(60)

    async def _tick(self, bot: Bot) -> None:
        now = now_tashkent()

        if now.hour == 8 and now.minute < 10:
            if await db.mark_outreach(f"digest:{now:%Y-%m-%d}", "digest"):
                text = await build_digest_text(1, "☀️ УТРЕННЯЯ СВОДКА")
                today = await db.count_appointments_on(f"{now:%Y-%m-%d}")
                text = f"{text}\n\n📅 <b>Сегодня записей:</b> {today}"
                if config.ADMIN_CHAT_ID:
                    await bot.send_message(config.ADMIN_CHAT_ID, text, parse_mode=ParseMode.HTML)

        await send_review_requests(bot)
        await send_recalls(bot)


growth_worker = GrowthWorker()
