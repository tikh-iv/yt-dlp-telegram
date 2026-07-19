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

### 5. (Optional) Add YouTube cookies

Some YouTube videos require Sign in to download (error: `Sign in to confirm you're not a bot`). To support them, export cookies from a logged-in browser and place them on the server — yt-dlp will pick them up automatically; if the file is absent, the bot works without cookies.

```bash
# Create config dir next to docker-compose.yml
mkdir -p config

# Export cookies from Chrome/Firefox via extension
# "Get cookies.txt LOCALLY" → save as config/cookies.txt

ls config/cookies.txt
```

Restart download-service to make the new cookies appear in logs:

```bash
docker compose restart download-service
docker compose logs --tail=5 download-service
# should print: "Starting download-service... (cookies: /app/cookies/cookies.txt)"
```

#### How the read-only cookies.txt is handled

`docker-compose.yml` mounts `./config` into the container **read-only** (`./config:/app/config:ro`) — the cookies file is a secret and the container must not modify it. But yt-dlp writes the session cookies back to the file it read from at the end of each run (`--cookies FILE` → `cookies.save`), which used to fail with:

```
OSError: [Errno 30] Read-only file system: '/app/config/cookies.txt'
```

`download-service/entrypoint.sh` now copies `/app/config/cookies.txt` (read-only, from the host) into `/app/cookies/cookies.txt` (a writable container-local path) on every container start. `download-service/main.py` then points `--cookies` at that writable copy. Result: yt-dlp can save its session to the writable copy, while the secret on the host stays untouched.

So after changing `config/cookies.txt`, **restart `download-service`** so the entrypoint re-copies the file.

### 6. Make sure yt-dlp runs in `download-service`, not `telegram-service`

If your `docker compose logs telegram-service` shows yt-dlp tracebacks, you are running an outdated image: the download logic was refactored out of `telegram-service` into `download-service`. On a correct setup, only `download-service` invokes yt-dlp.

```bash
docker compose pull
docker compose up -d
docker compose logs --tail=20 download-service  # yt-dlp output should be here
```

### 7. PO Token provider (bgutil) — required for YouTube since 2025-2026

YouTube now requires a **PO Token** (Proof-of-Origin) in addition to cookies. Without it, even valid cookies get rejected with `playability status: LOGIN_REQUIRED` → `Sign in to confirm you're not a bot`. Cookies alone no longer help.

This stack ships a [bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider) sidecar that generates PO Tokens on demand. yt-dlp calls it automatically via the `bgutil-ytdlp-pot-provider` plugin baked into the `download-service` image.

Components:

| Where | What |
|---|---|
| `docker-compose.yml` service `potoken-service` | `brainicism/bgutil-ytdlp-pot-provider:1.3.1` — token server (port 4416) |
| `download-service/Dockerfile` | `pip install bgutil-ytdlp-pot-provider==1.3.1` — yt-dlp plugin |
| `download-service/main.py` `potoken_args()` | passes `--extractor-args youtubepot-bgutilhttp:base_url=http://potoken-service:4416` to every yt-dlp call |

#### Why pinned to 1.3.1

The plugin inside `download-service` and the `potoken-service` server **must share the same major version** — otherwise the plugin silently refuses to talk to the server and PO Token generation fails. Both are pinned to `1.3.1`. Watchtower will NOT auto-bump (pinned tag); bump manually in both places together when you want a new release.

#### Verify it works

```bash
# 1. Provider container is up
docker compose ps potoken-service

# 2. Plugin is loaded and registered as a provider
docker compose exec download-service yt-dlp -v --simulate "https://www.youtube.com/watch?v=dQw4w9WgXcQ" 2>&1 | grep "PO Token Providers"
# expect: [debug] [youtube] [pot] PO Token Providers: bgutil:http-1.3.1 (external), ...

# 3. Startup log
docker compose logs --tail=10 download-service | grep potoken
# expect: Starting download-service... (potoken provider: http://potoken-service:4416)
```

#### Disable PO Token (optional)

Set `POTOKEN_URL=` (empty) in `download-service` env, or remove the env var. `potoken_args()` returns `[]` when the URL is empty, so yt-dlp runs without `--extractor-args`.

#### Caveat

A PO Token does **not** guarantee bypassing bot detection. If the server's IP is heavily flagged, you may additionally need cookies or an egress proxy. See [yt-dlp PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#po-token-guide).

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
| `POTOKEN_URL` | bgutil PO Token provider URL (set in compose, not `.env`) | `http://potoken-service:4416` |
| `REDIS_HOST` | Redis hostname for service name resolution | `redis` |
| `COOKIES_FILE` | Path to yt-dlp cookies file (writable) | `/app/cookies/cookies.txt` |

---

## GitHub Actions Workflow

**Triggered by:**
- Push to main branch
- Scheduled: Every Monday 04:00 UTC

**What it does:**
1. Builds 4 Docker images (api, download, telegram, cleanup)
2. Pushes to Docker Hub
3. Watchtower picks up changes within 5 minutes

> Note: the `potoken-service` uses a prebuilt public image (`brainicism/bgutil-ytdlp-pot-provider:1.3.1`) — it is **not** built by this workflow. Watchtower will not auto-update it because the tag is pinned.

**What it does NOT do:**
- Does NOT SSH to your server
- Does NOT deploy anything
- You are in control of your server
