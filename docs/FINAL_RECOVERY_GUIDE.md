# Final Recovery Guide - Genesis Protocol

**Version:** 1.0.0  
**Purpose:** Complete disaster recovery procedures

---

## Table of Contents

1. [Quick Recovery](#quick-recovery-5-minutes)
2. [Full System Restore](#full-system-restore-30-minutes)
3. [Database Recovery](#database-recovery)
4. [Infrastructure Recovery](#infrastructure-recovery)
5. [Complete Fresh Start](#complete-fresh-start)

---

## Quick Recovery (5 Minutes)

For most common failures.

### Case 1: Server Not Responding

```bash
# 1. Check Railway status
curl https://genesis-protocol-00a1.up.railway.app/api/health

# 2. If 404 or timeout - Redeploy from Railway Dashboard
# Railway Dashboard → Service → Deployments → Click "Redeploy"

# 3. Wait 2 minutes, then verify
curl https://genesis-protocol-00a1.up.railway.app/api/version
```

### Case 2: AI Returns "None" or Errors

```bash
# 1. Check provider status
curl https://genesis-protocol-00a1.up.railway.app/api/debug

# 2. Verify GROQ_API_KEY is set
# Railway Dashboard → Variables → Check GROQ_API_KEY

# 3. If missing - Add new key and Redeploy

# 4. Test Groq API directly
curl -X POST "https://api.groq.com/openai/v1/chat/completions" \
  -H "Authorization: Bearer $GROQ_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama-3.3-70b-versatile","messages":[{"role":"user","content":"hi"}]}'
```

### Case 3: High Error Rate

```bash
# 1. Check diagnostics
curl https://genesis-protocol-00a1.up.railway.app/api/diagnostics

# 2. View Railway logs
railway logs --service genesis-protocol --tail 100

# 3. If memory issues - Restart service
# Railway Dashboard → Service → Restart
```

---

## Full System Restore (30 Minutes)

Complete recovery after major incident.

### Step 1: Assess Damage

```bash
# Check all endpoints
curl https://genesis-protocol-00a1.up.railway.app/api/health
curl https://genesis-protocol-00a1.up.railway.app/api/version
curl https://genesis-protocol-00a1.up.railway.app/api/diagnostics

# Document current state
echo "=== Current State ===" > recovery_state.txt
date >> recovery_state.txt
curl -s https://genesis-protocol-00a1.up.railway.app/api/diagnostics >> recovery_state.txt
```

### Step 2: Check Database Integrity

```bash
# Download database backup from Railway
# Railway Dashboard → Service → Volumes → Download

# Verify database
sqlite3 genesis.db "PRAGMA integrity_check;"
sqlite3 genesis.db "SELECT COUNT(*) FROM chat_history;"
sqlite3 genesis.db "SELECT COUNT(*) FROM users;"
```

### Step 3: Redeploy Application

```bash
# Option A: Railway Dashboard
# 1. Go to Railway Dashboard
# 2. Select genesis-protocol service
# 3. Click "Redeploy"

# Option B: GitHub Actions
# 1. Go to GitHub Actions
# 2. Find "Deploy to Render" workflow
# 3. Click "Run workflow"
# 4. Select main branch

# Option C: Railway CLI
railway login
railway up --service genesis-protocol
```

### Step 4: Verify Recovery

```bash
# Wait 2 minutes for deployment

# Test all endpoints
echo "=== Post-Recovery Tests ===" >> recovery_state.txt

curl -f https://genesis-protocol-00a1.up.railway.app/api/health && echo "✓ Health OK" >> recovery_state.txt
curl -s https://genesis-protocol-00a1.up.railway.app/api/version >> recovery_state.txt
curl -s https://genesis-protocol-00a1.up.railway.app/api/diagnostics >> recovery_state.txt

# Test chat functionality
# Visit web interface and send test message
```

---

## Database Recovery

### Backup Database

```bash
# From Railway shell or local backup
python scripts/backup.py --output ./backups

# Or manual backup
cp genesis.db backups/genesis_db_$(date +%Y%m%d_%H%M%S).sqlite
```

### Restore from Backup

```bash
# List available backups
ls -la backups/

# Restore specific backup
python scripts/restore.py --sqlite backups/genesis_db_20260618_120000.sqlite --target genesis.db

# Verify restoration
sqlite3 genesis.db "SELECT COUNT(*) FROM chat_history;"
```

### Export/Import Chat History

```bash
# Export to JSON
python scripts/backup.py --db genesis.db --output ./exports

# Import from JSON (if needed)
# See docs/BACKUP_AND_RECOVERY.md for import procedure
```

---

## Infrastructure Recovery

### Railway Service Recovery

1. **Login to Railway**
   ```
   https://railway.app/dashboard
   ```

2. **Find Service**
   ```
   Project → genesis-protocol service
   ```

3. **Check Variables**
   ```
   Service → Variables → Verify:
   - GROQ_API_KEY (required)
   - TELEGRAM_BOT_TOKEN (optional)
   - CHROMA_DB_PATH=/app/data/chroma_db (optional)
   ```

4. **Redeploy**
   ```
   Service → Deployments → Click last working deployment → Redeploy
   ```

5. **Verify**
   ```
   curl https://genesis-protocol-00a1.up.railway.app/api/health
   ```

### Docker Recovery

```bash
# 1. Stop current container
docker stop genesis-protocol
docker rm genesis-protocol

# 2. Pull latest image
docker pull ghcr.io/aakash00a1-byte/genesis-protocol:v1.0.0

# 3. Start new container
docker run -d \
  --name genesis-protocol \
  -p 5000:5000 \
  -e GROQ_API_KEY=your_key \
  -e TELEGRAM_BOT_TOKEN=your_token \
  -v genesis-data:/app/data \
  genesis-protocol:v1.0.0

# 4. Verify
curl http://localhost:5000/api/health
```

### GitHub Actions Recovery

```bash
# Check workflow status
gh run list --repo aakash00a1-byte/Genesis-protocol- --limit 5

# Rerun failed workflow
gh run rerun <run-id>

# View logs
gh run view <run-id> --log
```

---

## Complete Fresh Start

For total infrastructure failure.

### Step 1: Fresh Railway Setup

1. Go to [Railway](https://railway.app)
2. Create new project
3. Connect GitHub repository
4. Set environment variables:
   ```
   GROQ_API_KEY=your_key
   TELEGRAM_BOT_TOKEN=your_token
   CHROMA_DB_PATH=/app/data/chroma_db
   ```
5. Deploy

### Step 2: Local Development Setup

```bash
# Clone repository
git clone https://github.com/aakash00a1-byte/Genesis-protocol-.git
cd Genesis-protocol-

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
pip install -r web/requirements.txt

# Copy environment file
cp .env.example .env
# Edit .env with your keys

# Initialize database
python -c "from web.server_simple import init_db; init_db()"

# Start development server
python web/server_simple.py
```

### Step 3: Docker Setup

```bash
# Build image
docker build -t genesis-protocol:v1.0.0 .

# Run container
docker run -d \
  --name genesis-protocol \
  -p 5000:5000 \
  -e GROQ_API_KEY=your_key \
  genesis-protocol:v1.0.0

# Verify
curl http://localhost:5000/api/health
```

---

## Emergency Contacts

### System Status
- Railway Dashboard: https://railway.app/dashboard
- GitHub Repository: https://github.com/aakash00a1-byte/Genesis-protocol-

### API Keys
- Groq Console: https://console.groq.com/keys
- Telegram BotFather: https://t.me/BotFather

---

## Recovery Checklist

Print or copy this checklist during recovery:

```
RECOVERY CHECKLIST
==================
Date: _______________
Technician: __________

PRE-RECOVERY
[ ] Document current state
[ ] Take database backup
[ ] Note error messages

RECOVERY STEPS
[ ] Redeploy application
[ ] Verify environment variables
[ ] Check database integrity
[ ] Test API endpoints

POST-RECOVERY
[ ] Health check passed
[ ] Version correct
[ ] Diagnostics show OK
[ ] Chat functionality works
[ ] Monitor for 1 hour

COMPLETION
[ ] Document incident
[ ] Update runbooks if needed
[ ] Notify stakeholders
```

---

## Prevention Checklist

- [ ] Daily backups configured
- [ ] Monitoring alerts set up
- [ ] Runbooks accessible
- [ ] Team trained on recovery
- [ ] Documentation current

---

**End of Recovery Guide**
