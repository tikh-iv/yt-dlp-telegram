# Simplified Deployment Architecture - Docker Compose Migration Plan

## Executive Summary
This plan outlines the migration from Docker Swarm to standard Docker Compose for the yt-dlp-telegram project, focusing on simplification, removing SSH deployment, and implementing a sidecar pattern for yt-dlp updates.

## Current State Analysis

### Current Architecture
- **Orchestration**: Docker Swarm with overlay networks
- **Deployment**: GitHub Actions SSH deployment via deploy.yml
- **Secrets Management**: Docker Swarm secrets (api_token, telegram_token)
- **Services**: api-service, telegram-service, download-service, redis, watchtower
- **Network**: download-service runs with --network host (bypass overlay VXLAN)
- **Updates**: Triple yt-dlp update (build time + entrypoint + weekly rebuild)

### Key Findings from Codebase Analysis
1. **Service Communication**: All services communicate via Redis queues
2. **Network Configuration**: download-service currently requires --network host for YouTube access
3. **Secrets Usage**: API and Telegram tokens read from `/run/secrets/` files
4. **Environment Variables**: 
   - REDIS_HOST (default: "redis") 
   - API_URL (telegram-service → api-service)
   - VLESS_URL (optional proxy configuration)

## New Architecture Design

### 1. Deployment Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     GitHub Actions                           │
│                   (Build & Push Only)                        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                        Docker Hub                            │
│              (Image Registry & Distribution)                 │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   Server (Standard Docker)                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Docker Compose Stack                     │  │
│  │  ┌──────────────┐  ┌──────────────┐                  │  │
│  │  │ api-service  │  │   redis      │                  │  │
│  │  └──────────────┘  └──────────────┘                  │  │
│  │  ┌──────────────┐  ┌──────────────┐                  │  │
│  │  │telegram-svc  │  │download-svc  │                  │  │
│  │  └──────────────┘  └──────────────┘                  │  │
│  │  ┌──────────────┐  ┌──────────────┐                  │  │
│  │  │  watchtower  │  │yt-dlp-updater│                  │  │
│  │  └──────────────┘  └──────────────┘                  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 2. Service Architecture Changes

#### Key Design Decisions

**Network Configuration**
- **Remove --network host**: Standard Docker Compose bridge networks are sufficient
- **Service Discovery**: Use Docker Compose service names as DNS names
- **Isolation**: All services on same network but properly isolated

**Configuration Management**
- **Replace secrets**: Environment variables via .env file
- **Simplicity**: Single source of truth for configuration
- **Security**: .env file permissions (chmod 600)

**Update Strategy**
- **Watchtower**: Handles container image updates (existing 5-minute polling)
- **Sidecar Pattern**: Dedicated yt-dlp-updater container for dependency updates
- **Separation of Concerns**: Container runtime vs dependency management

### 3. Detailed Component Design

#### A. GitHub Actions Simplification

**build.yml** (Keep & Simplify)
- Remove schedule trigger (no longer needed for weekly yt-dlp builds)
- Keep image building and pushing to Docker Hub
- Simplify to just CI/CD pipeline

**deploy.yml** (DELETE)
- Remove entire SSH deployment workflow
- Deployment becomes manual server-side operation

#### B. Docker Compose Configuration

**New docker-compose.yml Structure**
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

#### C. Sidecar yt-dlp Updater Design

**Update Mechanism**
- **Container**: Uses same image as download-service
- **Function**: Periodically updates yt-dlp binary and restarts download-service
- **Script**: New update-yt-dlp.sh script

**update-yt-dlp.sh Script**
```bash
#!/bin/bash
set -e

UPDATE_INTERVAL=${UPDATE_INTERVAL:-86400} # 24 hours
CONTAINER_NAME=${CONTAINER_NAME:-download-service}

while true; do
    echo "[$(date)] Checking yt-dlp updates..."
    
    # Update yt-dlp in the running container
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

#### D. Environment Configuration

**.env File Structure**
```bash
# Docker Hub Configuration
DOCKERHUB_USERNAME=eevarn

# API Authentication
API_TOKEN=your_api_token_here

# Telegram Configuration  
TELEGRAM_TOKEN=your_telegram_bot_token_here

# Optional VLESS Proxy (leave empty if not needed)
VLESS_URL=

