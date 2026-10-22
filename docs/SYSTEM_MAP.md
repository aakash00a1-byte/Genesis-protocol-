# Gluttony OS - System Map v1.3

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Gluttony OS v1.3 🔥                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    AUTONOMOUS LAYER (v1.3)                        │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │   │
│  │  │  Event   │ │  Mood   │ │Reflection│ │  User    │            │   │
│  │  │  System  │ │  Engine │ │  Engine  │ │ Profile  │            │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘            │   │
│  │  ┌──────────────────────────────────────────────────────┐        │   │
│  │  │              Autonomous Daemon (Background)           │        │   │
│  │  │  • Memory Maintenance  • Health Monitor              │        │   │
│  │  │  • Conversation Tracker • Reflection Trigger          │        │   │
│  │  └──────────────────────────────────────────────────────┘        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐     │
│  │ Personality │ │    Voice    │ │    Vision   │ │    Tasks    │     │
│  │   Layer     │ │    Module   │ │   Module    │ │    Queue    │     │
│  │  v1.1      │ │   v1.1     │ │   v1.1     │ │   v1.1     │     │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘     │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────┐     │
│  │                    Long-term Memory (ChromaDB)                │     │
│  └─────────────────────────────────────────────────────────────┘     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Module Structure (v1.3)

```
genesis_protocol/
├── autonomous/                    # v1.3 NEW - Autonomous Layer 🔥
│   ├── __init__.py
│   ├── event_system.py             # Event logging (22 types)
│   ├── autonomous_daemon.py       # Background loops
│   ├── mood_engine.py              # Mood management (5 moods)
│   ├── reflection_engine.py        # Self-reflection
│   ├── user_profile.py             # User profile learning
│   └── service_manager.py          # Unified service manager
│
├── integration/                    # v1.2 - Integration Layer
│   ├── __init__.py
│   ├── genesis_integration.py
│   └── commands.py
│
├── personality/                     # v1.1 - Personality Layer
│   ├── personality_engine.py        # 5 personas
│   ├── user_preferences.py
│   └── humor_engine.py
│
├── voice/                          # v1.1 - Voice Infrastructure
│   ├── stt.py, tts.py, voice_manager.py
│   └── providers/
│
├── vision/                         # v1.1 - Image Understanding
│   ├── vision_providers.py
│   ├── image_analyzer.py
│   └── providers/
│
├── tasks/                          # v1.1 - Task Queue
│   ├── task_queue.py
│   └── scheduler.py
│
└── memory/                         # v1.1 - Long-term Memory
    ├── long_term_memory.py
    └── memory_summarizer.py
```

## Moods

| Mood      | Emoji | Style | Use Case |
|-----------|-------|-------|----------|
| calm      | 🧘    | Serene | General conversation |
| playful   | 🎉    | Fun   | Happy/excited users |
| focused   | 🎯    | Precise | Urgent tasks |
| developer | 💻    | Technical | Code discussions |
| sleepy    | 😴    | Relaxed | Late night chats |

## Events (22 Types)

- `startup`, `shutdown`
- `provider_failure`, `provider_success`
- `task_created`, `task_executed`, `task_failed`, `task_completed`
- `memory_created`, `memory_accessed`, `memory_pruned`
- `conversation_start`, `conversation_end`
- `exception`
- `mood_change`, `persona_change`
- `user_profile_updated`
- `reflection_complete`
- `health_warning`, `health_ok`
- `module_loaded`, `module_error`

## API Endpoints (v1.3)

Verified against the routes defined in `web/app.py`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/status` | GET | Status with metrics |
| `/api/state` | GET | Full GLUTTONY state |
| `/api/chat` | POST | Chat with AI |
| `/api/diagnostics` | GET | Provider, memory, uptime and version diagnostics |
| `/api/telegram/webhook` | POST | Telegram update webhook |
| `/api/telegram/queue` | GET, DELETE | Read / clear parked Telegram replies |

See `web/app.py` for the full route list.

## /api/state Response

```json
{
  "entity": "gluttony",
  "version": "1.3.0",
  "layers": {},
  "metrics": {},
  "autonomy": {},
  "survival": {}
}
```

Key names come from `GluttonyEntity.get_state()` in
`genesis_protocol/gluttony/gluttony_core.py`; the contents of `layers`,
`metrics`, `autonomy` and `survival` depend on which subsystems are loaded.

## Background Daemon Loops

1. **Memory Maintenance** - Every 1 hour
2. **Health Monitor** - Every 1 minute
3. **Conversation Tracker** - Every 30 minutes
4. **Reflection Trigger** - Every 10 conversations

## Evolution Roadmap

```
v1.0 ✅ Core AI
v1.1 ✅ Capabilities (Voice, Vision, Tasks, Memory)
v1.2 ✅ Integration (Commands, Modules)
v1.3 ✅ Autonomous Behavior 🔥
v1.4 🔜 Voice + Vision Interaction
v1.5 🔜 Multi-agent Tools
v2.0 🔜 GLUTTONY Entity - Persistent personality
```
