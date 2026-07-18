# Plan: Migration from Docker Swarm to Docker Compose

## Context

Current deployment infrastructure uses Docker Swarm with GitHub Actions SSH-based deployment. This creates security risks (SSH keys in GitHub), unnecessary complexity (overlay networks, secrets management), and operational overhead. The goal is to simplify to standard Docker Compose with pull-based deployment.

### Problems Being Solved
- **Security Risk**: SSH private key stored in GitHub Actions secrets
- **Complex Infrastructure**: Docker Swarm with overlay networks, external secrets, stack commands
- **Tight Coupling**: GitHub Actions directly accesses server via SSH
- **Operational Overhead**: Complex deployment logic, network cleanup, Swarm mode management

### Intended Outcome
- GitHub Actions only builds and publishes Docker images to Docker Hub
- Server runs Docker Compose autonomously with .env file for configuration
- Watchtower handles automatic container updates
- Standard Docker Compose networking (bridge instead of overlay)
- Clean slate deployment (no volume migration needed)

---

## Phase 1: Clean up GitHub Actions

### Remove Deployment Workflow
- **Delete**: `.github/workflows/deploy.yml` (entire file)
- **Remove secrets**: `SSH_PRIVATE_KEY`, `SERVER`, `SERVERUSER` from GitHub Actions
- **Keep**: `.github/workflows/build.yml` - already properly configured for Docker Hub publishing

### Verify Build Workflow
- **Verify**: `.github/workflows/build.yml` publishes all 3 images correctly
- **Verify**: Scheduled builds (Mondays 04:00 UTC) are working for yt-dlp updates
- **No changes needed**: Build workflow is already optimal

**Files to modify:**
- `.github/workflows/deploy.yml` - DELETE

---

## Phase 2: Rewrite docker-compose.yaml

### Remove Swarm-Specific Configuration

**Remove sections:**
- `secrets:` block (lines 69-73)
- All `deploy:` blocks from services
- `networks.driver: overlay` - change to bridge
- Swarm secret references (`secrets:`, `source:`)

**Replace with standard Docker Compose:**
- Environment variables instead of secrets
- `restart: always` instead of `deploy.restart_policy`
- Bridge networking instead of overlay
- Standard volume declarations

### Service Changes

**api-service:**
- Replace `secrets: [api_token]` with `environment: API_TOKEN=${API_TOKEN}`
- Remove `deploy:` block, add `restart: always`
- Keep healthcheck and other configurations

**telegram-service:**
- Replace `secrets: [telegram_token]` with `environment: TELEGRAM_TOKEN=${TELEGRAM_TOKEN}`
- Remove `deploy:` block, add `restart: always`
- Keep network_mode: host for Xray proxy functionality

**download-service:**
- Remove `deploy:` block, add `restart: always`
- Remove Swarm-specific network workarounds
- Use standard bridge networking

**redis, watchtower:**
- Remove `deploy:` blocks, add `restart: always`
- Keep existing configurations

### Networks Simplification
- Change from overlay to bridge networks
- Remove external network dependencies
- Keep service discovery via service names

**Files to modify:**
- `docker-compose.yml` - Major rewrite to remove Swarm syntax

---

## Phase 3: Create Environment File Template

### Create .env.example Template
Create example file showing required environment variables:

```bash
# Telegram Bot Configuration
TELEGRAM_TOKEN=your_telegram_bot_token_here
API_TOKEN=your_api_token_here

# Xray Proxy Configuration  
VLESS_URL=your_vless_url_here

# Optional: Watchtower Configuration
WATCHTOWER_SCHEDULE=0 0 * * * *
WATCHTOWER_CLEANUP=true
WATCHTOWER_INCLUDE_STOPPED=false
```

### Create .env Production File
- User creates `.env` file on server with actual values
- Secure permissions: `chmod 600 .env`
- Added to `.gitignore` to prevent accidental commit

**Files to create:**
- `.env.example` - Template for users
- `.env` - Production file (user creates, not committed)
- `.gitignore` - Add `.env`

---

## Phase 4: Create Systemd Service

### Create docker-compose.service
Create systemd service file for auto-start and monitoring:

**Service file location**: `/etc/systemd/system/video-downloader.service`

