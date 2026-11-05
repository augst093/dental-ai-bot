"""
Модуль отправки карточек лидов и алертов в рабочий чат администраторов клиники.
Форматирование заявок с учетом часового пояса Ташкента (Asia/Tashkent).
Премиальная верстка Telegram HTML.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
import pytz
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import config
from services.outbox_worker import queued_bot

logger = logging.getLogger(__name__)


def get_tashkent_time_str() -> str:
    """Возвращает текущее время в Ташкенте (UTC+5) в формате ЧЧ:ММ (ДД.ММ.ГГГГ)."""
    try:
        tz = pytz.timezone(config.TIMEZONE)
        now = datetime.now(tz)
        return now.strftime("%H:%M (%d.%m.%Y)")
    except Exception:
        return datetime.utcnow().strftime("%H:%M UTC")


class NotifierService:
    def __init__(self, bot: Optional[Bot] = None):
        self.bot = bot

    def set_bot(self, bot: Bot) -> None:
        self.bot = bot

    async def notify_new_lead(
        self,
        lead_id: int,
        telegram_id: int,
        client_name: str,
        phone: str,
        service: str,
        preferred_time: str,
        summary: str,
        language: str,
        username: Optional[str] = None,
    ) -> bool:
        """
        Формирует и отправляет премиальную карточку лида в группу администраторов.
        """
        if not self.bot or not config.ADMIN_CHAT_ID:
            logger.warning("Bot instance or ADMIN_CHAT_ID not configured for lead notification.")
            return False

        time_str = get_tashkent_time_str()
        lang_names = {
            "uz": "🇺🇿 Узбекский (O'zbek)",
            "en": "🇬🇧 Английский (English)",
            "ru": "🇷🇺 Русский",
        }
        lang_str = lang_names.get(language, "🇷🇺 Русский")
        username_str = f"@{username}" if username else "<i>скрыт</i>"

        card_text = (
            "🔥 <b>НОВАЯ ЗАЯВКА С ТЕЛЕГРАМ-БОТА!</b>\n\n"
            f"🆔 <b>Заявка №:</b> #{lead_id}\n"
            f"👤 <b>Пациент:</b> <b>{client_name}</b>\n"
            f"📞 <b>Телефон:</b> <code>{phone}</code>\n"
            f"🦷 <b>Услуга:</b> {service}\n"
            f"📅 <b>Желаемое время:</b> {preferred_time}\n"
            f"🌐 <b>Язык клиента:</b> {lang_str}\n"
            f"⏰ <b>Время:</b> {time_str} (Ташкент)\n"
            f"📱 <b>Профиль:</b> {username_str} [ID: <code>{telegram_id}</code>]\n\n"
            f"<blockquote>💬 <b>Запрос клиента:</b>\n{summary or 'Запись на консультацию'}</blockquote>"
        )

        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💬 Написать пациенту в Telegram",
                        url=f"tg://user?id={telegram_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="✅ Принято в работу",
                        callback_data=f"lead_processed:{lead_id}"
                    )
                ]
            ]
        )

        try:
            await queued_bot.send_message(
                chat_id=config.ADMIN_CHAT_ID,
                text=card_text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            logger.info(f"Lead #{lead_id} successfully sent to admin chat {config.ADMIN_CHAT_ID}")
            return True
        except Exception as e:
            logger.error(
                f"Не удалось отправить карточку лида в чат {config.ADMIN_CHAT_ID}: {e}. "
                "ВАЖНО: Если это группа, убедитесь, что бот ДОБАВЛЕН в эту группу как участник/админ! "
                "Либо временно укажите ваш личный Telegram ID в ADMIN_CHAT_ID."
            )
            return False

    async def notify_operator_request(
        self,
        telegram_id: int,
        user_name: str,
        username: Optional[str] = None,
        reason: Optional[str] = None,
        last_message: Optional[str] = None,
    ) -> bool:
        """
        Отправляет мгновенный алерт, когда пациент просит живого оператора.
        """
        if not self.bot or not config.ADMIN_CHAT_ID:
            logger.warning("Bot instance or ADMIN_CHAT_ID not configured for operator alert.")
            return False

        time_str = get_tashkent_time_str()
        username_str = f"@{username}" if username else "<i>скрыт</i>"

        alert_text = (
            "🚨 <b>ВНИМАНИЕ: ПАЦИЕНТ ПРОСИТ СВЯЗАТЬСЯ С АДМИНИСТРАТОРОМ!</b>\n\n"
            f"👤 <b>Пациент:</b> <b>{user_name}</b> ({username_str})\n"
            f"🆔 <b>Telegram ID:</b> <code>{telegram_id}</code>\n"
            f"❓ <b>Причина:</b> {reason or 'Запрос оператора'}\n"
            f"⏰ <b>Время:</b> {time_str} (Ташкент)\n\n"
            f"<blockquote>💬 <b>Последнее сообщение:</b>\n<i>«{last_message or 'Не указано'}»</i></blockquote>\n\n"
            "⚠️ <i>AI временно приостановлен для этого диалога до ответа оператора.</i>"
        )

        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💬 Открыть чат с пациентом",
                        url=f"tg://user?id={telegram_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔄 Вернуть AI-ассистента пациенту",
                        callback_data=f"resume_ai:{telegram_id}"
                    )
                ]
            ]
        )

        try:
            await queued_bot.send_message(
                chat_id=config.ADMIN_CHAT_ID,
                text=alert_text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            logger.info(f"Operator request for user {telegram_id} sent to admin chat")
            return True
        except Exception as e:
            logger.error(f"Failed to send operator alert to admin chat: {e}", exc_info=True)
            return False


notifier = NotifierService()
