# План миграции с Docker Swarm на Docker Compose

## Контекст

Текущая инфраструктура использует Docker Swarm с GitHub Actions для SSH деплоя на сервер. Это создает излишнюю сложность для простой Telegram bot системы. Требуется упростить деплой до стандартного Docker Compose с .env файлом, сохранив всю существующую функциональность.

**Текущая ситуация:**
- GitHub Actions делает SSH деплой на сервер в Docker Swarm
- Используются Docker Swarm secrets для токенов
- GitHub Actions weekly rebuilds + entrypoint для обновления yt-dlp
- Watchtower для автообновления контейнеров

**Желаемая ситуация:**
- GitHub Actions только собирает и пушит образы в Docker Hub
- Docker Compose с .env файлом на сервере
- Ручное первоначальное развертывание
- Сохранение текущего механизма обновления yt-dlp

## Изменения

### 1. Упрощение docker-compose.yml

**Файл:** `docker-compose.yml`

**Заменить Docker Swarm специфику на Docker Compose:**
- Убрать `deploy:` секции (restart_policy, placement constraints)
- Убрать `secrets:` секцию и внешние secrets
- Заменить overlay network на стандартный bridge
- Убрать `networks: downloader:` секцию (используется только для watchtower)
- Использовать `restart: unless-stopped` вместо `deploy.restart_policy`
- Добавить `depends_on:` для правильного порядка запуска сервисов
- Добавить health check для Redis

**Специальные случаи:**
- `download-service`: оставить `network_mode: host` (требуется для YouTube)
- `watchtower`: упростить конфигурацию без Swarm placement constraints
- `redis`: добавить health check для зависимости других сервисов

### 2. Создание .env.example

**Файл:** `.env.example` (новый файл)

Создать шаблон для переменных окружения:
```bash
# API Service Configuration
API_TOKEN=your_api_token_here

# Telegram Service Configuration
TELEGRAM_TOKEN=your_telegram_token_here
VLESS_URL=your_vless_url_here
```

**Важные замечания:**
- Добавить `.env` в `.gitignore`
- Документировать каждую переменную
- Предупредить о безопасности хранения секретов в plaintext

### 3. Обновление кода сервисов для environment variables

**Файлы:**
- `api-service/app/main.py`
- `telegram-service/main.py`

**Изменения в api-service/app/main.py:**
Заменить функцию `get_api_token()` которая читает из `/run/secrets/api_token` на:
```python
API_TOKEN = os.getenv("API_TOKEN")
if not API_TOKEN:
    raise HTTPException(status_code=500, detail="API_TOKEN not set")
```

**Изменения в telegram-service/main.py:**
Заменить функцию `get_telegram_token()` которая читает из `/run/secrets/telegram_token` на:
```python
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise HTTPException(status_code=500, detail="TELEGRAM_TOKEN not set")
```

### 4. Удаление GitHub Actions SSH деплоя

**Файл:** `.github/workflows/deploy.yml` (удалить полностью)

Оставить только `.github/workflows/build.yml` который:
- Собирает 3 Docker образа (api, download, telegram)
- Пушит их в Docker Hub
- Делает weekly rebuilds для обновления yt-dlp
- **НЕ делает SSH деплой на сервер**

### 5. Создание инструкции по ручному развертыванию

**Файл:** `DEPLOYMENT.md` (новый файл)

Документация для ручного развертывания:
```bash
# Первоначальное развертывание
cd ~/video-downloader
git pull origin main
cp .env.example .env
nano .env  # Добавить реальные токены
docker-compose up -d

# Проверка статуса
docker-compose ps
docker-compose logs -f
```

### 6. Обновление .gitignore

**Файл:** `.gitignore`

Добавить `.env` в `.gitignore` для предотвращения коммита секретов.

## Детали реализации

### Новый docker-compose.yml структура:

```yaml
version: '3.8'

services:
  api-service:
    image: eevarn/video-downloader-api:latest
    ports:
      - "8000:8000"
    environment:
      - API_TOKEN=${API_TOKEN}
      - REDIS_HOST=redis
    networks:
      - downloader
    restart: unless-stopped
    depends_on:
      redis:
        condition: service_healthy

  telegram-service:
    image: eevarn/video-downloader-telegram:latest
    environment:
      - TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
      - API_URL=http://api-service:8000
      - VLESS_URL=${VLESS_URL}
      - REDIS_HOST=redis
    volumes:
      - /home/ivan/downloads:/app/downloads
    networks:
      - downloader
    restart: unless-stopped
    depends_on:
      redis:
        condition: service_healthy

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
    networks:
      - downloader
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  download-service:
    image: eevarn/video-downloader-download:latest
    network_mode: host
    environment:
      - REDIS_HOST=127.0.0.1
    volumes:
      - /home/ivan/downloads:/app/downloads
    restart: unless-stopped
    depends_on:
      redis:
        condition: service_healthy

  watchtower:
    image: containrrr/watchtower
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - WATCHTOWER_POLL_INTERVAL=300
      - WATCHTOWER_CLEANUP=true
      - WATCHTOWER_INCLUDE_RESTARTING=true
    networks:
      - downloader
    restart: unless-stopped

networks:
  downloader:
    driver: bridge
```

## Сохранение функциональности

**Что остается без изменений:**
- ✅ yt-dlp обновления: weekly rebuilds + entrypoint.sh с `yt-dlp -U`
- ✅ Watchtower: автообновление контейнеров каждые 5 минут
- ✅ Download service: host networking для YouTube
- ✅ Все существующие функции бота
- ✅ GitHub Actions: сборка и пуш в Docker Hub

**Что упрощается:**
- 🔄 Docker Compose вместо Docker Swarm
- 🔄 .env файл вместо Swarm secrets
- 🔄 Ручной деплой вместо SSH автоматизации
- 🔄 Стандартные Docker команды вместо Swarm stack

## Безопасность

**Важные замечания:**
- `.env` файл будет содержать секреты в plaintext
- Установить правильные права доступа: `chmod 600 .env`
- Добавить `.env` в `.gitignore`
- Ограничить доступ к .env файлу

## Проверка

**Пост-миграционное тестирование:**
1. Развернуть на сервере: `docker-compose up -d`
2. Проверить статус всех сервисов: `docker-compose ps`
3. Протестировать полный workflow скачивания видео
4. Проверить Telegram бот функциональность
5. Проверить что Watchtower обновляет контейнеры
6. Проверить что yt-dlp обновляется при запуске

**План отката:**
- Сохранить текущий `docker-compose.yml` как `docker-compose.swarm.yml` 
- Можно откатиться: `docker stack deploy -c docker-compose.swarm.yml video-downloader`

## Критические файлы

**Основные файлы для изменения:**
- `docker-compose.yml` - главная конфигурация Docker Compose
- `.env.example` - шаблон переменных окружения
- `api-service/app/main.py` - обработка API_TOKEN из environment
- `telegram-service/main.py` - обработка TELEGRAM_TOKEN из environment
- `.github/workflows/deploy.yml` - удалить этот файл
- `DEPLOYMENT.md` - инструкция по ручному развертыванию
- `.gitignore` - добавить `.env`

Этот план сохраняет всю существующую функциональность при упрощении инфраструктуры и повышении поддерживаемости.