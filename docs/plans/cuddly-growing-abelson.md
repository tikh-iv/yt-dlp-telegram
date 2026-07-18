# Упрощение деплоя: Docker Swarm → Docker Compose

## Контекст

Текущая инфраструктура использует Docker Swarm с SSH-деплоем через GitHub Actions, что создаёт излишнюю сложность для одиночного сервера. GitHub Actions хранит SSH-ключы для доступа к серверу, что увеличивает атакуемую поверхность. Swarm mode с overlay сетями не даёт преимуществ для single-server deployments.

**Цель:** Упростить деплой, убрать SSH-доступ из GitHub Actions, использовать стандартный Docker Compose с .env конфигурацией.

---

## Рекомендуемый подход

### Архитектурные изменения

**До (Docker Swarm):**
```
GitHub Actions → SSH → Server → docker stack deploy
                 (SSH_PRIVATE_KEY, SERVER, SERVERUSER)
```

**После (Docker Compose):**
```
GitHub Actions → Docker Hub → Server → docker-compose pull && up -d
(build & push only)              (manual or cron)
```

### Критические файлы для изменения

| Файл | Изменения |
|-------|-----------|
| [docker-compose.yml](docker-compose.yml) | Конвертация из Swarm в Docker Compose |
| [api-service/app/main.py](api-service/app/main.py:11-16) | Чтение `API_TOKEN` из env вместо `/run/secrets/` |
| [telegram-service/main.py](telegram-service/main.py:29-35) | Чтение `TELEGRAM_TOKEN` из env вместо `/run/secrets/` |
| [download-service/update-yt-dlp.sh](download-service/update-yt-dlp.sh) | **НОВЫЙ** скрипт для sidecar паттерна |
| [.env.example](.env.example) | **НОВЫЙ** шаблон конфигурации |
| [.github/workflows/deploy.yml](.github/workflows/deploy.yml) | **УДАЛИТЬ** весь файл |
| [.github/workflows/build.yml](.github/workflows/build.yml) | Упростить, убрать schedule trigger |

---

## Детали реализации

### 1. Новый docker-compose.yml

```yaml
services:
  api-service:
    image: ${DOCKERHUB_USERNAME}/video-downloader-api:latest
    restart: unless-stopped
    environment:
      - API_TOKEN=${API_TOKEN}
    networks:
      - app-network
    depends_on:
      - redis

  telegram-service:
    image: ${DOCKERHUB_USERNAME}/video-downloader-telegram:latest
    restart: unless-stopped
    environment:
      - TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
      - API_URL=http://api-service:8000
      - VLESS_URL=${VLESS_URL:-}
      - REDIS_HOST=redis
    volumes:
      - downloads:/app/downloads
    networks:
      - app-network
    depends_on:
      - api-service
      - redis

  download-service:
    image: ${DOCKERHUB_USERNAME}/video-downloader-download:latest
    restart: unless-stopped
    environment:
      - REDIS_HOST=redis
    volumes:
      - downloads:/app/downloads
    networks:
      - app-network
    depends_on:
      - redis

  redis:
    image: redis:alpine
    restart: unless-stopped
    networks:
      - app-network
    volumes:
      - redis-data:/data

  watchtower:
    image: containrrr/watchtower
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - WATCHTOWER_POLL_INTERVAL=300
      - WATCHTOWER_CLEANUP=true
      - WATCHTOWER_INCLUDE_RESTARTING=true
    networks:
      - app-network

  yt-dlp-updater:
    image: ${DOCKERHUB_USERNAME}/video-downloader-download:latest
    restart: unless-stopped
    command: /app/update-yt-dlp.sh
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - CONTAINER_NAME=video-downloader-download-service-1
      - UPDATE_INTERVAL=86400
    networks:
      - app-network

networks:
  app-network:
    driver: bridge

volumes:
  downloads:
  redis-data:
```

### 2. Изменение api-service/app/main.py

**Было (строки 11-16):**
```python
def get_api_token():
    try:
        with open("/run/secrets/api_token", "r") as secret_file:
            return secret_file.read().strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading secret: {e}")
```

**Станет:**
```python
def get_api_token():
    api_token = os.getenv("API_TOKEN")
    if not api_token:
        raise HTTPException(status_code=500, detail="API_TOKEN not set")
    return api_token
```

### 3. Изменение telegram-service/main.py

**Было (строки 29-35):**
```python
def get_telegram_token() -> str:
    try:
        with open("/run/secrets/telegram_token", "r") as secret_file:
            return secret_file.read().strip()
    except Exception as e:
        logger.error(f"Error reading Telegram token: {e}")
        raise HTTPException(status_code=500, detail="Failed to load Telegram token")
```

**Станет:**
```python
def get_telegram_token() -> str:
    telegram_token = os.getenv("TELEGRAM_TOKEN")
    if not telegram_token:
        logger.error("TELEGRAM_TOKEN not set")
        raise HTTPException(status_code=500, detail="TELEGRAM_TOKEN not set")
    return telegram_token
```

### 4. НОВЫЙ download-service/update-yt-dlp.sh

