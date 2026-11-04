"""
Асинхронная работа с базой данных SQLite через aiosqlite.
Хранение сессий пользователей, выбранного языка (RU/UZ/EN), истории диалогов и статусов лидов.
"""

import os
from datetime import datetime
from typing import Optional, List, Dict, Any
import aiosqlite
from config import config


class Database:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.DATABASE_PATH
        # Создаем директорию для базы данных, если её нет
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)

    async def init_db(self) -> None:
        """Создает таблицы в базе данных при первом запуске."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")

            # Таблица пользователей (language по умолчанию NULL для онбординга)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language TEXT DEFAULT NULL,
                    is_operator_mode INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # Таблица истории сообщений (контекст диалога)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (telegram_id) REFERENCES users (telegram_id)
                );
                """
            )

            # Таблица лидов (заявок на прием)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    client_name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    service TEXT,
                    preferred_time TEXT,
                    summary TEXT,
                    language TEXT DEFAULT 'ru',
                    status TEXT DEFAULT 'new',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (telegram_id) REFERENCES users (telegram_id)
                );
                """
            )

            # Таблица записей на прием (Appointment Lifecycle)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS appointments (
                    id TEXT PRIMARY KEY,
                    telegram_id INTEGER,
                    client_name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    doctor TEXT,
                    service TEXT,
                    date_time TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    source TEXT DEFAULT 'bot',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # Таблица напоминаний (Persistent, Restart-Safe Reminder Engine)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    appointment_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    due_at TIMESTAMP NOT NULL,
                    sent_at TIMESTAMP DEFAULT NULL,
                    status TEXT DEFAULT 'pending',
                    attempt_count INTEGER DEFAULT 0,
                    last_error TEXT DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(appointment_id, type)
                );
                """
            )
            await db.commit()

    async def get_or_create_user(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Возвращает пользователя или создает новую запись."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            )
            row = await cursor.fetchone()

            if row:
                return dict(row)

            # Создаем нового пользователя с language=NULL для языкового онбординга
            now = datetime.utcnow().isoformat()
            await db.execute(
                """
                INSERT INTO users (telegram_id, username, first_name, last_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (telegram_id, username, first_name, last_name, now, now),
            )
            await db.commit()

            cursor = await db.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            )
            new_row = await cursor.fetchone()
            return dict(new_row) if new_row else {}

    async def get_user_language(self, telegram_id: int) -> Optional[str]:
        """Возвращает сохраненный язык пользователя (ru, uz, en или None)."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT language FROM users WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = await cursor.fetchone()
            if row and row[0]:
                return row[0]
            return None

    async def update_user_language(self, telegram_id: int, language: str) -> None:
        """Обновляет предпочитаемый язык пользователя (ru, uz, en)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET language = ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                (language, telegram_id),
            )
            await db.commit()

    async def set_operator_mode(self, telegram_id: int, enabled: bool) -> None:
        """Включает или выключает режим связи с живым оператором."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET is_operator_mode = ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                (1 if enabled else 0, telegram_id),
            )
            await db.commit()

    async def is_operator_mode(self, telegram_id: int) -> bool:
        """Проверяет, включен ли режим живого оператора у пользователя."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT is_operator_mode FROM users WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = await cursor.fetchone()
            if row:
                return bool(row[0])
            return False

    async def save_message(self, telegram_id: int, role: str, content: str) -> None:
        """Сохраняет сообщение в историю диалога."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO messages (telegram_id, role, content) VALUES (?, ?, ?)",
                (telegram_id, role, content),
            )
            await db.commit()

    async def get_chat_history(
        self, telegram_id: int, limit: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        Возвращает последние N сообщений диалога для передачи в LLM.
        Ограничивается коротким контекстом (4-6 сообщений) для молниеносной генерации.
        """
        limit = limit or config.HISTORY_LIMIT
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT role, content FROM (
                    SELECT id, role, content FROM messages
                    WHERE telegram_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                ) ORDER BY id ASC
                """,
                (telegram_id, limit),
            )
            rows = await cursor.fetchall()
            return [{"role": row["role"], "content": row["content"]} for row in rows]

    async def clear_chat_history(self, telegram_id: int) -> None:
        """Очищает историю диалога пользователя (для команды /reset или /new)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM messages WHERE telegram_id = ?", (telegram_id,)
            )
            await db.commit()

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
        """Сохраняет новую карточку лида в базу данных и возвращает ID заявки."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO leads (
                    telegram_id, client_name, phone, service,
                    preferred_time, summary, language, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'new')
                """,
                (
                    telegram_id,
                    client_name,
                    phone,
                    service or "Консультация",
                    preferred_time or "Уточняется",
                    summary or "",
                    language,
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def update_lead_status(self, lead_id: int, status: str) -> bool:
        """Обновляет статус лида (new, contacted, confirmed, rejected)."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE leads SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, lead_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_stats(self) -> Dict[str, int]:
        """Возвращает общую статистику по пользователям и лидам."""
        async with aiosqlite.connect(self.db_path) as db:
            c1 = await db.execute("SELECT COUNT(*) FROM users")
            total_users = (await c1.fetchone())[0]

            c2 = await db.execute("SELECT COUNT(*) FROM leads")
            total_leads = (await c2.fetchone())[0]

            c3 = await db.execute(
                "SELECT COUNT(*) FROM leads WHERE DATE(created_at) = DATE('now')"
            )
            leads_today = (await c3.fetchone())[0]

            return {
                "total_users": total_users,
                "total_leads": total_leads,
                "leads_today": leads_today,
            }

    async def get_recent_leads(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Возвращает последние лиды."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, client_name, phone, service, preferred_time, status, created_at
                FROM leads
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

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
        """Сохраняет запись на приём в SQLite."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO appointments (
                    id, telegram_id, client_name, phone, doctor, service, date_time, status, source, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (appointment_id, telegram_id, client_name, phone, doctor, service, date_time, status, source),
            )
            await db.commit()
            return True

    async def get_appointment(self, appointment_id: str) -> Optional[Dict[str, Any]]:
        """Возвращает данные записи по её ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_appointment_status(self, appointment_id: str, status: str) -> bool:
        """Обновляет статус записи (pending, confirmed, reschedule_requested, cancelled, completed, no_show)."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE appointments SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, appointment_id),
            )
            if status == "cancelled":
                await db.execute(
                    "UPDATE reminders SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE appointment_id = ? AND status = 'pending'",
                    (appointment_id,),
                )
            await db.commit()
            return cursor.rowcount > 0

    async def schedule_reminder(
        self,
        appointment_id: str,
        reminder_type: str,
        due_at_iso: str,
    ) -> bool:
        """Планирует напоминание (24h или 2h). Перезапуск-безопасно и идемпотентно."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO reminders (appointment_id, type, due_at, status)
                VALUES (?, ?, ?, 'pending')
                """,
                (appointment_id, reminder_type, due_at_iso),
            )
            await db.commit()
            return True

    async def get_due_reminders(self) -> List[Dict[str, Any]]:
        """Возвращает список напоминаний, готовых к отправке (due_at <= now, status = 'pending')."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT r.id as reminder_id, r.appointment_id, r.type, r.due_at, r.attempt_count,
                       a.telegram_id, a.client_name, a.phone, a.doctor, a.service, a.date_time, a.status as app_status
                FROM reminders r
                JOIN appointments a ON r.appointment_id = a.id
                WHERE r.status = 'pending'
                  AND a.status NOT IN ('cancelled', 'completed', 'no_show')
                  AND datetime(r.due_at) <= datetime('now')
                ORDER BY r.due_at ASC
                LIMIT 50
                """
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def mark_reminder_sent(self, reminder_id: int) -> bool:
        """Отмечает напоминание как успешно отправленное."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE reminders
                SET status = 'sent', sent_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (reminder_id,),
            )
            await db.commit()
            return True

    async def mark_reminder_failed(self, reminder_id: int, error_text: str) -> bool:
        """Фиксирует ошибку отправки напоминания (например, бот заблокирован)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE reminders
                SET status = 'failed', attempt_count = attempt_count + 1, last_error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (error_text, reminder_id),
            )
            await db.commit()
            return True

    async def get_urgent_unconfirmed_appointments(self) -> List[Dict[str, Any]]:
        """
        Находит визиты, до которых осталось <= 2 часов, но пациент до сих пор в статусе 'pending'.
        Используется для мгновенного алерта администратору.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM appointments
                WHERE status = 'pending'
                  AND datetime(date_time) <= datetime('now', '+2 hours')
                  AND datetime(date_time) >= datetime('now')
                """
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


db = Database()
