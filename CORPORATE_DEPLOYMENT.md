# 🚀 Полное руководство по развертыванию SOLV на корпоративном сервере TOFSGROUP

Это пошаговое руководство описывает процесс развертывания проекта `onboarding-agent` на корпоративном сервере (`adminofs@OFSHGPM287`) с доменом `ai.tofsgroup.ru`. 

---

## 🛠 Рабочий процесс (Workflow)

**Критически важно:** Мы **не запускаем** Docker локально на рабочем месте во время доработок. 
1. Все изменения кода (дизайн, логика) делаются в локальной директории разработчика.
2. Изменения отправляются в репозиторий через Git (`git add`, `git commit`, `git push`).
3. На боевом сервере выполняется `git pull`, после чего контейнеры перезапускаются для применения изменений.

---

## Шаг 1. Настройка сервера и скачивание проекта

1. Подключитесь к серверу:
   ```bash
   ssh adminofs@OFSHGPM287
   ```
2. Перейдите в папку проекта и обновите код:
   ```bash
   cd ~/onboarding-agent
   git pull origin main
   ```

---

## Шаг 2. Запуск контейнеров

В проекте используется локальный LLM (Ollama) и n8n для автоматизации. 
1. Пересоберите и запустите контейнеры:
   ```bash
   sudo docker compose up -d --build
   ```
2. Убедитесь, что загружены необходимые модели:
   ```bash
   sudo docker exec ollama ollama pull bge-m3
   sudo docker exec ollama ollama pull gemma4:e4b
   ```
   *(Если используете другую модель, создайте файл `.env` в папке проекта и добавьте переменные:)*
   ```env
   LLM_MODEL=gemma4:e4b
   OLLAMA_KEEP_ALIVE=-1
   ```
   *(Параметр OLLAMA_KEEP_ALIVE=-1 не позволит выгружать модель из видеопамяти, обеспечивая мгновенные ответы).*
3. Пересоберите базу знаний:
   ```bash
   sudo docker exec solv-agent python backend/build_index.py
   ```

---

## Шаг 3. Настройка Nginx и SSL для ai.tofsgroup.ru

На сервере уже установлены корпоративные SSL-сертификаты. Их пути:
- Сертификат: `/etc/ssl/certs/ai.tofsgroup.ru.crt`
- Ключ: `/etc/ssl/private/ai.tofsgroup.ru.key`

1. Откройте конфигурацию Nginx:
   ```bash
   sudo nano /etc/nginx/sites-available/ai.tofsgroup.ru
   ```
2. Пропишите конфигурацию (пример для проксирования чата на порт 8000):
   ```nginx
   server {
       listen 80;
       server_name ai.tofsgroup.ru;
       return 301 https://$host$request_uri;
   }

   server {
       listen 443 ssl;
       server_name ai.tofsgroup.ru;

       ssl_certificate /etc/ssl/certs/ai.tofsgroup.ru.crt;
       ssl_certificate_key /etc/ssl/private/ai.tofsgroup.ru.key;

       ssl_protocols TLSv1.2 TLSv1.3;
       ssl_ciphers HIGH:!aNULL:!MD5;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```
3. Проверьте конфигурацию и перезапустите Nginx:
   ```bash
   sudo nginx -t
   sudo systemctl restart nginx
   ```

---

## Шаг 4. Настройка n8n (Почта и Автоматизация)

Если вам необходимо, чтобы n8n отправлял уведомления на почту, потребуется настроить SMTP внутри n8n.
1. Откройте интерфейс n8n (через SSH туннель или настройте Nginx для проксирования порта 5678).
2. В workflow используйте ноду `Send Email`.
3. Укажите корпоративные SMTP-настройки:
   - Хост: (ваш корпоративный SMTP-сервер)
   - Порт: 465 (SSL) или 587 (TLS)
   - Учетные данные: создайте в Credentials менеджере n8n корпоративную почту и пароль (или App Password).

**Готово!** Ваш ассистент доступен по адресу `https://ai.tofsgroup.ru`.
