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

### News, market and AI briefing (every 45 minutes)

`scripts/relay_loop.py` sends three things to the admin on a 45-minute cadence
(`NEWS_INTERVAL_SECONDS=2700`):

- News categories (World, India, Tech, Sports, Markets, Crypto, Obituaries)
  from free RSS feeds, each category as its own message
  (`NEWS_SEPARATE_MESSAGES=1`). Toggle with `NEWS_ENABLED`,
  `NEWS_MAX_PER_CATEGORY`.
- A live market ticker (indices, commodities, FX, crypto) with price and
  percent change from the Yahoo Finance chart API. Toggle with
  `MARKET_ENABLED`.
- An AI briefing: the relay posts the collected headlines and market numbers to
  `POST /api/briefing` on the Space, which runs them through
  `genesis_protocol.ai.provider_chain` and returns a short Hinglish summary the
  relay then posts. Toggle with `AGENT_BRIEFING_ENABLED`. The Space must be
  redeployed (`hf_deploy.sh`) for this endpoint to exist.
- A weather line from the free Open-Meteo API (no key). Toggle with
  `WEATHER_ENABLED`; pick a city with `WEATHER_CITY` (default `Delhi`, or `all`
  for every city in `WEATHER_PLACES`).

Set `TELEGRAM_NEWS_CHAT_ID` to a channel id to broadcast to a channel instead
of the admin DM. One-shot tests: `python3 scripts/relay_loop.py news|market|briefing|weather`.

## Agent self-improvement (Level B, continuous)
`scripts/self_improve.py` gives the agent a continuous job on the repo itself.
It is a long-running loop (like the relay): every `SELF_IMPROVE_INTERVAL_SECONDS`
(45 min) it starts one OpenHands Cloud conversation on a rotating topic, waits
for it to finish, pulls the agent's commit out of the sandbox, applies it on a
fresh `agent/` branch, pushes, opens a pull request, and pings Telegram. It
pauses when `SELF_IMPROVE_MAX_OPEN_PRS` (5) agent PRs await review, and it never
merges on its own -- see the approval gate below.

Run via `.github/workflows/self-improve.yml`: cron every 4 hours with a ~5h30m
run (`SELF_IMPROVE_RUN_SECONDS`), so the loop is continuous. Trigger a single
cycle with `workflow_dispatch` + `once: true`, or locally with
`python3 scripts/self_improve.py --once`. `--approvals-only` processes pending
`/approve` commands without starting a cycle. `--dry-run` prints the task prompt
without touching the network.

## Approval gate (owner approves, then it pushes and deploys)
`genesis_protocol/updates/` is the only path to `main`. An agent PR is inert
until the owner approves it: the owner replies `/approve <id|number>` (or
`/reject`, `/updates`), the webhook parks the command in
`/tmp/telegram_command_queue.json`, and the self-improvement loop merges the PR.
The merge *is* the push. Because a push made with the default `GITHUB_TOKEN`
does not trigger another workflow, the loop then explicitly dispatches
`deploy-space.yml` (`workflow_dispatch` is the one event that always runs), so
the HF Space deploys either way. The loop is transport-agnostic:
`handle_command` drives a `GitHubPRTransport` (only `agent/` branches are
approvable), and tests drive a fake transport, so no network is needed to test
the gate.

Tokens: **no new token is strictly required.** HF deploy uses the `HF_TOKEN`
secret, which is already set. GitHub push/PR/merge uses the default
`GITHUB_TOKEN` when the repo allows Actions to write (the workflow already
declares `contents: write` and `pull-requests: write`); set `AGENT_GH_TOKEN` (a
fine-grained PAT with Contents + Pull requests write) only if the repo is set to
read-only for Actions. The agent sandbox token is read-only either way, which is
why the harness lands the commit.

Note: the agent sandbox gets a read-only GitHub credential, so the agent can
commit locally but its `git push` / PR call returns 403. The harness lands the
commit for it: it reads the patch from the sandbox with
`POST {agent_server_url}/api/bash/execute_bash_command`
(`git format-patch {branch}..HEAD --stdout`), applies it, and opens the PR.

## Auto-deploy to the Space
`.github/workflows/deploy-space.yml` mirrors the repo to the HF Space on every
push to `main` (runs `scripts/hf_deploy.sh` with the `HF_TOKEN` repo secret),
so a GitHub push updates the live Space without a manual step. If `HF_TOKEN` is
unset the job fails loudly instead of silently skipping.

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

## Live runtime gotchas (found by driving the real Space)

- **AI brain / event loops:** providers must not cache `httpx.AsyncClient` in
  `__init__`. The Telegram webhook builds a fresh asyncio loop per request and
  closes it, so a cached client fails on the 2nd request with
  `groq: Event loop is closed`. Use `loop_safe_client()` from
  `genesis_protocol/ai/providers/base_provider.py` (one client per running
  loop). Regression: `tests/test_provider_loop_safety.py`.
- **web/app.py must import.** It once used `@limiter.limit` with no `limiter`
  defined -> `NameError` on import -> any redeploy crash. Keep the optional
  flask-limiter setup (no-op fallback) intact.
