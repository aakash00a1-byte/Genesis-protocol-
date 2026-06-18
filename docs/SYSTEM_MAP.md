# System Map - Genesis Protocol

**Version:** 1.0.0  
**Architecture Type:** Multi-Channel AI Assistant

---

## Architecture Overview

```
                                    ┌─────────────────┐
                                    │   Telegram Bot   │
                                    │  (start_telegram)│
                                    └────────┬────────┘
                                             │ Polling
                                             ▼
┌─────────────┐     ┌─────────────────────────────────────────┐
│   Web UI    │────▶│           Genesis Protocol               │
│   (Flask)   │     │                                         │
│   Port 5000 │     │  ┌─────────────────────────────────┐   │
└─────────────┘     │  │         AI Layer (genesis_protocol) │   │
                    │  │  ┌─────────┐ ┌─────────┐ ┌─────┐ │   │
                    │  │  │ Groq    │ │ OpenAI  │ │More │ │   │
                    │  │  │Provider │ │Provider │ │     │ │   │
                    │  │  └─────────┘ └─────────┘ └─────┘ │   │
                    │  └─────────────────────────────────┘   │
                    │                                         │
                    │  ┌─────────────────────────────────┐   │
                    │  │       Memory Layer               │   │
                    │  │  ┌─────────┐ ┌──────────────┐  │   │
                    │  │  │ChromaDB │ │  SQLite DB    │  │   │
                    │  │  │(Vector) │ │ (Historical)  │  │   │
                    │  │  └─────────┘ └──────────────┘  │   │
                    │  └─────────────────────────────────┘   │
                    └─────────────────────────────────────────┘
```

---

## Process Flow

### Web Chat Flow
```
User → Web UI → Flask (/api/chat) → Genesis Agent → Groq API
                                              │
                                              ▼
                                          SQLite DB ← Memory Layer
```

### Telegram Flow
```
User → Telegram → Bot API → start_telegram.py → Genesis Agent → Groq API
                                                            │
                                                            ▼
                                                        SQLite DB
```

---

## AI Layer Components

### Provider Chain
Location: `genesis_protocol/ai/provider_chain.py`

```
┌────────────────────────────────────────┐
│           ProviderChain                │
├────────────────────────────────────────┤
│ • Groq (Primary) - llama-3.3-70b       │
│ • OpenAI (Fallback)                     │
│ • Gemini (Fallback)                     │
│ • Claude (Fallback)                     │
│ • HuggingFace (Fallback)               │
├────────────────────────────────────────┤
│ Circuit Breaker: Opens after 5 failures│
│ Recovery: 60 seconds cooldown           │
└────────────────────────────────────────┘
```

### Agent
Location: `genesis_protocol/ai/agent.py`

```
GenesisAgent
├── process(message) → AI Response
├── Tools:
│   ├── web_search - Web search capability
│   ├── calculator - Math operations
│   └── code_executor - Run code
├── Memory:
│   ├── ConversationMemory (SQLite)
│   └── VectorStore (ChromaDB)
└── Modes:
    ├── auto (default)
    ├── creative
    └── precise
```

---

## Memory Layers

### 1. Conversation Memory (SQLite)
**Location:** `genesis.db` (root) or `/app/data/genesis.db` (Railway)

```sql
-- Tables:
users (
  id, username, email, password_hash, 
  role, created_at, last_login, 
  is_active, usage_count
)

chat_history (
  id, user_id, message, response,
  model_used, provider, quality_score,
  mode, created_at
)
```

### 2. Vector Memory (ChromaDB)
**Location:** `./data/chroma_db/` or `/app/data/chroma_db/`

```python
# Used for semantic search
VectorStore.search(query, limit=5)
```

### 3. Cache (Redis - Optional)
**Location:** Redis server or in-memory fallback

```python
RedisCache.get(key) / RedisCache.set(key, value)
# Falls back to in-memory dict if Redis unavailable
```

---

## API Endpoints

### Monitoring (Public)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/health` | GET | None | Health check |
| `/api/version` | GET | None | Version info |
| `/api/status` | GET | None | Metrics |
| `/api/debug` | GET | None | Provider debug |

### Diagnostics (Public)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/diagnostics` | GET | None | Full system status |

### Chat (Protected)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/chat` | POST | Login | Send message |
| `/api/history` | GET | Login | Get history |

### Admin (Admin Only)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/admin/stats` | GET | Admin | System stats |
| `/api/admin/users` | GET | Admin | User list |
| `/api/admin/logs` | GET | Admin | View logs |

---

## File Structure

```
/workspace/project/
├── web/
│   ├── server_simple.py    # DEPLOYED web server
│   ├── app.py              # Full web server (dev only)
│   ├── templates/          # HTML templates
│   └── static/             # CSS, JS, images
│
├── genesis_protocol/
│   ├── __init__.py
│   ├── config.py           # Configuration
│   ├── ai/
│   │   ├── agent.py        # Main agent
│   │   ├── provider_chain.py
│   │   ├── providers/
│   │   │   ├── groq_provider.py
│   │   │   └── base_provider.py
│   │   └── llm_router.py
│   ├── memory/
│   │   ├── conversation_memory.py
│   │   ├── vector_store.py
│   │   └── redis_cache.py
│   └── ...
│
├── start_telegram.py       # Telegram bot (DEPLOYED)
├── genesis.db              # SQLite database
├── Dockerfile              # Production Docker
├── railway.json            # Railway config
├── supervisord.conf        # Process manager
└── requirements.txt        # Python dependencies
```

---

## Dependencies

### Core
- flask>=3.0.0
- groq>=0.4.0
- python-dotenv>=1.0.0

### Memory
- chromadb>=0.4.0
- redis>=5.0.0

### Optional
- openai (fallback)
- anthropic (claude)
- google-generativeai (gemini)

---

## Configuration Priority

1. Environment variables (highest)
2. `.env` file
3. Default values (lowest)

### Key Config Values
```python
GROQ_MODEL = "llama-3.3-70b-versatile"
CHROMA_DB_PATH = "./data/chroma_db"
CIRCUIT_BREAKER_FAILURES = 5
CIRCUIT_BREAKER_TIMEOUT = 60
```
