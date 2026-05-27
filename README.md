# ИИ-ассистент SOLV (Onboarding AI Agent)

ИИ-ассистент службы ИТ-поддержки для новых сотрудников (и не только). Проект создан для автоматизации процесса ответов на частые ИТ-вопросы, помощи в настройке рабочего места и автоматического создания заявок (тикетов) в службу поддержки при сложных вопросах.

## Архитектура проекта

Проект полностью локален и независим от внешних API. В основе лежат следующие технологии:
- **Backend**: FastAPI (Python), обслуживает как API, так и статические файлы (Frontend).
- **LLM Engine**: Ollama (для локального запуска нейросетей). Используются модели `gemma2:2b` (генерация ответов) и `bge-m3` (создание эмбеддингов/векторов).
- **Vector Database**: Qdrant (локальная база `rag/` для хранения векторов).
- **Автоматизация**: n8n (получает Webhook-и от бэкенда при необходимости создать тикет и может быть настроен на пересылку в Jira, Telegram и т.д.).
- **Инфраструктура**: Docker & Docker Compose.

---

## 1. Локальный запуск (Разработка и тестирование)

Для локального запуска вам потребуется только **Docker Desktop** (или Docker Compose) и Git.

### Быстрый старт
1. Клонируйте репозиторий и перейдите в папку проекта:
   ```bash
   git clone <url-репозитория>
   cd onboarding-agent
   ```
2. Поднимите все контейнеры:
   ```bash
   docker compose up -d --build
   ```
3. Скачайте необходимые нейромодели в контейнер Ollama:
   ```bash
   docker exec ollama ollama pull gemma2:2b
   docker exec ollama ollama pull bge-m3
   ```
4. Соберите векторную базу знаний из файлов (из папки `data/`):
   ```bash
   docker exec solv-agent python backend/build_index.py
   ```
5. **Готово!** Ваш локальный стенд работает:
   - Чат-бот (Сайт): [http://localhost:8000](http://localhost:8000)
   - Панель управления n8n: [http://localhost:5678](http://localhost:5678)

### Как обновить базу знаний?
Документация и инструкции хранятся в формате `.md` (Markdown) в папке `data/`.
Чтобы добавить новую информацию:
1. Создайте или отредактируйте `.md` файл в папке `data/`.
2. Запустите пересборку базы:
   ```bash
   docker exec solv-agent python backend/build_index.py
   ```

### Как изменить LLM-модель?
Если вы хотите использовать более мощную (или наоборот, более легкую) модель:
1. Зайдите на сайт [ollama.com/library](https://ollama.com/library) и выберите модель (например, `qwen2.5:1.5b` или `llama3.2`).
2. Скачайте ее в работающий контейнер:
   ```bash
   docker exec ollama ollama pull <имя-модели>
   ```
3. Откройте файл `backend/app.py` и найдите строку `model="gemma2:2b"` (около 90-й строки). Замените название на новое.
4. Перезапустите бэкенд:
   ```bash
   docker compose up -d --build solv-agent
   ```

---

## 2. Разворачивание на боевом сервере (Production)

Для публикации проекта в интернете на собственном сервере с реальным доменом (например, `chat.company.com` и `n8n.company.com`) и безопасным HTTPS, необходимо настроить **Nginx** в качестве Reverse Proxy (обратного прокси) и выпустить SSL-сертификаты с помощью **Certbot (Let's Encrypt)**.

### Шаг 1. Подготовка сервера
1. Арендуйте Linux-сервер (рекомендуется Ubuntu 22.04/24.04). **Минимальные требования:** 8-16 ГБ ОЗУ (в зависимости от размера модели).
2. Привяжите ваши домены к IP-адресу сервера в панели вашего DNS-провайдера. 
   - `chat.company.com` -> IP сервера
   - `n8n.company.com` -> IP сервера
3. Установите Docker, Docker Compose, Nginx и Certbot:
   ```bash
   sudo apt update
   sudo apt install docker.io docker-compose nginx certbot python3-certbot-nginx -y
   ```

### Шаг 2. Запуск Docker Compose
Клонируйте проект и запустите его точно так же, как и локально:
```bash
docker compose up -d --build
docker exec ollama ollama pull gemma2:2b
docker exec ollama ollama pull bge-m3
docker exec solv-agent python backend/build_index.py
```
*Важно: Контейнеры по умолчанию открывают порты `8000` и `5678` наружу. Если ваш сервер не защищен файрволом, рекомендуется изменить `docker-compose.yml`, привязав порты к `127.0.0.1`, чтобы доступ к ним имел только Nginx.*

*Пример безопасного `docker-compose.yml`:*
```yaml
services:
  solv-agent:
    ...
    ports:
      - "127.0.0.1:8000:8000"  # Только Nginx сможет сюда достучаться
  n8n:
    ...
    ports:
      - "127.0.0.1:5678:5678"
```

### Шаг 3. Настройка Nginx

Создайте конфигурационные файлы для Nginx, чтобы направить трафик с доменов на нужные порты контейнеров.

**Для чат-бота (solv-agent):**
Создайте файл `sudo nano /etc/nginx/sites-available/chat.company.com`:
```nginx
server {
    listen 80;
    server_name chat.company.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Для n8n:**
Создайте файл `sudo nano /etc/nginx/sites-available/n8n.company.com`:
```nginx
server {
    listen 80;
    server_name n8n.company.com;

    location / {
        proxy_pass http://127.0.0.1:5678;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Настройки для WebSocket (необходимо для работы UI n8n)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Активируйте сайты и перезапустите Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/chat.company.com /etc/nginx/sites-enabled/
sudo ln -s /etc/nginx/sites-available/n8n.company.com /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Шаг 4. Установка SSL (HTTPS)
Выпустите бесплатные сертификаты Let's Encrypt. Certbot автоматически модифицирует конфигурацию Nginx для поддержки HTTPS.
```bash
sudo certbot --nginx -d chat.company.com
sudo certbot --nginx -d n8n.company.com
```

### Шаг 5. Как получить доступ в боевом режиме?
После успешной настройки:
1. Сайт с ботом будет доступен по защищенному адресу: `https://chat.company.com`.
2. Панель управления n8n будет доступна по адресу: `https://n8n.company.com`. *Рекомендуется немедленно зайти в панель n8n и установить надежный пароль администратора, чтобы закрыть публичный доступ к настройкам.*
3. Внешним сервисам (и сайту) доступ к Ollama (порт 11434) предоставлять **не нужно**! Контейнер `solv-agent` общается с `ollama` по внутренней закрытой сети Docker.

---

*Архитектура бота позволяет легко масштабироваться, подключая новые источники данных и создавая сложные workflow в n8n (например, отправка тикета в Jira/Telegram, если бот не справился).*
