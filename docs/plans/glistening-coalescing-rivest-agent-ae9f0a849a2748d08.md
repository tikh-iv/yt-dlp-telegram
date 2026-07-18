# Docker Deployment Refactoring Plan

## Executive Summary

This plan transforms the current Docker Swarm + GitHub Actions SSH deployment into a simplified Docker Compose + environment-based deployment with automatic image updates. The refactoring eliminates server SSH access from GitHub Actions, removes Docker Swarm complexity, and maintains security while simplifying operations.

## Current Architecture Analysis

### Components
- **3 Services**: api-service, telegram-service, download-service + redis + watchtower
- **Docker Swarm**: Overlay networks, Swarm secrets, placement constraints
- **GitHub Actions**: CI (build/push) + CD (SSH deployment)
- **Secret Management**: Docker Swarm secrets created via GitHub Actions
- **yt-dlp Updates**: Runtime `yt-dlp -U` + weekly rebuilds with `no-cache: true`
- **Networking**: Host workaround for download-service (YouTube access)

### Pain Points
1. **Complex Deployment**: Docker Swarm adds unnecessary complexity for single-server deployment
2. **SSH Dependencies**: GitHub Actions requires SSH access to server
3. **Secret Management**: Swarm secrets require remote creation
4. **Maintenance Overhead**: Weekly builds for yt-d updates, Swarm management

## Target Architecture

### Simplified Components
- **Standard Docker Compose**: Remove Swarm-specific configurations
- **Environment Variables**: `.env` file for all configuration
- **Watchtower**: Keep for automatic image updates
- **GitHub Actions**: Build and push only (no SSH)
- **Server-side Operations**: Manual/automated pulling via Watchtower

### Benefits
- **Simplified Operations**: Standard Docker Compose commands
- **Better Security**: No SSH credentials in GitHub Actions
- **Maintainability**: Easier troubleshooting and local development
- **Flexibility**: Easy to add/remove services
- **Cost Efficiency**: Build only when needed, not weekly schedule

## Implementation Strategy

### Phase 1: GitHub Actions Simplification
**Objective**: Remove SSH deployment, keep only build/push functionality

#### 1.1 Simplify build.yml
- **Keep**: Existing build and push functionality
- **Remove**: Schedule trigger (no longer needed for weekly updates)
- **Add**: Manual workflow dispatch for on-demand builds

**Changes:**
```yaml
# Remove schedule trigger - build only on push or manual dispatch
on:
  push:
    branches: [ main ]
  workflow_dispatch:  # Allow manual triggering
```

#### 1.2 Delete deploy.yml
- **Remove entire file**: No longer needed
- **Remove secrets from GitHub**: SSH_PRIVATE_KEY, SERVER, SERVERUSER

### Phase 2: Docker Compose Refactoring
**Objective**: Convert from Swarm to standard Docker Compose

#### 2.1 Create docker-compose.prod.yml
- **Remove Swarm-specific configs**:
  - `deploy.*` sections
  - `secrets.*` sections  
  - `networks.driver: overlay`
  - `placement constraints`

- **Add standard Docker Compose features**:
  - `restart: unless-stopped` policy
  - Environment variable references
  - Standard bridge networking

- **Maintain special networking**:
  - Keep download-service with host networking for YouTube access
  - Use `network_mode: host` instead of Swarm workaround

#### 2.2 Create .env.example Template
```bash
# API Configuration
API_TOKEN=your_api_token_here
API_URL=http://api-service:8000

# Telegram Configuration  
TELEGRAM_TOKEN=your_telegram_bot_token_here

# Proxy Configuration
VLESS_URL=your_vless_url_here

# Docker Configuration
DOCKERHUB_USERNAME=eevarn
```

#### 2.3 Create .env.production Template
```bash
# Production environment variables
# Copy this file to .env on the server and fill in actual values
API_TOKEN=production_api_token
TELEGRAM_TOKEN=production_telegram_token  
VLESS_URL=production_vless_url
DOCKERHUB_USERNAME=eevarn
```

### Phase 3: Server-Side Setup
**Objective**: Enable automatic pulling and simplify operations

#### 3.1 Create deploy.sh Script
```bash
#!/bin/bash
set -e

echo "Deploying video-downloader stack..."

# Create downloads directory if needed
mkdir -p /home/ivan/downloads

# Login to Docker Hub
echo "Logging into Docker Hub..."
docker login -u $DOCKERHUB_USERNAME -p $DOCKERHUB_TOKEN

# Pull latest images
echo "Pulling latest images..."
docker-compose pull

# Restart services with new images
echo "Restarting services..."
docker-compose up -d --remove-orphans

# Clean up old images
echo "Cleaning up old images..."
docker image prune -af --filter "until=24h"

echo "Deployment completed successfully!"
```

#### 3.2 Create update.sh Script
```bash
#!/bin/bash
set -e

echo "Checking for updates..."

# Pull latest images
docker-compose pull

# Restart if images changed
if [ $? -eq 0 ]; then
    echo "New images found, restarting..."
    docker-compose up -d
else
    echo "No updates available"
fi
```

#### 3.3 Server Setup Instructions
```bash
# 1. Copy files to server
scp docker-compose.prod.yml serveruser@server:~/video-downloader/docker-compose.yml
scp .env.production serveruser@server:~/video-downloader/.env
scp deploy.sh serveruser@server:~/video-downloader/
scp update.sh serveruser@server:~/video-downloader/

# 2. Set up environment
ssh serveruser@server
cd ~/video-downloader
chmod +x deploy.sh update.sh
# Edit .env with actual values
vim .env

# 3. Initial deployment
./deploy.sh
```

