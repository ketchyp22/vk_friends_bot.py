# Используем официальный Python образ
FROM python:3.9-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта
COPY . .

# Создаем директории для логов и данных
RUN mkdir -p /app/logs /app/data

# Устанавливаем переменную окружения для Python
ENV PYTHONUNBUFFERED=1

# Запускаем бота
CMD ["python", "vk_medical_bot.py"]
