# Deployment Audit - Genesis Protocol

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

**Primary Web Server:** `web/server_simple.py`

The Dockerfile uses `supervisord` to run TWO processes:

```bash
# In supervisord.conf
[program:web]
command=python web/server_simple.py
directory=/app

[program:telegram]
command=python start_telegram.py
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
python web/server_simple.py

# Telegram only
python start_telegram.py
```

---

## Process Tree

```
supervisord (PID 1)
├── python web/server_simple.py (web)
│   └── Flask app on port 5000
└── python start_telegram.py (telegram)
    └── Aiogram bot polling Telegram API
```

---

## File Locations

| File | Purpose | Used By |
|------|---------|---------|
| `web/server_simple.py` | Web server (DEPLOYED) | Railway, Docker |
| `web/app.py` | Full web server (NOT deployed) | Development only |
| `web/app_v3.py` | Legacy v3 (DEAD CODE) | None |
| `start_telegram.py` | Telegram bot (DEPLOYED) | Railway, Docker |
| `genesis_protocol/` | Core AI logic | Both web servers |
| `genesis.db` | SQLite database | Both services |

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

### 2. Two Web Entry Points
- `server_simple.py` - Production (deployed)
- `app.py` - Development (not deployed)

Only `server_simple.py` should be modified for production changes.

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
