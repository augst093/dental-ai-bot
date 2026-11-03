@echo off
chcp 65001 > nul
title DentaLux Tashkent AI Bot

echo ===================================================
echo     DentaLux Tashkent - Запуск AI Telegram Бота
echo ===================================================
echo.

if not exist ".env" (
    echo [ВНИМАНИЕ] Файл .env не найден!
    echo Создаю .env из шаблона .env.example...
    copy .env.example .env > nul
    echo.
    echo Пожалуйста, откройте файл .env в блокноте и укажите:
    echo 1. BOT_TOKEN (от @BotFather)
    echo 2. ADMIN_CHAT_ID (ID вашей группы или чата)
    echo 3. OPENAI_API_KEY (ключ от OpenAI)
    echo.
    pause
    exit /b
)

if exist "venv\Scripts\activate.bat" (
    echo [1/2] Активация виртуального окружения venv...
    call venv\Scripts\activate.bat
) else (
    echo [1/2] Виртуальное окружение venv не найдено. Используется системный Python...
)

echo [2/2] Запуск бота...
echo Для остановки нажмите Ctrl + C
echo.
python bot.py

echo.
echo [ИНФОРМАЦИЯ] Работа бота завершена.
pause
