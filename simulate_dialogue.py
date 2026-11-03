"""
Интерактивный симулятор диалога с AI-ассистентом DentaLux Tashkent в консоли.
Позволяет протестировать логику общения, автоопределение языка (RU/UZ) и сбор лидов
с использованием DeepSeek API или OpenAI API.
"""

import sys
import os
import asyncio

# Принудительно UTF-8 для вывода в консоль
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config
from database import db
from services.ai_service import ai_service
from services.notifier import get_tashkent_time_str


async def simulate_console():
    ai_cfg = config.get_active_ai_config()
    print("=" * 65)
    print("🦷 СИМУЛЯТОР AI-КОНСУЛЬТАНТА DENTALUX TASHKENT")
    print(f"   Провайдер: {ai_cfg['provider']} | Модель: {ai_cfg['model']}")
    print("=" * 65)

    if not ai_cfg["api_key"] or config._is_placeholder(ai_cfg["api_key"]):
        print("\n[ВНИМАНИЕ] API-ключ не задан в .env файле.")
        print("Пожалуйста, укажите ваш ключ в файле .env (DEEPSEEK_API_KEY=sk-...)")
        return

    await db.init_db()
    test_user_id = 7770001
    await db.clear_chat_history(test_user_id)
    await db.set_operator_mode(test_user_id, False)

    print("\n[Инфо] Диалог начат с чистого листа.")
    print("[Инфо] Попробуйте написать на русском или узбекском (латиница/кириллица).")
    print("[Команды] Для выхода введите 'exit', для сброса диалога — 'reset'.\n")

    while True:
        try:
            user_input = input("\n👤 Вы (Пациент): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nСессия завершена.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "q"):
            print("Выход из симулятора.")
            break

        if user_input.lower() in ("reset", "/reset"):
            await db.clear_chat_history(test_user_id)
            print("🔄 Контекст диалога очищен.")
            continue

        print(f"⏳ {ai_cfg['provider']} думает...")
        res = await ai_service.process_user_message(
            telegram_id=test_user_id,
            user_message=user_input,
            user_info={"first_name": "Тестовый Пациент", "username": "test_patient"}
        )

        print(f"\n🤖 DentaLux AI:\n{res.text}")

        # Если был зафиксирован лид
        if res.is_lead and res.lead_data:
            ld = res.lead_data
            time_str = get_tashkent_time_str()
            print("\n" + "=" * 50)
            print("🔥 [СИМУЛЯЦИЯ: КАРТОЧКА ЛИДА В АДМИН-ЧАТ]")
            print(f"👤 Имя: {ld.get('client_name')}")
            print(f"📞 Телефон: {ld.get('phone')}")
            print(f"🦷 Услуга: {ld.get('service')}")
            print(f"📅 Удобное время: {ld.get('preferred_time')}")
            print(f"💬 Краткая суть: {ld.get('summary')}")
            print(f"🌐 Язык: {ld.get('language')}")
            print(f"⏰ Время: {time_str} (Ташкент)")
            print("=" * 50)

        # Если был запрос оператора
        if res.is_operator_request:
            print("\n" + "!" * 50)
            print("🚨 [СИМУЛЯЦИЯ: АЛЕРТ В АДМИН-ЧАТ - ВЫЗОВ ОПЕРАТОРА]")
            print(f"❓ Причина: {res.operator_reason}")
            print("!" * 50)


if __name__ == "__main__":
    asyncio.run(simulate_console())
