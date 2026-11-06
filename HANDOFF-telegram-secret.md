# Handoff: finish the Telegram secret sync (needs AGENT_GH_TOKEN)

Paste this whole file into a **new OpenHands conversation** that has
`AGENT_GH_TOKEN` injected. That conversation can reach the GitHub Secrets API;
the one that wrote this file could not.

## Why a new conversation

OpenHands injects secrets into the environment only when a conversation
starts. `AGENT_GH_TOKEN` was added after this conversation began, so it is not
present here (verified: 79 env vars, the name is absent). It will be present in
a conversation started after the secret was added.

## Goal

Make the GitHub repo secret `TELEGRAM_WEBHOOK_SECRET` match the HF Space's
`TELEGRAM_WEBHOOK_SECRET`, so the relay in `keepalive.yml` can read the Space's
reply queue without getting 401. Rotate all three sides in one pass so no value
has to travel between conversations.

## Facts you can rely on (verified 2026-11-06)

| Thing | Value |
|---|---|
| GitHub repo | `aakash00a1-byte/Genesis-protocol-` (**private**) |
| HF Space | `GenesisNo/Genesis-Automaton` (public; stage RUNNING) |
| Bot (webhook points at the Space) | `@Genesis_autonomousbot`, id `8230642247` |
| Bot token env var | `Genesis_autonomousbot` |
| HF token env var | `Huggingface` (has `repo.write`) |
| Admin chat id | `1863492058` |
| Webhook URL | `https://genesisno-genesis-automaton.hf.space/api/telegram/webhook` |
| Repo secret name workflows use | `TELEGRAM_WEBHOOK_SECRET` (see `keepalive.yml`) |
| Merge token name | `AGENT_GH_TOKEN` (`self-improve.yml:96`) |

## The architecture in one paragraph

The Space can receive Telegram updates (Telegram POSTs the webhook to it) but
**cannot reach `api.telegram.org` outbound** — HF's free tier times that egress
out. So the Space only *parks* replies in `/tmp/telegram_reply_queue.json`.
`scripts/relay_loop.py` is the only caller of `sendMessage`, and it runs in
`keepalive.yml` on GitHub Actions. It authenticates to the Space's queue
endpoint with the shared secret `TELEGRAM_WEBHOOK_SECRET`. If that secret does
not match the Space's, every queue read is 401 and nothing is ever delivered.

## Steps

0. Read `AGENTS.md` — the procedure below is documented there with the reasons.
   Especially the sections on the two-leg Telegram path, the webhook secret,
   and the relay's minute cost.

1. **Verify the token before using it.**
   ```
   curl -s -D - -o /dev/null -H "Authorization: Bearer $AGENT_GH_TOKEN" \
     https://api.github.com/user | grep -i x-oauth-scopes
   ```
   Expect `repo` and `workflow` in `x-oauth-scopes`. A `ghu_` prefix or an empty
   `x-oauth-scopes` means this is NOT the classic PAT; stop and report.

2. **Generate a fresh secret** (43 chars is plenty). Write it to
   `~/.genesis-webhook-secret` with mode 600. Never print it into the chat.

3. **Set it on the HF Space.**
   ```
   POST https://huggingface.co/api/spaces/GenesisNo/Genesis-Automaton/secrets
   Authorization: Bearer $Huggingface
   {"key":"TELEGRAM_WEBHOOK_SECRET","value":"<v>"}
   ```
   The response is `{}`, not the value.

4. **Register the same value with Telegram.**
   ```
   POST https://api.telegram.org/bot$Genesis_autonomousbot/setWebhook
   {"url":"https://genesisno-genesis-automaton.hf.space/api/telegram/webhook",
    "secret_token":"<v>","max_connections":5,
    "allowed_updates":["message","callback_query"],"drop_pending_updates":false}
   ```

5. **Restart the Space.** HF injects a changed secret only on a fresh start.
   ```
   POST https://huggingface.co/api/spaces/GenesisNo/Genesis-Automaton/restart
   ```
   Until it is running again the OLD value is still enforced and the new one
   returns 401. Poll `runtime.stage` until `RUNNING`.

6. **Verify both ways.**
   ```
   # no header  -> 401
   # header "X-Telegram-Bot-Api-Secret-Token: <v>" -> 200
   ```
   Use a `/status` update body so the Space has something to do. A 200 here also
   proves the Space picked up the new value.

7. **Set the GitHub repo secret.**
   ```
   gh secret set TELEGRAM_WEBHOOK_SECRET --repo aakash00a1-byte/Genesis-protocol- \
     < ~/.genesis-webhook-secret
   ```
   This is the step the previous conversation could not do (403 on
   `/actions/secrets/public-key`). Confirm with
   `gh secret list --repo aakash00a1-byte/Genesis-protocol-`.

8. **Prove the whole path end to end, without Actions.** From a host that can
   reach `api.telegram.org` (the dev sandbox can, even when the Space cannot):
   ```
   export TELEGRAM_BOT_TOKEN=$Genesis_autonomousbot
   export TELEGRAM_WEBHOOK_SECRET=$(cat ~/.genesis-webhook-secret)
   export HF_SPACE_URL=https://genesisno-genesis-automaton.hf.space
   export RELAY_STATE_FILE=/tmp/relay-state.json
   python3 -c "import sys; sys.path.insert(0,'scripts'); import relay_loop; print(relay_loop.relay_once())"
   ```
   Send `/start` to `@Genesis_autonomousbot` first; the relay should report
   `relayed 1/1 queued replies` and the queue should drop to 0.
   Unset those env vars afterwards — a leftover `TELEGRAM_WEBHOOK_SECRET` breaks
   18 tests in `tests/test_web_work_orders.py` and `test_web_telegram_admin_gate.py`.

## Still blocked on the owner (not a code problem)

The repo is **private**, and one `keepalive.yml` run holds a runner for
`RELAY_RUN_SECONDS=19800` (330 min) every 4h, so ~1980 min/day against a
2000 min/**month** free budget — exhausted in about a day. Every run since
2026-11-02 fails in ~3s with 0 steps and `billable.total_ms: 0` (billing, not
code). Until the owner either makes the repo **public** (unlimited minutes) or
raises the Actions spending limit, the relay never runs on its own and the bot
stays silent. This is by design for a public repo.

The Space and the webhook are healthy throughout; a clean `getWebhookInfo` with
no `last_error_message` does NOT mean the bot works.