```bash
#!/bin/bash
set -e

UPDATE_INTERVAL=${UPDATE_INTERVAL:-86400} # 24 часа
CONTAINER_NAME=${CONTAINER_NAME:-video-downloader-download-service-1}

while true; do
    echo "[$(date)] Checking yt-dlp updates..."
    
    # Обновление yt-dlp в запущенном контейнере
    docker exec $CONTAINER_NAME yt-dlp -U
    
    if [ $? -eq 0 ]; then
        echo "[$(date)] yt-dlp updated successfully, restarting container..."
        docker restart $CONTAINER_NAME
    else
        echo "[$(date)] No updates available or update failed"
    fi
    
    echo "[$(date)] Sleeping for $UPDATE_INTERVAL seconds..."
    sleep $UPDATE_INTERVAL
done
```

### 5. НОВЫЙ .env.example

```bash
# Docker Hub Configuration
DOCKERHUB_USERNAME=eevarn

# API Authentication
API_TOKEN=your_api_token_here

# Telegram Configuration
TELEGRAM_TOKEN=your_telegram_bot_token_here

# Optional VLESS Proxy (leave empty if not needed)
VLESS_URL=

# yt-dlp Updater Configuration (seconds, 86400 = 24 hours)
UPDATE_INTERVAL=86400
```

### 6. УДАЛИТЬ .github/workflows/deploy.yml

Весь файл удаляется — SSH-деплой больше не нужен.

### 7. Упростить .github/workflows/build.yml

**Убрать schedule trigger:**
```yaml
on:
  push:  # оставить только push
  # schedule:  # УДАЛИТЬ эти строки
  #   - cron: '0 4 * * 1'
```

---

## Пошаговый план миграции

### Phase 1: Изменения кода (локально)

1. Обновить [api-service/app/main.py](api-service/app/main.py:11-16)
2. Обновить [telegram-service/main.py](telegram-service/main.py:29-35)
3. Создать [download-service/update-yt-dlp.sh](download-service/update-yt-dlp.sh)
4. Создать [.env.example](.env.example)
5. Обновить [docker-compose.yml](docker-compose.yml)
6. Упростить [.github/workflows/build.yml](.github/workflows/build.yml)
7. Удалить [.github/workflows/deploy.yml](.github/workflows/deploy.yml)
8. Добавить `.env` в `.gitignore`
9. Тест локально: `docker-compose up --build`

### Phase 2: Деплой на сервер

```bash
# 1. Остановить текущий Swarm stack
docker stack rm video-downloader
sleep 5

# 2. Покинуть Swarm mode
docker swarm leave --force

# 3. Создать .env файл (chmod 600!)
cat > .env << 'EOF'
DOCKERHUB_USERNAME=eevarn
API_TOKEN=your_actual_api_token
TELEGRAM_TOKEN=your_actual_telegram_token
VLESS_URL=
UPDATE_INTERVAL=86400
EOF
chmod 600 .env

# 4. Запустить новый Docker Compose stack
docker-compose up -d

# 5. Проверить статус
docker-compose ps
docker-compose logs -f
```

### Phase 3: Cleanup

```bash
# Удалить старые Swarm секреты и сети
docker secret ls
docker network ls
docker network rm video-downloader_downloader 2>/dev/null || true
```

---

## Верификация

После миграции проверить:

1. **Все сервисы запущены:**
   ```bash
   docker-compose ps
   ```
   
2. **API доступен:**
   ```bash
   curl -H "Authorization: Bearer $API_TOKEN" http://localhost:8000/health
   ```

3. **Telegram бот отвечает:**
   - Отправить `/start` или ссылку боту
   
4. **Watchtower следит за образами:**
   ```bash
   docker logs video-downloader-watchtower-1
   ```

5. **yt-dlp-updater работает:**
   ```bash
   docker logs video-downloader-yt-dlp-updater-1
   ```

6. **Загрузка видео работает:**
   - Отправить YouTube ссылку боту

---

## Rollback план (если что-то пойдёт не так)

```bash
# Остановить Docker Compose
docker-compose down

# Переинициализировать Swarm
docker swarm init --advertise-addr eth0

# Восстановить старый docker-compose.yml из git
git checkout HEAD~1 docker-compose.yml

# Создать Swarm секреты
echo "your_api_token" | docker secret create api_token -
echo "your_telegram_token" | docker secret create telegram_token -

# Передеплоить
docker stack deploy -c docker-compose.yml video-downloader
```

---

## Преимущества новой архитектуры

| Аспект | Было (Swarm) | Стало (Compose) |
|--------|--------------|-----------------|
| **Сложность** | Overlay сети, Swarm mode, stack deploy | Стандартный Docker Compose |
| **Деплой** | SSH через GitHub Actions | Локально или cron на сервере |
| **Безопасность** | SSH ключи в GitHub Secrets | .env файл на сервере (chmod 600) |
| **Конфигурация** | Docker Secrets | Environment variables |
| **Сеть** | --network host для download-service | Bridge сеть (достаточно для YouTube) |
| **Обновление yt-dlp** | Weekly rebuild + entrypoint | Sidecar контейнер (каждые 24 часа) |
| **Локальная разработка** | Сложно (требует Swarm) | Просто (docker-compose up) |
| **Стоимость CI/CD** | SSH deployment runtime | Только build & push |

---

## Автоматические обновления

**Watchtower** (каждые 5 минут):
- Проверяет новые образы в Docker Hub
- Перезапускает контейнеры с новыми образами
- Удаляет старые образы (`WATCHTOWER_CLEANUP=true`)

**yt-dlp-updater** (каждые 24 часа):
- Обновляет yt-dlp binary внутри download-service
- Перезапускает download-service
- Использует Docker socket через `/var/run/docker.sock`

**Ручное обновление:**
```bash
docker-compose pull
docker-compose up -d
```
