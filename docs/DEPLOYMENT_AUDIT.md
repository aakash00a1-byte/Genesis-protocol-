# Deployment Audit - Gluten OS

**Audit Date:** 2026-06-18  
**Version:** 1.0.0  
**Status:** RC1

---

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Railway Cloud                          │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              Docker Container                         │  │
│  │  ┌─────────────────────────────────────────────┐    │  │
│  │  │           supervisord                        │    │  │
│  │  │  ┌──────────────┐  ┌───────────────────┐    │    │  │
│  │  │  │ web (Flask)  │  │ telegram (Bot)   │    │    │  │
│  │  │  │ port 5000    │  │ background        │    │    │  │
│  │  │  └──────────────┘  └───────────────────┘    │    │  │
│  │  └─────────────────────────────────────────────┘    │  │
│  │                                                     │  │
│  │  📁 /app/data/                                     │  │
│  │    ├── genesis.db (SQLite)                         │  │
│  │    └── chroma_db/ (Vector DB)                      │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Actual Entrypoint

**Primary (and only) Web Server:** `web/app.py`

There is one web server. `supervisord.conf` (Docker) and `supervisord.hf.conf`
(Hugging Face Space) both run it; the HF Space Dockerfile sets
`FLASK_APP=web/app.py`. `web/server_simple.py` and `web/realtime_server.py`
were dead code (never imported, never deployed) and were removed.

```bash
# In supervisord.conf and supervisord.hf.conf
[program:web]
command=python web/app.py
directory=/app

[program:telegram]
command=python start_all_telegram_bots.py
directory=/app
```

---

## Deployment Commands

### Railway (Production)

```bash
# railway.json defines:
startCommand: supervisord -c /app/supervisord.conf

# Container starts with:
supervisord -c /app/supervisord.conf
```

### Docker (Local/Manual)

```bash
# Build
docker build -t genesis-protocol .

# Run
docker run -p 5000:5000 \
  -e GROQ_API_KEY=your_key \
  genesis-protocol
```

### Direct (Development)

```bash
# Web only
python web/app.py

# Telegram only
python start_telegram.py
```

---

## Process Tree

```
supervisord (PID 1)
├── python web/app.py (web)
│   └── Flask app on port 5000
└── python start_all_telegram_bots.py (telegram)
    └── Aiogram bot polling Telegram API
```

---

## File Locations

| File | Purpose | Used By |
|------|---------|---------|
| `web/app.py` | Web server (the only one) | Docker, HF Space |
| `start_all_telegram_bots.py` | Telegram bot | Docker, HF Space |
| `genesis_protocol/` | Core AI logic | Web + bots |
| `genesis.db` | SQLite database | All services |

---

## Health Checks

| Endpoint | Method | Returns |
|----------|--------|---------|
| `/` | GET | Homepage (HTML) |
| `/api/health` | GET | `{"status": "healthy"}` |
| `/api/debug` | GET | Provider status |
| `/api/version` | GET | Version info |

Railway healthcheck: `GET /` (configured in railway.json)

---

## Environment Variables

### Required
| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | Groq API key for AI |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |

### Optional
| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | `genesis-secret-key-2024` | Flask session key |
| `PORT` | `5000` | Server port |
| `FLASK_DEBUG` | `false` | Enable debug mode |
| `CHROMA_DB_PATH` | `./data/chroma_db` | Vector DB path |
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PASSWORD` | — | Redis password |

---

## GitHub Actions

### CI Pipeline (`.github/workflows/ci.yml`)
- Runs on every push
- Installs dependencies
- Runs tests
- No deployment

### Deploy Pipeline (`.github/workflows/deploy-railway.yml`)
- Runs on push to main
- Triggers **Render** deploy (NOT Railway!)
- Railway deployment may be manual

---

## Known Issues

### 1. Railway Not Auto-Deploying
The GitHub Action deploys to Render, not Railway. Railway may need manual redeployment.

**Workaround:**
1. Railway Dashboard → Service → Redeploy
2. Or update GitHub Action to deploy to Railway

### 2. Single Web Entry Point
`web/app.py` is the only web server. The former "second" entry point
(`server_simple.py`) was dead code and has been removed, along with
`realtime_server.py` and the templates only they rendered. Do not reintroduce a
second server; add routes to `web/app.py` above the `__main__` guard.

---

## Verification Commands

```bash
# Check server is running
curl https://genesis-protocol-00a1.up.railway.app/api/health

# Check version
curl https://genesis-protocol-00a1.up.railway.app/api/version

# Check diagnostics
curl https://genesis-protocol-00a1.up.railway.app/api/diagnostics

# Check debug
curl https://genesis-protocol-00a1.up.railway.app/api/debug
```

---

## Rollback Procedure

If deployment fails:

1. **Railway Dashboard:**
   - Go to Service → Deployments
   - Click previous working deployment
   - Select "Redeploy"

2. **Docker:**
   ```bash
   docker pull previous-image:tag
   docker run previous-image:tag
   ```

3. **Git:**
   ```bash
   git revert HEAD
   git push origin main
   ```
