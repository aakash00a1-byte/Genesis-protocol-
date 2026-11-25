#!/usr/bin/env python3
"""Command line for the Instagram publisher.

Every command is read-only unless it says otherwise:

    status                     account + token + calendar status (no secrets)
    plan                       validate a post and say what would happen
    publish                    publish - needs --approval and is refused otherwise
    schedule                   put a post on the calendar
    calendar                   list entries
    due                        process due entries (dry by default; --live to act)
    mint-approval              owner action: mint a short-lived approval token
    demo                       run the offline demo with fake accounts

Examples:

    python3 scripts/instagram.py status
    python3 scripts/instagram.py demo
    python3 scripts/instagram.py plan --account acme-cafe --client acme \\
        --media https://cdn.example.com/a.jpg --caption "Today's special"
    python3 scripts/instagram.py mint-approval --account acme-cafe --client acme \\
        --media https://cdn.example.com/a.jpg --caption "Today's special"
    python3 scripts/instagram.py publish --account acme-cafe --client acme \\
        --media https://cdn.example.com/a.jpg --caption "Today's special" \\
        --approval v1.1764...

No command prints a token or an app secret. ``publish`` without ``--approval``
is refused by the gate, not by this script.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genesis_protocol.instagram import (  # noqa: E402
    InstagramError,
    InstagramService,
    MediaItem,
    Post,
    PostKind,
)


def _post(args) -> Post:
    media = tuple(MediaItem(url=url) for url in args.media)
    return Post(
        account_id=args.account,
        client_id=args.client,
        kind=PostKind(args.kind),
        caption=args.caption or "",
        media=media,
        idempotency_key=args.idempotency_key or "",
    )


def _service(args) -> InstagramService:
    if args.accounts_file:
        os.environ["IG_ACCOUNTS_FILE"] = args.accounts_file
    if args.ledger_file:
        os.environ["IG_LEDGER_FILE"] = args.ledger_file
    if args.calendar_file:
        os.environ["IG_CALENDAR_FILE"] = args.calendar_file
    return InstagramService()


def cmd_status(args) -> int:
    print(json.dumps(_service(args).status(), indent=2, sort_keys=True))
    return 0


def cmd_plan(args) -> int:
    result = _service(args).plan(_post(args))
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


def cmd_publish(args) -> int:
    service = _service(args)
    result = service.publish(
        _post(args), approval_token=args.approval or "", dry_run=args.dry_run
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


def cmd_schedule(args) -> int:
    entry = _service(args).schedule(_post(args), args.at)
    print(json.dumps(entry.to_dict(), indent=2, sort_keys=True))
    return 0


def cmd_calendar(args) -> int:
    calendar = _service(args).calendar
    entries = calendar.list(account_id=args.account, client_id=args.client, status=args.status)
    print(json.dumps([e.to_dict() for e in entries], indent=2, sort_keys=True))
    return 0


def cmd_due(args) -> int:
    tokens = {}
    for pair in args.token or []:
        entry_id, _, token = pair.partition("=")
        tokens[entry_id] = token
    outcomes = _service(args).due(dry_run=not args.live, approval_tokens=tokens)
    print(json.dumps([o.__dict__ for o in outcomes], indent=2, sort_keys=True))
    return 0


def cmd_mint(args) -> int:
    service = _service(args)
    if not service.approvals.configured:
        print("refusing to mint: IG_APPROVAL_SECRET is not set", file=sys.stderr)
        return 2
    print(service.mint_approval_for(_post(args)))
    return 0


def cmd_demo(args) -> int:
    from genesis_protocol.instagram.demo import run

    run()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Instagram publisher for Genesis")
    for flag in ("--accounts-file", "--ledger-file", "--calendar-file"):
        parser.add_argument(flag, default="")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="account, token and calendar status")

    def post_args(p):
        p.add_argument("--account", required=True)
        p.add_argument("--client", required=True)
        p.add_argument("--kind", required=True, choices=[k.value for k in PostKind])
        p.add_argument("--media", action="append", required=True, help="public https URL")
        p.add_argument("--caption", default="")
        p.add_argument("--idempotency-key", default="")

    post_args(sub.add_parser("plan", help="validate and describe, no network"))
    publish = sub.add_parser("publish", help="publish (owner approval required)")
    post_args(publish)
    publish.add_argument("--approval", default="")
    publish.add_argument("--dry-run", action="store_true")

    schedule = sub.add_parser("schedule", help="add to the content calendar")
    post_args(schedule)
    schedule.add_argument("--at", required=True, help="ISO-8601 timestamp")

    calendar = sub.add_parser("calendar", help="list calendar entries")
    calendar.add_argument("--account", default="")
    calendar.add_argument("--client", default="")
    calendar.add_argument("--status", default="")

    due = sub.add_parser("due", help="process due entries (dry unless --live)")
    due.add_argument("--live", action="store_true")
    due.add_argument("--token", action="append", help="ENTRY_ID=approval-token")

    mint = sub.add_parser("mint-approval", help="owner: mint an approval token")
    post_args(mint)

    sub.add_parser("demo", help="offline demo with fake accounts")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "status": cmd_status,
        "plan": cmd_plan,
        "publish": cmd_publish,
        "schedule": cmd_schedule,
        "calendar": cmd_calendar,
        "due": cmd_due,
        "mint-approval": cmd_mint,
        "demo": cmd_demo,
    }
    try:
        return handlers[args.command](args)
    except InstagramError as exc:
        print(f"refused: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
