# Genesis Protocol - System Map v1.1

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Genesis Protocol v1.1                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐       │
│  │ Personality │    │    Voice    │    │    Vision   │       │
│  │   Layer     │    │    Module   │    │   Module    │       │
│  ├─────────────┤    ├─────────────┤    ├─────────────┤       │
│  │ • Gluttony  │    │ • STT       │    │ • Analyzer  │       │
│  │ • Jarvis    │    │ • TTS       │    │ • Providers │       │
│  │ • Friendly  │    │ • Manager   │    │             │       │
│  │ • Developer │    │             │    │             │       │
│  │ • Normal    │    │             │    │             │       │
│  └─────────────┘    └─────────────┘    └─────────────┘       │
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐       │
│  │    Tasks    │    │   Memory    │    │     AI      │       │
│  │    Queue    │    │   Module    │    │    Core     │       │
│  ├─────────────┤    ├─────────────┤    ├─────────────┤       │
│  │ • Scheduler │    │ • LTM       │    │ • Providers │       │
│  │ • Queue     │    │ • ChromaDB  │    │ • Chain     │       │
│  │ • Reminders │    │ • Summary   │    │ • Scoring   │       │
│  │ • Retry     │    │ • Importance│    │ • Reasoning │       │
│  └─────────────┘    └─────────────┘    └─────────────┘       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Module Structure

### personality/ - Personality Layer
```
personality/
├── __init__.py
├── personality_engine.py   # Core personality system
├── user_preferences.py    # User preferences & memory
└── humor_engine.py        # Humor & jokes
```

### voice/ - Voice Infrastructure
```
voice/
├── __init__.py
├── stt.py                 # Speech-to-text abstraction
├── tts.py                 # Text-to-speech abstraction
├── voice_manager.py       # Unified voice I/O
└── providers/
    ├── __init__.py
    ├── gtts_provider.py       # Google TTS (free)
    └── openai_tts.py          # OpenAI TTS
```

### vision/ - Image Understanding
```
vision/
├── __init__.py
├── vision_providers.py    # Provider abstraction
└── image_analyzer.py      # Image analysis
```

### tasks/ - Autonomous Task Queue
```
tasks/
├── __init__.py
├── task_queue.py          # Task storage & management
└── scheduler.py           # Background scheduler
```

### memory/ - Long-term Memory
```
memory/
├── __init__.py
├── long_term_memory.py    # ChromaDB integration
└── memory_summarizer.py   # Conversation summarization
```

## Memory Layers

```
┌────────────────────────────────────────────────────┐
│                   Memory Architecture               │
├────────────────────────────────────────────────────┤
│                                                     │
│  ┌─────────────┐    ┌─────────────┐               │
│  │   Short     │ →  │    Long     │               │
│  │   Term      │    │    Term     │               │
│  ├─────────────┤    ├─────────────┤               │
│  │ • Redis     │    │ • ChromaDB  │               │
│  │ • Session   │    │ • Vector    │               │
│  │ • Rolling   │    │ • Semantic  │               │
│  │   Context   │    │   Search    │               │
│  └─────────────┘    └─────────────┘               │
│         ↓                   ↓                       │
│  ┌─────────────────────────────────────────┐      │
│  │         Conversation Memory              │      │
│  │  • Rolling window (configurable)         │      │
│  │  • Importance-based retention             │      │
│  │  • Auto-summarization                    │      │
│  └─────────────────────────────────────────┘      │
│                                                     │
└────────────────────────────────────────────────────┘
```

## Personas

| Persona    | Humor | Formality | Empathy | Use Case |
|------------|-------|-----------|---------|----------|
| Normal     | 0.3   | 0.5       | 0.7     | Default balanced |
| Gluttony   | 0.9   | 0.1       | 0.9     | Fun, casual chat |
| Jarvis     | 0.1   | 0.9       | 0.6     | Formal, precise |
| Friendly   | 0.5   | 0.2       | 0.9     | Warm, supportive |
| Developer  | 0.4   | 0.6       | 0.5     | Code-focused |

## Conversation Modes

- **Assistant**: Formal, helpful, task-oriented
- **Friend**: Casual, friendly, personal
- **Casual**: Very relaxed, humor-heavy

## Dependencies

### Required for v1.1
- `chromadb` - Vector database for long-term memory
- `gtts` - Free TTS (optional)
- `openai` - OpenAI API for TTS/Vision (optional)
- `Pillow` - Image processing

### Optional Providers
- Groq API (Vision, Whisper)
- OpenAI API (GPT-4V, TTS)
- Anthropic API (Claude Vision)
