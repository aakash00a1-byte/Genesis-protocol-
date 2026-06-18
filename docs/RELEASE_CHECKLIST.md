# Release Checklist - Genesis Protocol v1.0

**Version:** 1.0.0 RC1  
**Release Date:** 2026-06-18

---

## Pre-Release Checklist

### Environment Variables
- [ ] `GROQ_API_KEY` - Set and verified
- [ ] `TELEGRAM_BOT_TOKEN` - Set (if using Telegram)
- [ ] `SECRET_KEY` - Changed from default
- [ ] `CHROMA_DB_PATH` - Set to `/app/data/chroma_db` (Railway)

### API Keys Verification
```bash
# Test Groq API
curl -X POST "https://api.groq.com/openai/v1/chat/completions" \
  -H "Authorization: Bearer $GROQ_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama-3.3-70b-versatile","messages":[{"role":"user","content":"test"}]}'
```

---

## Deployment Sequence

### 1. Local Testing
```bash
# Start web server
python web/server_simple.py

# In another terminal, test endpoints
curl http://localhost:5000/api/health
curl http://localhost:5000/api/version
curl http://localhost:5000/api/diagnostics
```

### 2. Build Docker Image
```bash
# Build
docker build -t genesis-protocol:v1.0.0 .

# Test locally
docker run -p 5000:5000 \
  -e GROQ_API_KEY=your_key \
  genesis-protocol:v1.0.0
```

### 3. Railway Deployment
```bash
# Option A: Railway CLI
railway login
railway init
railway up

# Option B: GitHub Actions
# Push to main branch (if configured)
git push origin main
```

### 4. Post-Deployment Verification
```bash
# Health check
curl https://genesis-protocol-00a1.up.railway.app/api/health

# Version check
curl https://genesis-protocol-00a1.up.railway.app/api/version

# Diagnostics
curl https://genesis-protocol-00a1.up.railway.app/api/diagnostics

# Chat test (login first)
# Visit: https://genesis-protocol-00a1.up.railway.app/
```

---

## Verification Steps

### Core Functionality
- [ ] Homepage loads: `GET /`
- [ ] Login works: `POST /login`
- [ ] Chat API works: `POST /api/chat`
- [ ] History works: `GET /api/history`

### Monitoring
- [ ] Health endpoint: `GET /api/health`
- [ ] Version endpoint: `GET /api/version`
- [ ] Status endpoint: `GET /api/status`
- [ ] Diagnostics: `GET /api/diagnostics`
- [ ] Debug info: `GET /api/debug`

### Metrics Verification
```bash
# Should return JSON with:
# - request_count
# - error_count
# - avg_latency_ms
# - uptime_seconds
curl -s https://genesis-protocol-00a1.up.railway.app/api/status | python3 -m json.tool
```

---

## Rollback Steps

### Railway (Instant)
1. Go to Railway Dashboard
2. Select service
3. Go to Deployments
4. Find last working deployment
5. Click "Redeploy"

### Docker (Manual)
```bash
# Stop current
docker stop genesis-protocol

# Pull/use previous image
docker run genesis-protocol:previous-version
```

### Git (Code)
```bash
# Find last good commit
git log --oneline

# Revert problematic commit
git revert HEAD

# Push
git push origin main
```

---

## Post-Release Verification

### Smoke Tests
```bash
# 1. Health
curl -f https://genesis-protocol-00a1.up.railway.app/api/health && echo "OK"

# 2. Version
curl -s https://genesis-protocol-00a1.up.railway.app/api/version

# 3. Diagnostics
curl -s https://genesis-protocol-00a1.up.railway.app/api/diagnostics | jq '.providers.available'

# 4. End-to-end chat
# Open browser: https://genesis-protocol-00a1.up.railway.app/
# Login and send a message
```

### Performance
- [ ] Response time < 5 seconds
- [ ] No errors in logs
- [ ] Memory stable under load

---

## Monitoring After Release

### Check Logs
```bash
# Railway CLI
railway logs --service genesis-protocol

# Or view in Railway Dashboard
```

### Metrics to Watch
- Request count increasing
- Error count at 0
- Average latency stable
- Provider availability

### Alerting (Future)
- Error rate > 5%
- Latency > 10 seconds
- Provider unavailable

---

## Quick Reference

| Action | Command |
|--------|---------|
| Health | `curl https://genesis-protocol-00a1.up.railway.app/api/health` |
| Version | `curl https://genesis-protocol-00a1.up.railway.app/api/version` |
| Status | `curl https://genesis-protocol-00a1.up.railway.app/api/status` |
| Diagnostics | `curl https://genesis-protocol-00a1.up.railway.app/api/diagnostics` |
| Logs | `railway logs` |

---

## Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Developer | | | |
| QA | | | |
| DevOps | | | |
