"""
Integration test for the outbox worker and reminders, against a LOCAL TEST database with a fake bot.
No Telegram is contacted. Run:
  DATABASE_URL=postgresql://...localhost.../test_db python scripts/test_outbox_worker.py
The script refuses to run unless DATABASE_URL points at localhost.
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

DB_URL = os.environ.get("DATABASE_URL", "")
if "localhost" not in DB_URL and "127.0.0.1" not in DB_URL:
    raise SystemExit("Refusing to run: DATABASE_URL must point at localhost (a test database).")
os.environ.setdefault("ADMIN_CHAT_ID", "-1009990001111")

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter  # noqa: E402
from aiogram.methods import SendMessage  # noqa: E402

import services.outbox_worker as ow  # noqa: E402
from database import db  # noqa: E402

ow.MIN_GAP_PRIVATE = 0.0
ow.MIN_GAP_GROUP = 0.0
ow.MIN_GAP_GLOBAL = 0.0

CHAT_OK, CHAT_BLOCKED, CHAT_RETRY, CHAT_CANCELLED = 778001, 778002, 778003, 778004


class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_message(self, chat_id, text, **kwargs):
        self.calls.append(chat_id)
        if chat_id == CHAT_BLOCKED:
            raise TelegramForbiddenError(method=SendMessage(chat_id=chat_id, text=text), message="Forbidden: bot was blocked by the user")
        if chat_id == CHAT_RETRY:
            raise TelegramRetryAfter(method=SendMessage(chat_id=chat_id, text=text), message="Too Many Requests", retry_after=7)
        return None


async def make_visit(conn, chat_id: int, visit_status: str = "pending"):
    """Creates a patient, a future appointment and one due reminder. Returns (appointment_id, reminder_id)."""
    patient_id = str(uuid.uuid4())
    await conn.execute(
        """INSERT INTO "Patient" (id, "telegramId", name, phone, "createdAt", "updatedAt")
           VALUES ($1, $2, 'Тест Очередь', '+998900001122', now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC')
           ON CONFLICT ("telegramId") DO UPDATE SET name = EXCLUDED.name""",
        patient_id, chat_id,
    )
    pid = await conn.fetchval('SELECT id FROM "Patient" WHERE "telegramId" = $1', chat_id)
    app_id = str(uuid.uuid4())
    visit = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=2)
    await conn.execute(
        """INSERT INTO "Appointment" (id, "patientId", "serviceTitle", "doctorName", "dateTime", status, source, "createdAt", "updatedAt")
           VALUES ($1, $2, 'Консультация', 'Д-р Тест', $3, $4::"AppointmentStatus", 'test',
                   now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC')""",
        app_id, pid, visit, visit_status,
    )
    rem_id = str(uuid.uuid4())
    await conn.execute(
        """INSERT INTO "Reminder" (id, "appointmentId", type, "dueAt", status, "attemptCount", "createdAt", "updatedAt")
           VALUES ($1, $2, 'reminder_24h'::"ReminderType", now() AT TIME ZONE 'UTC' - interval '1 minute', 'pending'::"ReminderStatus",
                   0, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC')""",
        rem_id, app_id,
    )
    return app_id, rem_id


async def main():
    await db.init_db()
    results = []

    def check(name, ok, extra=""):
        results.append(bool(ok))
        print(f"{'PASS' if ok else 'FAIL'}  {name} {extra}")

    async with db._p().acquire() as conn:
        await conn.execute('DELETE FROM "Outbox" WHERE "chatId" BETWEEN 778001 AND 778004 OR "kind" = \'staff_alert\' AND "text" LIKE \'%Тест Очередь%\'')
        await conn.execute('DELETE FROM "Appointment" WHERE "patientId" IN (SELECT id FROM "Patient" WHERE "telegramId" BETWEEN 778001 AND 778004)')
        await conn.execute('DELETE FROM "Patient" WHERE "telegramId" BETWEEN 778001 AND 778004')

        _, ok_rem = await make_visit(conn, CHAT_OK)
        _, blocked_rem = await make_visit(conn, CHAT_BLOCKED)
        _, retry_rem = await make_visit(conn, CHAT_RETRY)
        cancelled_app, cancelled_rem = await make_visit(conn, CHAT_CANCELLED)
        await conn.execute("""UPDATE "Appointment" SET status = 'cancelled' WHERE id = $1""", cancelled_app)

        # 1. A reminder is queued once, however many times it is picked up
        first = await ow.enqueue(CHAT_OK, "reminder", "тест", ref_type="reminder", ref_id=ok_rem)
        second = await ow.enqueue(CHAT_OK, "reminder", "тест", ref_type="reminder", ref_id=ok_rem)
        count = await conn.fetchval('SELECT count(*) FROM "Outbox" WHERE "refType" = $1 AND "refId" = $2', "reminder", ok_rem)
        check("reminder is queued at most once", first and not second and count == 1, f"(rows={count})")

        # Queue the other reminders
        await ow.enqueue(CHAT_BLOCKED, "reminder", "тест", ref_type="reminder", ref_id=blocked_rem)
        await ow.enqueue(CHAT_RETRY, "reminder", "тест", ref_type="reminder", ref_id=retry_rem)
        await ow.enqueue(CHAT_CANCELLED, "reminder", "тест", ref_type="reminder", ref_id=cancelled_rem)

        bot = FakeBot()
        for _ in range(5):
            await ow.outbox_worker.run_once(bot)

        ok_status = await conn.fetchval('SELECT status::text FROM "Reminder" WHERE id = $1', ok_rem)
        check("delivered reminder is marked sent", ok_status == "sent", f"({ok_status})")

        blocked_status = await conn.fetchval('SELECT status::text FROM "Reminder" WHERE id = $1', blocked_rem)
        blocked_outbox = await conn.fetchval('SELECT status::text FROM "Outbox" WHERE "refId" = $1', blocked_rem)
        check("blocked patient: reminder failed, no retry", blocked_status == "failed" and blocked_outbox == "failed", f"({blocked_status}/{blocked_outbox})")
        unreachable = await conn.fetchval('SELECT count(*) FROM "InboxThread" WHERE "telegramId" = $1', CHAT_BLOCKED)
        alert = await conn.fetchval("""SELECT count(*) FROM "Outbox" WHERE kind = 'staff_alert' AND text LIKE '%Пациент заблокировал%' AND text LIKE '%Тест Очередь%'""")
        check("blocked patient: staff is alerted through the outbox", alert >= 1, f"(alerts={alert})")

        retry_row = await conn.fetchrow('SELECT status::text AS s, attempts, "nextAttemptAt" FROM "Outbox" WHERE "refId" = $1', retry_rem)
        in_seven = retry_row and retry_row["s"] == "pending" and retry_row["attempts"] == 1
        check("429 keeps the reminder pending and schedules a retry", in_seven, f"({retry_row['s'] if retry_row else None}, attempts={retry_row['attempts'] if retry_row else None})")

        cancelled_outbox = await conn.fetchrow('SELECT status::text AS s, "lastError" FROM "Outbox" WHERE "refId" = $1', cancelled_rem)
        cancelled_sent = CHAT_CANCELLED in bot.calls
        check("cancelled visit: reminder is not sent", cancelled_outbox and cancelled_outbox["s"] == "failed" and not cancelled_sent, f"({cancelled_outbox['lastError'] if cancelled_outbox else None})")

        # 7. Proactive sends queue with the right kind and keep both keyboard types
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
        await ow.queued_bot.send_message(CHAT_OK, "<b>Дайджест</b>", parse_mode="HTML",
                                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="ОК", callback_data="x:1")]]))
        await ow.queued_bot.send_message(CHAT_OK, "Plain & text", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Меню")]], resize_keyboard=True))
        kinds = await conn.fetch('SELECT kind, "replyMarkup" FROM "Outbox" WHERE "chatId" = $1 AND "refId" IS NULL ORDER BY "createdAt" DESC LIMIT 2', CHAT_OK)
        html_row = next((r for r in kinds if r["kind"] == "patient_html"), None)
        plain_row = next((r for r in kinds if r["kind"] == "patient_text"), None)
        check("HTML message is queued as patient_html with its inline keyboard", html_row is not None and ow.keyboard_from_json(html_row["replyMarkup"]).inline_keyboard[0][0].callback_data == "x:1")
        check("plain message is queued as patient_text with its reply keyboard", plain_row is not None and isinstance(ow.keyboard_from_json(plain_row["replyMarkup"]), ReplyKeyboardMarkup))

        # Clean up the test data
        await conn.execute('DELETE FROM "Outbox" WHERE "chatId" BETWEEN 778001 AND 778004 OR ("kind" = \'staff_alert\' AND "text" LIKE \'%Тест Очередь%\')')
        await conn.execute('DELETE FROM "Appointment" WHERE "patientId" IN (SELECT id FROM "Patient" WHERE "telegramId" BETWEEN 778001 AND 778004)')
        await conn.execute('DELETE FROM "Patient" WHERE "telegramId" BETWEEN 778001 AND 778004')

    await db.close()
    print(f"\n{sum(results)}/{len(results)} passed")
    return all(results)


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)
