# ⚡ Genesis Protocol - Autonomous Deployment Guide

Genesis Protocol can deploy itself anywhere automatically!

## 🚀 Quick Deploy (One Command)

```bash
curl -s https://raw.githubusercontent.com/aakash00a1-byte/Genesis-protocol-/main/scripts/genesis-deploy.sh | bash
```

## 🌐 Cloud Platforms

### Railway (Recommended)
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new?template=https://github.com/aakash00a1-byte/Genesis-protocol-)

1. Click the button above
2. Add environment variables
3. Deploy!

### Render
[![Deploy to Render](https://render.com/badge)](https://render.com/deploy)

### Fly.io
```bash
fly launch
fly deploy
```

## 🐳 Docker Deploy

```bash
# Clone
git clone https://github.com/aakash00a1-byte/Genesis-protocol-.git
cd Genesis-protocol-

# Setup .env
cp .env.example .env
nano .env  # Add your API keys

# Run with Docker
docker-compose up -d
```

## 🤖 Autonomous Mode

Genesis can run itself with auto-restart, auto-update, and health monitoring:

```bash
python scripts/autonomous_mode.py
```

### Features:
- ✅ Auto-restart on crash
- ✅ Auto-update from git
- ✅ Health monitoring
- ✅ Memory management
- ✅ Railway detection

## 📱 Telegram Commands

After deployment, use these commands:

| Command | Description |
|---------|-------------|
| `/start` | Start Genesis |
| `/help` | Show help |
| `/model groq` | Switch to Groq |
| `/models` | List all models |
| `/deploy` | Show deploy options (Admin) |
| `/stats` | View usage stats |

## 🔑 Required Environment Variables

### AI Providers (at least one)
```env
GROQ_API_KEY=     # Free, fastest (https://console.groq.com)
OPENAI_API_KEY=   # GPT-4o (https://platform.openai.com)
GEMINI_API_KEY=   # Gemini 1.5 (https://aistudio.google.com)
ANTHROPIC_API_KEY= # Claude 3.5 (https://console.anthropic.com)
DEEPSEEK_API_KEY=  # DeepSeek V3/R1
```

### Services
```env
TELEGRAM_BOT_TOKEN=  # From @BotFather
TAVILY_API_KEY=      # For web search (https://tavily.com)
```

### App Settings
```env
SECRET_KEY=your-random-secret-key
PORT=5000
AUTONOMOUS_MODE=true
```

## 🏗️ All 14 AI Providers

| Provider | Model | Tier |
|----------|-------|------|
| Groq | LLaMA 3.3 70B | Free tier |
| OpenAI | GPT-4o / GPT-4o Mini | Premium |
| Google | Gemini 1.5 Flash/Pro | Free tier |
| Anthropic | Claude 3.5 Sonnet | Premium |
| DeepSeek | V3 / R1 | Free tier |
| Mistral | Mistral Large | Premium |
| Cohere | Command R+ | Free tier |
| Perplexity | Sonar / Pro | Free tier |
| Fireworks | Llama 3.3 | Premium |
| Together AI | Llama 3.3 70B | Free tier |
| AI21 | Jamba 1.5 | Premium |
| HuggingFace | Llama 3.1 70B | Free tier |
| Ollama | Llama 3.2 | Local (Free) |
| Azure | GPT-4 | Enterprise |

## 📊 Architecture

```
┌─────────────────────────────────────────────┐
│           Genesis Protocol                  │
├─────────────────────────────────────────────┤
│  Telegram Bot  │  Web UI  │  API             │
├─────────────────────────────────────────────┤
│         AI Provider Router                  │
│  (Auto-failover, Load balancing)            │
├─────────────────────────────────────────────┤
│  Groq │ OpenAI │ Gemini │ Claude │ DeepSeek │
│  Mistral │ Cohere │ Perplexity │ +6 more    │
├─────────────────────────────────────────────┤
│  Memory │ Tools │ Planning │ Quality Judge  │
└─────────────────────────────────────────────┘
```

## 🔧 Troubleshooting

### Bot not responding?
1. Check Telegram bot token is correct
2. Verify webhook is set: `https://api.telegram.org/bot<TOKEN>/setWebhook`

### AI not working?
1. Verify API keys are set
2. Check if provider is down
3. Genesis auto-switches to next provider

### Want to contribute?
1. Fork the repo
2. Create a branch: `git checkout -b feature/amazing`
3. Commit: `git commit -m 'Add amazing feature'`
4. Push: `git push origin feature/amazing`
5. Open a PR!

## 📄 License

MIT License - Use freely!

---

**Genesis Protocol** - The autonomous AI agent that runs itself! ⚡🤖