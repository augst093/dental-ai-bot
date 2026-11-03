"""
Модуль статичных шаблонов сообщений (Telegram HTML).
Обеспечивает мгновенный отклик (0 секунд) на 3 языках: RU, UZ, EN.
Строгая типографика уровня премиальных частных клиник.
"""

from typing import Dict, Any

# Экран выбора языка при старте / переключении
LANGUAGE_SELECT_TEXT = (
    "✨ <b>DentaLux Tashkent</b> 🦷\n"
    "<i>Премиальная цифровая стоматология у метро Ойбек</i>\n\n"
    "🌐 <b>Пожалуйста, выберите удобный язык общения:</b>\n"
    "🌐 <b>Iltimos, qulay muloqot tilini tanlang:</b>\n"
    "🌐 <b>Please select your preferred language:</b>"
)

# Приветствие в Главном Меню
GREETING_TEMPLATES: Dict[str, str] = {
    "ru": (
        "<b>Здравствуйте, {name}!</b> 👋\n\n"
        "Добро пожаловать в цифровую стоматологию <b>DentaLux Tashkent</b>.\n\n"
        "<blockquote>🎁 <b>Специальное предложение месяца:</b>\n"
        "При записи через Telegram-бот — первичная консультация главного врача и компьютерная 3D-томография (КТ) — <b>БЕСПЛАТНО</b> (вместо 350 000 сум)!</blockquote>\n\n"
        "<i>Используйте кнопки меню внизу для быстрого перехода, либо просто напишите свой вопрос в чат — наш AI-консультант ответит мгновенно.</i>"
    ),
    "uz": (
        "<b>Assalomu alaykum, {name}!</b> 👋\n\n"
        "<b>DentaLux Tashkent</b> raqamli stomatologiyasiga xush kelibsiz.\n\n"
        "<blockquote>🎁 <b>Oyning maxsus aksiyasi:</b>\n"
        "Telegram-bot orqali yozilganda — bosh shifokor ko'rigi va 3D-kompyuter tomografiyasi (KT) rentgen — <b>MUTLAQO BEPUL</b> (350 000 so'm o'rniga)!</blockquote>\n\n"
        "<i>Quyidagi tugmalar orqali kerakli bo'limni tanlang yoki savolingizni to'g'ridan-to'g'ri yozing — AI-yordamchimiz darhol javob beradi.</i>"
    ),
    "en": (
        "<b>Hello, {name}!</b> 👋\n\n"
        "Welcome to <b>DentaLux Tashkent</b> premium digital dental clinic.\n\n"
        "<blockquote>🎁 <b>Special Offer of the Month:</b>\n"
        "Book via Telegram and receive a Chief Medical Officer consultation and 3D CT scan for <b>FREE</b> (regular price 350,000 UZS)!</blockquote>\n\n"
        "<i>Use the menu buttons below or simply type your question — our AI assistant will answer right away.</i>"
    ),
}

