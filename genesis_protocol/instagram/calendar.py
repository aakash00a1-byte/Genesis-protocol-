"""Content calendar and scheduled publishing.

Meta's Instagram content-publishing guide has no "publish at a time" parameter:
it tells applications that *allow* users to schedule posts that the app must
enforce the rate limit itself. Scheduling is therefore ours, and it lives here
as a durable JSON calendar - not as a background timer inside the web app.

Two invariants keep a calendar safe:

* the calendar never publishes. It records intent; only ``scheduler.run_due``
  acts, and only with a per-entry approval token;
* an entry keeps its content fingerprint, so the duplicate guard applies to
  scheduled posts exactly as it does to immediate ones.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .dedupe import fingerprint
from .errors import DuplicatePostError, ValidationError
from .models import MediaItem, Post, PostKind, parse_iso, validate_post

DEFAULT_CALENDAR_FILE = "data/instagram_calendar.json"
STATUSES = ("planned", "published", "failed", "cancelled")


@dataclass
class CalendarEntry:
    entry_id: str
    account_id: str
    client_id: str
    kind: str
    caption: str
    media: list[dict] = field(default_factory=list)
    scheduled_at: str = ""
    status: str = "planned"
    fingerprint: str = ""
    idempotency_key: str = ""
    created_at: str = ""
    post_id: str = ""
    note: str = ""

    def to_post(self) -> Post:
        return Post(
            account_id=self.account_id,
            client_id=self.client_id,
            kind=PostKind(self.kind),
            caption=self.caption,
            media=tuple(MediaItem(url=m["url"], alt_text=m.get("alt_text", "")) for m in self.media),
            idempotency_key=self.idempotency_key,
            scheduled_at=self.scheduled_at,
        )

    def to_dict(self) -> dict:
        return asdict(self)


class ContentCalendar:
    """Durable list of planned posts, per client and per account."""

    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.path = str(path or os.environ.get("IG_CALENDAR_FILE", DEFAULT_CALENDAR_FILE))
        self._lock = threading.Lock()
        self._entries: dict[str, CalendarEntry] = {}
        self._load()

    # -- persistence ---------------------------------------------------
    def _load(self) -> None:
        if self.path == ":memory:" or not Path(self.path).exists():
            return
        try:
            payload = json.loads(Path(self.path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._entries = {}
            return
        for record in (payload.get("entries") or []) if isinstance(payload, dict) else []:
            try:
                entry = CalendarEntry(**record)
            except TypeError:
                continue
            self._entries[entry.entry_id] = entry

    def _save(self) -> None:
        if self.path == ":memory:":
            return
        target = Path(self.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {"entries": [e.to_dict() for e in self._entries.values()]}
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".calendar-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # -- writes --------------------------------------------------------
    def add(self, post: Post, scheduled_at: str, now: datetime | None = None) -> CalendarEntry:
        validate_post(post)
        parse_iso(scheduled_at)
        moment = now or datetime.now(UTC)
        content_id = fingerprint(post)
        with self._lock:
            for entry in self._entries.values():
                if entry.status == "planned" and entry.fingerprint == content_id:
                    raise DuplicatePostError(
                        f"identical content is already scheduled as {entry.entry_id} "
                        f"at {entry.scheduled_at}"
                    )
            entry = CalendarEntry(
                entry_id=uuid.uuid4().hex[:12],
                account_id=post.account_id,
                client_id=post.client_id,
                kind=post.kind.value,
                caption=post.caption,
                media=[{"url": m.url, "alt_text": m.alt_text} for m in post.media],
                scheduled_at=scheduled_at,
                status="planned",
                fingerprint=content_id,
                idempotency_key=post.idempotency_key,
                created_at=moment.isoformat(),
            )
            self._entries[entry.entry_id] = entry
            self._save()
            return entry

    def cancel(self, entry_id: str) -> CalendarEntry:
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                raise ValidationError(f"no calendar entry {entry_id!r}")
            if entry.status != "planned":
                raise ValidationError(
                    f"entry {entry_id} is {entry.status}; only planned entries can be cancelled"
                )
            entry.status = "cancelled"
            self._save()
            return entry

    def mark(self, entry_id: str, status: str, *, post_id: str = "", note: str = "") -> CalendarEntry:
        if status not in STATUSES:
            raise ValidationError(f"unknown status {status!r}")
        with self._lock:
            entry = self._entries.get(entry_id)
            if entry is None:
                raise ValidationError(f"no calendar entry {entry_id!r}")
            entry.status = status
            if post_id:
                entry.post_id = post_id
            if note:
                entry.note = note
            self._save()
            return entry

    # -- reads ---------------------------------------------------------
    def list(
        self,
        *,
        account_id: str | None = None,
        client_id: str | None = None,
        status: str | None = None,
    ) -> list[CalendarEntry]:
        with self._lock:
            entries = list(self._entries.values())
        if account_id:
            entries = [e for e in entries if e.account_id == account_id]
        if client_id:
            entries = [e for e in entries if e.client_id == client_id]
        if status:
            entries = [e for e in entries if e.status == status]
        return sorted(entries, key=lambda e: e.scheduled_at)

    def due(self, now: datetime | None = None) -> list[CalendarEntry]:
        moment = now or datetime.now(UTC)
        out = []
        for entry in self.list(status="planned"):
            try:
                when = parse_iso(entry.scheduled_at)
            except ValidationError:
                continue
            if when <= moment:
                out.append(entry)
        return out
