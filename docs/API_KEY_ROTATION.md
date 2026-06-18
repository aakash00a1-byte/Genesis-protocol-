# API Key Rotation Guide

## Keys Used by Genesis Protocol

| Variable | Required | Regeneration Link |
|----------|----------|-------------------|
| GROQ_API_KEY | Yes | https://console.groq.com/keys |
| TELEGRAM_BOT_TOKEN | No | https://t.me/BotFather → /revoke |
| REDIS_PASSWORD | No | Via Redis provider dashboard |

## Rotation Steps

1. Generate new key from provider dashboard
2. Update Railway Dashboard → Variables → Update key value
3. Click Redeploy
4. Verify with `curl https://genesis-protocol-00a1.up.railway.app/api/debug`

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| GROQ_API_KEY | - | Required: Groq API key |
| GROQ_MODEL | llama-3.3-70b-versatile | Model name |
| CHROMA_DB_PATH | ./data/chroma_db | Vector DB path |
| REDIS_HOST | localhost | Redis host |
| REDIS_PORT | 6379 | Redis port |
| REDIS_PASSWORD | - | Redis password |
