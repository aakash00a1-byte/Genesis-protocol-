# Gluttony OS v1.0 Release Notes

**Version:** 1.0.0  
**Type:** Release Candidate 1 (RC1)  
**Release Date:** 2026-06-18  
**Status:** STABLE

---

## Overview

Gluttony OS v1.0 is a multi-channel AI assistant platform with:

- **Web Interface** - Flask-based chat application
- **Telegram Bot** - Integration with Telegram messaging
- **AI Integration** - Groq API with fallback providers
- **Memory System** - SQLite + ChromaDB + Redis
- **Monitoring** - Built-in health checks and diagnostics

---

## What's New in v1.0

### Monitoring & Observability
- `/api/health` - Basic health check endpoint
- `/api/version` - Version information
- `/api/status` - Real-time metrics (request count, latency)
- `/api/diagnostics` - Full system diagnostics
- `/api/debug` - AI provider status

### Backup & Recovery
- `scripts/backup.py` - Automated SQLite backup
- `scripts/restore.py` - Database restore utility
- `docs/BACKUP_AND_RECOVERY.md` - Comprehensive backup guide

### Documentation
- `docs/SYSTEM_MAP.md` - Architecture overview
- `docs/DEPLOYMENT_AUDIT.md` - Deployment details
- `docs/RELEASE_CHECKLIST.md` - Release procedures
- `CHANGELOG.md` - Version history
- `VERSION` - Version file

### Stability Improvements
- Graceful fallback for ChromaDB (in-memory)
- Graceful fallback for Redis (in-memory)
- Startup self-check system
- Startup banner with system status

---

## Bug Fixes

### Fixed in v1.0
- **"None" Response Bug** - Fixed Groq API key environment variable case sensitivity
- **Railway Deployment** - Improved Dockerfile and supervisor configuration
- **Memory Persistence** - Added CHROMA_DB_PATH support

---

## Known Limitations

### v1.0 Limitations
1. **Railway Auto-Deploy** - GitHub Actions deploys to Render, not Railway
2. **Memory Persistence** - ChromaDB requires manual CHROMA_DB_PATH configuration
3. **Single Replica** - No horizontal scaling support
4. **No TLS** - HTTPS handled by Railway/Cloudflare

---

## System Requirements

### Minimum
- Python 3.11+
- 512MB RAM
- SQLite support

### Recommended
- Python 3.11+
- 1GB RAM
- Redis server (optional)
- ChromaDB (optional)

---

## Environment Variables

### Required
```bash
GROQ_API_KEY=your_groq_api_key_here
```

### Optional
```bash
TELEGRAM_BOT_TOKEN=your_telegram_token  # For Telegram bot
SECRET_KEY=your_secret_key              # Flask sessions
CHROMA_DB_PATH=/app/data/chroma_db     # Vector DB path
REDIS_HOST=localhost                   # Redis host
REDIS_PASSWORD=password                # Redis password
```

---

## API Reference

### Public Endpoints
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/health` | GET | None | Health check |
| `/api/version` | GET | None | Version info |
| `/api/status` | GET | None | Metrics |
| `/api/debug` | GET | None | Provider debug |

### Protected Endpoints
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/chat` | POST | Login | Send message |
| `/api/history` | GET | Login | Get history |

---

## Upgrade Notes

### From v0.x to v1.0
1. Pull latest code: `git pull origin main`
2. Update environment variables
3. Rebuild Docker image
4. Redeploy

### Docker Upgrade
```bash
docker build -t genesis-protocol:v1.0.0 .
docker stop genesis-protocol
docker run -d --name genesis-protocol \
  -e GROQ_API_KEY=your_key \
  -p 5000:5000 \
  genesis-protocol:v1.0.0
```

---

## Support

### Documentation
- [SYSTEM_MAP.md](SYSTEM_MAP.md) - System architecture
- [DEPLOYMENT_AUDIT.md](DEPLOYMENT_AUDIT.md) - Deployment guide
- [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) - Release procedures

### Troubleshooting
```bash
# Check health
curl https://genesis-protocol-00a1.up.railway.app/api/health

# Check diagnostics
curl https://genesis-protocol-00a1.up.railway.app/api/diagnostics

# View logs
railway logs --service genesis-protocol
```

---

## Roadmap

### v1.1 (Planned)
- Voice input/output
- Image generation
- Advanced memory patterns
- Autonomous workflows

---

## Changelog Summary

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 RC1 | 2026-06-18 | Initial release candidate |

---

## Contributors

- Gluttony OS Development Team

---

**End of Release Notes**
