# Оптимизированный базовый образ Python 3.11
FROM python:3.11-slim

# Отключаем буферизацию вывода и запись .pyc файлов
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Рабочая директория контейнера
WORKDIR /app

# Установка системных зависимостей (при необходимости компиляции)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Копирование и установка зависимостей Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода проекта
COPY . .

# Создание директории данных для базы SQLite
RUN mkdir -p /app/data

# Запуск бота
CMD ["python", "bot.py"]
