# Genesis Protocol

**Autonomous Multimodal AI Agent with Telegram Interface**

![Version](https://img.shields.io/badge/version-1.0.0--dev-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![License](https://img.shields.io/badge/license-MIT-green)

## Overview

Genesis Protocol is an autonomous AI agent system that processes text, voice, and image inputs through an intelligent multi-provider AI fallback chain. It provides a Telegram interface for seamless communication with persistent conversation memory.

## Features

- **Multi-Provider AI**: Groq → OpenAI → Gemini → HuggingFace with automatic fallback
- **Memory System**: Redis cache + ChromaDB vector store for semantic search
- **Voice Processing**: Speech-to-text and text-to-speech synthesis
- **Image Analysis**: Vision-based image understanding and OCR
- **Real-time Search**: Tavily web search integration
- **Telegram Bot**: Native messaging, voice notes, and image support
- **Streamlit Dashboard**: Monitor usage and manage conversations

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Genesis Protocol                          │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐     ┌──────────────────────────────────────┐  │
│  │   Telegram   │────▶│           Message Processor          │  │
│  │     Bot      │     │  ┌─────────┐ ┌─────────┐ ┌─────────┐ │  │
│  │              │     │  │  Voice  │ │  Image  │ │   Text  │ │  │
│  │  - Commands  │     │  │ Handler │ │ Handler │ │ Handler │ │  │
│  │  - Messages  │     │  └────┬────┘  └────┬────┘  └────┬────┘ │  │
│  │  - Voice     │     │       │            │            │      │  │
│  │  - Photos    │     │       ▼            ▼            ▼      │  │
│  └──────────────┘     └───────────────────────────────────────┤ │
│                              │                                  │
│                              ▼                                  │
│                    ┌────────────────────────────────┐           │
│                    │         Memory System          │           │
│                    │  Redis │ ChromaDB │ Conversation │           │
│                    └────────────────────────────────┘           │
│                              │                                  │
│                              ▼                                  │
│                    ┌────────────────────────────────┐           │
│                    │       AI Provider Chain        │           │
│                    │  Groq → OpenAI → Gemini → HF   │           │
│                    └────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Telegram Bot Token
- API keys for AI providers (at least one)

### Installation

```bash
# Clone the repository
git clone https://github.com/aakash00a1-byte/Genesis-protocol-.git
cd Genesis-protocol-

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run the bot
python src/main.py
```

### Docker

```bash
# Build and run with Docker Compose
docker-compose up -d
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token

# AI Providers (at least one required)
GROQ_API_KEY=your_groq_key
OPENAI_API_KEY=your_openai_key
GEMINI_API_KEY=your_gemini_key
HUGGINGFACE_API_KEY=your_hf_key

# Memory
REDIS_HOST=localhost
REDIS_PORT=6379
CHROMA_DB_PATH=./data/chroma_db

# Integrations
TAVILY_API_KEY=your_tavily_key
```

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot |
| `/help` | Show help message |
| `/settings` | Configure settings |
| `/stats` | View usage statistics |
| `/reset` | Clear conversation history |
| `/model <provider>` | Switch AI provider (groq/openai/gemini) |

## Project Structure

```
genesis_protocol/
├── src/
│   ├── ai/              # AI providers and chain
│   ├── bot/             # Telegram bot
│   ├── memory/          # Memory system
│   ├── processors/      # Voice/image processing
│   ├── integrations/    # External integrations
│   ├── utils/           # Utilities
│   └── models/          # Data models
├── tests/               # Test suite
├── streamlit/          # Dashboard
├── docs/                # Documentation
└── scripts/             # Helper scripts
```

## Deployment

### Docker (Recommended)

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Railway/Render/VPS

1. Push to GitHub
2. Connect repo to Railway/Render
3. Set environment variables from `.env.example`
4. Deploy!

### Local Development

```bash
# Web server
python web/server_simple.py

# Telegram bot (separate terminal)
python start_telegram.py
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat/history` | GET | Get chat history |
| `/api/chat/<id>` | GET | Get specific chat |
| `/api/stats` | GET | Get user statistics |
| `/api/export/chats?format=csv` | GET | Export chats |
| `/api/export/stats` | GET | Export analytics |
| `/api/analytics` | GET | Real-time analytics |

## License

MIT License - See [LICENSE](LICENSE) for details.

---

**Built with ❤️ by Genesis Protocol Team**