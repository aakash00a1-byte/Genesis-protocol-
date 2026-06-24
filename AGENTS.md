# Genesis Protocol - Agent Memory & Context

## Identity
- **Name**: Genesis Protocol
- **Creator**: Aakash Kumar (@aakash00a1-byte)
- **Type**: AI Agent / Assistant
- **Platform**: OpenHands-based agent with Discord integration
- **Version**: 2.0.0

## Repository
- **GitHub**: https://github.com/aakash00a1-byte/Genesis-protocol-
- **Railway**: https://genesis-protocol-00a1.up.railway.app

## Capabilities
Genesis has access to these skills/tools:

### Development
- `github` - GitHub repositories, PRs, workflows
- `github-pr-review` - Post PR review comments
- `github-actions` - CI/CD workflows
- `docker` - Container management
- `code-review` - Code quality review
- `code-simplifier` - Refine code

### Integrations
- `discord` - Discord bot development
- `telegram` - Telegram bot development
- `slack` - Slack integrations

### Cloud & DevOps
- `railway` - Deploy to Railway
- `vercel` - Deploy to Vercel
- `kubernetes` - K8s clusters
- `ssh` - Remote server access

### AI & Data
- `linear` - Project management
- `notion` - Documentation
- `datadog` - Monitoring & logs

### Productivity
- `prd` - Product requirements document
- `research-brief` - Research automation
- `incident-retrospective` - Post-mortem docs

## Environment Variables Required
```
DISCORD_BOT_TOKEN - Discord bot token
GROQ_API_KEY - Groq AI
OPENAI_API_KEY - OpenAI
GEMINI_API_KEY - Google AI
HUGGINGFACE_API_TOKEN - HuggingFace
```

## Discord Server
- **Server Name**: Genesis Board
- **Bot**: Genesis_protocol
- **Commands**: /ping, /status, /help

## Deployment
- Railway production deployment
- 3 services: discord, telegram, web
- Supervisord for process management
