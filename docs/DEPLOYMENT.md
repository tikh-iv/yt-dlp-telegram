# Deployment Guide

## Overview

This bot uses a simple Docker Compose setup with automatic updates via Watchtower.

**Architecture:**
- GitHub Actions → Build & push to Docker Hub only
- Server → Pull & run with docker-compose
- Watchtower → Auto-update containers every 5 minutes

---

## First-time Setup

### 1. Clone the repository

```bash
git clone <your-repo-url> ~/video-downloader
cd ~/video-downloader
```

### 2. Create environment file

```bash
cp .env.example .env
nano .env
```

Fill in the actual values:
- `API_TOKEN` - Your API authentication token
- `TELEGRAM_TOKEN` - Your Telegram bot token from @BotFather

### 3. Create downloads directory

```bash
mkdir -p /home/ivan/downloads
```

### 4. Start the bot

```bash
docker-compose up -d
```

---

## How Updates Work

### Automatic Updates (Watchtower)

**Watchtower** checks every 5 minutes:
- If a new image is pushed to Docker Hub
- It pulls the new image
- Restarts the container with the new image
- Removes old images to save space

**No manual intervention needed!**

### yt-dlp Updates

**GitHub Actions** rebuilds images weekly (every Monday 04:00 UTC):
- Pulls latest yt-dlp version
- Builds fresh images
- Pushes to Docker Hub
- Watchtower picks up the update within 5 minutes

---

## Manual Operations

### Check container status

```bash
docker-compose ps
```

### View logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f telegram-service
```

### Manual update

```bash
docker-compose pull
docker-compose up -d
```

### Restart bot

```bash
docker-compose restart
```

### Stop bot

```bash
docker-compose down
```

---

## Troubleshooting

### Bot not responding

```bash
# Check logs
docker-compose logs telegram-service

# Check if container is running
docker-compose ps
```

### Download issues

```bash
# Check download-service logs
docker-compose logs download-service

# Verify downloads directory
ls -la /home/ivan/downloads
```

### Watchtower not updating

```bash
# Check watchtower logs
docker-compose logs watchtower

# Force manual update
docker-compose pull
docker-compose up -d
```

---

## Environment Variables Reference

| Variable | Description | Example |
|----------|-------------|---------|
| `API_TOKEN` | Token for API authentication | `your-secret-token` |
| `TELEGRAM_TOKEN` | Bot token from @BotFather | `123456:ABC-DEF...` |

---

## GitHub Actions Workflow

**Triggered by:**
- Push to main branch
- Scheduled: Every Monday 04:00 UTC

**What it does:**
1. Builds 3 Docker images (api, download, telegram)
2. Pushes to Docker Hub
3. Watchtower picks up changes within 5 minutes

**What it does NOT do:**
- Does NOT SSH to your server
- Does NOT deploy anything
- You are in control of your server
