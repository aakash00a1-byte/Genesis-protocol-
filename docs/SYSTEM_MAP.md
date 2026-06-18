# Genesis Protocol - System Map v1.2

## Architecture Overview

```
┌───────────────────────────────────────────────────────────────────────┐
│                         Genesis Protocol v1.2                         │
├───────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    Integration Layer (v1.2)                      │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │ │
│  │  │ Commands │  │ Background│  │  Status  │  │  Self-   │       │ │
│  │  │ Handler  │  │   Loops  │  │  Report  │  │   Test   │       │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐│
│  │ Personality │  │    Voice    │  │    Vision   │  │    Tasks    ││
│  │   Layer     │  │    Module   │  │   Module    │  │    Queue    ││
│  ├─────────────┤  ├─────────────┤  ├─────────────┤  ├─────────────┤│
│  │ • 5 Personas│  │ • STT       │  │ • Analyzer  │  │ • Scheduler ││
│  │ • 3 Modes   │  │ • TTS       │  │ • Providers │  │ • Queue     ││
│  │ • Humor     │  │ • Manager   │  │ • Memory    │  │ • Retry     ││
│  │ • Preferences│  │ • Providers │  │ • Integration│ │ • Reminders ││
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘│
│                        │                                           │
│                        ▼                                           │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    Long-term Memory (ChromaDB)                │ │
│  │  • Semantic Search  • Importance Scoring  • Summarization    │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

## Module Structure (v1.2)

```
genesis_protocol/
├── integration/                    # v1.2 NEW - Integration Layer
│   ├── __init__.py
│   ├── genesis_integration.py       # Main orchestrator
│   └── commands.py                  # Command handlers
│
├── personality/                     # v1.1 - Personality Layer
│   ├── __init__.py
│   ├── personality_engine.py        # 5 personas + modes
│   ├── user_preferences.py         # Persistent preferences
│   └── humor_engine.py             # Jokes & responses
│
├── voice/                          # v1.1 - Voice Infrastructure
│   ├── __init__.py
│   ├── stt.py                      # Speech-to-text
│   ├── tts.py                      # Text-to-speech
│   ├── voice_manager.py            # Unified I/O
│   └── providers/
│       ├── gtts_provider.py        # Free Google TTS
│       └── openai_tts.py          # OpenAI TTS
│
├── vision/                         # v1.1 - Image Understanding
│   ├── __init__.py
│   ├── vision_providers.py         # Provider abstraction
│   ├── image_analyzer.py          # Image analysis
│   └── providers/
│       └── groq_vision.py         # Groq Vision API
│
├── tasks/                          # v1.1 - Task Queue
│   ├── __init__.py
│   ├── task_queue.py              # Persistent storage
│   └── scheduler.py               # Background scheduler
│
└── memory/                         # v1.1 - Long-term Memory
    ├── __init__.py
    ├── long_term_memory.py         # ChromaDB integration
    └── memory_summarizer.py       # Conversation summaries
```

## Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/persona <name>` | Switch personality | `/persona gluttony` |
| `/mode <mode>` | Change conversation mode | `/mode casual` |
| `/remind <time> <msg>` | Schedule reminder | `/remind 1h Check email` |
| `/memory` | Check memory status | `/memory` |
| `/remember <text>` | Store important info | `/remember I prefer dark mode` |
| `/forget <text>` | Remove from memory | `/forget old preference` |
| `/vision` | Enable vision mode | `/vision` |
| `/voice` | Enable voice mode | `/voice` |
| `/modules` | Check module status | `/modules` |

## Personas

| Persona | Humor | Formality | Empathy | Use Case |
|---------|-------|-----------|---------|----------|
| Normal  | 0.3   | 0.5       | 0.7     | Default balanced |
| Gluttony| 0.9   | 0.1       | 0.9     | Fun, casual chat! |
| Jarvis  | 0.1   | 0.9       | 0.6     | Formal, precise |
| Friendly| 0.5   | 0.2       | 0.9     | Warm, supportive |
| Developer| 0.4   | 0.6       | 0.5     | Code-focused |

## Conversation Modes

- **assistant**: Formal, helpful, task-oriented
- **friend**: Casual, friendly, personal
- **casual**: Very relaxed, humor-heavy

## API Endpoints (v1.2)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Chat with AI (personality-aware) |
| `/api/modules` | GET | Get v1.2 module statuses |
| `/api/diagnostics` | GET | Full system diagnostics |
| `/api/health` | GET | Basic health check |
| `/api/version` | GET | Version info |

## Memory Layers

```
Short-term (Redis) ──────► Long-term (ChromaDB)
      │                            │
      ▼                            ▼
  Session Context ───► Semantic Search + Summaries
```

## Background Loops

1. **Memory Summarization** - Every 5 minutes
2. **Task Execution** - Every second
3. **Health Monitoring** - Every minute
