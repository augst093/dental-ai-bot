"""
Главный модуль запуска Telegram-бота клиники DentaLux Tashkent.
Гибридная архитектура:
1. Мгновенные статичные шаблоны на 3 языках (RU/UZ/EN) для кнопок меню (0 секунд отклика).
2. Языковой онбординг на старте.
3. DeepSeek API (deepseek-chat) с непрерывным typing-индикатором для произвольных вопросов.
"""

import re
import sys
import json
import asyncio
import logging
from typing import Optional

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode
from aiogram.types import WebAppInfo, MenuButtonWebApp, BufferedInputFile

from config import config
from database import db
from keyboards import (
    get_language_inline_keyboard,
    get_main_menu_keyboard,
    get_services_catalog_keyboard,
    get_service_detail_keyboard,
    get_contacts_inline_keyboard,
    MENU_BUTTON_TEXTS,
    MINIAPP_URL,
)
from templates import (
    LANGUAGE_SELECT_TEXT,
    GREETING_TEMPLATES,
    CONTACTS_TEMPLATES,
    ABOUT_TEMPLATES,
    SERVICES_CATALOG_INTRO,
    SERVICE_DETAILS,
    BOOKING_PROMPT_TEMPLATES,
    OPERATOR_MODE_TEMPLATES,
    LANGUAGE_CHANGED_TEMPLATES,
)
from services.ai_service import ai_service
from services.notifier import notifier, get_tashkent_time_str
from services.sheets_service import sheets_service
from services.reminder_service import reminder_engine
from services.outbox_worker import outbox_worker
from services.growth_service import (
    growth_worker,
    build_ics,
    build_digest_text,
    notify_waitlist,
    visit_instructions,
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("dental_bot")

# Инициализация диспетчера
dp = Dispatcher()


async def keep_typing(bot: Bot, chat_id: int):
    """Фоновая задача: обновляет статус 'печатает...' каждые 3.5 секунды, пока LLM генерирует ответ."""
    try:
        while True:
            await bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(3.5)
    except asyncio.CancelledError:
        pass


async def get_user_lang(user_id: int) -> str:
    """Возвращает сохраненный язык пользователя или 'ru' по умолчанию."""
    lang = await db.get_user_language(user_id)
    return lang if lang in ("ru", "uz", "en") else "ru"


# =========================================================================
# 1. ЯЗЫКОВОЙ ОНБОРДИНГ И КОМАНДА /start
# =========================================================================

@dp.message(CommandStart())
async def handle_start(message: types.Message):
    """
    Команда /start.
    ВСЕГДА первым сообщением встречает стильным экраном выбора языка с инлайн-кнопками!
    """
    user = message.from_user
    if not user:
        return

    # Регистрируем или обновляем пользователя в базе данных
    await db.get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )
    # Сбрасываем флаг ожидания оператора
    await db.set_operator_mode(user.id, False)

    # Источник пациента из ссылки t.me/<bot>?start=instagram (сохраняется один раз)
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2 and re.fullmatch(r"[A-Za-z0-9_-]{1,32}", parts[1].strip()):
        await db.set_user_source(user.id, parts[1].strip().lower())

    # ВСЕГДА отправляем эстетичный экран выбора языка с инлайн-кнопками первым сообщением
    await message.answer(
        text=LANGUAGE_SELECT_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=get_language_inline_keyboard(),
    )


@dp.callback_query(F.data.startswith("set_lang:"))
async def handle_set_language_callback(callback: types.CallbackQuery):
    """Обработка клика по инлайн-кнопке выбора языка."""
    lang = callback.data.split(":")[1]
    user = callback.from_user
    if not user:
        return

    # Сохраняем выбранный язык в базе
    await db.update_user_language(user.id, lang)

    # Красивое подтверждение выбора языка в текущем сообщении
    lang_labels = {
        "ru": "✅ <b>Язык выбран: Русский</b> 🇷🇺",
        "uz": "✅ <b>Muloqot tili tanlandi: O'zbekcha</b> 🇺🇿",
        "en": "✅ <b>Language selected: English</b> 🇬🇧",
    }
    confirm_text = lang_labels.get(lang, "✅")

    try:
        await callback.message.edit_text(text=confirm_text, parse_mode=ParseMode.HTML)
    except Exception:
        pass

    await callback.answer()

    # Отправляем стильное Главное Меню на выбранном языке
    name = user.first_name or ("Пациент" if lang == "ru" else "Bemor" if lang == "uz" else "Patient")
    greeting_text = GREETING_TEMPLATES.get(lang, GREETING_TEMPLATES["ru"]).format(name=name)

    await callback.message.answer(
        text=greeting_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(lang),
    )


@dp.message(Command("lang", "language"))
async def handle_change_language_command(message: types.Message):
    """Команда /lang для принудительной смены языка."""
    await message.answer(
        text=LANGUAGE_SELECT_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=get_language_inline_keyboard(),
    )


# =========================================================================
# 2. МГНОВЕННЫЕ СТАТИЧНЫЕ ШАБЛОНЫ (КНОПКИ МЕНЮ - 0 СЕКУНД)
# =========================================================================

# Список всех текстовых меток кнопок для мгновенного матчинга
SERVICES_BUTTONS = {
    MENU_BUTTON_TEXTS["ru"]["services"],
    MENU_BUTTON_TEXTS["uz"]["services"],
    MENU_BUTTON_TEXTS["en"]["services"],
    "Услуги и цены",
    "Xizmatlar va narxlar",
}

