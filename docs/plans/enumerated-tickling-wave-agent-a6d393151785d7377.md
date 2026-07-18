# Docker and Deployment Infrastructure Analysis

## Current Docker Architecture

### Services Overview
The project consists of 4 main services:

1. **api-service** (Python/FastAPI)
   - Base image: `python:3.11`
   - Purpose: REST API for download management
   - Port: 8000
   - Dependencies: fastapi, uvicorn, requests, dotenv, redis

2. **telegram-service** (Python/Telegram Bot)
   - Base image: `python:3.11`
   - Purpose: Telegram bot interface
   - Special feature: Xray proxy integration for circumventing censorship
   - Dependencies: redis, requests[socks], fastapi
   - Volume: `/home/ivan/downloads:/app/downloads`

3. **download-service** (Python/yt-dlp worker)
   - Base image: `python:3.11`
   - Purpose: Actual video downloading using yt-dlp
   - Dependencies: redis, PySocks>=1.7.1, curl_cffi>=0.10,<0.15
   - Special tools: ffmpeg, yt-dlp (installed via curl)

4. **redis** (Cache/Queue)
   - Base image: `redis:alpine`
   - Port: 6379

5. **watchtower** (Auto-update service)
   - Base image: `containrrr/watchtower`
   - Purpose: Automatic container updates from Docker Hub
   - Poll interval: 300 seconds

## Docker Swarm Specific Features (NEED REMOVAL)

### 1. Secrets Management
```yaml
secrets:
  api_token:
    external: true
  telegram_token:
    external: true
```
**Issue**: Uses Swarm secrets that must be pre-created
**Removal**: Replace with environment variables or use Kubernetes secrets

### 2. Overlay Networks
```yaml
networks:
  downloader:
    driver: overlay
    attachable: true
```
**Issue**: Swarm-specific overlay driver
**Removal**: Change to bridge driver for compose, or use Kubernetes network policies

### 3. Deploy Constraints & Policies
```yaml
deploy:
  restart_policy:
    condition: on-failure
    delay: 5s
    max_attempts: 3
    window: 60s
  placement:
    constraints:
      - node.role == manager
```
**Issue**: Swarm-specific deployment configuration
**Removal**: Use docker-compose restart policies or Kubernetes deployment strategies

### 4. Stack Commands
Current deployment uses:
- `docker stack deploy` 
- `docker stack rm`
- `docker swarm init`

**Issue**: Stack commands require Swarm mode
**Removal**: Use standard `docker-compose up` commands or Kubernetes deployments

## Environment Variable Handling

### Current Approach
- Uses `${VARIABLE}` syntax in docker-compose.yml
- Mix of environment variables and Swarm secrets
- GitHub Actions injects secrets during deployment

### Complexity Issues
1. **Hybrid approach**: Some vars as env vars, others as Swarm secrets
2. **Secret creation**: Requires manual Swarm secret creation in deployment script
3. **Hardcoded paths**: Volume paths like `/home/ivan/downloads` are hardcoded

### Variables in Use
- `API_TOKEN` (Swarm secret + env var)
- `TELEGRAM_TOKEN` (Swarm secret + env var)  
- `VLESS_URL` (env var for Xray proxy)
- `DOCKERHUB_USERNAME` (env var for auth)
- `REDIS_HOST` (env var, different values for different services)

## yt-dlp Management

### Installation Method
**Current**: Binary installation in Dockerfile
```dockerfile
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
    -o /usr/local/bin/yt-dlp && chmod +x /usr/local/bin/yt-dlp
```

### Update Mechanism
**Current**: Runtime update in entrypoint.sh
```bash
yt-dlp -U || true
```

### Build Strategy
- **Scheduled builds**: GitHub Actions cron job every Monday at 04:00 UTC
- **Force rebuild**: `no-cache: true` for download-service
- **Latest tag**: Always uses `:latest` Docker images

### Watchtower Integration
- Polls Docker Hub every 300 seconds
- Automatically updates running containers
- Cleans up old images
- Includes restarting containers

## Swarm-Specific Complexity

### 1. Deployment Script Complexity
The `.github/workflows/deploy.yml` contains Swarm-specific logic:
- Swarm initialization check (`docker node ls`)
- Swarm init command (`docker swarm init`)
- Stack removal and cleanup
- Manual download-service deployment with host networking

### 2. Host Networking Workaround
```bash
docker run -d --name download-service \
  --network host \  # Swarm overlay bypass
  --restart unless-stopped \
  -v /home/ivan/downloads:/app/downloads \
  -e REDIS_HOST=127.0.0.1 \
  eevarn/video-downloader-download:latest
```
**Issue**: Special case for download-service to avoid overlay network issues

### 3. Secret Management Complexity
```bash
echo "${{ secrets.API_TOKEN }}" | docker secret create api_token - 2>/dev/null || \
  echo "Secret api_token already exists, skipping..."
```
**Issue**: Try/catch pattern for secret creation shows Swarm secret management friction

### 4. Network Cleanup
```bash
docker network rm video-downloader_downloader 2>/dev/null || true
```
**Issue**: Manual network cleanup indicates Swarm networking issues

## Alternative: Kubernetes Deployment

The project also has Kubernetes manifests in `/k8s/manifests/` that show:
- Proper secret management (SealedSecrets)
- Resource limits and requests
- Health checks (liveness/readiness probes)
- Rolling update strategies
- Service exposure (ClusterIP)

## Recommendations for Simplification

### Immediate Changes Needed:
1. **Remove Swarm secrets** - Use environment variables consistently
2. **Remove deploy section** - Use standard docker-compose restart policies
3. **Remove overlay network** - Use bridge driver
4. **Simplify deployment** - Use standard docker-compose commands
5. **Remove host networking workaround** - Fix the underlying network issue

### Medium-term Improvements:
1. **Unified environment management** - Use .env files with docker-compose
2. **Simplify yt-dlp updates** - Remove runtime update, rely on rebuilds
3. **Remove Watchtower dependency** - Use proper deployment pipeline
4. **Standardize volume paths** - Use relative paths or proper volume management

### Long-term Considerations:
1. **Kubernetes adoption** - Existing K8s manifests show better practices
2. **Proper CI/CD** - Replace Watchtower with proper deployment automation
3. **GitOps** - Use proper configuration management instead of manual deployments
