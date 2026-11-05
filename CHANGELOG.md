# Changelog - Gluten OS

## [2.0.0] - 2026-11-05

### Changed - Entity renamed GLUTTONY -> GLUTEN 🖤

The entity evolved. The lineage is now part of the identity, not hidden:

    GENESIS  ->  GLUTTONY  ->  GLUTEN

- Canonical name is **GLUTEN** (nickname **Gluten**), surfaced from
  `genesis_protocol.gluten.identity` (`NAME`, `NICKNAME`, `EVOLUTION_CHAIN`,
  `Identity.lineage()`).
- Packages moved: `genesis_protocol/gluttony` -> `genesis_protocol/gluten`,
  `genesis_protocol/gluttony_os` -> `genesis_protocol/gluten_os`.
- Back-compat shims keep the old import paths working (with a
  `DeprecationWarning`): `genesis_protocol.gluttony`, `genesis_protocol.gluttony_os`.
  `GluttonyEntity`/`get_gluttony` remain as aliases of
  `GlutenEntity`/`get_gluten`.
- Persisted state migrates on load: `data/gluttony_os` -> `data/gluten_os`, and
  a stored identity name from the lineage is re-pointed at the current name.
- Persona `gluttony` -> `gluten` (`Persona.GLUTTONY` kept as an alias);
  `/persona gluten` and `/persona g` are the documented forms. The identity
  router still recognises the whole lineage in user questions.

## [1.4.0] - 2026-06-18

### Added - Interaction Layer 🔥

#### Unified Context Manager
- Merges persona, mood, profile, history, memory, tasks
- Single context object for every response
- `to_prompt_context()` generates AI prompt injection

#### Tool System (7 tools)
- `calculator`: Math expressions (2+2, sqrt(16), sin(pi/2))
- `notes`: Save/get/list/delete notes
- `reminder`: Create reminders (/remind 1h message)
- `history_search`: Search conversation history
- `memory_search`: Search long-term memories
- `file_reader`: Read project files
- `web_search`: Web search capability

#### Voice Pipeline
- STT → AI → TTS integration
- Continuous conversation mode
- Interrupt support

#### Vision Pipeline
- Image upload and validation
- Multi-image analysis
- Auto-save to memory

#### Session Continuity
- Restore persona on reconnect
- Restore mood on reconnect
- Restore pending tasks

#### Agent Actions
- AI can create tasks
- AI can save memories
- AI can search memories
- AI can call tools

## [1.3.0] - 2026-06-18

### Added - Autonomous Layer
- Event System (22 event types)
- Autonomous Daemon
- Mood Engine (5 moods)
- Reflection Engine
- User Profile learning

## [1.2.0] - 2026-06-18

### Added
- GenesisIntegration
- Personality commands
- /api/modules endpoint

## [1.1.0] - 2026-06-18

### Added
- Personality Layer
- Voice Infrastructure
- Vision Module
- Task Queue
- Long-term Memory

## [1.0.0] - 2026-06-17

Initial Gluten OS release
