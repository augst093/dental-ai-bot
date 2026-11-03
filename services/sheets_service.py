"""
Интеграция с Google Таблицами через gspread.
Асинхронная запись лидов в таблицу клиники без блокировки основного цикла событий.
"""

import os
import asyncio
import logging
from typing import Optional, Dict, Any
from config import config
from services.notifier import get_tashkent_time_str

logger = logging.getLogger(__name__)

# Заголовки столбцов таблицы Google Sheets
HEADERS = [
    "ID заявки",
    "Дата и время (Ташкент)",
    "Имя клиента",
    "Телефон",
    "Услуга",
    "Удобное время",
    "Краткая суть",
    "Язык",
    "Telegram Username",
    "Telegram ID",
    "Статус",
]


class SheetsService:
    def __init__(self):
        self.creds_file = config.GOOGLE_SHEETS_CREDENTIALS_FILE
        self.sheet_name = config.GOOGLE_SHEET_NAME
        self._client = None
        self._worksheet = None
        self._is_available = None

    def _check_and_init_sync(self) -> bool:
        """Синхронная инициализация клиента gspread и открытие листа."""
        if self._is_available is not None:
            return self._is_available

        if not os.path.exists(self.creds_file):
            logger.info(
                f"Google Sheets: файл учетных данных '{self.creds_file}' не найден. "
                "Интеграция с Google Таблицами отключена. Лиды сохраняются в SQLite."
            )
            self._is_available = False
            return False

        try:
            import gspread

            gc = gspread.service_account(filename=self.creds_file)
            try:
                sh = gc.open(self.sheet_name)
            except gspread.SpreadsheetNotFound:
                logger.warning(
                    f"Google Таблица '{self.sheet_name}' не найдена. "
                    "Убедитесь, что таблица создана и предоставлен доступ сервисному аккаунту."
                )
                self._is_available = False
                return False

            ws = sh.sheet1
            # Проверяем, есть ли шапка таблицы
            existing_values = ws.row_values(1)
            if not existing_values:
                ws.append_row(HEADERS)
                logger.info(f"Созданы заголовки в таблице '{self.sheet_name}'")

            self._client = gc
            self._worksheet = ws
            self._is_available = True
            logger.info(f"Успешное подключение к Google Таблице: {self.sheet_name}")
            return True

        except Exception as e:
            logger.error(f"Ошибка подключения к Google Sheets: {e}", exc_info=True)
            self._is_available = False
            return False

    def _append_row_sync(self, row_data: list) -> bool:
        """Синхронная вставка строки в рабочий лист."""
        try:
            if not self._worksheet:
                if not self._check_and_init_sync():
                    return False
            self._worksheet.append_row(row_data)
            return True
        except Exception as e:
            logger.error(f"Не удалось записать строку в Google Таблицу: {e}")
            return False

    async def append_lead(
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
        status: str = "new",
    ) -> bool:
        """
        Асинхронно добавляет новую строку с лидом в Google Таблицу.
        Выполняется в отдельном потоке (asyncio.to_thread).
        """
        # Если файл credentials изначально отсутствует, не тратим ресурсы
        if not os.path.exists(self.creds_file) and self._is_available is False:
            return False

        time_str = get_tashkent_time_str()
        username_str = f"@{username}" if username else "-"

        row = [
            lead_id,
            time_str,
            client_name,
            phone,
            service,
            preferred_time,
            summary,
            "Узбекский" if language == "uz" else "Русский",
            username_str,
            str(telegram_id),
            status,
        ]

        try:
            return await asyncio.to_thread(self._append_row_sync, row)
        except Exception as e:
            logger.error(f"Async error appending lead to Google Sheets: {e}")
            return False


sheets_service = SheetsService()
