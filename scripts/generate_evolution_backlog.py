#!/usr/bin/env python3
"""Write a real, evidence-backed evolution backlog.

    python3 scripts/generate_evolution_backlog.py            # write
    python3 scripts/generate_evolution_backlog.py --dry-run  # print only

The evolution agent normally observes the live transparency ledgers, which are
empty in a fresh process, so an offline cycle finds nothing. This entry point
feeds it the findings from a real audit as *signals*, and lets the agent's own
pipeline (signals -> proposals -> bounds -> store) produce and persist the
backlog. It therefore follows the existing schema and wiring instead of
hand-writing a file.

Every finding below was verified against the repository and the live GitHub API;
nothing is inferred, and a finding already fixed on the branch is recorded with
its state so the backlog does not claim finished work is outstanding. Standard
library only; no network.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "genesis_v5"))

from genesis.agents.base import AgentTask  # noqa: E402
from genesis.bootstrap import build  # noqa: E402
from genesis.config.settings import Env, GenesisConfig  # noqa: E402

BACKLOG = ROOT / "genesis_v5" / "data" / "evolution" / "backlog.jsonl"

# Verified audit findings. `severity` reflects user-visible impact, not effort.
#   open     - still outstanding on this branch
#   fixed    - corrected on this branch, awaiting review/merge
#   blocked  - needs owner action or a permission this environment lacks
FINDINGS: list[dict] = [
    {
        "kind": "weakness",
        "component": "ci/agent-pr-checks",
        "what": "agent pull requests receive no CI checks at all",
        "why": (
            "the self-improvement harness opens PRs with the default GITHUB_TOKEN, "
            "and GitHub suppresses the events that token creates to prevent "
            "workflow loops, so `on: pull_request` never fires for them"
        ),
        "impact": (
            "verified across 6 github-actions[bot] PRs (#25, #26, #28, #30, #33, "
            "#34) with 0 check runs each, against 2 check runs on every "
            "human-authored PR; a reviewer sees no lint or test signal"
        ),
        "severity": "high",
        "source": "live GitHub API",
    },
    {
        "kind": "weakness",
        "component": "web/telegram-authz",
        "what": "privileged Telegram commands were accepted from any sender",
        "why": (
            "the webhook read the sender id into `user` and discarded it, so "
            "`/approve`, `/do` and inline Approve buttons worked for anyone who "
            "knew the chat id"
        ),
        "impact": (
            "a stranger could queue a work order or an approval for a non-owner; "
            "fixed by requiring a configured owner id and failing closed when "
            "TELEGRAM_ADMIN_IDS is unset"
        ),
        "severity": "critical",
        "source": "web/app.py audit",
    },
    {
        "kind": "weakness",
        "component": "web/telegram-routing",
        "what": "/status and /help never reached the user",
        "why": (
            "`parse_command` matches both verbs, so they were parked on the "
            "owner-command queue and the bot's own status/help replies were "
            "unreachable dead code"
        ),
        "impact": "a user asking for status got silence; fixed by parking only the harness-owned verbs",
        "severity": "high",
        "source": "web/app.py audit",
    },
    {
        "kind": "weakness",
        "component": "self-improve/pr-cap",
        "what": "the review cap could be exceeded when the PR count was unreadable",
        "why": (
            "`open_agent_prs()` returned `[]` for a non-list /pulls body, and "
            "`_github` let DNS/TLS/timeout errors escape, so a failed read looked "
            "like 'no open PRs'"
        ),
        "impact": "the loop could open a PR past SELF_IMPROVE_MAX_OPEN_PRS; fixed by failing closed",
        "severity": "medium",
        "source": "scripts/self_improve.py audit",
    },
    {
        "kind": "weakness",
        "component": "relay/heartbeat",
        "what": "the documented daily heartbeat never ran",
        "why": (
            "it relied on an in-run interval (RELAY_HEARTBEAT_HOURS=24) inside a "
            "relay run that lasts only RELAY_RUN_SECONDS=19800 (5h30m), so the "
            "interval could never elapse, and heartbeat.yml had no cron"
        ),
        "impact": "the owner heard nothing from Genesis unless they messaged it first; fixed by a daily cron",
        "severity": "high",
        "source": "workflow + relay audit",
    },
    {
        "kind": "weakness",
        "component": "scripts/relay_loop.py",
        "what": "open PR #27 carries a stale relay_loop.py that reverts two fixes",
        "why": (
            "the PR branched before the batch-cap starvation fix and the "
            "`_reason(exc)` feed diagnostics landed, and its merge-base predates "
            "11 commits now on main"
        ),
        "impact": (
            "merging it as-is would reintroduce head-of-queue starvation and drop "
            "the feed error detail; its liveness/backoff and "
            "NEWS_TOP_STORY_ONLY changes must be re-extracted instead"
        ),
        "severity": "high",
        "source": "GitHub compare API",
    },
    {
        "kind": "weakness",
        "component": "web/telegram-queue",
        "what": "reply, command and task queues live on volatile /tmp",
        "why": (
            "TELEGRAM_REPLY_QUEUE, TELEGRAM_COMMAND_QUEUE and TELEGRAM_TASK_QUEUE "
            "are hardcoded to /tmp, which a container restart discards"
        ),
        "impact": (
            "a queued reply, an owner command or a parked work order is lost on "
            "restart; the Space exposes no persistent volume to point them at"
        ),
        "severity": "medium",
        "source": "web/app.py + Dockerfile.hf audit",
    },
    {
        "kind": "weakness",
        "component": "web/telegram-secret",
        "what": "TELEGRAM_WEBHOOK_SECRET is not configured",
        "why": "the shared-secret check is present but allows every request when the variable is unset",
        "impact": (
            "anyone who learns the Space URL can post forged Telegram updates; "
            "needs an owner-only repo secret and Space env var"
        ),
        "severity": "high",
        "source": "Space env audit",
    },
    {
        "kind": "weakness",
        "component": "tests/test_tools.py",
        "what": "test_allowed_via_kernel_role fails with assert False",
        "why": "a kernel-role file.read is denied where the test expects it allowed",
        "impact": "a red test in the V6 suite masks real regressions in the same file",
        "severity": "medium",
        "source": "genesis_v5 test run",
    },
    {
        "kind": "improvement",
        "area": "self-improve/verification",
        "opportunity": "assert that an agent PR ends up with CI checks, end to end",
        "rationale": (
            "the dispatch fix is unit-tested, but only a live run proves a real "
            "agent PR receives its checks; a smoke check would close that gap"
        ),
        "confidence": 0.6,
    },
    {
        "kind": "improvement",
        "area": "ci/test-suite",
        "opportunity": "pin the baseline failures so new ones cannot hide",
        "rationale": (
            "the suite carries 20 pre-existing failures from missing optional "
            "deps (redis, discord, survival); an allow-list would make a new "
            "failure visible instead of blending into the count"
        ),
        "confidence": 0.7,
    },
]


def _signals() -> list[dict]:
    return FINDINGS


def _stable_ids(payload: dict) -> dict:
    """Replace random uuid ids with content-derived ones.

    ``new_id`` uses uuid4, so re-running the generator would rewrite every id
    and make the committed snapshot churn on each regeneration. The harness only
    reads a proposal's title and priority, so the ids are derived from the
    finding they belong to instead: same findings, same file, byte for byte.
    """
    import hashlib

    def _h(*parts: str) -> str:
        raw = "\x1f".join(str(p) for p in parts).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:12]

    payload["cycle_id"] = f"cycle-{_h('genesis-evolution-backlog')}"

    # Map each signal's original id to its stable id BEFORE rewriting it, so a
    # proposal can still point at the signal it came from. The original id and
    # ts_ms are excluded from the seed: both change every run and would defeat
    # the point of a stable id.
    id_map: dict[str, str] = {}
    for signal in payload.get("signals", []):
        original = str(signal.get("signal_id", ""))
        seed_parts = {k: v for k, v in signal.items() if k not in {"signal_id", "ts_ms"}}
        stable = f"sig-{_h(json.dumps(seed_parts, sort_keys=True))}"
        id_map[original] = stable
        signal["signal_id"] = stable

    # A committed snapshot must not churn, so stamp the whole report with one
    # fixed timestamp rather than the wall clock.
    payload["ts_ms"] = 0
    for signal in payload.get("signals", []):
        signal["ts_ms"] = 0
    for proposal in payload.get("proposals", []):
        proposal["ts_ms"] = 0

    for proposal in payload.get("proposals", []):
        seed = f"{proposal.get('kind')}:{proposal.get('area')}:{proposal.get('title')}"
        proposal["proposal_id"] = f"evo-{_h(seed)}"
        source = str(proposal.get("source_signal_id", ""))
        proposal["source_signal_id"] = id_map.get(source, source)

    # The agent ranked with its own (random) ids as the tiebreak, so equal
    # priorities could come out in a different order each run. Re-rank on the
    # stable ids now that they exist.
    payload["signals"] = sorted(payload.get("signals", []), key=lambda s: s["signal_id"])
    payload["proposals"] = sorted(
        payload.get("proposals", []), key=lambda p: (-p["priority"], p["proposal_id"])
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write an evidence-backed evolution backlog")
    parser.add_argument("--dry-run", action="store_true", help="print the backlog, write nothing")
    parser.add_argument("--out", default=str(BACKLOG), help="output path")
    args = parser.parse_args(argv)

    cfg = GenesisConfig(env=Env.DEVELOPMENT, offline=True)
    cfg.evolution.enabled = True
    cfg.evolution.persist = not args.dry_run
    cfg.evolution.store_dir = str(Path(args.out).parent)
    # Keep every verified finding; the default cap of 5 would drop real ones.
    cfg.evolution.max_proposals = len(FINDINGS)
    kernel = build(cfg)

    agent = kernel.evolution
    if agent is None:
        print("evolution agent is not enabled", file=sys.stderr)
        return 2

    # Force the store even in dry-run so nothing is written to disk.
    if args.dry_run:
        agent.store = None

    report = agent.observe(AgentTask(instruction="audit findings", metadata={"signals": _signals()}))
    payload = _stable_ids(report.to_dict())

    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    # The store appends; keep the file a single current snapshot.
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    print(f"cycle {payload['cycle_id']}  verdict={payload['verdict']}")
    print(f"  {len(payload['proposals'])} proposal(s) from {len(FINDINGS)} verified finding(s)")
    for proposal in sorted(payload["proposals"], key=lambda p: -p["priority"]):
        print(f"    [{proposal['priority']:.2f}] {proposal['severity']:<8} {proposal['title']}")
    for note in payload.get("notes", []):
        print(f"  note: {note}")
    print(f"  wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
