# 🚀 Полное руководство по развертыванию SOLV на корпоративном сервере с GPU

Это пошаговое руководство описывает процесс переноса проекта `onboarding-agent` на чистый корпоративный Linux-сервер (Ubuntu/Debian) с использованием мощной видеокарты (GPU) и модели `gemma4:e4b`.

---

## Шаг 1. Базовая настройка сервера

1. Подключитесь к серверу по SSH:
   ```bash
   ssh user@your-server-ip
   ```
2. Обновите систему:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```
3. Установите необходимые пакеты (Git, Nginx, Certbot):
   ```bash
   sudo apt install -y git nginx certbot python3-certbot-nginx
   ```

---

## Шаг 2. Установка Docker и NVIDIA Container Toolkit

Чтобы Ollama могла использовать вашу видеокарту внутри Docker, необходимо установить официальные драйверы.

1. **Установите Docker** (если еще не установлен):
   ```bash
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   ```
2. **Установите драйверы NVIDIA** (если они еще не стоят на сервере):
   ```bash
   sudo apt install -y nvidia-driver-535  # Или другая актуальная версия для вашей карты
   ```
3. **Установите NVIDIA Container Toolkit** (КРИТИЧЕСКИ ВАЖНО для проброса видеокарты в Docker):
   ```bash
   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
     && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
       sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
       sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

   sudo apt update
   sudo apt install -y nvidia-container-toolkit
   ```
4. Перезапустите службу Docker для применения изменений:
   ```bash
   sudo systemctl restart docker
   ```

---

## Шаг 3. Клонирование проекта

Скачайте исходный код проекта с вашего GitHub (потребуется настроить SSH ключи или ввести токен, если репозиторий приватный):

```bash
git clone https://github.com/DeNICE-AI/onboarding-agent.git
cd onboarding-agent
```

---

## Шаг 4. Подготовка кода (Переход на мощную модель и кэш VRAM)

Поскольку у вас есть мощная видеокарта, нам нужно убрать "костыли" для слабых ПК и включить использование новой модели.

### 4.1. Изменение модели в `backend/app.py`
Откройте файл `backend/app.py` любым редактором (например, `nano backend/app.py`):
Найдите строку (около 88 строки):
```python
    answer = client.chat(messages=messages, model="gemma2:2b", temperature=req.temperature)
```
Замените `"gemma2:2b"` на `"gemma4:e4b"`:
```python
    answer = client.chat(messages=messages, model="gemma4:e4b", temperature=req.temperature)
```

### 4.2. Включение кэширования в памяти (Оптимизация скорости)
Откройте файл `backend/ollama_client.py` (`nano backend/ollama_client.py`).
Удалите или закомментируйте **все три** строчки `"keep_alive": 0,`. 
Без них Ollama будет постоянно держать модели в VRAM видеокарты, что обеспечит мгновенные ответы бота.

---

## Шаг 5. Настройка `docker-compose.yml` для видеокарты

Откройте `docker-compose.yml` (`nano docker-compose.yml`) и добавьте блок `deploy` в сервис `ollama`, чтобы Docker отдал контейнеру доступ к GPU. Должно получиться так:

```yaml
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    volumes:
      - ollama_data:/root/.ollama
    ports:
      - "11434:11434"
    # ЭТОТ БЛОК ПРОБРАСЫВАЕТ ВИДЕОКАРТУ ВНУТРЬ КОНТЕЙНЕРА
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

*(Опционально: если вы используете Nginx, привяжите порты `solv-agent` и `n8n` к `127.0.0.1`, чтобы закрыть их от внешнего мира, как описано в основном `README.md`)*.

---

## Шаг 6. Запуск и загрузка моделей

1. Запустите сборку и старт всех контейнеров:
   ```bash
   sudo docker compose up -d --build
   ```
2. Скачайте эмбеддинг-модель:
   ```bash
   sudo docker exec ollama ollama pull bge-m3
   ```
3. Скачайте вашу основную модель:
   ```bash
   sudo docker exec ollama ollama pull gemma4:e4b
   ```
   *(Примечание: Убедитесь, что модель gemma4:e4b существует в реестре Ollama под таким точным именем, или используйте соответствующий тег, например `gemma:7b` и т.д.)*.

4. Пересоберите базу знаний (вектора):
   ```bash
   sudo docker exec solv-agent python backend/build_index.py
   ```

---

## Шаг 7. Настройка доменов и HTTPS (Nginx)

Выполните шаги из основного `README.md` (Раздел 2), чтобы:
1. Создать конфиги Nginx для `chat.company.com` и `n8n.company.com`.
2. Включить проксирование на порты `8000` и `5678`.
3. Выполнить `sudo certbot --nginx` для получения бесплатного SSL сертификата HTTPS.

---
**🎉 Готово! Ваш ИИ-ассистент теперь работает на всю мощь корпоративной видеокарты!**
