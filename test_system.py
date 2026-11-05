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

    print("\n--- 2. Проверка работы с языком пользователя в PostgreSQL ---")
    # ВНИМАНИЕ: тест пишет в базу из DATABASE_URL. Используйте тестовую базу, не продакшен.
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("Задайте DATABASE_URL тестовой базы Postgres и запустите снова.")
    test_telegram_id = 55555

    db = Database()
    await db.init_db()
    try:
        user = await db.get_or_create_user(test_telegram_id, "newbie", "Тест", "Тестов")
        assert user["language"] is None
        assert await db.get_user_language(test_telegram_id) is None
        print("Языковой онбординг (новый пользователь без языка): OK")

        await db.update_user_language(test_telegram_id, "uz")
        assert await db.get_user_language(test_telegram_id) == "uz"
        await db.update_user_language(test_telegram_id, "en")
        assert await db.get_user_language(test_telegram_id) == "en"
        print("Сохранение и смена языка: OK")

        lead_id = await db.save_lead(
            telegram_id=test_telegram_id,
            client_name="Test User",
            phone="+998901112233",
            service="Consultation",
            preferred_time="Tomorrow 10:00",
            summary="Testing appointment",
            language="en",
        )
        assert lead_id > 0
        print(f"Сохранение лида #{lead_id}: OK")
    finally:
        async with db._p().acquire() as conn:
            await conn.execute("DELETE FROM bot_leads WHERE telegram_id = $1", test_telegram_id)
            await conn.execute("DELETE FROM bot_messages WHERE telegram_id = $1", test_telegram_id)
            await conn.execute("DELETE FROM bot_users WHERE telegram_id = $1", test_telegram_id)
        await db.close()

    print("\n[SUCCESS] Все тесты гибридной архитектуры (v2) пройдены успешно!")


if __name__ == "__main__":
    asyncio.run(run_tests())