- **News digest runs in the relay, not the Space.** `scripts/relay_loop.py`
  builds a tech/sports/markets digest from public RSS feeds (BBC Tech, The
  Verge, BBC Sport, BBC Business, CNBC) and sends it to TELEGRAM_ADMIN_ID every
  `NEWS_INTERVAL_SECONDS` (default 300s). Tune via `NEWS_ENABLED`,
  `NEWS_INTERVAL_SECONDS`, `NEWS_MAX_PER_CATEGORY`. By default each category
  is sent as its own message (`NEWS_SEPARATE_MESSAGES=1`); set it to `0` for one
  combined digest. `TELEGRAM_NEWS_CHAT_ID` posts to a channel instead of the DM. One-shot test:
  `python3 scripts/relay_loop.py news`. The Space has no Telegram egress; only
  the GitHub Actions relay can send.
- **Groq model deprecations are a live outage.** `llama-3.3-70b-versatile`
  was shut down 2026-08-16 for free/developer tiers (enterprise-only now), so
  every Groq call 404s. Current production models: `openai/gpt-oss-120b`
  (default) and `openai/gpt-oss-20b` (fast). Check
  https://console.groq.com/docs/deprecations before pinning a model.
- **Deploying:** GitHub push does NOT update the Space. Use
  `HF_TOKEN=hf_... bash scripts/hf_deploy.sh` (the Space is a standalone git
  repo; the script preserves README front-matter and maps Dockerfile.hf ->
  Dockerfile).
- **HF Space runs a frozen snapshot.** `GenesisNo/Genesis-Automaton` is
  `sdk: docker` and is NOT auto-deployed from GitHub (no workflow uploads it);
  its `lastModified` lags `main` by weeks. So the live Space can be running old
  code regardless of what is merged. To run the current code live, start
  `PORT=<port> python web/app.py` (routes: `/api/status`, `/api/health`,
  `/api/telegram/webhook`, `/api/telegram/queue`).
- **Legacy root `tests/` need** `python-dotenv`, `flask`, `httpx`, `structlog`
  (and the rest of `requirements.txt`); without them collection errors are the
  norm. With them installed: ~408 pass, 1 pre-existing unrelated failure
  (`personality` module status).

- **Self-improvement approval (`/approve`) runs on the Actions runner, not the
  Space.** The webhook parks owner commands in the Space's command queue; the
  `self-improve.yml` loop reads them, merges the PR (`GitHubPRTransport`), then
  dispatches `deploy-space.yml`. Two runner-only traps, both fixed and covered
  by tests:
  1. The workflow runs `python3 scripts/self_improve.py`, which puts `scripts/`
     (not the repo root) on `sys.path`. `self_improve.py` now inserts the repo
     root so `import genesis_protocol.updates` works.
  2. `genesis_protocol/__init__.py` exports `Config`/`Message`/`...` lazily
     (PEP 562). An eager import pulled in `config` -> `python-dotenv`, which the
     runner does not install, so every `/approve` died with
     `ModuleNotFoundError: dotenv`. Keep leaf imports (`genesis_protocol.updates`)
     stdlib-only; there is a regression test for this.
  Verify the runner path with `python3 scripts/self_improve.py --check-approvals`
  and `--approvals-only` (process pending commands, no OpenHands key needed).
- **Work orders (`/do`) are the owner's way to aim the agent.** `/do <instruction>`
  is parsed by `genesis_protocol/updates/work_orders.py` (stdlib-only) and parked
  on the Space's task queue (`/tmp/telegram_task_queue.json`, exposed at
  `/api/telegram/tasks`). The `self-improve.yml` loop drains it **before** an
  autonomous cycle: it starts an OpenHands conversation from the instruction
  (`start_conversation_for_work`), lands the resulting patch as a PR, and pings
  Telegram with the same Approve/Reject buttons. Order state is patched
  queued -> running -> done/failed via `PATCH /api/telegram/tasks`; a `running`
  order left by a dead run is requeued at loop start (`_requeue_stuck_orders`).
  An order still only opens a PR — nothing merges without `/approve`.
  Debug with `python3 scripts/self_improve.py --tasks-only`.
- **The Telegram webhook is registered from GitHub Actions.** HF free tier
  blocks egress to `api.telegram.org`, so the Space's `setWebhook` times out.
  `.github/workflows/register-webhook.yml` runs the idempotent
  `scripts/register_telegram_webhook.py` on push to main / every 6h / on demand
  and re-registers only on drift. Never call `deleteWebhook` from the Space.
- **Health check: `scripts/health_check.py` answers "is anything broken?".**
  Three independent checks: every `genesis_protocol` package imports, the live
  HF Space answers `/api/health`, and no workflow's latest run is red. It only
  messages the owner on failure, so a healthy day is quiet. Run it by hand
  (`python3 scripts/health_check.py --no-send`), or let
  `.github/workflows/health-check.yml` run it twice a day. This is the "who
  checks it?" answer — the repo no longer relies on a human noticing.
- **Stale AI reports live in `docs/archive/`, not the repo root.** The root
  keeps only live docs (README, AGENTS, CHANGELOG, the BOOK_OF_* books the code
  writes, and the deployment guides). Historical snapshots moved to
  `docs/archive/` with an index; see `docs/archive/README.md`. Do not treat
  anything in there as current — it describes older states of the project.

