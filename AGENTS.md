# Gluttony OS - Agent Memory & Context

## Identity
- **Name**: Gluttony OS
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

## Telegram delivery (HF Space)

The HF Space `GenesisNo/Genesis-Automaton` runs Genesis, but HF free-tier
egress cannot reach `api.telegram.org` (verified: groq/onrender/vercel OK,
telegram.org times out). So the Space only *receives* updates via webhook and
parks replies in `/tmp/telegram_reply_queue.json`; a GitHub Actions relay
delivers them.

- `.github/workflows/keepalive.yml` runs one ~5h30m job that pings the Space
  every 60s (keeps it from sleeping) and relays the queue near real time.
  A long loop is used because GitHub scheduled cron is delayed by hours on
  free tier. A public repo has unlimited Actions minutes.
- `.github/workflows/heartbeat.yml` sends the admin one proactive status
  message per day (03:30 UTC), so Genesis reports in without being messaged.
- Both call `scripts/relay_loop.py` (stdlib only). Required repo secrets:
  `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ADMIN_ID`.

## V6 hardening notes (relay + authority gate)

- V6 kernel lives in `genesis_v5/genesis/`. Run its suite from that dir with
  `python -m pytest tests/ -q` (the AGENTS `-tb=no` flag is invalid for the
  installed pytest). Root `tests/` are legacy and fail only because `dotenv`
  and `flask` are absent here.
- The authority gate (`genesis/tools/gateway.py`) now has `forbid_tools()`.
  With autonomy enabled, `bootstrap.build()` installs the autonomy guard's
  forbidden-tool list as a hard gate rule, so no actor/role (admin included)
  can reach `docker.exec`, `terminal.run`, `api.call`, `search.web` on the
  agent path. Keep this invariant: a role must never widen the tool set past
  the gate's forbidden list.
- The chat gateway rejects messages longer than `integration.max_message_chars`
  (4000) before the guard or a command parser sees them.
- Relay delivery is idempotent: each queued reply carries an `id`, and the
  worker persists sent ids in `RELAY_STATE_FILE` (restored via actions/cache)
  before clearing the queue. Do not reintroduce a bare "clear after send".
- The webhook and reply-queue endpoints accept an optional shared secret
  (`TELEGRAM_WEBHOOK_SECRET`, header `X-Telegram-Bot-Api-Secret-Token`); the
  relay sends it. Set the same value on the Space and as a repo secret to turn
  enforcement on (absent = allowed, to avoid breaking an existing deploy).
- Never claim the HF Space "never sleeps" or that an HTTP 200 is a health
  check; the heartbeat reports only verified status.
