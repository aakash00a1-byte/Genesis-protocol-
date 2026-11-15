# QUARANTINE — dangerous, unused legacy modules

This directory holds legacy `genesis_protocol` modules that are **not part of
the production package** and **must not be executed, imported, or deployed**.

They were moved here (not deleted) by the V7 P1 "dangerous code quarantine"
change so their history and contents survive for review, while they stop being
reachable from the running application.

## Status

- **Quarantined** — do not run. Not imported by any production path.
- **Not packaged** — this tree is outside the `genesis_protocol` package, so
  build/packaging and `scripts/health_check.py` package discovery do not see it.
- **Not a compatibility shim** — there is no importable alias that keeps the old
  `genesis_protocol.<name>` paths working. Importing them now fails on purpose.

## Prohibited execution

Do **not**:

- import these modules from application, test, script, or workflow code;
- re-add them to `genesis_protocol/` or any `sys.path` entry;
- run any of the deployment, shell, or financial entry points below;
- wire them to secrets, exchange keys, or a live host.

If a module here is ever needed again, it must first be reviewed for the risks
listed below and re-introduced deliberately — never by moving it back blindly.

## What is here, and why

Each entry was proven unused by an import-closure trace from the production
entry points (`web.app`, `genesis_protocol.updates`,
`genesis_protocol.integrations.telegram_commands`, `genesis_protocol.ai.tool_system`,
`genesis_protocol.agentic.identity`) — none of them reach any module below.

| Quarantined path | Risk |
| --- | --- |
| `genesis_protocol/agent/` | `ToolExecutor._run_bash` runs commands with `subprocess.run(..., shell=True)` and no sandbox or resource cap. |
| `genesis_protocol/autonomy/` | `github_agent` commits and `git push`es to a branch; `scheduler_agent` runs subprocesses on a timer. |
| `genesis_protocol/deploy/` | `genesis_deploy_agent` writes plaintext API keys into a `.env`, clones/pulls the repo, and starts a server via `subprocess`. |
| `genesis_protocol/self_sustaining/` | `crypto_exchange_agent` stores exchange `api_key`/`api_secret`, generates wallet addresses, and models trading; `revenue_generator` models income. |
| `genesis_protocol/financial/` | `genesis_financial_manager` models accounts, transfers, and withdrawals; `telegram_handler` exposes them over chat. |

## Rollback

To restore any module, move it back with history preserved:

```bash
git mv quarantine/genesis_protocol/<name> genesis_protocol/<name>
```

Then re-run the full suite (`bash scripts/verify_all.sh`). A restore is a
deliberate, reviewed change — it is not part of normal operation.