# Адрес и контакты
CONTACTS_TEMPLATES: Dict[str, str] = {
    "ru": (
        "📍 <b>Адрес и контактная информация:</b>\n\n"
        "🏢 <b>Клиника DentaLux Tashkent:</b>\n"
        "г. Ташкент, Мирабадский район, ул. Афросиёб, 12Б\n\n"
        "🚇 <b>Ориентиры:</b>\n"
        "• Метро «Ойбек» (300 метров пешком)\n"
        "• Напротив гостиницы «Grand Mir Hotel»\n"
        "• Рядом с посольством РФ\n\n"
        "⏱ <b>График работы:</b>\n"
        "• Понедельник – Суббота: 09:00 – 20:00\n"
        "• Воскресенье: выходной (дежурный врач по острой боли)\n\n"
        "📞 <b>Телефоны регистратуры:</b>\n"
        "• +998 71 200 44 88\n"
        "• +998 90 999 44 88\n\n"
        "<blockquote>🚗 <b>Парковка:</b>\n"
        "Для пациентов клиники предусмотрена собственная бесплатная охраняемая автостоянка.</blockquote>"
    ),
    "uz": (
        "📍 <b>Manzil va aloqa ma'lumotlari:</b>\n\n"
        "🏢 <b>DentaLux Tashkent klinikasi:</b>\n"
        "Toshkent shahri, Mirobod tumani, Afrosiyob ko'chasi, 12B\n\n"
        "🚇 <b>Mo'ljallar:</b>\n"
        "• «Oybek» metro bekati (300 metr)\n"
        "• «Grand Mir Hotel» mehmonxonasi ro'parasi\n"
        "• Rossiya Federatsiyasi elchixonasi yonida\n\n"
        "⏱ <b>Ish vaqti:</b>\n"
        "• Dushanba – Shanba: 09:00 – 20:00\n"
        "• Yakshanba: dam olish kuni (og'ir og'riqlar uchun navbatchi shifokor)\n\n"
        "📞 <b>Telefonlar:</b>\n"
        "• +998 71 200 44 88\n"
        "• +998 90 999 44 88\n\n"
        "<blockquote>🚗 <b>Avtoturargoh:</b>\n"
        "Klinika bemorlari uchun shaxsiy bepul va qo'riqlanadigan avtoturargoh mavjud.</blockquote>"
    ),
    "en": (
        "📍 <b>Address & Contact Details:</b>\n\n"
        "🏢 <b>DentaLux Tashkent Clinic:</b>\n"
        "12B Afrosiyob Street, Mirabad District, Tashkent\n\n"
        "🚇 <b>Landmarks:</b>\n"
        "• Metro station 'Oybek' (300 meters walk)\n"
        "• Opposite to Grand Mir Hotel\n"
        "• Near the Embassy of the Russian Federation\n\n"
        "⏱ <b>Working Hours:</b>\n"
        "• Monday – Saturday: 09:00 – 20:00\n"
        "• Sunday: Closed (Emergency doctor on duty)\n\n"
        "📞 <b>Reception Desk:</b>\n"
        "• +998 71 200 44 88\n"
        "• +998 90 999 44 88\n\n"
        "<blockquote>🚗 <b>Parking:</b>\n"
        "Free private secured parking available for our patients.</blockquote>"
    ),
}

# О клинике, технологиях и врачах
ABOUT_TEMPLATES: Dict[str, str] = {
    "ru": (
        "⭐️ <b>О клинике DentaLux Tashkent:</b>\n\n"
        "Мы объединили европейские стандарты стоматологии, немецкое оборудование и ведущих специалистов Узбекистана.\n\n"
        "👨‍⚕️ <b>Ведущие доктора:</b>\n"
        "• <b>Д-р Сардор Каримов</b> — Главный врач, челюстно-лицевой хирург, имплантолог (стаж 16 лет, член ITI, стажировки в Швейцарии и Германии).\n"
        "• <b>Д-р Мадина Усманова</b> — Ведущий ортодонт (брекеты Damon, элайнеры Spark, стаж 11 лет, 1300+ идеальных улыбок).\n"
        "• <b>Д-р Тимур Рахимов</b> — Стоматолог-ортопед (мастер керамических виниров E.max и Digital Smile Design, стаж 13 лет).\n\n"
        "🛡 <b>Безопасность и стандарты:</b>\n"
        "• <b>100% стерильность:</b> немецкие автоклавы Melag класса B, индивидуальные крафт-пакеты вскрываются строго при пациенте (протоколы «Анти-СПИД / Анти-Гепатит»).\n"
        "• <b>Лечение под микроскопом:</b> оптика Carl Zeiss (Германия) с 25-кратным увеличением.\n"
        "• <b>3D-томография:</b> безопасный аппарат Vatech с пониженной лучевой нагрузкой.\n"
        "• <b>Абсолютно без боли:</b> компьютерная деликатная анестезия.\n\n"
        "<blockquote>💳 <b>Рассрочка 0%:</b>\n"
        "Беспроцентная рассрочка до 12 месяцев через банки-партнеры: Uzum Nasiya, Anorbank, Zoodpay.</blockquote>"
    ),
    "uz": (
        "⭐️ <b>DentaLux Tashkent klinikasi haqida:</b>\n\n"
        "Biz Yevropa stomatologiya standartlari, Germaniya uskunalari va O'zbekistonning yetakchi shifokorlarini jamladik.\n\n"
        "👨‍⚕️ <b>Yetakchi mutaxassislar:</b>\n"
        "• <b>Dr. Sardor Karimov</b> — Bosh shifokor, jag'-yuz jarrohi, implantolog (16 yil tajriba, ITI a'zosi, Shveytsariya va Germaniya amaliyoti).\n"
        "• <b>Dr. Madina Usmonova</b> — Yetakchi ortodont (Damon breketlari, Spark elaynerlari, 11 yil tajriba, 1300+ tabassum).\n"
        "• <b>Dr. Timur Rahimov</b> — Ortoped-stomatolog (E.max vinirlari va raqamli tabassum ustasi, 13 yil tajriba).\n\n"
        "🛡 <b>Xavfsizlik va kafolat:</b>\n"
        "• <b>100% sterilizatsiya:</b> Germaniyaning Melag B-klass avtoklavlari, steril kraft-paketlar shaxsan bemor oldida ochiladi.\n"
        "• <b>Carl Zeiss mikroskopi:</b> eng nozik kanallarni 25 barobar kattalashtirib davolash.\n"
        "• <b>3D-tomografiya:</b> kam nurlanishli zamonaviy Vatech apparati.\n"
        "• <b>Mutlaqo og'riqsiz:</b> nozik ignali kompyuter anesteziyasi.\n\n"
        "<blockquote>💳 <b>0% Muddatli to'lov:</b>\n"
        "12 oygacha foizsiz bo'lib to'lash: Uzum Nasiya, Anorbank, Zoodpay.</blockquote>"
    ),
    "en": (
        "⭐️ <b>About DentaLux Tashkent:</b>\n\n"
        "We combine European dental standards, state-of-the-art German equipment, and leading dental specialists.\n\n"
        "👨‍⚕️ <b>Key Doctors:</b>\n"
        "• <b>Dr. Sardor Karimov</b> — Chief Medical Officer, Maxillofacial Surgeon, Implantologist (16 yrs exp, ITI member).\n"
        "• <b>Dr. Madina Usmanova</b> — Senior Orthodontist (Damon braces, Spark aligners, 11 yrs exp, 1,300+ smiles).\n"
        "• <b>Dr. Timur Rakhimov</b> — Prosthodontist & Aesthetic Dentist (E.max veneers master, 13 yrs exp).\n\n"
        "🛡 <b>Safety & Quality:</b>\n"
        "• <b>Strict Sterilization:</b> Melag Class B autoclaves (Germany), single-use packages opened in front of you.\n"
        "• <b>Microscope Dentistry:</b> Carl Zeiss optics with 25x magnification.\n"
        "• <b>3D Tomography:</b> Low-radiation Vatech CT scanner.\n"
        "• <b>100% Pain-free:</b> Gentle computerized local anesthesia.\n\n"
        "<blockquote>💳 <b>0% Installment:</b>\n"
        "Flexible 0% payment plans up to 12 months via Uzum Nasiya, Anorbank, Zoodpay.</blockquote>"
    ),
}

