"""
Модуль клавиатур Telegram-бота DentaLux Tashkent.
Включает инлайн-клавиатуры выбора языка, категорий услуг и главное Reply-меню на 3 языках.
"""

from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
)

MINIAPP_URL = "https://dentalminiapp.vercel.app"

# 1. Инлайн-клавиатура первичного выбора языка
def get_language_inline_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang:ru"),
            InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="set_lang:uz"),
        ],
        [
            InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang:en"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# Тексты кнопок главного меню на 3 языках
MENU_BUTTON_TEXTS = {
    "ru": {
        "miniapp": "✨ Каталог Mini App",
        "booking": "📅 Записаться на консультацию",
        "services": "🦷 Услуги и цены",
        "contacts": "📍 Адрес и контакты",
        "about": "⭐️ О клинике и врачах",
        "operator": "📞 Позвать администратора",
        "lang": "🌐 Сменить язык",
        "contact_phone": "📱 Отправить мой телефон",
    },
    "uz": {
        "miniapp": "✨ Mini App katalogi",
        "booking": "📅 Qabulga yozilish",
        "services": "🦷 Xizmatlar va narxlar",
        "contacts": "📍 Manzil va aloqa",
        "about": "⭐️ Klinika haqida",
        "operator": "📞 Operator bilan bog'lanish",
        "lang": "🌐 Tilni o'zgartirish",
        "contact_phone": "📱 Telefon raqamimni yuborish",
    },
    "en": {
        "miniapp": "✨ Mini App Showcase",
        "booking": "📅 Book an Appointment",
        "services": "🦷 Services & Prices",
        "contacts": "📍 Address & Contacts",
        "about": "⭐️ About Clinic & Doctors",
        "operator": "📞 Call Operator",
        "lang": "🌐 Change Language",
        "contact_phone": "📱 Share My Phone Number",
    },
}


# 2. Постоянное Главное Меню (Reply Keyboard)
def get_main_menu_keyboard(lang: str = "ru") -> ReplyKeyboardMarkup:
    t = MENU_BUTTON_TEXTS.get(lang, MENU_BUTTON_TEXTS["ru"])
    kb = [
        [
            KeyboardButton(text=t["miniapp"], web_app=WebAppInfo(url=MINIAPP_URL)),
            KeyboardButton(text=t["booking"]),
        ],
        [
            KeyboardButton(text=t["services"]),
            KeyboardButton(text=t["contacts"]),
        ],
        [
            KeyboardButton(text=t["about"]),
            KeyboardButton(text=t["operator"]),
        ],
        [
            KeyboardButton(text=t["lang"]),
            KeyboardButton(text=t["contact_phone"], request_contact=True),
        ],
    ]
    return ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Напишите вопрос или выберите раздел...",
    )


# 3. Инлайн-каталог категорий услуг
def get_services_catalog_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    labels = {
        "ru": {
            "miniapp": "✨ Открыть интерактивную витрину (Mini App)",
            "brackets": "🦷 Брекеты Damon (США)",
            "aligners": "✨ Элайнеры (невидимые капы)",
            "implants": "🔩 Имплантация Osstem / Straumann",
            "veneers": "💎 Керамические виниры E.max",
            "whitening": "🌟 Отбеливание Beyond / Zoom",
            "therapy": "🩺 Лечение кариеса и гигиена",
            "pediatric": "🧸 Детская стоматология",
            "book": "📅 Записаться на бесплатный осмотр",
        },
        "uz": {
            "miniapp": "✨ Interaktiv vitrina (Mini App)",
            "brackets": "🦷 Damon breketlari (AQSh)",
            "aligners": "✨ Elaynerlar (shaffof kapalar)",
            "implants": "🔩 Osstem / Straumann implantlari",
            "veneers": "💎 E.max keramika vinirlari",
            "whitening": "🌟 Beyond / Zoom tish oqartirish",
            "therapy": "🩺 Karies davolash va tozalash",
            "pediatric": "🧸 Bolalar stomatologiyasi",
            "book": "📅 Bepul ko'rikka yozilish",
        },
        "en": {
            "miniapp": "✨ Open Interactive Showcase (Mini App)",
            "brackets": "🦷 Damon Braces (USA)",
            "aligners": "✨ Clear Aligners",
            "implants": "🔩 Osstem / Straumann Implants",
            "veneers": "💎 E.max Ceramic Veneers",
            "whitening": "🌟 Teeth Whitening Beyond/Zoom",
            "therapy": "🩺 Therapy & Cleaning",
            "pediatric": "🧸 Pediatric Dentistry",
            "book": "📅 Book Free Initial Exam",
        },
    }
    lbl = labels.get(lang, labels["ru"])
    buttons = [
        [
            InlineKeyboardButton(text=lbl["miniapp"], web_app=WebAppInfo(url=MINIAPP_URL)),
        ],
        [
            InlineKeyboardButton(text=lbl["brackets"], callback_data="svc:brackets"),
        ],
        [
            InlineKeyboardButton(text=lbl["aligners"], callback_data="svc:aligners"),
        ],
        [
            InlineKeyboardButton(text=lbl["implants"], callback_data="svc:implants"),
        ],
        [
            InlineKeyboardButton(text=lbl["veneers"], callback_data="svc:veneers"),
        ],
        [
            InlineKeyboardButton(text=lbl["whitening"], callback_data="svc:whitening"),
        ],
        [
            InlineKeyboardButton(text=lbl["therapy"], callback_data="svc:therapy"),
            InlineKeyboardButton(text=lbl["pediatric"], callback_data="svc:pediatric"),
        ],
        [
            InlineKeyboardButton(text=lbl["book"], callback_data="book_prompt"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# 4. Инлайн-кнопки под конкретной услугой
def get_service_detail_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    labels = {
        "ru": {
            "book": "📅 Записаться на эту процедуру",
            "back": "◀️ Назад ко всем услугам",
        },
        "uz": {
            "book": "📅 Ushbu muolajaga yozilish",
            "back": "◀️ Barcha xizmatlarga qaytish",
        },
        "en": {
            "book": "📅 Book this treatment",
            "back": "◀️ Back to all services",
        },
    }
    lbl = labels.get(lang, labels["ru"])
    buttons = [
        [
            InlineKeyboardButton(text=lbl["book"], callback_data="book_prompt"),
        ],
        [
            InlineKeyboardButton(text=lbl["back"], callback_data="services_catalog"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# 5. Инлайн-кнопки для контактов и локации
def get_contacts_inline_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    labels = {
        "ru": {
            "maps": "🗺 Открыть на Яндекс.Картах",
            "book": "📅 Записаться на консультацию",
        },
        "uz": {
            "maps": "🗺 Yandex Kartada ochish",
            "book": "📅 Qabulga yozilish",
        },
        "en": {
            "maps": "🗺 Open in Yandex Maps",
            "book": "📅 Book an Appointment",
        },
    }
    lbl = labels.get(lang, labels["ru"])
    buttons = [
        [
            InlineKeyboardButton(
                text=lbl["maps"],
                url="https://yandex.uz/maps/-/CDuWjF8A"
            ),
        ],
        [
            InlineKeyboardButton(text=lbl["book"], callback_data="book_prompt"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