CONTACTS_BUTTONS = {
    MENU_BUTTON_TEXTS["ru"]["contacts"],
    MENU_BUTTON_TEXTS["uz"]["contacts"],
    MENU_BUTTON_TEXTS["en"]["contacts"],
    "Адрес и контакты",
    "Manzil va aloqa",
}

ABOUT_BUTTONS = {
    MENU_BUTTON_TEXTS["ru"]["about"],
    MENU_BUTTON_TEXTS["uz"]["about"],
    MENU_BUTTON_TEXTS["en"]["about"],
    "О клинике и врачах",
    "Klinika haqida",
}

BOOKING_BUTTONS = {
    MENU_BUTTON_TEXTS["ru"]["booking"],
    MENU_BUTTON_TEXTS["uz"]["booking"],
    MENU_BUTTON_TEXTS["en"]["booking"],
    "Записаться на приём",
    "Qabulga yozilish",
}

OPERATOR_BUTTONS = {
    MENU_BUTTON_TEXTS["ru"]["operator"],
    MENU_BUTTON_TEXTS["uz"]["operator"],
    MENU_BUTTON_TEXTS["en"]["operator"],
    "Позвать администратора",
    "Operator bilan bog'lanish",
}

CHANGE_LANG_BUTTONS = {
    MENU_BUTTON_TEXTS["ru"]["lang"],
    MENU_BUTTON_TEXTS["uz"]["lang"],
    MENU_BUTTON_TEXTS["en"]["lang"],
    "Сменить язык",
    "Tilni o'zgartirish",
}


@dp.message(F.text.in_(SERVICES_BUTTONS))
async def handle_menu_services(message: types.Message):
    """Мгновенный каталог услуг и цен (0 секунд, без LLM)."""
    lang = await get_user_lang(message.from_user.id)
    text = SERVICES_CATALOG_INTRO.get(lang, SERVICES_CATALOG_INTRO["ru"])
    await message.answer(
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_services_catalog_keyboard(lang),
    )


@dp.message(F.text.in_(CONTACTS_BUTTONS))
async def handle_menu_contacts(message: types.Message):
    """Мгновенные контакты, график работы и геолокация (0 секунд, без LLM)."""
    lang = await get_user_lang(message.from_user.id)
    text = CONTACTS_TEMPLATES.get(lang, CONTACTS_TEMPLATES["ru"])
    await message.answer(
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_contacts_inline_keyboard(lang),
    )


@dp.message(F.text.in_(ABOUT_BUTTONS))
async def handle_menu_about(message: types.Message):
    """Информация о клинике, врачах, микроскопе и стерилизации (0 секунд, без LLM)."""
    lang = await get_user_lang(message.from_user.id)
    text = ABOUT_TEMPLATES.get(lang, ABOUT_TEMPLATES["ru"])
    await message.answer(
        text=text,
        parse_mode=ParseMode.HTML,
    )


@dp.message(F.text.in_(BOOKING_BUTTONS))
async def handle_menu_booking(message: types.Message):
    """Экран записи на бесплатную 3D-диагностику и прием (0 секунд, без LLM)."""
    lang = await get_user_lang(message.from_user.id)
    text = BOOKING_PROMPT_TEMPLATES.get(lang, BOOKING_PROMPT_TEMPLATES["ru"])
    await message.answer(
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(lang),
    )


@dp.message(F.text.in_(OPERATOR_BUTTONS))
async def handle_menu_operator(message: types.Message):
    """Мгновенный вызов оператора клиники."""
    user = message.from_user
    lang = await get_user_lang(user.id)

    await db.set_operator_mode(user.id, True)

    user_label = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Пациент"
    await notifier.notify_operator_request(
        telegram_id=user.id,
        user_name=user_label,
        username=user.username,
        reason="Клик по кнопке 'Позвать администратора'",
        last_message="Клик по кнопке вызова оператора",
    )

    text = OPERATOR_MODE_TEMPLATES.get(lang, OPERATOR_MODE_TEMPLATES["ru"])
    await message.answer(text=text, parse_mode=ParseMode.HTML)


@dp.message(F.text.in_(CHANGE_LANG_BUTTONS))
async def handle_menu_change_language(message: types.Message):
    """Кнопка смены языка в главном меню."""
    await message.answer(
        text=LANGUAGE_SELECT_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=get_language_inline_keyboard(),
    )


# =========================================================================
# 3. ИНЛАЙН-НАВИГАЦИЯ ПО КАТАЛОГУ УСЛУГ
# =========================================================================

@dp.callback_query(F.data == "services_catalog")
async def handle_cb_services_catalog(callback: types.CallbackQuery):
    """Возврат в общий каталог услуг."""
    lang = await get_user_lang(callback.from_user.id)
    text = SERVICES_CATALOG_INTRO.get(lang, SERVICES_CATALOG_INTRO["ru"])
    try:
        await callback.message.edit_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_services_catalog_keyboard(lang),
        )
    except Exception:
        await callback.message.answer(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_services_catalog_keyboard(lang),
        )
    await callback.answer()


@dp.callback_query(F.data.startswith("svc:"))
async def handle_cb_service_detail(callback: types.CallbackQuery):
    """Мгновенный показ деталей конкретной услуги по инлайн-кнопке."""
    category = callback.data.split(":")[1]
    lang = await get_user_lang(callback.from_user.id)

    cat_dict = SERVICE_DETAILS.get(category, {})
    text = cat_dict.get(lang, cat_dict.get("ru", "Информация обновляется..."))

    try:
        await callback.message.edit_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_service_detail_keyboard(lang),
        )
    except Exception:
        await callback.message.answer(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_service_detail_keyboard(lang),
        )
    await callback.answer()