# Каталог услуг (вводный экран)
SERVICES_CATALOG_INTRO: Dict[str, str] = {
    "ru": (
        "🦷 <b>Прайс-лист и направления лечения DentaLux:</b>\n\n"
        "Мы работаем по системе прозрачных цен «под ключ» без скрытых платежей.\n\n"
        "<i>Выберите интересующее Вас направление ниже:</i>"
    ),
    "uz": (
        "🦷 <b>DentaLux xizmatlari va narxlari:</b>\n\n"
        "Biz barcha narxlarni yashirin to'lovlarsiz, shaffof va qulay taklif etamiz.\n\n"
        "<i>Quyidagi yo'nalishlardan birini tanlang:</i>"
    ),
    "en": (
        "🦷 <b>DentaLux Services & Price List:</b>\n\n"
        "All procedures are transparent and all-inclusive without hidden fees.\n\n"
        "<i>Select the category you are interested in below:</i>"
    ),
}

# Детальные описания услуг по категориям
SERVICE_DETAILS: Dict[str, Dict[str, str]] = {
    "brackets": {
        "ru": (
            "🦷 <b>Брекеты и исправление прикуса:</b>\n\n"
            "• <b>Металлические Damon Q2 (США):</b>\n"
            "  от 7 500 000 сум за челюсть\n"
            "  <i>Мировой эталон. Быстрое выравнивание без удаления зубов. Посещение врача 1 раз в 1.5–2 месяца.</i>\n\n"
            "• <b>Керамические / Сапфировые Damon Clear:</b>\n"
            "  от 11 000 000 сум за челюсть\n"
            "  <i>Полностью прозрачные замочки, незаметны на зубах при улыбке.</i>\n\n"
            "<blockquote>🎁 <b>Акция:</b> 3D-диагностика и консультация ортодонта — 0 сум при записи через бота! Доступна рассрочка 0%.</blockquote>"
        ),
        "uz": (
            "🦷 <b>Breketlar va tishlamni to'g'irlash:</b>\n\n"
            "• <b>Damon Q2 metall breketlari (AQSh):</b>\n"
            "  7 500 000 so'mdan jag' uchun\n"
            "  <i>Jahon standarti. Tish sug'urmasdan tez tekislash. Shifokorga har 1.5–2 oyda 1 marta kelinadi.</i>\n\n"
            "• <b>Damon Clear sapfir / keramika breketlari:</b>\n"
            "  11 000 000 so'mdan jag' uchun\n"
            "  <i>Butunlay shaffof, jilmayganda deyarli ko'rinmaydi.</i>\n\n"
            "<blockquote>🎁 <b>Aksiya:</b> 3D-diagnostika va ortodont ko'rigi — 0 so'm! 0% muddatli to'lov mavjud.</blockquote>"
        ),
        "en": (
            "🦷 <b>Braces & Orthodontics:</b>\n\n"
            "• <b>Damon Q2 Metal Braces (USA):</b>\n"
            "  from 7,500,000 UZS per jaw\n"
            "  <i>Gold standard. Rapid alignment without extractions. Visits every 6–8 weeks.</i>\n\n"
            "• <b>Damon Clear Aesthetic Braces:</b>\n"
            "  from 11,000,000 UZS per jaw\n"
            "  <i>Virtually invisible transparent brackets matching tooth enamel.</i>\n\n"
            "<blockquote>🎁 <b>Special:</b> 3D CT scan and orthodontic exam are FREE! 0% financing available.</blockquote>"
        ),
    },
    "aligners": {
        "ru": (
            "✨ <b>Элайнеры (невидимые капы):</b>\n\n"
            "• <b>Spark / 3D Smile (полный кейс):</b>\n"
            "  от 15 000 000 до 35 000 000 сум ($1,200 – $2,800)\n\n"
            "• <b>Преимущества:</b>\n"
            "  • Абсолютно прозрачные — никто не заметит лечение.\n  • Снимаются во время еды и чистки зубов.\n  • 3D-моделирование финального результата до начала лечения.\n\n"
            "<blockquote>💳 Доступна беспроцентная рассрочка на весь период лечения.</blockquote>"
        ),
        "uz": (
            "✨ <b>Elaynerlar (ko'rinmas kapalar):</b>\n\n"
            "• <b>Spark / 3D Smile to'liq kursi:</b>\n"
            "  15 000 000 dan 35 000 000 so'mgacha ($1,200 – $2,800)\n\n"
            "• <b>Afzalliklari:</b>\n"
            "  • Mutlaqo shaffof — hech kim sezmaydi.\n  • Ovqatlanish va tish yuvishda yechiladi.\n  • Natijani davolash boshlanishidan oldin kompyuterda ko'rish mumkin.\n\n"
            "<blockquote>💳 0% foizsiz bo'lib to'lash imkoniyati mavjud.</blockquote>"
        ),
        "en": (
            "✨ <b>Clear Aligners:</b>\n\n"
            "• <b>Spark / 3D Smile Full Treatment:</b>\n"
            "  15,000,000 – 35,000,000 UZS ($1,200 – $2,800)\n\n"
            "• <b>Key Benefits:</b>\n"
            "  • 100% transparent and discreet.\n  • Removable for eating and brushing.\n  • Digital 3D smile preview before starting.\n\n"
            "<blockquote>💳 0% installment plans available.</blockquote>"
        ),
    },
    "implants": {
        "ru": (
            "🔩 <b>Имплантация зубов под ключ:</b>\n\n"
            "• <b>Osstem (Южная Корея):</b>\n"
            "  от 4 200 000 сум ($330)\n"
            "  <i>Надежная проверенная система. Приживаемость 98.8%, пожизненная заводская гарантия.</i>\n\n"
            "• <b>Straumann SLActive (Швейцария):</b>\n"
            "  от 8 500 000 сум ($670)\n"
            "  <i>Премиум №1 в мире. Ускоренное приживление за 3-4 недели, подходит при диабете.</i>\n\n"
            "• <b>All-on-4 / All-on-6 (все зубы за 1–3 дня):</b>\n"
            "  от 38 000 000 сум за челюсть\n\n"
            "<blockquote>🎁 3D-томография челюсти и консультация имплантолога — бесплатно!</blockquote>"
        ),
        "uz": (
            "🔩 <b>Tish implantatsiyasi (to'liq kalit ostida):</b>\n\n"
            "• <b>Osstem (Janubiy Koreya):</b>\n"
            "  4 200 000 so'mdan ($330)\n"
            "  <i>Ishonchli va mashhur tizim. Ildiz otishi 98.8%, umrbod zavod kafolati.</i>\n\n"
            "• <b>Straumann SLActive (Shveytsariya):</b>\n"
            "  8 500 000 so'mdan ($670)\n"
            "  <i>Dunyoda 1-o'rindagi premium tizim. 3-4 haftada ildiz otadi, qandli diabetda ham mos keladi.</i>\n\n"
            "• <b>All-on-4 / All-on-6 (barcha tishlar 1–3 kunda):</b>\n"
            "  38 000 000 so'mdan jag' uchun\n\n"
            "<blockquote>🎁 3D-KT rentgen va bosh jarroh ko'rigi — mutlaqo bepul!</blockquote>"
        ),
        "en": (
            "🔩 <b>Dental Implantation:</b>\n\n"
            "• <b>Osstem (South Korea):</b>\n"
            "  from 4,200,000 UZS ($330)\n"
            "  <i>98.8% success rate, lifetime manufacturer warranty.</i>\n\n"
            "• <b>Straumann SLActive (Switzerland):</b>\n"
            "  from 8,500,000 UZS ($670)\n"
            "  <i>World's #1 premium implant. Heals in just 3–4 weeks.</i>\n\n"
            "• <b>All-on-4 / All-on-6 (Full jaw restoration in 1–3 days):</b>\n"
            "  from 38,000,000 UZS per jaw\n\n"
            "<blockquote>🎁 3D CT scan and surgical consultation are complimentary!</blockquote>"
        ),
    },
    "veneers": {
        "ru": (
            "💎 <b>Керамические виниры и эстетика:</b>\n\n"
            "• <b>Керамические виниры E.max (Германия):</b>\n"
            "  от 2 800 000 сум ($220) за 1 зуб\n"
            "  <i>Ультратонкие (0.3 мм). Не темнеют от кофе и чая, сохраняют блеск 15+ лет.</i>\n\n"
            "• <b>Циркониевые коронки Prettau Zirkonzahn:</b>\n"
            "  от 1 900 000 сум за 1 зуб\n"
            "  <i>Сверхпрочный безметалловый цирконий, натуральная прозрачность.</i>\n\n"
            "<blockquote>✨ Компьютерный дизайн улыбки (Digital Smile Design) перед началом работы.</blockquote>"
        ),
        "uz": (
            "💎 <b>Keramika vinirlari va estetika:</b>\n\n"
            "• <b>E.max keramika vinirlari (Germaniya):</b>\n"
            "  2 800 000 so'mdan ($220) 1 ta tish uchun\n"
            "  <i>O'ta yupqa (0.3 mm). Qahva va choydan aslo rangini o'zgartirmaydi, 15+ yil xizmat qiladi.</i>\n\n"
            "• <b>Tsirkon qoplamalar (Zirkonzahn):</b>\n"
            "  1 900 000 so'mdan 1 ta tish uchun\n"
            "  <i>Metallsiz o'ta mustahkam va tabiiy tishdek ko'rinish.</i>\n\n"
            "<blockquote>✨ Boshlashdan oldin raqamli tabassum dizayni ko'rsatiladi.</blockquote>"
        ),
        "en": (
            "💎 <b>Ceramic Veneers & Aesthetics:</b>\n\n"
            "• <b>E.max Ultra-thin Veneers (Germany):</b>\n"
            "  from 2,800,000 UZS ($220) per tooth\n"
            "  <i>0.3 mm thickness, minimal prep, stain-resistant, 15+ years lifespan.</i>\n\n"
            "• <b>Prettau Zirconia Crowns:</b>\n"
            "  from 1,900,000 UZS per tooth\n\n"
            "<blockquote>✨ Digital Smile Design preview included.</blockquote>"
        ),
    },
    "whitening": {
        "ru": (
            "🌟 <b>Профессиональное отбеливание:</b>\n\n"
            "• <b>Beyond Polus Ultra / Philips Zoom 4:</b>\n"
            "  2 200 000 сум за обе челюсти\n\n"
            "• <b>Особенности процедуры:</b>\n"
            "  • Осветление на 6–8 тонов за 45 минут.\n  • Технология холодного света — без перегрева нерва и боли.\n  • Включает укрепление эмали минеральным гелем.\n\n"
            "<blockquote>✅ Результат сохраняется до 2 лет при соблюдении рекомендаций.</blockquote>"
        ),
        "uz": (
            "🌟 <b>Professional tish oqartirish:</b>\n\n"
            "• <b>Beyond Polus / Philips Zoom 4:</b>\n"
            "  2 200 000 so'm ikkala jag' uchun (45 daqiqa)\n\n"
            "• <b>Afzalliklari:</b>\n"
            "  • 1 seansda 6–8 tongacha oqartirish.\n  • Sovuq nur texnologiyasi — og'riqsiz va emalni kuydirmaydi.\n  • Ftorli mustahkamlovchi terapiyani o'z ichiga oladi.\n\n"
            "<blockquote>✅ Natija 2 yilgacha saqlanadi.</blockquote>"
        ),
        "en": (
            "🌟 <b>Professional Teeth Whitening:</b>\n\n"
            "• <b>Beyond Polus / Philips Zoom 4:</b>\n"
            "  2,200,000 UZS for both jaws (45 min session)\n\n"
            "• <b>Features:</b>\n"
            "  • 6–8 shades lighter in a single visit.\n  • Cold light prevents nerve sensitivity.\n  • Enamel strengthening included.\n\n"
            "<blockquote>✅ Results last up to 2 years.</blockquote>"
        ),
    },
    "therapy": {
        "ru": (
            "🩺 <b>Терапия, гигиена и лечение кариеса:</b>\n\n"
            "• <b>Комплексная гигиена полости рта:</b>\n"
            "  550 000 сум\n"
            "  <i>Ультразвук + AirFlow + полировка + фторирование. Удаление налета от чая и сигарет.</i>\n\n"
            "• <b>Лечение кариеса Estelite Asteria (Япония):</b>\n"
            "  от 450 000 до 850 000 сум\n"
            "  <i>Анатомическая художественная реставрация с коффердамом.</i>\n\n"
            "• <b>Лечение каналов под микроскопом Carl Zeiss:</b>\n"
            "  от 900 000 сум за зуб\n"
            "  <i>Спасаем даже сложные и безнадежные зубы.</i>"
        ),
        "uz": (
            "🩺 <b>Terapiya, gigiyena va davolash:</b>\n\n"
            "• <b>Kompleks tozalash (Ultratovush + AirFlow):</b>\n"
            "  550 000 so'm\n"
            "  <i>Toshlar, qorayishlarni ketkazish va tishlarni mustahkamlash.</i>\n\n"
            "• <b>Karies davolash (Estelite Asteria, Yaponiya):</b>\n"
            "  450 000 dan 850 000 so'mgacha\n\n"
            "• <b>Carl Zeiss mikroskopi ostida kanallarni davolash:</b>\n"
            "  900 000 so'mdan boshlab"
        ),
        "en": (
            "🩺 <b>Therapy & Dental Hygiene:</b>\n\n"
            "• <b>Full Hygiene (AirFlow + Ultrasound):</b>\n"
            "  550,000 UZS\n\n"
            "• <b>Caries Treatment (Estelite, Japan):</b>\n"
            "  450,000 – 850,000 UZS\n\n"
            "• <b>Microscopic Root Canal (Carl Zeiss):</b>\n"
            "  from 900,000 UZS"
        ),
    },
    "pediatric": {
        "ru": (
            "🧸 <b>Детская стоматология:</b>\n\n"
            "• <b>Лечение молочного зуба без слез и боли:</b>\n"
            "  от 250 000 сум\n\n"
            "• <b>Почему дети любят DentaLux:</b>\n"
            "  • Специальный детский кабинет с любимыми мультфильмами.\n  • Вкусная аппликационная анестезия (малиновый/банановый гель).\n  • Подарки и грамоты каждому храброму маленькому пациенту!\n  • Врач-эксперт по мягкой детской психологии."
        ),
        "uz": (
            "🧸 <b>Bolalar stomatologiyasi:</b>\n\n"
            "• <b>Sut tishlarini og'riqsiz va qo'rquvsiz davolash:</b>\n"
            "  250 000 so'mdan\n\n"
            "• <b>Nega bolajonlar bizni yaxshi ko'rishadi:</b>\n"
            "  • Sevimli multfilmlar va shinam bolalar xonasi.\n  • Yoqimli mevali muzlatuvchi gellar.\n  • Har bir mitti qahramonga sovg'alar!\n  • Bolalar psixologiyasini chuqur biluvchi muloyim shifokorlar."
        ),
        "en": (
            "🧸 <b>Pediatric Dentistry:</b>\n\n"
            "• <b>Gentle Treatment for Kids:</b>\n"
            "  from 250,000 UZS\n\n"
            "• Cartoons during treatment, flavored numbing gels, gifts for courage, and a caring, friendly team!"
        ),
    },
}

