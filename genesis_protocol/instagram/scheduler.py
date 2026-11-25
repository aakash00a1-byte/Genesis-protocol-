"""Drain due calendar entries - dry by default, approval-gated when live.

This is the only thing in the module that turns a calendar entry into a publish
call, and it is deliberately awkward to run by accident:

* ``dry_run=True`` is the default, so an operator sees what *would* publish;
* a live run needs an approval token **per entry**, supplied by the owner. An
  entry with no token is left ``planned`` and reported as
  ``awaiting-approval`` - it is never skipped silently and never published
  anyway;
* failures are recorded on the entry, so a broken post is visible in the
  calendar instead of disappearing into a log.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .calendar import CalendarEntry, ContentCalendar
from .errors import InstagramError
from .publisher import Publisher


@dataclass(frozen=True)
class DueOutcome:
    entry_id: str
    account_id: str
    result: str  # planned | published | awaiting-approval | failed | skipped
    detail: str = ""


def run_due(
    calendar: ContentCalendar,
    publisher: Publisher,
    *,
    approval_tokens: dict[str, str] | None = None,
    dry_run: bool = True,
    now: datetime | None = None,
    limit: int = 10,
) -> list[DueOutcome]:
    """Process entries that are due. Never publishes without a matching token."""
    moment = now or datetime.now(UTC)
    tokens = approval_tokens or {}
    outcomes: list[DueOutcome] = []

    for entry in calendar.due(moment)[:limit]:
        outcomes.append(_process(calendar, publisher, entry, tokens, dry_run, moment))
    return outcomes


def _process(
    calendar: ContentCalendar,
    publisher: Publisher,
    entry: CalendarEntry,
    tokens: dict[str, str],
    dry_run: bool,
    moment: datetime,
) -> DueOutcome:
    post = entry.to_post()

    if dry_run:
        try:
            publisher.plan(post)
        except InstagramError as exc:
            return DueOutcome(entry.entry_id, entry.account_id, "planned",
                              f"would fail: {type(exc).__name__}: {exc}")
        return DueOutcome(entry.entry_id, entry.account_id, "planned",
                          "dry run: nothing was published")

    token = tokens.get(entry.entry_id, "")
    if not token:
        return DueOutcome(entry.entry_id, entry.account_id, "awaiting-approval",
                          "no owner approval token for this entry")

    try:
        result = publisher.publish(post, approval_token=token)
    except InstagramError as exc:
        calendar.mark(entry.entry_id, "failed", note=f"{type(exc).__name__}: {exc}"[:200])
        return DueOutcome(entry.entry_id, entry.account_id, "failed",
                          f"{type(exc).__name__}: {exc}")

    calendar.mark(entry.entry_id, "published", post_id=result.post_id)
    return DueOutcome(entry.entry_id, entry.account_id, "published", result.post_id)
