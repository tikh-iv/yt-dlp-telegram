# Deployment Refactoring Plan: Docker Swarm → Docker Compose

## Context

This refactoring addresses the complexity of the current Docker Swarm deployment with GitHub Actions-based SSH access. The current setup requires:
- SSH credentials stored in GitHub Actions
- Docker Swarm initialization and management
- Complex deployment orchestration via GitHub Actions
- Swarm-specific networking and secret management

The goal is to simplify the deployment while maintaining all functionality and improving security by removing SSH access from GitHub Actions.

## Current Architecture Analysis

### GitHub Actions (Complex)
- **build.yml**: Weekly scheduled builds + push triggers for Docker images
- **deploy.yml**: SSH-based deployment with Swarm stack management
- **Secrets required**: SSH_PRIVATE_KEY, SERVER, SERVERUSER, API_TOKEN, TELEGRAM_TOKEN, DOCKERHUB_TOKEN, VLESS_URL

### Docker Configuration (Swarm-specific)
- **Overlay networking** with VXLAN encapsulation
- **Swarm secrets** for sensitive data
- **Deploy configurations** with placement constraints
- **Host networking workaround** for download-service (YouTube access)
- **Watchtower** for automatic container updates

### yt-dlp Management (Triple-layer)
1. **Runtime updates**: `yt-dlp -U` in entrypoint.sh
2. **Scheduled rebuilds**: Weekly Monday 04:00 UTC builds
3. **Watchtower monitoring**: 5-minute polling for new images

## Recommended Approach

### Core Principles
1. **Simplicity over complexity**: Use standard Docker Compose patterns
2. **Security through reduced attack surface**: Remove SSH access from GitHub
3. **Maintain all functionality**: Preserve host networking workaround, automatic updates
4. **Standard tooling**: Leverage Watchtower for auto-updates instead of custom solutions

### Implementation Strategy

#### Phase 1: GitHub Actions Simplification

**Remove SSH Deployment Entirely**
- Delete `.github/workflows/deploy.yml` completely
- Remove GitHub secrets: SSH_PRIVATE_KEY, SERVER, SERVERUSER
- Keep only DOCKERHUB_USERNAME and DOCKERHUB_TOKEN

**Simplify Build Workflow** (`.github/workflows/build.yml`)
```yaml
name: CI - Build and Push Docker Images

on:
  push:
    branches: [ main ]
  workflow_dispatch:  # Allow manual triggers
  schedule:
    # Monthly on the 1st at 02:00 UTC (reduced from weekly)
    - cron: '0 2 1 * *'

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Login to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      
      - name: Build and push API service
        uses: docker/build-push-action@v4
        with:
          context: ./api-service
          tags: ${{ secrets.DOCKERHUB_USERNAME }}/video-downloader-api:latest
          push: true
      
      - name: Build and push Download service  
        uses: docker/build-push-action@v4
        with:
          context: ./download-service
          tags: ${{ secrets.DOCKERHUB_USERNAME }}/video-downloader-download:latest
          push: true
          no-cache: true  # Ensure fresh yt-dlp builds
      
      - name: Build and push Telegram service
        uses: docker/build-push-action@v4
        with:
          context: ./telegram-service
          tags: ${{ secrets.DOCKERHUB_USERNAME }}/video-downloader-telegram:latest
          push: true
```

#### Phase 2: Docker Compose Refactoring

**Create Simplified docker-compose.yml**
```yaml
services:
  api-service:
    image: ${DOCKERHUB_USERNAME:-eevarn}/video-downloader-api:latest
    ports:
      - "8000:8000"
    environment:
      - API_TOKEN=${API_TOKEN}
    restart: unless-stopped
    networks:
      - downloader

  telegram-service:
    image: ${DOCKERHUB_USERNAME:-eevarn}/video-downloader-telegram:latest
    environment:
      - TELEGRAM_TOKEN=${TELEGRAM_TOKEN}
      - API_URL=http://api-service:8000
      - VLESS_URL=${VLESS_URL}
    depends_on:
      - api-service
    volumes:
      - /home/ivan/downloads:/app/downloads
    restart: unless-stopped
    networks:
      - downloader

  download-service:
    image: ${DOCKERHUB_USERNAME:-eevarn}/video-downloader-download:latest
    environment:
      - REDIS_HOST=redis
    volumes:
      - /home/ivan/downloads:/app/downloads
    # Keep host networking for YouTube access workaround
    network_mode: host
    restart: unless-stopped

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
    restart: unless-stopped
    networks:
      - downloader

  watchtower:
    image: containrrr/watchtower
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - WATCHTOWER_POLL_INTERVAL=300
      - WATCHTOWER_CLEANUP=true
      - WATCHTOWER_INCLUDE_RESTARTING=true
    restart: unless-stopped

networks:
  downloader:
    driver: bridge
```

**Key Changes:**
- Removed all `deploy.*` sections (Swarm-specific)
- Removed `secrets.*` section (Swarm secrets)
- Changed network driver from `overlay` to `bridge`
- Added `restart: unless-stopped` to all services
- Simplified `network_mode: host` for download-service
- Added `${DOCKERHUB_USERNAME:-eevarn}` for flexibility

#### Phase 3: Environment Management

**Create `.env.example`**
```bash
# Docker Hub Configuration
DOCKERHUB_USERNAME=eevarn

# API Authentication
API_TOKEN=your_secret_api_token_here

# Telegram Bot Configuration
TELEGRAM_TOKEN=your_telegram_bot_token_here

# Proxy Configuration (Optional)
VLESS_URL=https://your-proxy-url-here
```