# yt-dlp Updater Configuration
UPDATE_INTERVAL=86400
```

#### E. Application Code Changes

**api-service/app/main.py**
```python
# Change from Docker secrets to environment variable
def get_api_token():
    api_token = os.getenv("API_TOKEN")
    if not api_token:
        raise HTTPException(status_code=500, detail="API_TOKEN not set")
    return api_token
```

**telegram-service/main.py**
```python
# Change from Docker secrets to environment variable  
def get_telegram_token() -> str:
    telegram_token = os.getenv("TELEGRAM_TOKEN")
    if not telegram_token:
        logger.error("TELEGRAM_TOKEN not set")
        raise HTTPException(status_code=500, detail="TELEGRAM_TOKEN not set")
    return telegram_token
```

### 4. Implementation Steps

#### Phase 1: Code Updates (Local Development)
1. Update api-service/app/main.py - read API_TOKEN from env
2. Update telegram-service/main.py - read TELEGRAM_TOKEN from env
3. Create update-yt-dlp.sh script for download-service
4. Update download-service/Dockerfile - include update script
5. Create .env.example file
6. Update docker-compose.yml - convert to standard Compose
7. Simplify .github/workflows/build.yml
8. Delete .github/workflows/deploy.yml

#### Phase 2: Testing (Local)
1. Test with docker-compose up --build
2. Verify service communication
3. Test .env file loading
4. Verify volume mounts
5. Test watchtower functionality

#### Phase 3: Server Deployment
1. SSH to server
2. Stop existing Swarm stack: `docker stack rm video-downloader`
3. Leave Swarm mode: `docker swarm leave --force`
4. Create .env file with proper permissions
5. Start new Compose stack: `docker-compose up -d`
6. Verify all services are running

#### Phase 4: Cleanup
1. Remove unused Swarm networks
2. Remove unused Docker secrets
3. Clean up old images

### 5. Migration Challenges & Solutions

#### Challenge 1: Network Configuration
**Problem**: Current download-service uses --network host for YouTube access  
**Solution**: Standard Docker Compose bridge networks are sufficient for YouTube access

#### Challenge 2: Service Discovery
**Problem**: Services need to discover each other  
**Solution**: Docker Compose provides built-in DNS using service names

#### Challenge 3: Configuration Security
**Problem**: Moving from secrets to environment variables  
**Solution**: .env file with chmod 600 permissions, added to .gitignore

#### Challenge 4: Container Restart Coordination
**Problem**: yt-dlp updater needs to restart download-service  
**Solution**: Docker socket access and proper container naming

### 6. Rollback Strategy

If issues arise during migration:
1. Stop Docker Compose: `docker-compose down`
2. Re-initialize Swarm: `docker swarm init`
3. Restore old docker-compose.yml (Swarm version)
4. Redeploy: `docker stack deploy -c docker-compose.yml video-downloader`

### 7. Benefits of New Architecture

1. **Simplicity**: No Swarm complexity, standard Docker commands
2. **Security**: .env file instead of SSH deployment
3. **Maintainability**: Single docker-compose.yml file
4. **Flexibility**: Easy local development and testing
5. **Reliability**: Sidecar pattern for yt-dlp updates
6. **Cost**: Reduced GitHub Actions runtime (no SSH deployment)

### 8. Monitoring & Maintenance

**Health Checks**
- `docker-compose ps` - check service status
- `docker-compose logs` - view logs
- `docker exec -it <container> <command>` - debug

**Updates**
- Watchtower: Automatic image updates every 5 minutes
- yt-dlp-updater: Automatic dependency updates every 24 hours
- Manual: `docker-compose pull && docker-compose up -d`

**Backup**
- Redis data: Volume mount `redis-data:/data`
- Downloaded files: Volume mount `downloads:/app/downloads`
- Configuration: .env file (backup separately)

### 9. Security Considerations

1. **.env File**: chmod 600, never commit to git
2. **Docker Socket**: Only yt-dlp-updater and watchtower need access
3. **Network Isolation**: Single bridge network, no external exposure
4. **Token Security**: Environment variables instead of files

### 10. Next Steps

1. Review and approve this plan
2. Create implementation branch
3. Make code changes locally
4. Test thoroughly
5. Plan server migration window
6. Execute migration with rollback plan ready
7. Monitor and validate

