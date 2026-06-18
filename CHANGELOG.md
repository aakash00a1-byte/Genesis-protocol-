# Changelog - Genesis Protocol

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.2.0] - 2026-06-18

### Added

#### Integration Layer
- `GenesisIntegration`: Main integration class orchestrating all v1.1 modules
- `ModuleStatus` enum: Track module states (READY, ERROR, DISABLED)
- `/api/modules` endpoint: Shows all module statuses
- Background loops: Memory summarization, task execution, health monitoring
- Startup self-test for all modules

#### Commands
- `/persona <name>`: Switch personality (normal, jarvis, gluttony, friendly, developer)
- `/mode <mode>`: Change conversation mode (assistant, friend, casual)
- `/remind <time> <message>`: Schedule reminders
- `/memory`, `/remember`, `/forget`: Memory commands
- `/vision`, `/voice`: Feature toggles

#### Chat Pipeline Integration
- Personality engine affects every response
- Long-term memory influences conversations
- Task queue for reminders and delayed actions
- Vision module for image analysis
- Voice module for speech processing

### Changed
- Version bumped to 1.2.0
- server_simple.py updated with v1.2 features
- All v1.1 modules now accessible via integration layer

## [1.1.0] - 2026-06-18

### Added

#### Personality Layer ("Gluttony")
- `PersonalityEngine` class with 5 personas: Normal, Jarvis, Gluttony, Friendly, Developer
- `ConversationMode` system: Assistant, Friend, Casual modes
- `UserPreferences` and `PreferenceManager` for persistent user memory
- `HumorEngine` with jokes, witty responses, and encouragement
- Personality-specific greetings, farewells, and catchphrases

#### Voice Infrastructure
- `SpeechToTextProvider` abstract layer for STT providers
- `TextToSpeechProvider` abstract layer for TTS providers
- `VoiceManager` for unified voice I/O
- Provider implementations: gTTS (free), OpenAI TTS
- Multi-language support (en, hi, es, fr, de, zh, ja)

#### Image Understanding Module
- `ImageAnalyzer` for image analysis
- `VisionProvider` abstract layer with fallback support
- Provider implementations: Groq Vision, OpenAI Vision, Claude Vision
- Image validation and analysis results

#### Autonomous Task Queue
- `TaskQueue` with persistent storage
- `TaskScheduler` for background job processing
- Task priorities, retries, and status tracking
- Reminder scheduling functionality
- Thread-safe operations

#### Long-term Memory Architecture
- `LongTermMemory` with ChromaDB integration
- `MemoryImportance` scoring: Critical, High, Medium, Low, Forgettable
- `MemorySummarizer` for conversation summarization
- Semantic search and context retrieval
- Memory pruning for space management

## [1.0.0] - 2026-06-17

### Added
- Initial Genesis Protocol release
- Groq provider integration
- Redis caching layer
- Vector store support
- Telegram bot integration
- Monitoring endpoints (health, status, version, debug)
- Comprehensive documentation

### Features
- AI-powered chat with provider chain
- Conversation memory with rolling context
- Autonomous mode for continuous tasks
- Code execution capabilities
- Security encryption utilities
