# Gluten OS - System Map v1.3

The architecture and module tree below describe the v1.3 layer, which is still
accurate for those packages. Packages added by later phases are listed under
[V7 phases](#v7-phases), and the endpoint table is a selected subset, not the
full route list.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Gluten OS v1.3 🔥                          │
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

## API Endpoints (selected)

A small, stable subset of the routes defined in `web/app.py` (141 routes at the
time of writing). `web/app.py` is the single source of truth for the full list,
and every route is defined above its `if __name__ == '__main__':` block.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/status` | GET | Status with metrics |
| `/api/state` | GET | Full GLUTEN state |
| `/api/chat` | POST | Chat with AI |
| `/api/diagnostics` | GET | Provider, memory, uptime and version diagnostics |
| `/api/telegram/webhook` | POST | Telegram update webhook |
| `/api/telegram/queue` | GET, DELETE | Read / clear parked Telegram replies |

See `web/app.py` for the full route list.

## /api/state Response

```json
{
  "entity": "gluten",
  "version": "1.3.0",
  "layers": {},
  "metrics": {},
  "autonomy": {},
  "survival": {}
}
```

Key names come from `GlutenEntity.get_state()` in
`genesis_protocol/gluten/gluten_core.py`; the contents of `layers`,
`metrics`, `autonomy` and `survival` depend on which subsystems are loaded.

## Background Daemon Loops

1. **Memory Maintenance** - Every 1 hour
2. **Health Monitor** - Every 1 minute
3. **Conversation Tracker** - Every 30 minutes
4. **Reflection Trigger** - Every 10 conversations

## V7 phases

The v1.x roadmap below was completed and superseded. The repository now ships a
series of V7 phases, each a package under `genesis_protocol/` with its own tests
in `tests/` and its invariants documented in `AGENTS.md`:

| Phase | Package | What it adds |
|-------|---------|--------------|
| P1 | `quarantine/genesis_protocol/` | Legacy modules moved out of the package (not importable) |
| P2 | `agentic/identity_registry.py`, `credentials.py`, `boundaries.py`, `trust.py` | Verifiable agent identity, short-lived credentials, least-privilege gate |
| P3 | `agentic/memory.py`, `memory_safety.py`, `retrieval.py`, `reflection.py` | Durable memory with provenance, retrieval and reflection |
| P4 | `agentic/reasoning.py`, `planning.py`, `decision.py` | Deterministic reasoning, planning and decision records |
| P5 | `guardian/` (read-only) | Security monitoring, threat intel, tamper-evident event log |
| P6 | `guardian/defence.py` | Bounded autonomous defence: low-risk, reversible, owner-gated |
| P7 | `coordination/` | Multi-agent manifests, signed messaging, shared context |
| P8 | `bounded/`, `recovery/` | Cost-aware autonomy limits; encrypted, restorable backups |
| P9 | `evolution/` | Propose-only self-improvement with red/green regression tests |
| P10 | `mission/` | Mission planning into a task DAG, run only on owner approval |

`diagnostics/` observes all of the above and reports a missing subsystem as
`missing`, not an error.

## Evolution Roadmap (v1.x, completed)

```
v1.0 ✅ Core AI
v1.1 ✅ Capabilities (Voice, Vision, Tasks, Memory)
v1.2 ✅ Integration (Commands, Modules)
v1.3 ✅ Autonomous Behavior 🔥
```
