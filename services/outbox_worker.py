"""
Outbox: every outgoing Telegram message is written to the shared "Outbox" table first, then delivered here.

Sending side (this worker):
- Claims rows with FOR UPDATE SKIP LOCKED, so two bot instances never send the same message twice.
- Respects Telegram limits: about 20 messages per second overall, 1 per second per private chat,
  3 seconds between messages to the same group.
- Honours retry_after on 429, backs off on network errors, stops for good on 403 (blocked) and 400.
- Before sending a reminder it checks the appointment is still active; a cancelled visit is not reminded.
- Updates the thing a message is about: reminder status, inbox message status, patient unreachable flag.

Queueing side (enqueue_*): used by the reminder engine and the staff alerts. Reminders are queued at most once.
"""

import asyncio
import json
import logging
import time
from typing import Dict, Optional

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramMigrateToChat,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from config import config
from database import db
from services.outbox_policy import after_failure, classify_failure, is_group_chat

logger = logging.getLogger(__name__)

BATCH_SIZE = 20
MIN_GAP_PRIVATE = 1.0
MIN_GAP_GROUP = 3.0
MIN_GAP_GLOBAL = 0.05  # about 20 messages per second overall

HTML_KINDS = ("staff_alert", "reminder", "patient_html")
ACTIVE_APPOINTMENT = ("pending", "confirmed", "reschedule_requested")


# ---------------------------------------------------------------------------
# Queueing
# ---------------------------------------------------------------------------

def keyboard_to_json(markup) -> Optional[str]:
    if markup is None:
        return None
    if isinstance(markup, InlineKeyboardMarkup):
        payload = {"type": "inline", "rows": [[{"text": b.text, "callback_data": b.callback_data} for b in row] for row in markup.inline_keyboard]}
    elif isinstance(markup, ReplyKeyboardMarkup):
        payload = {"type": "reply", "rows": [[b.text for b in row] for row in markup.keyboard]}
    else:
        return None
    return json.dumps(payload, ensure_ascii=False)


def keyboard_from_json(data):
    if not data:
        return None
    payload = json.loads(data) if isinstance(data, str) else data
    if isinstance(payload, list):  # rows saved without a type (inline)
        payload = {"type": "inline", "rows": payload}
    if payload.get("type") == "reply":
        return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=t) for t in row] for row in payload["rows"]], resize_keyboard=True)
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=b["text"], callback_data=b["callback_data"]) for b in row] for row in payload["rows"]]
    )


async def enqueue(
    chat_id: int,
    kind: str,
    text: str,
    *,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    ref_type: Optional[str] = None,
    ref_id: Optional[str] = None,
) -> bool:
    """Adds a message to the outbox. For a reference (reminder or inbox message) it is added at most once."""
    async with db._p().acquire() as conn:
        if ref_type and ref_id:
            row = await conn.fetchrow(
                """
                INSERT INTO "Outbox" (id, "chatId", kind, text, "replyMarkup", "refType", "refId", "nextAttemptAt", "createdAt", "updatedAt")
                SELECT gen_random_uuid()::text, $1, $2, $3, $4::jsonb, $5, $6,
                       (now() AT TIME ZONE 'UTC'), (now() AT TIME ZONE 'UTC'), (now() AT TIME ZONE 'UTC')
                WHERE NOT EXISTS (
                    SELECT 1 FROM "Outbox" WHERE "refType" = $5 AND "refId" = $6 AND status IN ('pending', 'sent')
                )
                RETURNING id
                """,
                chat_id, kind, text, keyboard_to_json(reply_markup), ref_type, ref_id,
            )
            return row is not None
        await conn.execute(
            """
            INSERT INTO "Outbox" (id, "chatId", kind, text, "replyMarkup", "nextAttemptAt", "createdAt", "updatedAt")
            VALUES (gen_random_uuid()::text, $1, $2, $3, $4::jsonb,
                    (now() AT TIME ZONE 'UTC'), (now() AT TIME ZONE 'UTC'), (now() AT TIME ZONE 'UTC'))
            """,
            chat_id, kind, text, keyboard_to_json(reply_markup),
        )
        return True


class QueuedSender:
    """Same call as bot.send_message, but the message is queued and delivered by the outbox worker."""

    async def send_message(self, chat_id, text, parse_mode=None, reply_markup=None, **kwargs):
        chat = int(chat_id)
        is_html = str(parse_mode) == "HTML"
        if config.ADMIN_CHAT_ID and chat == int(config.ADMIN_CHAT_ID):
            kind = "staff_alert"
        else:
            kind = "patient_html" if is_html else "patient_text"
        await enqueue(chat, kind, text, reply_markup=reply_markup)
        return None


