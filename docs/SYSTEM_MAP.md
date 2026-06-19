# Genesis Protocol - System Map v1.3

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Genesis Protocol v1.3 🔥                          │
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

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Chat with AI |
| `/api/modules` | GET | Module status |
| `/api/state` | GET | Full autonomous state |
| `/api/events` | GET | Event log |
| `/api/health` | GET | Health check |

## /state Response

```json
{
  "persona": "gluttony",
  "mood": "playful",
  "tasks_pending": 2,
  "tasks_total": 15,
  "memories": 47,
  "uptime_seconds": 3600,
  "health": {
    "status": "ok",
    "events_last_hour": 12,
    "errors": 0
  }
}
```

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