**Create server deployment script** (`deploy.sh`)
```bash
#!/bin/bash
set -e

echo "Deploying yt-dlp-telegram..."

# Copy docker-compose.yml to server directory
cp docker-compose.yml ~/video-downloader/

# Change to deployment directory
cd ~/video-downloader

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "Please edit .env with your actual values"
    exit 1
fi

# Create downloads directory
mkdir -p /home/ivan/downloads

# Login to Docker Hub
echo "Logging into Docker Hub..."
docker login

# Pull latest images
echo "Pulling latest images..."
docker-compose pull

# Restart services
echo "Restarting services..."
docker-compose down
docker-compose up -d

echo "Deployment complete!"
```

#### Phase 4: Server-Side Setup

**Initial Server Setup Instructions**
1. Create deployment directory:
   ```bash
   mkdir -p ~/video-downloader
   cd ~/video-downloader
   ```

2. Copy files to server:
   - `docker-compose.yml`
   - `.env.example` (rename to `.env` and configure)

3. Configure environment:
   ```bash
   cp .env.example .env
   chmod 600 .env  # Secure permissions
   nano .env  # Edit with actual values
   ```

4. Start services:
   ```bash
   docker-compose up -d
   ```

#### Phase 5: yt-dlp Update Strategy

**Maintain Dual Approach:**
1. **Runtime updates**: Keep existing `yt-dlp -U` in [`download-service/entrypoint.sh`](download-service/entrypoint.sh)
2. **Monthly rebuilds**: Reduced frequency from weekly to monthly
3. **Watchtower**: Continues automatic container updates

**Rationale:**
- Runtime updates handle YouTube API changes quickly
- Monthly rebuilds ensure fresh base images and dependencies
- Watchtower provides continuous deployment for new images

## Critical Files to Modify

### Files to Change
- [`.github/workflows/build.yml`](.github/workflows/build.yml) - Simplify triggers and reduce schedule
- [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) - DELETE entirely
- [`docker-compose.yml`](docker-compose.yml) - Remove Swarm specifics, add standard Compose patterns

### Files to Create  
- `.env.example` - Environment variable template
- `deploy.sh` - Server deployment script
- `UPDATE.md` - Deployment documentation

### Files That Remain Unchanged
- [`api-service/Dockerfile`](api-service/Dockerfile)
- [`telegram-service/Dockerfile`](telegram-service/Dockerfile)  
- [`download-service/Dockerfile`](download-service/Dockerfile)
- [`download-service/entrypoint.sh`](download-service/entrypoint.sh) - Keep yt-dlp update logic

## Security Considerations

### Improvements
- **Eliminates SSH exposure**: No more SSH credentials in GitHub Actions
- **Reduced attack surface**: GitHub Actions only builds images, doesn't access server
- **Local environment management**: `.env` file with proper permissions (600)

### Best Practices
- Store `.env` securely with restricted permissions: `chmod 600 .env`
- Consider encrypting `.env` for backup purposes
- Use Docker secrets for sensitive data if additional security needed
- Regular security updates via Watchtower automatic updates

## Trade-offs Analysis

### Benefits
1. **Significantly simpler**: Standard Docker Compose vs Swarm orchestration
2. **Enhanced security**: No SSH credentials in GitHub Actions  
3. **Better maintainability**: Easier troubleshooting and local development
4. **Cost efficiency**: Build only when needed vs forced weekly schedule
5. **Standard patterns**: Uses familiar Docker Compose conventions

### Considerations
1. **Manual initial setup**: One-time server configuration required
2. **Environment variables**: Slightly less secure than Swarm secrets (mitigated with file permissions)
3. **No Swarm scaling**: Not applicable for single-server use case anyway
4. **Manual deployment trigger**: Need to run `deploy.sh` or wait for Watchtower

## Implementation Timeline

**Total: ~5.5 hours**

### Phase 1: GitHub Actions (30 min)
- Remove deploy.yml workflow
- Update build.yml triggers
- Clean up GitHub secrets

### Phase 2: Docker Compose (1 hour)
- Refactor docker-compose.yml
- Test locally with `docker-compose up`
- Verify networking and host networking workaround

### Phase 3: Environment Setup (30 min)
- Create .env.example and .env files
- Create deployment scripts
- Test environment variable loading

### Phase 4: Server Migration (2 hours)
- SSH into server (manual, one-time)
- Setup deployment directory
- Configure .env file
- Test deployment with docker-compose
- Verify all services start correctly

### Phase 5: Testing & Validation (1 hour)
- Test YouTube download functionality
- Verify Watchtower automatic updates
- Test manual deployment process
- Validate all services communicate correctly

### Phase 6: Documentation (30 min)
- Create deployment guide
- Document troubleshooting steps
- Update README with new deployment method

## Verification Plan

### Testing Checklist
- [ ] All services start correctly: `docker-compose ps`
- [ ] API responds to health checks: `curl http://localhost:8000/health`
- [ ] Telegram bot responds to commands
- [ ] YouTube download functionality works
- [ ] Watchtower updates containers when new images appear
- [ ] Host networking workaround still functions
- [ ] Environment variables load correctly
- [ ] Manual deployment script works

### Rollback Strategy
If issues arise, rollback steps:
1. Stop new services: `docker-compose down`
2. Pull old docker-compose.yml from git history
3. Restart old Swarm stack: `docker stack deploy -c docker-compose.yml video-downloader`

## Next Steps

Once this plan is approved:
1. Create implementation tasks in project management system
2. Set up milestone tracking for the ~5.5 hour implementation
3. Schedule maintenance window for server migration
4. Prepare rollback procedures in case of issues
5. Communicate changes to any relevant stakeholders

This refactoring maintains all current functionality while significantly reducing complexity and improving security posture.