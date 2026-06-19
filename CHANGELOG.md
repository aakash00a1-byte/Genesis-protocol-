# Changelog - Genesis Protocol

## [1.3.0] - 2026-06-18

### Added - Autonomous Layer 🔥

#### Event System
- Internal event logging with 22 event types
- Events: startup, shutdown, provider failure/success, task lifecycle, memory operations, conversations, exceptions, mood/persona changes, reflections, health checks
- Thread-safe with persistence
- Subscribe/unsubscribe for real-time notifications

#### Autonomous Daemon
- Background loops running continuously
- Memory maintenance loop (prunes low-importance memories hourly)
- Health monitor loop (checks system health every minute)
- Conversation tracker (triggers reflections every N conversations)
- Event-driven logging of all autonomous actions

#### Mood Engine
- 5 moods: calm, playful, focused, developer, sleepy
- Mood affects response style and modifiers
- Auto-detection based on conversation context
- Mood-specific system prompts

#### Reflection Engine
- Self-reflection after every 10 conversations
- Generates "What did I learn?" summaries
- Stores learnings in long-term memory
- Can answer self-knowledge questions

#### User Profile
- Auto-learns from every message
- Tracks: preferred language, favorite topics, humor level, conversation style
- Detects Hindi/English automatically
- Persisted per user

#### Service Manager
- Unified management of all autonomous services
- `/state` endpoint: Full system state
- `/events` endpoint: Event log access

## [1.2.0] - 2026-06-18

### Added
- GenesisIntegration: Module orchestration
- Personality commands: /persona, /mode, /remind
- /api/modules endpoint

## [1.1.0] - 2026-06-18

### Added
- Personality Layer (Gluttony, Jarvis, etc.)
- Voice Infrastructure
- Vision Module
- Task Queue
- Long-term Memory

## [1.0.0] - 2026-06-17

Initial Genesis Protocol release
