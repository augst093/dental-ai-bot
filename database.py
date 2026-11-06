"""
Работа с базой данных PostgreSQL (та же база, что у Mini App).

Общие таблицы (создаёт Prisma в dental_miniapp, бот только читает и пишет в них):
  "Patient", "Appointment", "Reminder", "AuditLog"
Таблицы только бота (создаёт бот при запуске):
  bot_users, bot_messages, bot_leads, bot_waitlist, bot_outreach

Все даты в базе хранятся в UTC без часового пояса (как у Prisma).
Для показа пациенту и администратору время переводится в Asia/Tashkent (UTC+5).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import asyncpg

from config import config

logger = logging.getLogger(__name__)

TASHKENT = ZoneInfo("Asia/Tashkent")
UTC = timezone.utc

# Какие записи считаются активными (занимают слот и ждут визита)
ACTIVE_STATUSES = ("pending", "confirmed", "reschedule_requested")


def _parse_visit_time(text: Optional[str]) -> Optional[datetime]:
    """Разбирает время визита. Без пояса считаем, что это время Ташкента. Возвращает aware datetime."""
    if not text:
        return None
    raw = text.strip()
    parsed: Optional[datetime] = None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TASHKENT)
    return parsed


def _to_db_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Переводит datetime в наивное UTC-время, как хранит Prisma."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=TASHKENT)
    return value.astimezone(UTC).replace(tzinfo=None)


def _local_text(db_utc: Optional[datetime]) -> str:
    """Время из базы в строку 'YYYY-MM-DD HH:MM' по Ташкенту."""
    if db_utc is None:
        return ""
    return db_utc.replace(tzinfo=UTC).astimezone(TASHKENT).strftime("%Y-%m-%d %H:%M")


def _now_utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Database:
    def __init__(self) -> None:
        self._pool: Optional[asyncpg.Pool] = None

    # ------------------------------------------------------------------
    # Подключение и схема
    # ------------------------------------------------------------------

    async def init_db(self) -> None:
        """Подключается к базе и создаёт таблицы бота. Общие таблицы создаёт Prisma."""
        if not config.DATABASE_URL:
            raise RuntimeError("DATABASE_URL не задан: бот работает только с общей базой Postgres")

        self._pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=5)

        async with self._pool.acquire() as conn:
            exists = await conn.fetchval(
                "SELECT to_regclass('public.\"Appointment\"') IS NOT NULL"
            )
            if not exists:
                raise RuntimeError(
                    'В базе нет таблицы "Appointment". Сначала выполните в dental_miniapp: npx prisma db push'
                )

            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_users (
                    telegram_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language TEXT,
                    is_operator_mode BOOLEAN NOT NULL DEFAULT FALSE,
                    source TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
                    updated_at TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'UTC')
                );
                CREATE TABLE IF NOT EXISTS bot_messages (
                    id BIGSERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'UTC')
                );
                CREATE INDEX IF NOT EXISTS bot_messages_user_idx ON bot_messages (telegram_id, id);
                CREATE TABLE IF NOT EXISTS bot_leads (
                    id BIGSERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    client_name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    service TEXT,
                    preferred_time TEXT,
                    summary TEXT,
                    language TEXT NOT NULL DEFAULT 'ru',
                    status TEXT NOT NULL DEFAULT 'new',
                    created_at TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
                    updated_at TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'UTC')
                );
                CREATE TABLE IF NOT EXISTS bot_waitlist (
                    id BIGSERIAL PRIMARY KEY,
                    telegram_id BIGINT NOT NULL,
                    wanted_date TEXT NOT NULL,
                    doctor TEXT NOT NULL DEFAULT 'any',
                    created_at TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'UTC')
                );
                CREATE TABLE IF NOT EXISTS bot_outreach (
                    item_key TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    sent_at TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'UTC'),
                    PRIMARY KEY (item_key, kind)
                );
                """
            )
        logger.info("PostgreSQL подключена, таблицы бота проверены")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    def _p(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("База не подключена: сначала вызовите init_db()")
        return self._pool

    async def _audit(self, conn, appointment_id: str, actor_type: str, action: str,
                     from_status: Optional[str], to_status: Optional[str], details: Optional[str] = None) -> None:
        await conn.execute(
            """
            INSERT INTO "AuditLog" (id, "appointmentId", "actorType", action, "fromStatus", "toStatus", details, "createdAt")
            VALUES (gen_random_uuid()::text, $1, $2, $3, $4, $5, $6, now() AT TIME ZONE 'UTC')
            """,
            appointment_id, actor_type, action, from_status, to_status, details,
        )

    # ------------------------------------------------------------------
    # Пользователи бота
    # ------------------------------------------------------------------

    async def get_or_create_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Возвращает пользователя или создаёт нового (язык пока пустой, для онбординга)."""
        async with self._p().acquire() as conn:
            await conn.execute(
                """
                INSERT INTO bot_users (telegram_id, username, first_name, last_name)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (telegram_id) DO NOTHING
                """,
                telegram_id, username, first_name, last_name,
            )
            row = await conn.fetchrow("SELECT * FROM bot_users WHERE telegram_id = $1", telegram_id)
            return dict(row) if row else {}

    async def get_user_language(self, telegram_id: int) -> Optional[str]:
        async with self._p().acquire() as conn:
            return await conn.fetchval(
                "SELECT language FROM bot_users WHERE telegram_id = $1", telegram_id
            )

    async def update_user_language(self, telegram_id: int, language: str) -> None:
        async with self._p().acquire() as conn:
            await conn.execute(
                "UPDATE bot_users SET language = $2, updated_at = now() AT TIME ZONE 'UTC' WHERE telegram_id = $1",
                telegram_id, language,
            )

    async def set_operator_mode(self, telegram_id: int, enabled: bool) -> None:
        async with self._p().acquire() as conn:
            await conn.execute(
                "UPDATE bot_users SET is_operator_mode = $2, updated_at = now() AT TIME ZONE 'UTC' WHERE telegram_id = $1",
                telegram_id, enabled,
            )

    async def is_operator_mode(self, telegram_id: int) -> bool:
        async with self._p().acquire() as conn:
            value = await conn.fetchval(
                "SELECT is_operator_mode FROM bot_users WHERE telegram_id = $1", telegram_id
            )
            return bool(value)

    async def save_message(self, telegram_id: int, role: str, content: str) -> None:
        async with self._p().acquire() as conn:
            await conn.execute(
                "INSERT INTO bot_messages (telegram_id, role, content) VALUES ($1, $2, $3)",
                telegram_id, role, content,
            )

    async def get_chat_history(self, telegram_id: int, limit: Optional[int] = None) -> List[Dict[str, str]]:
        """Последние N сообщений диалога для передачи в LLM."""
        limit = limit or config.HISTORY_LIMIT
        async with self._p().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT role, content FROM (
                    SELECT id, role, content FROM bot_messages
                    WHERE telegram_id = $1
                    ORDER BY id DESC
                    LIMIT $2
                ) last_messages ORDER BY id ASC
                """,
                telegram_id, limit,
            )
            return [{"role": row["role"], "content": row["content"]} for row in rows]

    async def clear_chat_history(self, telegram_id: int) -> None:
        async with self._p().acquire() as conn:
            await conn.execute("DELETE FROM bot_messages WHERE telegram_id = $1", telegram_id)

    # ------------------------------------------------------------------
    # Лиды (заявки из чата и Mini App)
    # ------------------------------------------------------------------

    async def save_lead(
        self,
        telegram_id: int,
        client_name: str,
        phone: str,
        service: Optional[str] = None,
        preferred_time: Optional[str] = None,
        summary: Optional[str] = None,
        language: str = "ru",
    ) -> int:
        async with self._p().acquire() as conn:
            return await conn.fetchval(
                """
                INSERT INTO bot_leads (telegram_id, client_name, phone, service, preferred_time, summary, language, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'new')
                RETURNING id
                """,
                telegram_id, client_name, phone,
                service or "Консультация",
                preferred_time or "Уточняется",
                summary or "",
                language,
            )

    async def update_lead_status(self, lead_id: int, status: str) -> bool:
        async with self._p().acquire() as conn:
            result = await conn.execute(
                "UPDATE bot_leads SET status = $2, updated_at = now() AT TIME ZONE 'UTC' WHERE id = $1",
                lead_id, status,
            )
            return result.endswith("1")

    async def get_stats(self) -> Dict[str, int]:
        async with self._p().acquire() as conn:
            total_users = await conn.fetchval("SELECT COUNT(*) FROM bot_users")
            total_leads = await conn.fetchval("SELECT COUNT(*) FROM bot_leads")
            leads_today = await conn.fetchval(
                "SELECT COUNT(*) FROM bot_leads WHERE created_at >= date_trunc('day', now() AT TIME ZONE 'UTC')"
            )
            return {"total_users": total_users, "total_leads": total_leads, "leads_today": leads_today}

    async def get_recent_leads(self, limit: int = 5) -> List[Dict[str, Any]]:
        async with self._p().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, client_name, phone, service, preferred_time, status, created_at
                FROM bot_leads ORDER BY id DESC LIMIT $1
                """,
                limit,
            )
            return [dict(row) for row in rows]

    async def anonymize_user_data(self, telegram_id: int) -> None:
        """Стирает имя и телефон пациента в лидах и записях (по запросу /delete_my_data)."""
        async with self._p().acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE bot_leads SET client_name = 'Анонимизированный пациент', phone = '+998000000000' WHERE telegram_id = $1",
                    telegram_id,
                )
                await conn.execute(
                    """
                    UPDATE "Patient" SET name = 'Анонимизированный пациент', phone = '+998000000000',
                           "telegramId" = NULL, "updatedAt" = now() AT TIME ZONE 'UTC'
                    WHERE "telegramId" = $1
                    """,
                    telegram_id,
                )

    # ------------------------------------------------------------------
    # Записи (общие с Mini App)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Каталог из общей базы и запись из бота (таблицы Doctor, Service, Appointment)
    # ------------------------------------------------------------------

    async def fetch_active_doctors(self) -> List[Dict[str, Any]]:
        async with self._p().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, name, specialty, "experienceYears" AS experience_years, "photoUrl" AS photo_url,
                       "workingDays" AS working_days, "workingHoursStart" AS hours_start,
                       "workingHoursEnd" AS hours_end, "slotDurationMinutes" AS slot_minutes
                FROM "Doctor" WHERE "isActive" = true ORDER BY name
                """
            )
            return [dict(r) for r in rows]

    async def fetch_active_services(self) -> List[Dict[str, Any]]:
        async with self._p().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, title, category, "priceUzs" AS price_uzs, "durationMinutes" AS duration_minutes,
                       description
                FROM "Service" WHERE "isActive" = true ORDER BY "sortOrder", title
                """
            )
            return [dict(r) for r in rows]

    async def fetch_busy_utc(self, doctor_id: str, start_utc: datetime, end_utc: datetime) -> List[datetime]:
        """Занятые времена врача за интервал (aware UTC). Учитываются только активные записи."""
        async with self._p().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT "dateTime" FROM "Appointment"
                WHERE "doctorId" = $1 AND "dateTime" >= $2 AND "dateTime" < $3
                  AND status::text = ANY($4::text[])
                """,
                doctor_id, _to_db_utc(start_utc), _to_db_utc(end_utc), list(ACTIVE_STATUSES),
            )
            return [r["dateTime"].replace(tzinfo=UTC) for r in rows]

    async def list_my_appointments(self, telegram_id: int) -> List[Dict[str, Any]]:
        """Будущие активные записи пациента (по Telegram ID), ближайшие первыми."""
        async with self._p().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT a.id, a."serviceTitle" AS service, a."doctorName" AS doctor, a."doctorId" AS doctor_id,
                       a."serviceId" AS service_id, a."dateTime" AS visit_utc, a.status::text AS status
                FROM "Appointment" a JOIN "Patient" p ON p.id = a."patientId"
                WHERE p."telegramId" = $1 AND a."dateTime" >= now() AT TIME ZONE 'UTC'
                  AND a.status::text = ANY($2::text[])
                ORDER BY a."dateTime" LIMIT 10
                """,
                telegram_id, list(ACTIVE_STATUSES),
            )
            result = []
            for r in rows:
                item = dict(r)
                item["visit_utc"] = item["visit_utc"].replace(tzinfo=UTC)
                result.append(item)
            return result

    async def book_slot(
        self,
        *,
        appointment_id: str,
        telegram_id: int,
        client_name: str,
        phone: str,
        doctor_id: str,
        doctor_name: str,
        service_id: Optional[str],
        service_title: str,
        price_uzs: Optional[int],
        duration_minutes: int,
        visit_utc: datetime,
    ) -> str:
        """Создаёт запись, если слот свободен. Возвращает 'ok' или 'taken'.
        Блокировка по врачу и времени не даёт двум пациентам занять один слот одновременно."""
        visit_db = _to_db_utc(visit_utc)
        async with self._p().acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"{doctor_id}|{visit_db.isoformat()}")
                taken = await conn.fetchval(
                    'SELECT 1 FROM "Appointment" WHERE "doctorId" = $1 AND "dateTime" = $2 AND status::text = ANY($3::text[])',
                    doctor_id, visit_db, list(ACTIVE_STATUSES),
                )
                if taken:
                    return "taken"
                patient_id = await self._upsert_patient(conn, telegram_id or None, client_name, phone)
                # Согласие на обработку персональных данных фиксируем с временем (как в Mini App)
                await conn.execute(
                    'UPDATE "Patient" SET "consentAt" = COALESCE("consentAt", now() AT TIME ZONE \'UTC\') WHERE id = $1',
                    patient_id,
                )
                await conn.execute(
                    """
                    INSERT INTO "Appointment" (id, "patientId", "doctorId", "serviceId", "serviceTitle", "priceUzs",
                                               "doctorName", "dateTime", "durationMinutes", status, source,
                                               "createdAt", "updatedAt")
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending'::"AppointmentStatus", 'bot',
                            now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC')
                    """,
                    appointment_id, patient_id, doctor_id, service_id, service_title, price_uzs,
                    doctor_name, visit_db, duration_minutes,
                )
                await self._audit(conn, appointment_id, "bot", "created", None, "pending", "bot")
        return "ok"

    async def reschedule_slot(self, *, appointment_id: str, telegram_id: int, new_visit_utc: datetime) -> str:
        """Переносит запись на новый слот того же врача. 'ok', 'taken' или 'not_found' (не владелец / нет записи)."""
        new_db = _to_db_utc(new_visit_utc)
        async with self._p().acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT a."doctorId" AS doctor_id, a.status::text AS status, a."dateTime" AS old_dt
                    FROM "Appointment" a JOIN "Patient" p ON p.id = a."patientId"
                    WHERE a.id = $1 AND p."telegramId" = $2 FOR UPDATE OF a
                    """,
                    appointment_id, telegram_id,
                )
                if row is None:
                    return "not_found"
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", f"{row['doctor_id']}|{new_db.isoformat()}")
                taken = await conn.fetchval(
                    """
                    SELECT 1 FROM "Appointment"
                    WHERE "doctorId" = $1 AND "dateTime" = $2 AND id <> $3 AND status::text = ANY($4::text[])
                    """,
                    row["doctor_id"], new_db, appointment_id, list(ACTIVE_STATUSES),
                )
                if taken:
                    return "taken"
                await conn.execute(
                    """
                    UPDATE "Appointment" SET "dateTime" = $2, status = 'pending'::"AppointmentStatus",
                           "updatedAt" = now() AT TIME ZONE 'UTC'
                    WHERE id = $1
                    """,
                    appointment_id, new_db,
                )
                await conn.execute(
                    """
                    UPDATE "Reminder" SET status = 'cancelled', "updatedAt" = now() AT TIME ZONE 'UTC'
                    WHERE "appointmentId" = $1 AND status = 'pending'
                    """,
                    appointment_id,
                )
                await self._audit(conn, appointment_id, "bot", "rescheduled", row["status"], "pending", "bot")
        return "ok"

    async def _upsert_patient(self, conn, telegram_id: Optional[int], name: str, phone: str) -> str:
        """Находит пациента по Telegram ID или телефону, иначе создаёт. Возвращает его id."""
        if telegram_id:
            row = await conn.fetchrow(
                """
                INSERT INTO "Patient" (id, "telegramId", name, phone, "createdAt", "updatedAt")
                VALUES (gen_random_uuid()::text, $1, $2, $3, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC')
                ON CONFLICT ("telegramId") DO UPDATE SET name = EXCLUDED.name, phone = EXCLUDED.phone,
                       "updatedAt" = now() AT TIME ZONE 'UTC'
                RETURNING id
                """,
                telegram_id, name, phone,
            )
            return row["id"]

        row = await conn.fetchrow('SELECT id FROM "Patient" WHERE phone = $1 LIMIT 1', phone)
        if row:
            return row["id"]
        row = await conn.fetchrow(
            """
            INSERT INTO "Patient" (id, name, phone, "createdAt", "updatedAt")
            VALUES (gen_random_uuid()::text, $1, $2, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC')
            RETURNING id
            """,
            name, phone,
        )
        return row["id"]

    async def save_appointment(
        self,
        appointment_id: str,
        telegram_id: int,
        client_name: str,
        phone: str,
        doctor: str,
        service: str,
        date_time: str,
        status: str = "pending",
        source: str = "bot",
    ) -> bool:
        """Создаёт запись в общей таблице Appointment. False, если время визита не распознано."""
        visit = _parse_visit_time(date_time)
        if visit is None:
            logger.warning("Не удалось разобрать время визита: %r (запись %s не создана)", date_time, appointment_id)
            return False

        visit_utc = _to_db_utc(visit)
        async with self._p().acquire() as conn:
            async with conn.transaction():
                patient_id = await self._upsert_patient(conn, telegram_id or None, client_name, phone)
                await conn.execute(
                    """
                    INSERT INTO "Appointment" (id, "patientId", "serviceTitle", "doctorName", "dateTime",
                                               status, source, "createdAt", "updatedAt")
                    VALUES ($1, $2, $3, $4, $5, $6::"AppointmentStatus", $7,
                            now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC')
                    ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, "dateTime" = EXCLUDED."dateTime",
                           "updatedAt" = now() AT TIME ZONE 'UTC'
                    """,
                    appointment_id, patient_id, service or "Консультация", doctor or "Врач",
                    visit_utc, status, source,
                )
                await self._audit(conn, appointment_id, "bot", "created", None, status, source)
        return True

    def _appointment_row_to_dict(self, row) -> Dict[str, Any]:
        data = dict(row)
        return {
            "id": data["id"],
            "telegram_id": data.get("telegram_id"),
            "client_name": data.get("client_name"),
            "phone": data.get("phone"),
            "doctor": data.get("doctor"),
            "service": data.get("service"),
            "date_time": _local_text(data.get("date_time_utc")),
            "status": data.get("status"),
            "source": data.get("source"),
        }

    _APPOINTMENT_SELECT = """
        SELECT a.id, p."telegramId" AS telegram_id, p.name AS client_name, p.phone,
               a."doctorName" AS doctor, a."serviceTitle" AS service,
               a."dateTime" AS date_time_utc, a.status::text AS status, a.source
        FROM "Appointment" a JOIN "Patient" p ON p.id = a."patientId"
    """

    async def get_appointment(self, appointment_id: str) -> Optional[Dict[str, Any]]:
        async with self._p().acquire() as conn:
            row = await conn.fetchrow(self._APPOINTMENT_SELECT + " WHERE a.id = $1", appointment_id)
            return self._appointment_row_to_dict(row) if row else None

    async def update_appointment_status(self, appointment_id: str, status: str) -> bool:
        """Меняет статус записи. Для отмены гасит ожидающие напоминания."""
        async with self._p().acquire() as conn:
            async with conn.transaction():
                previous = await conn.fetchval(
                    'SELECT status::text FROM "Appointment" WHERE id = $1 FOR UPDATE', appointment_id
                )
                if previous is None:
                    return False
                await conn.execute(
                    """
                    UPDATE "Appointment" SET status = $2::"AppointmentStatus", "updatedAt" = now() AT TIME ZONE 'UTC'
                    WHERE id = $1
                    """,
                    appointment_id, status,
                )
                if status == "cancelled":
                    await conn.execute(
                        """
                        UPDATE "Reminder" SET status = 'cancelled', "updatedAt" = now() AT TIME ZONE 'UTC'
                        WHERE "appointmentId" = $1 AND status = 'pending'
                        """,
                        appointment_id,
                    )
                await self._audit(conn, appointment_id, "bot", "status_change", previous, status)
            return True

    async def schedule_reminder(self, appointment_id: str, reminder_type: str, due_at_iso: str) -> bool:
        """Ставит напоминание (reminder_24h или reminder_2h). Повторный вызов ничего не меняет."""
        due = _parse_visit_time(due_at_iso)
        if due is None:
            return False
        async with self._p().acquire() as conn:
            await conn.execute(
                """
                INSERT INTO "Reminder" (id, "appointmentId", type, "dueAt", status, "attemptCount",
                                        "createdAt", "updatedAt")
                VALUES (gen_random_uuid()::text, $1, $2::"ReminderType", $3, 'pending', 0,
                        now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC')
                ON CONFLICT ("appointmentId", type) DO NOTHING
                """,
                appointment_id, reminder_type, _to_db_utc(due),
            )
        return True

    async def get_due_reminders(self) -> List[Dict[str, Any]]:
        """Напоминания, время которых уже наступило, по активным записям с Telegram ID пациента."""
        async with self._p().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT r.id AS reminder_id, r."appointmentId" AS appointment_id, r.type::text AS type,
                       r."dueAt" AS due_at, r."attemptCount" AS attempt_count,
                       p."telegramId" AS telegram_id, p.name AS client_name, p.phone,
                       a."doctorName" AS doctor, a."serviceTitle" AS service,
                       a."dateTime" AS date_time_utc, a.status::text AS app_status
                FROM "Reminder" r
                JOIN "Appointment" a ON a.id = r."appointmentId"
                JOIN "Patient" p ON p.id = a."patientId"
                WHERE r.status = 'pending'
                  AND a.status::text NOT IN ('cancelled', 'completed', 'no_show')
                  AND r."dueAt" <= (now() AT TIME ZONE 'UTC')
                ORDER BY r."dueAt" ASC
                LIMIT 50
                """
            )
            result = []
            for row in rows:
                item = dict(row)
                item["date_time"] = _local_text(item.pop("date_time_utc"))
                item["telegram_id"] = int(item["telegram_id"]) if item["telegram_id"] else None
                result.append(item)
            return result

    async def mark_reminder_sent(self, reminder_id: str) -> bool:
        async with self._p().acquire() as conn:
            await conn.execute(
                """
                UPDATE "Reminder" SET status = 'sent', "sentAt" = now() AT TIME ZONE 'UTC',
                       "updatedAt" = now() AT TIME ZONE 'UTC'
                WHERE id = $1
                """,
                reminder_id,
            )
            return True

    async def mark_reminder_failed(self, reminder_id: str, error_text: str) -> bool:
        async with self._p().acquire() as conn:
            await conn.execute(
                """
                UPDATE "Reminder" SET status = 'failed', "attemptCount" = "attemptCount" + 1,
                       "lastError" = $2, "updatedAt" = now() AT TIME ZONE 'UTC'
                WHERE id = $1
                """,
                reminder_id, error_text,
            )
            return True

    async def get_urgent_unconfirmed_appointments(self) -> List[Dict[str, Any]]:
        """Визиты через 2 часа и меньше, которые пациент так и не подтвердил."""
        now = _now_utc_naive()
        async with self._p().acquire() as conn:
            rows = await conn.fetch(
                self._APPOINTMENT_SELECT
                + """
                WHERE a.status = 'pending'
                  AND a."dateTime" >= $1 AND a."dateTime" <= $2
                """,
                now, now + timedelta(hours=2),
            )
            return [self._appointment_row_to_dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Рост: источники, дайджест, лист ожидания, рассылки
    # ------------------------------------------------------------------

    async def set_user_source(self, telegram_id: int, source: str) -> None:
        """Запоминает источник первого прихода; существующий источник не перезаписывает."""
        async with self._p().acquire() as conn:
            await conn.execute(
                "UPDATE bot_users SET source = $2 WHERE telegram_id = $1 AND source IS NULL",
                telegram_id, source,
            )

    async def get_sources_breakdown(self) -> List[Dict[str, Any]]:
        async with self._p().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT COALESCE(source, 'direct') AS source, COUNT(*) AS total
                FROM bot_users GROUP BY COALESCE(source, 'direct') ORDER BY total DESC
                """
            )
            return [dict(row) for row in rows]

    async def get_digest_stats(self, days: int = 7) -> Dict[str, int]:
        """Цифры записей за период, по дате создания."""
        async with self._p().acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE status::text IN ('confirmed', 'completed')) AS confirmed,
                       COUNT(*) FILTER (WHERE status::text = 'no_show') AS no_show,
                       COUNT(*) FILTER (WHERE status::text = 'cancelled') AS cancelled
                FROM "Appointment"
                WHERE "createdAt" >= (now() AT TIME ZONE 'UTC') - make_interval(days => $1)
                """,
                int(days),
            )
            return {k: int(row[k] or 0) for k in ("total", "confirmed", "no_show", "cancelled")}

    async def count_appointments_on(self, date_prefix: str) -> int:
        """Активные записи на дату по Ташкенту (формат YYYY-MM-DD)."""
        async with self._p().acquire() as conn:
            return await conn.fetchval(
                """
                SELECT COUNT(*) FROM "Appointment"
                WHERE to_char(("dateTime" AT TIME ZONE 'UTC') AT TIME ZONE 'Asia/Tashkent', 'YYYY-MM-DD') = $1
                  AND status::text <> 'cancelled'
                """,
                date_prefix,
            )

    async def mark_outreach(self, item_key: str, kind: str) -> bool:
        """True, если отметка поставлена впервые: так каждое сообщение уходит один раз."""
        async with self._p().acquire() as conn:
            result = await conn.execute(
                "INSERT INTO bot_outreach (item_key, kind) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                item_key, kind,
            )
            return result.endswith("1")

    async def get_review_candidates(self) -> List[Dict[str, Any]]:
        """Визиты 2+ часа назад (не отменённые) за последние 3 дня: просим отзыв."""
        now = _now_utc_naive()
        async with self._p().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT a.id, p."telegramId" AS telegram_id, a."serviceTitle" AS service,
                       a."dateTime" AS date_time_utc
                FROM "Appointment" a JOIN "Patient" p ON p.id = a."patientId"
                WHERE a.status::text IN ('confirmed', 'completed')
                  AND p."telegramId" IS NOT NULL
                  AND a."dateTime" <= $1 AND a."dateTime" >= $2
                """,
                now - timedelta(hours=2), now - timedelta(days=3),
            )
            return [{"id": r["id"], "telegram_id": int(r["telegram_id"]), "service": r["service"],
                     "date_time": _local_text(r["date_time_utc"])} for r in rows]

    async def get_recall_candidates(self) -> List[Dict[str, Any]]:
        """Пациенты, у которых последний визит был 180+ дней назад."""
        cutoff = _now_utc_naive() - timedelta(days=180)
        async with self._p().acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT p."telegramId" AS telegram_id, MAX(a."dateTime") AS last_visit_utc
                FROM "Appointment" a JOIN "Patient" p ON p.id = a."patientId"
                WHERE a.status::text IN ('confirmed', 'completed') AND p."telegramId" IS NOT NULL
                GROUP BY p."telegramId"
                HAVING MAX(a."dateTime") <= $1
                """,
                cutoff,
            )
            return [{"telegram_id": int(r["telegram_id"]), "last_visit": _local_text(r["last_visit_utc"])}
                    for r in rows]

    async def add_waitlist(self, telegram_id: int, wanted_date: str, doctor: str = "any") -> None:
        async with self._p().acquire() as conn:
            await conn.execute(
                "INSERT INTO bot_waitlist (telegram_id, wanted_date, doctor) VALUES ($1, $2, $3)",
                telegram_id, wanted_date, doctor,
            )

    async def pop_waitlist_for(self, date_prefix: str, doctor: str) -> List[Dict[str, Any]]:
        """Забирает людей из листа ожидания на дату, подходящих под врача (или 'any')."""
        async with self._p().acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    """
                    DELETE FROM bot_waitlist
                    WHERE wanted_date = $1 AND (doctor = 'any' OR doctor = $2)
                    RETURNING id, telegram_id, wanted_date, doctor, created_at
                    """,
                    date_prefix, doctor,
                )
            return [dict(r) for r in sorted(rows, key=lambda r: r["created_at"])]


db = Database()
