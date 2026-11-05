"""
Outbox worker: delivers every queued message from the shared "Outbox" table.

- Claims rows with FOR UPDATE SKIP LOCKED, so two bot instances never send the same message twice.
- Respects Telegram limits: about 25 messages per second overall, 1 per second per private chat,
  and 3 seconds between messages to the same group.
- Honours retry_after on 429, backs off on network errors, stops for good on 403 (blocked) and 400.
- Updates the thing the message is about (inbox message status, patient unreachable flag) when done.
"""

import asyncio
import logging
import time
from typing import Dict, Optional

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)

from database import db
from services.outbox_policy import after_failure, classify_failure, is_group_chat

logger = logging.getLogger(__name__)

BATCH_SIZE = 20
MIN_GAP_PRIVATE = 1.0
MIN_GAP_GROUP = 3.0
MIN_GAP_GLOBAL = 0.05  # about 20 messages per second overall


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
                    SELECT id, "chatId", kind, text, attempts, "refType", "refId"
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

    async def _deliver(self, bot: Bot, conn, row) -> None:
        chat_id = int(row["chatId"])
        await self._respect_limits(chat_id)
        # Staff alerts are written with HTML markup; patient replies are plain text
        parse_mode = ParseMode.HTML if row["kind"] == "staff_alert" else None
        try:
            await bot.send_message(chat_id, row["text"], parse_mode=parse_mode, disable_web_page_preview=True)
        except TelegramRetryAfter as error:
            await self._failed_attempt(conn, row, "retry_after", str(error), retry_after=int(error.retry_after))
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

        if status == "failed" and row["refType"] == "inbox_message" and row["refId"]:
            await conn.execute(
                """UPDATE "InboxMessage" SET "deliveryStatus" = 'failed', "deliveryError" = $2 WHERE id = $1""",
                row["refId"],
                failure,
            )
        if failure == "blocked":
            # The patient blocked the bot: mark them so staff call instead of writing
            await conn.execute(
                """UPDATE "InboxThread" SET "patientUnreachable" = TRUE WHERE "telegramId" = $1""",
                int(row["chatId"]),
            )


outbox_worker = OutboxWorker()
