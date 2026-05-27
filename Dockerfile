FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код и файлы
COPY . .

# Прописываем PYTHONPATH для корректных импортов
ENV PYTHONPATH=/app

# Команда для запуска (FastAPI сервер)
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
