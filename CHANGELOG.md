# Changelog

All notable changes to Genesis Protocol will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.0.0] - 2026-06-18

### Added
- **Monitoring Endpoints**
  - `/api/version` - Version information
  - `/api/health` - Basic health check
  - `/api/status` - Metrics with request count, latency
  - `/api/diagnostics` - Full system diagnostics

- **Metrics Tracking**
  - Request count
  - Error count
  - Average latency
  - Provider-specific latency

- **Backup System**
  - `scripts/backup.py` - SQLite backup and chat history export
  - `scripts/restore.py` - Database restore functionality

- **Streamlit Dashboard**
  - Live API status from `/api/debug`
  - Provider configuration display
  - Circuit breaker status
  - Refresh button

- **Unit Tests**
  - Provider tests
  - Memory fallback tests
  - Health endpoint tests

### Fixed
- "None" response bug in AI chat
- GROQ_API_KEY case sensitivity issue (was groq_api_key)
- ChromaDB graceful fallback
- Redis graceful fallback with in-memory fallback

### Security
- API key rotation documentation
- Environment variable configuration

### Infrastructure
- Railway deployment configured
- GitHub Actions for CI/CD
- SQLite database for persistence
