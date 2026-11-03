"""
Автоматический тест обновленной гибридной архитектуры (v2) бота DentaLux Tashkent.
"""

import sys
import os
import asyncio

# Принудительно устанавливаем UTF-8 для вывода в консоль Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from database import Database
from templates import (
    LANGUAGE_SELECT_TEXT,
    GREETING_TEMPLATES,
    CONTACTS_TEMPLATES,
    SERVICES_CATALOG_INTRO,
    SERVICE_DETAILS,
)
from keyboards import (
    get_language_inline_keyboard,
    get_main_menu_keyboard,
    get_services_catalog_keyboard,
    get_service_detail_keyboard,
)
from services.notifier import get_tashkent_time_str


async def run_tests():
    print("--- 1. Проверка шаблонов и мультиязычности (RU/UZ/EN) ---")
    assert "DentaLux" in LANGUAGE_SELECT_TEXT
    for lang in ("ru", "uz", "en"):
        assert lang in GREETING_TEMPLATES
        assert lang in CONTACTS_TEMPLATES
        assert lang in SERVICES_CATALOG_INTRO
        assert "brackets" in SERVICE_DETAILS
        assert lang in SERVICE_DETAILS["brackets"]
        # Проверяем генерацию клавиатур для каждого языка
        menu_kb = get_main_menu_keyboard(lang)
        assert len(menu_kb.keyboard) >= 4
        cat_kb = get_services_catalog_keyboard(lang)
        assert len(cat_kb.inline_keyboard) >= 5
    print("Шаблоны и клавиатуры на 3 языках: OK")

    print("\n--- 2. Проверка работы с языком пользователя в SQLite ---")
    test_db_path = os.path.join(os.path.dirname(__file__), "data", "test_dental.db")
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    db = Database(test_db_path)
    await db.init_db()

    # Новый пользователь без языка (онбординг)
    user = await db.get_or_create_user(55555, "newbie", "Тест", "Тестов")
    assert user["language"] is None
    assert await db.get_user_language(55555) is None
    print("Языковой онбординг (новый пользователь без языка): OK")

    # Выбор языка UZ
    await db.update_user_language(55555, "uz")
    assert await db.get_user_language(55555) == "uz"
    print("Сохранение выбранного языка: OK")

    # Смена языка на EN
    await db.update_user_language(55555, "en")
    assert await db.get_user_language(55555) == "en"
    print("Смена языка на EN: OK")

    # Проверка сохранения лида
    lead_id = await db.save_lead(
        telegram_id=55555,
        client_name="Test User",
        phone="+998901112233",
        service="Consultation",
        preferred_time="Tomorrow 10:00",
        summary="Testing appointment",
        language="en",
    )
    assert lead_id == 1
    print(f"Сохранение лида #{lead_id}: OK")

    # Очистка тестовой базы
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    print("\n[SUCCESS] Все тесты гибридной архитектуры (v2) пройдены успешно!")


if __name__ == "__main__":
    asyncio.run(run_tests())