# Экран записи на прием
BOOKING_PROMPT_TEMPLATES: Dict[str, str] = {
    "ru": (
        "📅 <b>Запись на бесплатную первичную консультацию и 3D-снимок:</b>\n\n"
        "<blockquote>🎁 <b>Напоминаем:</b>\n"
        "При бронировании через Telegram — осмотр главного врача и компьютерная томография (КТ) — <b>0 сум</b> (вместо 350 000 сум)!</blockquote>\n\n"
        "Чтобы старший администратор забронировал за Вами удобное время:\n"
        "1. Нажмите кнопку <b>«📱 Отправить мой телефон»</b> внизу, либо\n"
        "2. Напишите в чат Ваше <b>имя, телефон (+998...) и удобный день/время</b>.\n\n"
        "Мы перезвоним Вам в течение 10 минут (в рабочее время) для подтверждения записи!"
    ),
    "uz": (
        "📅 <b>Bepul qabul va 3D-rentgenga yozilish:</b>\n\n"
        "<blockquote>🎁 <b>Eslatma:</b>\n"
        "Telegram orqali yozilganda bosh shifokor ko'rigi va 3D-tomografiya — <b>MUTLAQO 0 SO'M</b> (350 000 so'm o'rniga)!</blockquote>\n\n"
        "Administrator siz uchun qulay vaqtni band qilishi uchun:\n"
        "1. Pastdagi <b>«📱 Telefon raqamimni yuborish»</b> tugmasini bosing, yoki\n"
        "2. Chatga <b>ismingiz, telefon raqamingiz (+998...) va qulay vaqtni</b> yozing.\n\n"
        "Biz 10 daqiqa ichida qo'ng'iroq qilib, vaqtingizni tasdiqlaymiz!"
    ),
    "en": (
        "📅 <b>Book Free Initial Exam & 3D CT Scan:</b>\n\n"
        "<blockquote>🎁 <b>Reminder:</b>\n"
        "Chief Doctor exam + 3D scan are <b>FREE (0 UZS)</b> when booking through this bot!</blockquote>\n\n"
        "To reserve your appointment:\n"
        "1. Click <b>«📱 Share My Phone Number»</b> below, or\n"
        "2. Send your <b>name, phone (+998...) and preferred date/time</b>.\n\n"
        "Our receptionist will contact you within 10 minutes to confirm!"
    ),
}

