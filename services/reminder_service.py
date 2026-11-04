"""
Persistent, restart-safe reminder engine for DentaLux dental clinic.
Polls SQLite/Postgres reminders table every 60 seconds.
Generates 24h and 2h reminders with interactive confirmation buttons (Приду / Перенести / Отменить).
Handles blocked bots, edits original messages without spam, and alerts administrators.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from config import config
from database import db

logger = logging.getLogger("reminder_engine")


def get_reminder_keyboard(appointment_id: str, lang: str = "ru") -> InlineKeyboardMarkup:
    """Инлайн-кнопки для подтверждения визита: Приду / Перенести / Отменить."""
    labels = {
        "ru": {
            "confirm": "🟢 Приду на приём",
            "reschedule": "🔄 Перенести",
            "cancel": "❌ Отменить запись",
        },
        "uz": {
            "confirm": "🟢 Qabulga boraman",
            "reschedule": "🔄 Boshqa vaqtga ko‘chirish",
            "cancel": "❌ Bekor qilish",
        },
        "en": {
            "confirm": "🟢 I will attend",
            "reschedule": "🔄 Reschedule",
            "cancel": "❌ Cancel visit",
        },
    }
    t = labels.get(lang, labels["ru"])

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t["confirm"],
                    callback_data=f"confirm_visit:{appointment_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=t["reschedule"],
                    callback_data=f"reschedule_visit:{appointment_id}",
                ),
                InlineKeyboardButton(
                    text=t["cancel"],
                    callback_data=f"cancel_visit:{appointment_id}",
                ),
            ],
        ]
    )
    return keyboard


class ReminderEngine:
    """Движок регулярных напоминаний о визитах."""

    def __init__(self):
        self._worker_task: Optional[asyncio.Task] = None
        self._alerted_unconfirmed: set = set()

    def start_worker(self, bot: Bot):
        """Запускает фоновый воркер опроса напоминаний каждую минуту."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._poll_loop(bot))
            logger.info("Persistent Reminder Worker успешно запущен (интервал: 60 сек)")

    async def _poll_loop(self, bot: Bot):
        while True:
            try:
                await self.process_due_reminders(bot)
                await self.check_unconfirmed_urgent(bot)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка в цикле reminder worker: {e}", exc_info=True)
            await asyncio.sleep(60)

    async def process_due_reminders(self, bot: Bot):
        """Обрабатывает напоминания, срок которых наступил."""
        due_list = await db.get_due_reminders()
        if not due_list:
            return

        logger.info(f"Найдено напоминаний к отправке: {len(due_list)}")

        for item in due_list:
            reminder_id = item["reminder_id"]
            appointment_id = item["appointment_id"]
            telegram_id = item.get("telegram_id")
            client_name = item.get("client_name") or "Пациент"
            phone = item.get("phone") or ""
            doctor = item.get("doctor") or "Врач-стоматолог"
            service = item.get("service") or "Приём"
            date_time = item.get("date_time") or ""
            reminder_type = item.get("type")

            if not telegram_id or telegram_id == 0:
                # Нет telegram_id (записан только по телефону), отмечаем как пропущенный
                await db.mark_reminder_failed(reminder_id, "No telegram_id (phone booking)")
                continue

            # Определяем язык пользователя
            lang = await db.get_user_language(telegram_id) or "ru"

            # Формируем текст напоминания
            time_prefix = "через 24 часа" if reminder_type == "reminder_24h" else "через 2 часа"
            if lang == "uz":
                time_prefix = "24 soatdan keyin" if reminder_type == "reminder_24h" else "2 soatdan keyin"
            elif lang == "en":
                time_prefix = "in 24 hours" if reminder_type == "reminder_24h" else "in 2 hours"

            messages = {
                "ru": (
                    f"⏰ <b>Напоминание о приёме в клинике DentaLux ({time_prefix})!</b>\n\n"
                    f"Здравствуйте, {client_name}! Напоминаем о вашей записи к врачу:\n"
                    f"🦷 <b>Услуга:</b> {service}\n"
                    f"👨‍⚕️ <b>Врач:</b> {doctor}\n"
                    f"📅 <b>Дата и время:</b> {date_time}\n"
                    f"📍 <b>Адрес:</b> г. Ташкент, ул. Шота Руставели, 54 (метро Ойбек)\n\n"
                    "Пожалуйста, подтвердите визит нажатием кнопки ниже, чтобы закрепить за собой кресло и врача:"
                ),
                "uz": (
                    f"⏰ <b>DentaLux klinikasida qabul haqida eslatma ({time_prefix})!</b>\n\n"
                    f"Assalomu alaykum, {client_name}! Qabul vaqtingizni eslatib o‘tamiz:\n"
                    f"🦷 <b>Xizmat:</b> {service}\n"
                    f"👨‍⚕️ <b>Shifokor:</b> {doctor}\n"
                    f"📅 <b>Vaqt:</b> {date_time}\n"
                    f"📍 <b>Manzil:</b> Toshkent sh., Shota Rustaveli ko‘chasi, 54 (Oybek metrosi)\n\n"
                    "Shifokor sizni kutishi uchun, iltimos, quyidagi tugma orqali tashrifingizni tasdiqlang:"
                ),
                "en": (
                    f"⏰ <b>Appointment reminder at DentaLux clinic ({time_prefix})!</b>\n\n"
                    f"Hello, {client_name}! This is a reminder for your dental appointment:\n"
                    f"🦷 <b>Service:</b> {service}\n"
                    f"👨‍⚕️ <b>Doctor:</b> {doctor}\n"
                    f"📅 <b>Time:</b> {date_time}\n"
                    f"📍 <b>Address:</b> 54 Shota Rustaveli st., Tashkent (Oybek metro)\n\n"
                    "Please confirm your attendance using the button below:"
                ),
            }

            text = messages.get(lang, messages["ru"])
            reply_markup = get_reminder_keyboard(appointment_id, lang)

            try:
                await bot.send_message(
                    chat_id=telegram_id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
                await db.mark_reminder_sent(reminder_id)
                logger.info(f"Напоминание {reminder_id} успешно отправлено {client_name} ({telegram_id})")

            except (TelegramForbiddenError, TelegramBadRequest) as ex:
                err_str = f"Бот заблокирован пользователем: {ex}"
                logger.warning(f"Ошибка отправки пациенту {telegram_id}: {err_str}")
                await db.mark_reminder_failed(reminder_id, err_str)

                # Уведомляем администратора, что пациент недоступен в боте
                if config.ADMIN_CHAT_ID:
                    alert_admin = (
                        f"⚠️ <b>ВНИМАНИЕ АДМИНИСТРАТОРУ! Пациент заблокировал бота:</b>\n\n"
                        f"👤 <b>Пациент:</b> {client_name}\n"
                        f"📞 <b>Телефон:</b> <code>{phone}</code>\n"
                        f"🦷 <b>Услуга:</b> {service}\n"
                        f"📅 <b>Время приёма:</b> {date_time}\n\n"
                        "Пациент не получил напоминание в Telegram. Рекомендуется позвонить по телефону."
                    )
                    try:
                        await bot.send_message(
                            chat_id=config.ADMIN_CHAT_ID,
                            text=alert_admin,
                            parse_mode="HTML",
                        )
                    except Exception as adm_e:
                        logger.error(f"Не удалось отправить алерт администратору: {adm_e}")

    async def check_unconfirmed_urgent(self, bot: Bot):
        """
        Проверяет записи за 2 часа до приёма: если статус всё ещё 'pending',
        отправляет администратору алерт для предотвращения пустого слота (no-show).
        """
        if not config.ADMIN_CHAT_ID:
            return

        urgent_list = await db.get_urgent_unconfirmed_appointments()
        for app in urgent_list:
            app_id = app["id"]
            if app_id in self._alerted_unconfirmed:
                continue

            self._alerted_unconfirmed.add(app_id)
            name = app.get("client_name") or "Пациент"
            phone = app.get("phone") or "Не указан"
            doctor = app.get("doctor") or "Врач"
            date_time = app.get("date_time") or ""

            alert_text = (
                f"🚨 <b>СЛОТ В ЗОНЕ РИСКА! Запись через 2 часа НЕ ПОДТВЕРЖДЕНА:</b>\n\n"
                f"👤 <b>Пациент:</b> {name}\n"
                f"📞 <b>Телефон:</b> <code>{phone}</code>\n"
                f"👨‍⚕️ <b>Врач:</b> {doctor}\n"
                f"📅 <b>Время:</b> {date_time}\n"
                f"⚠️ Пациент не нажал «Приду». Чтобы избежать пустого слота, свяжитесь с ним прямо сейчас!"
            )

            try:
                await bot.send_message(
                    chat_id=config.ADMIN_CHAT_ID,
                    text=alert_text,
                    parse_mode="HTML",
                )
                logger.info(f"Алерт о неподтвержденной записи {app_id} отправлен администратору")
            except Exception as e:
                logger.error(f"Не удалось отправить urgent alert: {e}")


reminder_engine = ReminderEngine()