**Service configuration:**
- WorkingDirectory: `/home/ivan/video-downloader/`
- ExecStart: `/usr/local/bin/docker-compose up -d`
- ExecStop: `/usr/local/bin/docker-compose down`
- Restart: always
- WantedBy: multi-user.target

**Installation commands:**
```bash
# Create service file
sudo cp docker-compose.service /etc/systemd/system/video-downloader.service
# Reload systemd
sudo systemctl daemon-reload
# Enable service (start on boot)
sudo systemctl enable video-downloader.service
# Start service
sudo systemctl start video-downloader.service
# Check status
sudo systemctl status video-downloader.service
```

**Files to create:**
- `docker-compose.service` - Systemd service file
- `README.md` - Updated deployment instructions

---

## Phase 5: Deployment Instructions

### Create Deployment Guide
Update README.md with new deployment process:

**Initial Setup:**
1. Clone repository to server: `~/video-downloader/`
2. Create `.env` file with required variables
3. Run `docker-compose up -d` to start services
4. Install systemd service for auto-start

**Ongoing Operation:**
- Watchtower monitors Docker Hub for new images
- Automatically updates and restarts containers
- No manual intervention needed
- Check logs: `docker-compose logs -f`

**Troubleshooting:**
- Check status: `systemctl status video-downloader.service`
- View logs: `docker-compose logs -f [service]`
- Manual restart: `systemctl restart video-downloader.service`

**Files to modify:**
- `README.md` - Add new deployment section

---

## Phase 6: Cleanup and Verification

### Remove Swarm Artifacts
- Remove Docker Swarm initialization if present
- Clean up any remaining overlay networks
- Remove Swarm-specific deployment scripts

### Verify Operation
- Test all services start correctly: `docker-compose up -d`
- Verify Watchtower detects new images
- Test manual restart: `systemctl restart video-downloader.service`
- Check logs for errors: `docker-compose logs -f`
- Verify Telegram bot functionality
- Test download service end-to-end

### Update GitHub Secrets
- Remove: `SSH_PRIVATE_KEY`, `SERVER`, `SERVERUSER`
- Keep: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `API_TOKEN`, `TELEGRAM_TOKEN`, `VLESS_URL`

---

## Implementation Order

1. **Update docker-compose.yml** - Remove Swarm, add standard config
2. **Create .env.example** - Environment variable template  
3. **Create systemd service** - Auto-start configuration
4. **Update README.md** - New deployment instructions
5. **Delete deploy.yml** - Remove SSH-based deployment
6. **Test locally** - Verify docker-compose works
7. **Deploy to server** - Clean setup, no migration needed
8. **Clean GitHub secrets** - Remove SSH credentials

---

## Verification Steps

### Pre-deployment Verification:
- [ ] Docker Compose file validates: `docker-compose config`
- [ ] .env file template has all required variables
- [ ] Systemd service file syntax is correct
- [ ] All images exist on Docker Hub

### Post-deployment Verification:
- [ ] All containers start: `docker-compose ps`
- [ ] Watchtower is running and monitoring
- [ ] Telegram bot responds to commands
- [ ] Download service works end-to-end
- [ ] Logs show no errors: `docker-compose logs -f`
- [ ] Systemd service status is active
- [ ] New images trigger automatic updates

### Functionality Testing:
- [ ] Test YouTube download functionality
- [ ] Verify Redis caching works
- [ ] Test Xray proxy connectivity
- [ ] Verify auto-update triggers new image pull

---

## Key Files to Modify

**Configuration files:**
- `docker-compose.yml` - Rewrite to remove Swarm
- `.env.example` - Create new template
- `docker-compose.service` - Create systemd service
- `.gitignore` - Add `.env`

**GitHub Actions:**
- `.github/workflows/deploy.yml` - DELETE

**Documentation:**
- `README.md` - Update deployment section

---

## Benefits of This Approach

**Security:**
- No SSH keys in GitHub Actions
- Server pulls updates autonomously
- Environment variables in .env file (user-controlled)

**Simplicity:**
- Standard Docker Compose syntax
- No Swarm mode complexity
- Bridge networking instead of overlay
- Fewer moving parts

**Reliability:**
- Systemd ensures containers stay running
- Watchtower handles updates automatically
- Clean separation of concerns (build vs deploy)
- No manual intervention needed

**Maintainability:**
- Clear deployment process
- Easy to understand and modify
- Standard Linux service management
- Better documentation