@dp.callback_query(F.data == "book_prompt")
async def handle_cb_book_prompt(callback: types.CallbackQuery):
    """Инлайн-кнопка перехода к записи на прием."""
    lang = await get_user_lang(callback.from_user.id)
    text = BOOKING_PROMPT_TEMPLATES.get(lang, BOOKING_PROMPT_TEMPLATES["ru"])
    await callback.message.answer(
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(lang),
    )
    await callback.answer()


# =========================================================================
# 4. ОБРАБОТКА ДРУГИХ СТАНДАРТНЫХ КОМАНД
# =========================================================================

@dp.message(Command("id", "myid", "chatid"))
async def handle_get_id(message: types.Message):
    """Показывает ID текущего чата или группы."""
    chat_type_str = "Личный диалог" if message.chat.type == "private" else f"Группа «{message.chat.title}»"
    text = (
        f"🆔 <b>Информация о чате:</b>\n\n"
        f"• <b>Тип:</b> {chat_type_str}\n"
        f"• <b>Chat ID:</b> <code>{message.chat.id}</code>\n\n"
        f"<i>Скопируйте это число в параметр <code>ADMIN_CHAT_ID</code> в файле <code>.env</code>!</i>"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(F.new_chat_members)
async def on_bot_added_to_group(message: types.Message):
    """Срабатывает при добавлении бота в группу администраторов."""
    for member in message.new_chat_members:
        if member.id == message.bot.id:
            text = (
                f"👋 <b>Бот успешно подключен к группе «{message.chat.title}»!</b>\n\n"
                f"🆔 <b>Точный Chat ID этой группы:</b> <code>{message.chat.id}</code>\n\n"
                "Чтобы карточки лидов приходили сюда, укажите в файле <code>.env</code>:\n"
                f"<code>ADMIN_CHAT_ID={message.chat.id}</code>"
            )
            await message.answer(text, parse_mode=ParseMode.HTML)


@dp.message(Command("help"))
async def handle_help(message: types.Message):
    """Справка по боту."""
    lang = await get_user_lang(message.from_user.id)
    help_texts = {
        "ru": (
            "💡 <b>Как пользоваться ботом DentaLux Tashkent:</b>\n\n"
            "• <b>Кнопки меню:</b> Мгновенный просмотр цен, врачей, адреса и акций.\n"
            "• <b>Живой AI-диалог:</b> Напишите любой произвольный вопрос (о боли, рассрочке, гарантиях) — AI ответит емко и по существу.\n"
            "• <b>Запись на 3D-снимок (0 сум):</b> Отправьте контакт или напишите имя и телефон.\n\n"
            "<b>Команды:</b>\n"
            "/start — Перезапуск меню\n"
            "/lang — Выбрать язык\n"
            "/reset — Очистить историю диалога\n"
            "/operator — Позвать живого администратора\n"
            "/bot — Вернуть AI-помощника"
        ),
        "uz": (
            "💡 <b>DentaLux boti bo'yicha qo'llanma:</b>\n\n"
            "• <b>Menyu tugmalari:</b> Narxlar, shifokorlar va manzilni tezkor ko'rish.\n"
            "• <b>AI muloqot:</b> Har qanday savolingizni yozing — AI darhol aniq javob beradi.\n"
            "• <b>Bepul 3D-rentgenga yozilish:</b> Kontakt yuboring yoki telefon raqamingizni qoldiring.\n\n"
            "<b>Buyruqlar:</b>\n"
            "/start — Menyuni ochish\n"
            "/lang — Tilni tanlash\n"
            "/reset — Muloqot tarixini tozalash\n"
            "/operator — Jonli administratorni chaqirish\n"
            "/bot — AI-yordamchini qaytarish"
        ),
        "en": (
            "💡 <b>DentaLux Bot Guide:</b>\n\n"
            "• <b>Menu buttons:</b> Instant access to prices, doctors, and location.\n"
            "• <b>AI Consultation:</b> Ask any question about treatments, pain-free anesthesia, or financing.\n"
            "• <b>Free 3D Scan Booking:</b> Share your phone number to reserve your appointment.\n\n"
            "<b>Commands:</b>\n"
            "/start — Main Menu\n"
            "/lang — Change Language\n"
            "/reset — Clear conversation\n"
            "/operator — Call live receptionist\n"
            "/bot — Resume AI assistant"
        ),
    }
    await message.answer(help_texts.get(lang, help_texts["ru"]), parse_mode=ParseMode.HTML)


@dp.message(Command("reset", "new"))
async def handle_reset(message: types.Message):
    """Очистка контекста диалога."""
    user = message.from_user
    if not user:
        return

    lang = await get_user_lang(user.id)
    await db.clear_chat_history(user.id)
    await db.set_operator_mode(user.id, False)

    reset_texts = {
        "ru": "🔄 <b>История диалога обновлена.</b> Чем я могу помочь Вам?",
        "uz": "🔄 <b>Muloqot yangilandi.</b> Sizga qanday yordam bera olaman?",
        "en": "🔄 <b>Conversation refreshed.</b> How can I help you today?",
    }
    await message.answer(
        reset_texts.get(lang, reset_texts["ru"]),
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(lang),
    )


@dp.message(Command("operator"))
async def handle_operator_command(message: types.Message):
    """Команда /operator."""
    await handle_menu_operator(message)


@dp.message(Command("bot", "resume_ai"))
async def handle_resume_bot(message: types.Message):
    """Возврат в режим AI-ассистента."""
    user = message.from_user
    if not user:
        return

    lang = await get_user_lang(user.id)
    await db.set_operator_mode(user.id, False)

    resume_texts = {
        "ru": "🤖 <b>AI-ассистент снова с Вами!</b> Задавайте любой вопрос.",
        "uz": "🤖 <b>AI-yordamchi yana faol!</b> Savolingizni yozishingiz mumkin.",
        "en": "🤖 <b>AI Assistant is back!</b> Feel free to ask any question.",
    }
    await message.answer(
        resume_texts.get(lang, resume_texts["ru"]),
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(lang),
    )


# =========================================================================
# 5. КОМАНДЫ АДМИНИСТРАТОРА И ОБРАБОТКА ИНЛАЙН-КНОПОК
# =========================================================================

@dp.message(Command("stats"))
async def handle_stats(message: types.Message):
    """Статистика лидов для руководства клиники."""
    if config.ADMIN_CHAT_ID and message.chat.id != config.ADMIN_CHAT_ID and message.from_user.id != config.ADMIN_CHAT_ID:
        return

    stats = await db.get_stats()
    stats_text = (
        "📊 <b>СТАТИСТИКА DENTALUX AI BOT:</b>\n\n"
        f"👥 Всего пользователей в базе: <b>{stats['total_users']}</b>\n"
        f"🔥 Всего заявок (лидов): <b>{stats['total_leads']}</b>\n"
        f"📅 Новых заявок за сегодня: <b>{stats['leads_today']}</b>\n\n"
        f"⏰ Время сервера: {get_tashkent_time_str()}"
    )
    await message.answer(stats_text, parse_mode=ParseMode.HTML)


@dp.callback_query(F.data.startswith("lead_processed:"))
async def handle_lead_processed(callback: types.CallbackQuery):
    """Администратор нажал 'Принято в работу'."""
    lead_id = int(callback.data.split(":")[1])
    admin_name = callback.from_user.username or callback.from_user.first_name

    await db.update_lead_status(lead_id, "contacted")

    original_text = callback.message.html_text if callback.message else ""
    time_str = get_tashkent_time_str()

    updated_text = (
        f"{original_text}\n\n"
        f"✅ <b>ВЗЯТО В РАБОТУ АДМИНИСТРАТОРОМ @{admin_name} в {time_str}</b>"
    )

    try:
        await callback.message.edit_text(
            text=updated_text,
            parse_mode=ParseMode.HTML,
            reply_markup=None,
        )
    except Exception as e:
        logger.warning(f"Could not edit message: {e}")

    await callback.answer("Статус заявки обновлен: Принято в работу!")


@dp.callback_query(F.data.startswith("resume_ai:"))
async def handle_admin_resume_ai(callback: types.CallbackQuery):
    """Администратор клиники возвращает пациенту AI-режим."""
    target_user_id = int(callback.data.split(":")[1])
    await db.set_operator_mode(target_user_id, False)

    user_lang = await get_user_lang(target_user_id)
    try:
        await callback.bot.send_message(
            chat_id=target_user_id,
            text=(
                "🤖 Диалог с администратором завершен. "
                "AI-консультант DentaLux снова к Вашим услугам! Чем могу помочь?"
            ),
            reply_markup=get_main_menu_keyboard(user_lang),
        )
    except Exception as e:
        logger.warning(f"Could not notify user {target_user_id}: {e}")

    await callback.answer("AI-режим возвращен пациенту.")
    if callback.message:
        await callback.message.reply("✅ AI-режим для пациента успешно восстановлен.")


# =========================================================================
# 5.5. ОБРАБОТКА ИНЛАЙН-КНОПОК НАПОМИНАНИЙ (Приду / Перенести / Отменить)
# =========================================================================

@dp.callback_query(F.data.startswith("confirm_visit:"))
async def handle_confirm_visit(callback: types.CallbackQuery):
    """Пациент нажал '🟢 Приду' в сообщении-напоминании."""
    app_id = callback.data.split(":")[1]
    await db.update_appointment_status(app_id, "confirmed")
    app = await db.get_appointment(app_id)
    lang = await get_user_lang(callback.from_user.id)

    texts = {
        "ru": (
            "✅ <b>Спасибо! Ваш визит подтверждён.</b>\n\n"
            "Мы закрепили за вами кабинет и врача. Ждём вас в клинике DentaLux!\n"
            "📍 г. Ташкент, ул. Шота Руставели, 54 (метро Ойбек)"
        ),
        "uz": (
            "✅ <b>Rahmat! Qabulingiz tasdiqlandi.</b>\n\n"
            "Siz uchun shifokor va xona band qilindi. DentaLux klinikasida kutamiz!\n"
            "📍 Toshkent sh., Shota Rustaveli ko‘chasi, 54 (Oybek metrosi)"
        ),
        "en": (
            "✅ <b>Thank you! Your appointment is confirmed.</b>\n\n"
            "We have reserved the room and doctor for you. See you at DentaLux!\n"
            "📍 54 Shota Rustaveli st., Tashkent (Oybek metro)"
        ),
    }

    try:
        await callback.message.edit_text(
            text=texts.get(lang, texts["ru"]),
            parse_mode=ParseMode.HTML,
            reply_markup=None,
        )
    except Exception as e:
        logger.warning(f"Could not edit confirmation message: {e}")

    await callback.answer("Визит успешно подтверждён! Ждём вас.")

    # Оповещаем администратора
    if config.ADMIN_CHAT_ID:
        client_name = app.get("client_name") if app else callback.from_user.first_name
        phone = app.get("phone") if app else "—"
        doctor = app.get("doctor") if app else "—"
        date_time = app.get("date_time") if app else "—"
        admin_alert = (
            f"✅ <b>ПАЦИЕНТ ПОДТВЕРДИЛ ВИЗИТ:</b>\n\n"
            f"👤 <b>Пациент:</b> {client_name}\n"
            f"📞 <b>Телефон:</b> <code>{phone}</code>\n"
            f"👨‍⚕️ <b>Врач:</b> {doctor}\n"
            f"📅 <b>Время:</b> {date_time}\n"
            f"Статус обновлён на: <b>Confirmed</b>"
        )
        try:
            await callback.bot.send_message(
                chat_id=config.ADMIN_CHAT_ID,
                text=admin_alert,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.error(f"Failed to alert admin on confirm: {e}")


@dp.callback_query(F.data.startswith("reschedule_visit:"))
async def handle_reschedule_visit(callback: types.CallbackQuery):
    """Пациент нажал '🔄 Перенести'."""
    app_id = callback.data.split(":")[1]
    await db.update_appointment_status(app_id, "reschedule_requested")
    app = await db.get_appointment(app_id)
    lang = await get_user_lang(callback.from_user.id)

    texts = {
        "ru": (
            "🔄 <b>Запрос на перенос записи принят!</b>\n\n"
            "Наш администратор перезвонит вам в течение 10–15 минут, чтобы предложить удобные свободные слоты.\n"
            "Также вы можете открыть Mini App и выбрать новое время самостоятельно."
        ),
        "uz": (
            "🔄 <b>Qabulni ko‘chirish so‘rovingiz qabul qilindi!</b>\n\n"
            "Qulay bo‘sh vaqtlarni taklif qilish uchun administratorimiz 10–15 daqiqa ichida siz bilan bog‘lanadi."
        ),
        "en": (
            "🔄 <b>Reschedule request received!</b>\n\n"
            "Our administrator will call you within 10–15 minutes to arrange a new convenient time slot."
        ),
    }

    try:
        await callback.message.edit_text(
            text=texts.get(lang, texts["ru"]),
            parse_mode=ParseMode.HTML,
            reply_markup=None,
        )
    except Exception as e:
        logger.warning(f"Could not edit reschedule message: {e}")

    await callback.answer("Запрос на перенос отправлен.")

    if config.ADMIN_CHAT_ID:
        client_name = app.get("client_name") if app else callback.from_user.first_name
        phone = app.get("phone") if app else "—"
        doctor = app.get("doctor") if app else "—"
        date_time = app.get("date_time") if app else "—"
        admin_alert = (
            f"🔄 <b>ПАЦИЕНТ ПРОСИТ ПЕРЕНЕСТИ ВИЗИТ:</b>\n\n"
            f"👤 <b>Пациент:</b> {client_name}\n"
            f"📞 <b>Телефон:</b> <code>{phone}</code>\n"
            f"👨‍⚕️ <b>Врач:</b> {doctor}\n"
            f"📅 <b>Исходное время:</b> {date_time}\n"
            f"Пожалуйста, свяжитесь с пациентом для согласования новой даты."
        )
        try:
            await callback.bot.send_message(
                chat_id=config.ADMIN_CHAT_ID,
                text=admin_alert,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.error(f"Failed to alert admin on reschedule: {e}")


@dp.callback_query(F.data.startswith("cancel_visit:"))
async def handle_cancel_visit(callback: types.CallbackQuery):
    """Пациент нажал '❌ Отменить запись'."""
    app_id = callback.data.split(":")[1]
    await db.update_appointment_status(app_id, "cancelled")
    app = await db.get_appointment(app_id)
    lang = await get_user_lang(callback.from_user.id)
    if app:
        # Освободившийся слот сразу предлагаем людям из листа ожидания
        await notify_waitlist(callback.bot, app.get("date_time", ""), app.get("doctor", ""))

    texts = {
        "ru": (
            "❌ <b>Ваша запись отменена. Слот освобождён.</b>\n\n"
            "Если вам снова понадобится консультация или лечение, вы всегда можете записаться через меню или наш Mini App!"
        ),
        "uz": (
            "❌ <b>Qabulingiz bekor qilindi. Vaqt boshqalar uchun ochildi.</b>\n\n"
            "Zarur bo‘lganda istalgan vaqtda Mini App orqali qayta yozilishingiz mumkin!"
        ),
        "en": (
            "❌ <b>Your appointment has been cancelled. The slot has been freed.</b>\n\n"
            "You are welcome to book again anytime via our Mini App!"
        ),
    }

    try:
        await callback.message.edit_text(
            text=texts.get(lang, texts["ru"]),
            parse_mode=ParseMode.HTML,
            reply_markup=None,
        )
    except Exception as e:
        logger.warning(f"Could not edit cancel message: {e}")

    await callback.answer("Запись отменена.")

    if config.ADMIN_CHAT_ID:
        client_name = app.get("client_name") if app else callback.from_user.first_name
        phone = app.get("phone") if app else "—"
        doctor = app.get("doctor") if app else "—"
        date_time = app.get("date_time") if app else "—"
        admin_alert = (
            f"❌ <b>ПАЦИЕНТ ОТМЕНИЛ ЗАПИСЬ:</b>\n\n"
            f"👤 <b>Пациент:</b> {client_name}\n"
            f"📞 <b>Телефон:</b> <code>{phone}</code>\n"
            f"👨‍⚕️ <b>Врач:</b> {doctor}\n"
            f"📅 <b>Время:</b> {date_time}\n"
            f"<b>Слот освобождён и доступен для других пациентов.</b>"
        )
        try:
            await callback.bot.send_message(
                chat_id=config.ADMIN_CHAT_ID,
                text=admin_alert,
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.error(f"Failed to alert admin on cancel: {e}")


# =========================================================================
# 5.6. КОМАНДЫ ДЛЯ ОТЧЁТА ВЛАДЕЛЬЦУ (/digest) И УДАЛЕНИЯ ДАННЫХ (/delete_my_data)
# =========================================================================

@dp.message(Command("digest"))
async def handle_digest_command(message: types.Message):
    """Команда /digest для мгновенной генерации отчёта владельцу клиники (демо-сценарий)."""
    # Цифры считаются из базы: раньше здесь были захардкоженные проценты
    time_str = get_tashkent_time_str()
    digest_text = await build_digest_text(7, "📊 <b>НЕДЕЛЬНЫЙ ДАЙДЖЕСТ КЛИНИКИ DENTALUX</b>")
    digest_text += f"\n\n<i>Сформировано: {time_str} (Asia/Tashkent)</i>"
    await message.answer(digest_text, parse_mode=ParseMode.HTML)


@dp.message(Command("waitlist"))
async def handle_waitlist_command(message: types.Message):
    """/waitlist YYYY-MM-DD: сообщить, когда освободится окно на дату."""
    parts = (message.text or "").split()
    if len(parts) < 2 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[1]):
        await message.answer("Укажите дату в формате: /waitlist 2026-11-06")
        return
    await db.add_waitlist(message.from_user.id, parts[1])
    await message.answer(f"🔔 Готово. Сообщим, если освободится окно на {parts[1]}.")


@dp.message(Command("delete_my_data"))
async def handle_delete_my_data(message: types.Message):
    """Пациент запрашивает удаление персональных данных по закону о защите ПДн Узбекистана."""
    user = message.from_user
    if not user:
        return

    await db.anonymize_user_data(user.id)

    lang = await get_user_lang(user.id)
    confirm_text = {
        "ru": (
            "🔒 <b>Ваши персональные данные успешно удалены.</b>\n\n"
            "Ваше имя и номер телефона были стёрты из базы данных клиники в соответствии с требованиями закона о защите персональных данных."
        ),
        "uz": (
            "🔒 <b>Shaxsiy ma’lumotlaringiz muvaffaqiyatli o‘chirildi.</b>\n\n"
            "O‘zbekiston Respublikasining shaxsiy ma’lumotlar to‘g‘risidagi qonuniga muvofiq ismingiz va telefon raqamingiz bazadan o‘chirildi."
        ),
        "en": (
            "🔒 <b>Your personal data has been erased.</b>\n\n"
            "Your name and phone number have been anonymized in our systems in accordance with personal data protection regulations."
        ),
    }
    await message.answer(confirm_text.get(lang, confirm_text["ru"]), parse_mode=ParseMode.HTML)


# =========================================================================
# 6. ОБРАБОТКА НАЖАТИЯ «ОТПРАВИТЬ МОЙ ТЕЛЕФОН» (F.contact)
# =========================================================================

@dp.message(F.contact)
async def handle_contact_sharing(message: types.Message):
    """Пользователь поделился контактом через нативную кнопку Telegram."""
    contact = message.contact
    user = message.from_user
    if not contact or not user:
        return

    lang = await get_user_lang(user.id)
    phone = contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone

    client_name = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or (user.first_name or "Пациент")

    # Сохраняем заявку в PostgreSQL
    lead_id = await db.save_lead(
        telegram_id=user.id,
        client_name=client_name,
        phone=phone,
        service="Консультация главного врача + 3D-снимок (АКЦИЯ)",
        preferred_time="Ближайшее свободное время",
        summary="Пациент нажал нативную кнопку отправки контакта в Telegram.",
        language=lang,
    )

    # Отправляем карточку лида администраторам
    await notifier.notify_new_lead(
        lead_id=lead_id,
        telegram_id=user.id,
        client_name=client_name,
        phone=phone,
        service="Консультация главного врача + 3D-снимок (АКЦИЯ)",
        preferred_time="Уточняется при подтверждении",
        summary="Быстрая заявка по кнопке контакта.",
        language=lang,
        username=user.username,
    )

    # Записываем в Google Таблицу (фоновая задача)
    asyncio.create_task(
        sheets_service.append_lead(
            lead_id=lead_id,
            telegram_id=user.id,
            client_name=client_name,
            phone=phone,
            service="Консультация + 3D-снимок",
            preferred_time="Ближайшее время",
            summary="Быстрая отправка контакта",
            language=lang,
            username=user.username,
        )
    )

    confirmations = {
        "ru": (
            f"Рахмат, {client_name}! 🙏\n\n"
            "✅ <b>Ваша заявка передана старшему администратору клиники DentaLux.</b>\n"
            "Мы забронировали за Вами бесплатную первичную консультацию и 3D-снимок. "
            "Перезвоним для подтверждения времени в течение 10 минут (в рабочее время)!"
        ),
        "uz": (
            f"Rahmat, {client_name}! 🙏\n\n"
            "✅ <b>Arizangiz DentaLux katta administratoriga topshirildi.</b>\n"
            "Siz uchun bepul ko'rik va 3D-tomografiya band qilindi. "
            "10 daqiqa ichida vaqtni tasdiqlash uchun qo'ng'iroq qilamiz!"
        ),
        "en": (
            f"Thank you, {client_name}! 🙏\n\n"
            "✅ <b>Your request has been received by our receptionist.</b>\n"
            "Your free exam and 3D scan are reserved. We will call you within 10 minutes to confirm your appointment!"
        ),
    }

    await message.answer(
        text=confirmations.get(lang, confirmations["ru"]),
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard(lang),
    )


# =========================================================================
# 7. ПРОИЗВОЛЬНЫЙ ТЕКСТОВЫЙ ДИАЛОГ С DEEPSEEK (AI ЯДРО)
# =========================================================================

# Совокупность всех кнопок меню, чтобы бот не передавал их в LLM
ALL_KNOWN_MENU_TEXTS = SERVICES_BUTTONS | CONTACTS_BUTTONS | ABOUT_BUTTONS | BOOKING_BUTTONS | OPERATOR_BUTTONS | CHANGE_LANG_BUTTONS


@dp.message(F.text)
async def handle_user_arbitrary_text(message: types.Message):
    """
    Обработка произвольных вопросов пользователя с помощью DeepSeek API.
    Вызывается ТОЛЬКО когда пользователь пишет вопрос от руки, а не нажимает кнопки меню.
    Включает непрерывный typing-индикатор и лимит токенов 250 для максимальной скорости.
    """
    user = message.from_user
    if not user:
        return

    text = message.text.strip()

    # Если текст совпадает с какой-то кнопкой меню, пропускаем (уже обработано выше)
    if text in ALL_KNOWN_MENU_TEXTS:
        return

    lang = await get_user_lang(user.id)

    # Проверяем режим ожидания живого оператора
    is_in_operator_mode = await db.is_operator_mode(user.id)
    if is_in_operator_mode:
        if config.ADMIN_CHAT_ID:
            user_label = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Пациент"
            username_part = f"(@{user.username})" if user.username else ""
            forward_msg = (
                f"📩 <b>Сообщение от пациента в режиме оператора:</b>\n"
                f"👤 {user_label} {username_part} [ID: <code>{user.id}</code>]\n\n"
                f"<blockquote>«{text}»</blockquote>"
            )
            await notifier.bot.send_message(
                chat_id=config.ADMIN_CHAT_ID,
                text=forward_msg,
                parse_mode=ParseMode.HTML,
            )

        wait_texts = {
            "ru": "⏳ Ваше сообщение передано администратору. Мы ответим Вам в ближайшее время!\n<i>(Для возврата к AI нажмите /bot)</i>",
            "uz": "⏳ Xabaringiz administratorga yuborildi. Tez orada javob beramiz!\n<i>(AI-ga qaytish uchun /bot bosing)</i>",
            "en": "⏳ Your message has been forwarded to the receptionist. We will reply shortly!\n<i>(Type /bot to return to AI)</i>",
        }
        await message.answer(wait_texts.get(lang, wait_texts["ru"]), parse_mode=ParseMode.HTML)
        return

    # Запускаем фоновую непрерывную отправку статуса "печатает..." (typing)
    typing_task = asyncio.create_task(keep_typing(message.bot, message.chat.id))

    try:
        user_info = {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
        }

        # Отправляем сообщение в DeepSeek через оптимизированный сервис
        ai_res = await ai_service.process_user_message(
            telegram_id=user.id,
            user_message=text,
            user_info=user_info,
            forced_language=lang,
        )

        # 1. Если модель вызвала функцию регистрации лида
        if ai_res.is_lead and ai_res.lead_data:
            ld = ai_res.lead_data
            client_name = ld.get("client_name") or user.first_name or "Пациент"
            phone = ld.get("phone", "")
            service = ld.get("service", "Консультация")
            preferred_time = ld.get("preferred_time", "Уточняется")
            summary = ld.get("summary", "Запись на прием")
            lead_lang = ld.get("language", lang)

            lead_id = await db.save_lead(
                telegram_id=user.id,
                client_name=client_name,
                phone=phone,
                service=service,
                preferred_time=preferred_time,
                summary=summary,
                language=lead_lang,
            )

            await notifier.notify_new_lead(
                lead_id=lead_id,
                telegram_id=user.id,
                client_name=client_name,
                phone=phone,
                service=service,
                preferred_time=preferred_time,
                summary=summary,
                language=lead_lang,
                username=user.username,
            )

            asyncio.create_task(
                sheets_service.append_lead(
                    lead_id=lead_id,
                    telegram_id=user.id,
                    client_name=client_name,
                    phone=phone,
                    service=service,
                    preferred_time=preferred_time,
                    summary=summary,
                    language=lead_lang,
                    username=user.username,
                )
            )

        # 2. Если модель вызвала вызов оператора
        if ai_res.is_operator_request:
            await db.set_operator_mode(user.id, True)
            user_label = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Пациент"
            await notifier.notify_operator_request(
                telegram_id=user.id,
                user_name=user_label,
                username=user.username,
                reason=ai_res.operator_reason,
                last_message=text,
            )

        # 3. Отправляем лаконичный ответ пациенту
        if ai_res.text:
            await message.answer(
                text=ai_res.text,
                parse_mode=ParseMode.HTML,
                reply_markup=get_main_menu_keyboard(lang),
            )

    finally:
        # Останавливаем индикатор набора текста
        typing_task.cancel()


# =========================================================================
# 7.5. ОБРАБОТКА ДАННЫХ ИЗ TELEGRAM MINI APP
# =========================================================================

@dp.message(F.web_app_data)
async def handle_web_app_data(message: types.Message):
    """
    Обработка данных онлайн-записи из Telegram Mini App (DentaLux Showcase).
    """
    user = message.from_user
    data_raw = message.web_app_data.data if message.web_app_data else "{}"
    lang = await get_user_lang(user.id if user else 0)
    
    logger.info(f"Получены данные из Mini App от {user.id if user else '?'}: {data_raw}")
    
    try:
        data = json.loads(data_raw)
        name = data.get("name") or (f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "Пациент")
        phone = data.get("phone") or "Не указан"
        service = data.get("service") or "Консультация"
        doctor = data.get("doctor") or "Любой специалист"
        date = data.get("date") or "Ближайшее время"
        time = data.get("time") or ""
        preferred_time = f"{date} {time}".strip()
        summary = f"Запись через Mini App. Врач: {doctor}"
        
        # 1. Сохраняем лид в общую базу
        lead_id = await db.save_lead(
            telegram_id=user.id if user else 0,
            client_name=name,
            phone=phone,
            service=service,
            preferred_time=preferred_time,
            summary=summary,
            language=lang,
        )

        # Запись в клинику создаёт Mini App (API пишет её в общую базу вместе с напоминаниями).
        # Здесь создавать запись нельзя: иначе появится дубль, а напоминания будут без реального времени визита.
        
        # Карточку для группы администраторов отправляет сам API Mini App (чтобы не было дублей).
        
        # 3. Синхронизируем с Google Sheets
        await sheets_service.append_lead(
            lead_id=lead_id,
            time_str=get_tashkent_time_str(),
            name=name,
            phone=phone,
            service=service,
            preferred_time=preferred_time,
            summary=summary,
            language=lang,
            username=user.username if user else None,
        )
        
        # 4. Отправляем подтверждение пациенту
        confirm_text = {
            "ru": (
                "🎉 <b>Ваша запись через Mini App успешно принята!</b>\n\n"
                f"👤 <b>Имя:</b> {name}\n"
                f"📞 <b>Телефон:</b> <code>{phone}</code>\n"
                f"🦷 <b>Услуга:</b> {service}\n"
                f"👨‍⚕️ <b>Врач:</b> {doctor}\n"
                f"📅 <b>Желаемое время:</b> {preferred_time}\n\n"
                "📞 Наш администратор перезвонит вам в течение 10–15 минут для подтверждения бронирования кабинета."
            ),
            "uz": (
                "🎉 <b>Mini App orqali arizangiz qabul qilindi!</b>\n\n"
                f"👤 <b>Ism:</b> {name}\n"
                f"📞 <b>Telefon:</b> <code>{phone}</code>\n"
                f"🦷 <b>Xizmat:</b> {service}\n"
                f"👨‍⚕️ <b>Shifokor:</b> {doctor}\n"
                f"📅 <b>Vaqt:</b> {preferred_time}\n\n"
                "📞 Qabul vaqtini tasdiqlash uchun administratorimiz 10–15 daqiqa ichida siz bilan bog'lanadi."
            ),
            "en": (
                "🎉 <b>Your booking via Mini App has been received!</b>\n\n"
                f"👤 <b>Name:</b> {name}\n"
                f"📞 <b>Phone:</b> <code>{phone}</code>\n"
                f"🦷 <b>Service:</b> {service}\n"
                f"👨‍⚕️ <b>Doctor:</b> {doctor}\n"
                f"📅 <b>Preferred time:</b> {preferred_time}\n\n"
                "📞 Our administrator will call you within 10–15 minutes to confirm the appointment."
            ),
        }
        await message.answer(
            text=confirm_text.get(lang, confirm_text["ru"]),
            parse_mode=ParseMode.HTML,
            reply_markup=get_main_menu_keyboard(lang),
        )

        # Адрес и памятка, затем файл для календаря
        await message.answer(visit_instructions(lang), parse_mode=ParseMode.HTML)
        ics_payload = build_ics(service, doctor, preferred_time)
        if ics_payload:
            await message.answer_document(
                BufferedInputFile(ics_payload, filename="DentaLux_visit.ics"),
                caption="📅 Добавьте визит в календарь",
            )
    except Exception as e:
        logger.error(f"Ошибка при обработке WebApp данных: {e}", exc_info=True)
        await message.answer(
            "✅ Ваша заявка успешно получена! Администратор свяжется с вами в ближайшее время.",
            reply_markup=get_main_menu_keyboard(lang),
        )


# =========================================================================
# 8. ТОЧКА ВХОДА И ЗАПУСК БОТА
# =========================================================================

async def main():
    """Инициализация базы данных и запуск polling."""
    validation_errors = config.validate()
    if validation_errors:
        for err in validation_errors:
            logger.warning(f"Конфигурация: {err}")

    if not config.BOT_TOKEN:
        logger.critical("BOT_TOKEN не указан в .env!")
        return

    # Инициализация базы данных
    await db.init_db()
    logger.info("База данных PostgreSQL подключена (общая с Mini App)")

    bot = Bot(token=config.BOT_TOKEN)
    notifier.set_bot(bot)

    # Запуск фонового воркера напоминаний (Persistent Reminder Engine)
    reminder_engine.start_worker(bot)
    growth_worker.start(bot)
    outbox_worker.start(bot)

    # Уведомление администраторов о запуске (сигнал, что бот поднялся после деплоя или сбоя)
    if config.ADMIN_CHAT_ID:
        try:
            await bot.send_message(config.ADMIN_CHAT_ID, "✅ Бот DentaLux запущен и принимает обращения.")
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление о запуске: {e}")

    # Настройка кнопки Web App в меню чата (слева от поля ввода)
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="✨ Mini App",
                web_app=WebAppInfo(url=MINIAPP_URL),
            )
        )
        logger.info(f"MenuButtonWebApp настроена на {MINIAPP_URL}")
    except Exception as e:
        logger.warning(f"Не удалось установить MenuButtonWebApp: {e}")

    # Пропуск накопившихся апдейтов перед стартом
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот DentaLux Tashkent (v2 Hybrid) успешно запущен и слушает события...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Сессия бота закрыта.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен пользователем.")
