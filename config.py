"""
Модуль конфигурации бота DentaLux Tashkent.
Загружает переменные окружения из .env и валидирует параметры.
Поддерживает официальный DeepSeek API (deepseek-chat) и OpenAI API.
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Базовая директория проекта
BASE_DIR = Path(__file__).resolve().parent

# Загрузка переменных из .env файла
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)


class Config:
    """Конфигурация проекта с типизацией и значениями по умолчанию."""

    # Telegram Bot Token
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

    # ID чата или группы администраторов для уведомлений о лидах
    ADMIN_CHAT_ID: int = int(os.getenv("ADMIN_CHAT_ID", "0"))

    # DeepSeek API (основной провайдер)
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "").strip()
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()

    # OpenAI API (обратная совместимость)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip()
    OPENAI_BASE_URL: Optional[str] = os.getenv("OPENAI_BASE_URL") or None
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

    # Общая база PostgreSQL (та же, что у Mini App). Берётся из переменных Railway.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()

    # Google Sheets интеграция
    GOOGLE_SHEETS_CREDENTIALS_FILE: str = os.getenv(
        "GOOGLE_SHEETS_CREDENTIALS_FILE", str(BASE_DIR / "credentials.json")
    )
    GOOGLE_SHEET_NAME: str = os.getenv(
        "GOOGLE_SHEET_NAME", "Dental Leads Tashkent"
    ).strip()

    # Часовой пояс клиники (Ташкент: UTC+5)
    TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Tashkent").strip()

    # Максимальное количество сообщений в истории диалога для LLM (4-6 для скорости)
    HISTORY_LIMIT: int = int(os.getenv("HISTORY_LIMIT", "6"))

    @staticmethod
    def _is_placeholder(val: str) -> bool:
        """Проверяет, не является ли значение плейсхолдером."""
        if not val:
            return True
        val_lower = val.lower()
        return any(x in val_lower for x in ["ваш_", "вставь_", "your_", "here", "placeholder", "xxx"])

    @classmethod
    def get_active_ai_config(cls) -> Dict[str, Any]:
        """
        Определяет активного AI провайдера (DeepSeek или OpenAI)
        и возвращает словарь: api_key, base_url, model, provider.
        """
        # 1. Приоритет: DeepSeek API
        if cls.DEEPSEEK_API_KEY and not cls._is_placeholder(cls.DEEPSEEK_API_KEY):
            return {
                "api_key": cls.DEEPSEEK_API_KEY,
                "base_url": cls.DEEPSEEK_BASE_URL or "https://api.deepseek.com",
                "model": cls.DEEPSEEK_MODEL or "deepseek-chat",
                "provider": "DeepSeek",
            }

        # 2. Обратная совместимость: OpenAI API
        if cls.OPENAI_API_KEY and not cls._is_placeholder(cls.OPENAI_API_KEY):
            return {
                "api_key": cls.OPENAI_API_KEY,
                "base_url": cls.OPENAI_BASE_URL,
                "model": cls.OPENAI_MODEL or "gpt-4o-mini",
                "provider": "OpenAI",
            }

        # По умолчанию возвращаем настройки DeepSeek
        return {
            "api_key": cls.DEEPSEEK_API_KEY or cls.OPENAI_API_KEY,
            "base_url": cls.DEEPSEEK_BASE_URL or "https://api.deepseek.com",
            "model": cls.DEEPSEEK_MODEL or "deepseek-chat",
            "provider": "DeepSeek",
        }

    @classmethod
    def validate(cls) -> list[str]:
        """Проверяет обязательные настройки и возвращает список предупреждений/ошибок."""
        errors = []
        if not cls.BOT_TOKEN or cls._is_placeholder(cls.BOT_TOKEN):
            errors.append("BOT_TOKEN не задан в .env")

        has_deepseek = bool(cls.DEEPSEEK_API_KEY and not cls._is_placeholder(cls.DEEPSEEK_API_KEY))
        has_openai = bool(cls.OPENAI_API_KEY and not cls._is_placeholder(cls.OPENAI_API_KEY))

        if not has_deepseek and not has_openai:
            errors.append(
                "Не задан API-ключ: укажите DEEPSEEK_API_KEY (рекомендуется) или OPENAI_API_KEY в .env"
            )

        if cls.ADMIN_CHAT_ID == 0:
            errors.append(
                "ADMIN_CHAT_ID не задан или равен 0 (уведомления администраторам не будут доходить)"
            )
        return errors


config = Config()