queued_bot = QueuedSender()


async def enqueue_staff_alert(text: str) -> None:
    """Message for the clinic's admin group (HTML)"""
    if not config.ADMIN_CHAT_ID:
        return
    await enqueue(config.ADMIN_CHAT_ID, "staff_alert", text[:4000])


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

class OutboxWorker:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._last_sent: Dict[int, float] = {}
        self._last_any: float = 0.0

    def start(self, bot: Bot) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(bot))
            logger.info("Outbox worker запущен")

    async def _loop(self, bot: Bot) -> None:
        while True:
            try:
                processed = await self.run_once(bot)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Ошибка в outbox worker")
                processed = 0
            await asyncio.sleep(1 if processed else 3)

    async def run_once(self, bot: Bot) -> int:
        """Delivers one batch. Returns how many messages were handled."""
        async with db._p().acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    """
                    SELECT id, "chatId", kind, text, attempts, "refType", "refId", "replyMarkup"
                    FROM "Outbox"
                    WHERE status = 'pending' AND "nextAttemptAt" <= (now() AT TIME ZONE 'UTC')
                    ORDER BY "nextAttemptAt"
                    LIMIT $1
                    FOR UPDATE SKIP LOCKED
                    """,
                    BATCH_SIZE,
                )
                for row in rows:
                    await self._deliver(bot, conn, row)
        return len(rows)

    async def _respect_limits(self, chat_id: int) -> None:
        now = time.monotonic()
        wait_global = MIN_GAP_GLOBAL - (now - self._last_any)
        if wait_global > 0:
            await asyncio.sleep(wait_global)
        gap = MIN_GAP_GROUP if is_group_chat(chat_id) else MIN_GAP_PRIVATE
        last = self._last_sent.get(chat_id)
        if last is not None:
            wait_chat = gap - (time.monotonic() - last)
            if wait_chat > 0:
                await asyncio.sleep(wait_chat)
        stamp = time.monotonic()
        self._last_any = stamp
        self._last_sent[chat_id] = stamp

    async def _reminder_still_valid(self, conn, reminder_id: str) -> bool:
        row = await conn.fetchrow(
            """
            SELECT r.status::text AS reminder_status, a.status::text AS app_status
            FROM "Reminder" r JOIN "Appointment" a ON a.id = r."appointmentId"
            WHERE r.id = $1
            """,
            reminder_id,
        )
        return bool(row) and row["reminder_status"] == "pending" and row["app_status"] in ACTIVE_APPOINTMENT

    async def _deliver(self, bot: Bot, conn, row) -> None:
        chat_id = int(row["chatId"])

        if row["refType"] == "reminder" and row["refId"]:
            if not await self._reminder_still_valid(conn, row["refId"]):
                # The visit was cancelled or the reminder was closed in the meantime: do not send
                await conn.execute(
                    """UPDATE "Outbox" SET status = 'failed', "lastError" = 'не отправлено: запись уже неактуальна',
                       "updatedAt" = (now() AT TIME ZONE 'UTC') WHERE id = $1""",
                    row["id"],
                )
                return

        await self._respect_limits(chat_id)
        parse_mode = ParseMode.HTML if row["kind"] in HTML_KINDS else None
        try:
            await bot.send_message(
                chat_id,
                row["text"],
                parse_mode=parse_mode,
                reply_markup=keyboard_from_json(row["replyMarkup"]),
                disable_web_page_preview=True,
            )
        except TelegramRetryAfter as error:
            await self._failed_attempt(conn, row, "retry_after", str(error), retry_after=int(error.retry_after))
            return
        except TelegramMigrateToChat as error:
            # The group became a supergroup and has a new id: move the row and send again right away
            logger.warning("Чат %s стал супергруппой, новый id %s", chat_id, error.migrate_to_chat_id)
            await conn.execute(
                """UPDATE "Outbox" SET "chatId" = $2, "updatedAt" = (now() AT TIME ZONE 'UTC') WHERE id = $1""",
                row["id"],
                int(error.migrate_to_chat_id),
            )
            return
        except TelegramForbiddenError as error:
            await self._failed_attempt(conn, row, "blocked", str(error))
            return
        except TelegramBadRequest as error:
            await self._failed_attempt(conn, row, "bad_request", str(error))
            return
        except (TelegramNetworkError, TelegramAPIError, asyncio.TimeoutError, OSError) as error:
            status = getattr(error, "status_code", None)
            await self._failed_attempt(conn, row, classify_failure(status) if status else "transient", str(error))
            return

        await conn.execute(
            """
            UPDATE "Outbox"
            SET status = 'sent', attempts = attempts + 1, "sentAt" = (now() AT TIME ZONE 'UTC'),
                "lastError" = NULL, "updatedAt" = (now() AT TIME ZONE 'UTC')
            WHERE id = $1
            """,
            row["id"],
        )
        await self._mark_done(conn, row)

    async def _mark_done(self, conn, row) -> None:
        if row["refType"] == "inbox_message" and row["refId"]:
            await conn.execute(
                """UPDATE "InboxMessage" SET "deliveryStatus" = 'sent', "deliveryError" = NULL WHERE id = $1""",
                row["refId"],
            )
            await conn.execute(
                """
                UPDATE "InboxThread" SET status = 'answered', "updatedAt" = (now() AT TIME ZONE 'UTC')
                WHERE id = (SELECT "threadId" FROM "InboxMessage" WHERE id = $1)
                """,
                row["refId"],
            )
        elif row["refType"] == "reminder" and row["refId"]:
            await conn.execute(
                """UPDATE "Reminder" SET status = 'sent', "sentAt" = (now() AT TIME ZONE 'UTC'),
                   "updatedAt" = (now() AT TIME ZONE 'UTC') WHERE id = $1""",
                row["refId"],
            )

    async def _failed_attempt(self, conn, row, failure: str, error_text: str, retry_after: Optional[int] = None) -> None:
        status, delay = after_failure(int(row["attempts"]), failure, retry_after)
        await conn.execute(
            """
            UPDATE "Outbox"
            SET status = $2::"OutboxStatus",
                attempts = attempts + 1,
                "nextAttemptAt" = (now() AT TIME ZONE 'UTC') + make_interval(secs => $3),
                "lastError" = $4,
                "updatedAt" = (now() AT TIME ZONE 'UTC')
            WHERE id = $1
            """,
            row["id"],
            status,
            float(delay),
            error_text[:500],
        )
        logger.warning("Outbox %s: %s -> %s (%s)", row["id"], failure, status, error_text[:120])

        if status != "failed":
            return

        if row["refType"] == "inbox_message" and row["refId"]:
            await conn.execute(
                """UPDATE "InboxMessage" SET "deliveryStatus" = 'failed', "deliveryError" = $2 WHERE id = $1""",
                row["refId"],
                failure,
            )
        if row["refType"] == "reminder" and row["refId"]:
            await conn.execute(
                """UPDATE "Reminder" SET status = 'failed', "lastError" = $2, "attemptCount" = "attemptCount" + 1,
                   "updatedAt" = (now() AT TIME ZONE 'UTC') WHERE id = $1""",
                row["refId"],
                error_text[:300],
            )
        if failure == "blocked":
            await conn.execute(
                """UPDATE "InboxThread" SET "patientUnreachable" = TRUE WHERE "telegramId" = $1""",
                int(row["chatId"]),
            )
            if row["refType"] == "reminder" and row["refId"]:
                await self._alert_unreachable(conn, row["refId"])

    async def _alert_unreachable(self, conn, reminder_id: str) -> None:
        """Tells staff that a patient blocked the bot, so they call instead"""
        info = await conn.fetchrow(
            """
            SELECT p.name, p.phone, a."serviceTitle", a."dateTime"
            FROM "Reminder" r
            JOIN "Appointment" a ON a.id = r."appointmentId"
            JOIN "Patient" p ON p.id = a."patientId"
            WHERE r.id = $1
            """,
            reminder_id,
        )
        if not info:
            return
        when = info["dateTime"].replace(tzinfo=None).strftime("%d.%m.%Y, %H:%M")
        text = (
            "⚠️ <b>Пациент заблокировал бота</b>\n\n"
            f"👤 <b>Пациент:</b> {_html(info['name'])}\n"
            f"📞 <b>Телефон:</b> <code>{_html(info['phone'])}</code>\n"
            f"🦷 <b>Услуга:</b> {_html(info['serviceTitle'])}\n"
            f"📅 <b>Время приёма:</b> {when} (Ташкент)\n\n"
            "Напоминание не доставлено. Позвоните пациенту."
        )
        await enqueue_staff_alert(text)


def _html(value) -> str:
    text = "" if value is None else str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


outbox_worker = OutboxWorker()