### Phase 4: yt-dlp Update Strategy
**Objective**: Ensure yt-dlp stays current without weekly rebuilds

#### 4.1 Enhanced Runtime Updates
- **Keep existing**: `yt-dlp -U` in download-service entrypoint.sh
- **Add fallback**: Monthly rebuild schedule for catch-up

#### 4.2 Optional: Watchtower Integration
- **Current**: Watchtower already pulls new images
- **Enhancement**: Add specific yt-dlp update container

### Phase 5: Security Hardening
**Objective**: Maintain security without Swarm secrets

#### 5.1 Environment Variable Security
- **File permissions**: `.env` should be `chmod 600`
- **Docker secrets**: Consider Docker secret files for sensitive data
- **Backup**: Encrypted backup of `.env` file

#### 5.2 Alternative: Docker Secret Files
```yaml
# In docker-compose.yml
services:
  api-service:
    secrets:
      - api_token_secret
    environment:
      - API_TOKEN_FILE=/run/secrets/api_token

secrets:
  api_token_secret:
    file: ./secrets/api_token.txt
```

## File Changes Summary

### Files to Modify
1. **`.github/workflows/build.yml`** - Simplify triggers
2. **`docker-compose.yml`** - Refactor to standard Compose (or create new docker-compose.prod.yml)

### Files to Delete  
1. **`.github/workflows/deploy.yml`** - No longer needed
2. **GitHub Secrets** - Remove SSH_PRIVATE_KEY, SERVER, SERVERUSER

### Files to Create
1. **`.env.example`** - Template for environment variables
2. **`.env.production`** - Production environment template
3. **`deploy.sh`** - Server deployment script
4. **`update.sh`** - Server update script
5. **`README.deploy.md`** - Deployment documentation

## Implementation Timeline

### Step 1: Preparation (1 hour)
- Create all new files (scripts, templates)
- Review current environment variables
- Document current setup

### Step 2: GitHub Actions Changes (30 minutes)
- Modify build.yml triggers
- Delete deploy.yml
- Clean up GitHub secrets

### Step 3: Docker Compose Refactoring (1 hour)
- Create docker-compose.prod.yml or modify existing
- Test locally with standard Docker Compose
- Verify networking configuration

### Step 4: Server Migration (2 hours)
- Copy files to server
- Set up environment variables
- Test deployment script
- Verify all services start correctly

### Step 5: Testing & Validation (1 hour)
- Test automatic updates via Watchtower
- Verify yt-dlp updates work
- Test service communication
- Validate YouTube download functionality

### Total Time: ~5.5 hours

## Trade-offs Analysis

### Pros
- **Simplicity**: Standard Docker Compose is easier to manage
- **Security**: No SSH credentials in GitHub Actions
- **Flexibility**: Easy to modify and test locally
- **Cost**: Build only when needed, not weekly
- **Debugging**: Standard tools and commands

### Cons
- **Manual Deployment**: Initial server setup requires manual work
- **No Native Secrets**: Environment variables less secure than Swarm secrets
- **Scaling**: Lose Swarm scaling capabilities (not needed for single server)
- **Monitoring**: Lose Swarm-level monitoring (can be added separately)

## Risk Mitigation

### Low Risk
- **GitHub Actions changes**: Only removing functionality, not adding complexity
- **Docker Compose conversion**: Standard, well-documented process

### Medium Risk  
- **Environment variables**: Need careful handling and documentation
- **Server migration**: Requires careful testing and validation

### Mitigation Strategies
- **Backup current setup**: Document current working state
- **Gradual migration**: Keep Swarm setup available as fallback
- **Testing**: Comprehensive testing of each component
- **Documentation**: Clear deployment and rollback procedures

## Success Criteria

### Functional Requirements
- [ ] All services start correctly with new setup
- [ ] YouTube downloads work via host networking
- [ ] Telegram bot responds to commands
- [ ] API endpoints function correctly

### Operational Requirements  
- [ ] Watchtower pulls new images automatically
- [ ] yt-dlp updates work via runtime command
- [ ] Easy deployment and update processes
- [ ] Clear documentation for troubleshooting

### Security Requirements
- [ ] No SSH credentials in GitHub Actions
- [ ] Sensitive data properly protected
- [ ] Proper file permissions on .env file
- [ ] Backup/restore procedures documented

## Rollback Plan

If issues arise during migration:

1. **Immediate Rollback**: Stop new services, restart Swarm setup
2. **GitHub Actions**: Restore deploy.yml workflow  
3. **Server**: Re-initialize Swarm and deploy using existing method
4. **Investigation**: Analyze logs and debug issues

## Post-Migration Optimizations

### Future Enhancements
- **CI/CD**: Add health checks to GitHub Actions
- **Monitoring**: Add Prometheus/Grafana stack
- **Backups**: Automated backup procedures
- **Scaling**: Consider Kubernetes if multi-server needed
- **Security**: Add Traefik reverse proxy

### Maintenance
- **Monthly reviews**: Check yt-dlp update effectiveness
- **Security audits**: Review access and credentials
- **Performance monitoring**: Track resource usage
- **Cost optimization**: Review Docker Hub storage and pulls

## Conclusion

This refactoring transforms a complex Docker Swarm + SSH deployment into a simple, secure, and maintainable Docker Compose setup. The elimination of GitHub Actions SSH access reduces security risks, while Watchtower maintains automatic updates. Standard Docker Compose simplifies operations and troubleshooting, making the system easier to maintain and scale.

The migration maintains all current functionality while significantly reducing complexity and improving security posture. The incremental approach with clear rollback procedures minimizes risk during the transition.