# Подтверждение перевода на оператора
OPERATOR_MODE_TEMPLATES: Dict[str, str] = {
    "ru": (
        "👨‍💼 <b>Запрос отправлен старшему администратору клиники.</b>\n\n"
        "Наш специалист уже подключился и ответит Вам прямо в этом чате в течение нескольких минут.\n\n"
        "<i>Если захотите вернуться к меню или AI-консультанту, нажмите /bot или кнопку внизу.</i>"
    ),
    "uz": (
        "👨‍💼 <b>Xabar katta administratorga yuborildi.</b>\n\n"
        "Mutaxassisimiz ushbu chatga ulandi va bir necha daqiqa ichida javob beradi.\n\n"
        "<i>AI-yordamchiga qaytish uchun /bot buyrug'ini yoki pastdagi tugmani bosing.</i>"
    ),
    "en": (
        "👨‍💼 <b>A live administrator has been notified.</b>\n\n"
        "Our specialist will join this conversation and assist you in a few minutes.\n\n"
        "<i>To return to the AI assistant at any time, tap /bot or the menu button below.</i>"
    ),
}

# Подтверждение смены языка
LANGUAGE_CHANGED_TEMPLATES: Dict[str, str] = {
    "ru": "✅ Язык успешно изменен на <b>Русский</b>.",
    "uz": "✅ Muloqot tili <b>O'zbekcha</b>ga o'zgartirildi.",
    "en": "✅ Language successfully switched to <b>English</b>.",
}
