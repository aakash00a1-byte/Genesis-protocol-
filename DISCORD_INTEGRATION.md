# Discord Integration Guide

## Overview
Genesis Protocol Discord Bot - Python 3.11+ with discord.py

## Features
- Message listening in #general channel
- Greeting responses (hlo genesis, hello genesis)
- Slash commands (/ping, /status, /help)
- Guild connection logging
- Environment variable configuration

## Environment Variables

### Required
| Variable | Description | Example |
|----------|-------------|---------|
| `DISCORD_TOKEN` or `DISCORD_BOT_TOKEN` | Bot token from Discord Developer Portal | `MTIx...` |

### Optional (for AI features)
| Variable | Description | Provider |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key | OpenAI |
| `GROQ_API_KEY` | Groq API key | Groq |
| `GEMINI_API_KEY` | Gemini API key | Google |
| `HUGGINGFACE_API_TOKEN` | Hugging Face token | HuggingFace |

## Discord Developer Portal Setup

### 1. Create Application
1. Go to https://discord.com/developers/applications
2. Click "New Application"
3. Name it (e.g., "Genesis Protocol")

### 2. Create Bot
1. Select your application
2. Go to "Bot" in left sidebar
3. Click "Add Bot"
4. Copy the Token (DISCORD_TOKEN)

### 3. Enable Privileged Intents
1. Go to "Bot" → "Privileged Gateway Intents"
2. Enable:
   - ✅ **MESSAGE CONTENT INTENT** (required for reading messages)

### 4. Invite Bot to Server
1. Go to "OAuth2" → "URL Generator"
2. Scopes: `bot`
3. Permissions: `8` (Administrator) or specific permissions
4. Copy generated URL
5. Open in browser and select server

### 5. Disable OAuth2 Code Grant (if needed)
1. Go to "OAuth2" → "General"
2. Uncheck "Require OAuth2 Code Grant"
3. Save changes

## Railway Deployment

### Set Environment Variables
```bash
railway variables set DISCORD_BOT_TOKEN=your_token
railway variables set GROQ_API_KEY=your_key
```

### Add Bot to Server
```
https://discord.com/api/oauth2/authorize?client_id=BOT_CLIENT_ID&permissions=8&scope=bot
```
Replace `BOT_CLIENT_ID` with your bot's Application ID.

## Bot Commands

### 🌐 PUBLIC Commands (Everyone can use)
| Command | Description |
|---------|-------------|
| `/ping` | Check if bot is online |
| `/status` | Show bot status and info |
| `/health` | Show system health |
| `/ask [question]` | Chat with Genesis AI |
| `/help` | Show available commands |

### 🔒 ADMIN Commands (Only admins)
| Command | Description |
|---------|-------------|
| `/admin` | Open admin panel |
| `/admin_status` | Detailed system status |
| `/admin_stats` | View bot statistics |
| `/admin_reload` | Reload configuration |

### Text Commands
| Command | Response |
|---------|----------|
| `hello genesis` | Greets the user |
| `hlo genesis` | Greets the user |
| `@Genesis Protocol` | AI chat response |
| New member joins | Auto welcome message |

### 👑 Admin Setup
Set admin Discord IDs via environment variable:
```bash
railway variables set ADMIN_USER_IDS=123456789,987654321
```
Or the bot will default to the creator's Discord ID.

## Files
- `start_discord.py` - Main Discord bot file
- `supervisord.conf` - Process manager config

## Logs
View logs in Railway dashboard or via CLI:
```bash
railway logs --service bot
```
