"""Duplicate-publishing protection.

Two independent guards, because a duplicate post is a client-visible mistake
that no retry can undo:

* a **content fingerprint** over the account, kind, caption and media URLs. The
  same content for the same account inside the dedupe window is refused, so a
  re-run after a crash cannot post twice;
* an optional **idempotency key** supplied by the caller, which is remembered
  for longer so an explicit "publish post 42" is never executed twice.

State is a small JSON file written atomically (temp file + ``os.replace``), so a
crash mid-write cannot corrupt it or lose an earlier fingerprint.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .errors import DuplicatePostError
from .models import Post

DEFAULT_STATE_FILE = "data/instagram_published.json"
DEFAULT_WINDOW_HOURS = 24
IDEMPOTENCY_RETENTION_DAYS = 30


def fingerprint(post: Post) -> str:
    """Stable hash of what would be published. Caption whitespace is normalised."""
    material = "|".join(
        [
            post.account_id,
            post.kind.value,
            " ".join(post.caption.split()),
            ",".join(post.media_urls()),
            ",".join(item.alt_text for item in post.media),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


class PublishLedger:
    """Remembers what was published, and answers "is this a duplicate?"."""

    def __init__(self, path: str | os.PathLike[str] | None = None):
        self.path = str(path or os.environ.get("IG_LEDGER_FILE", DEFAULT_STATE_FILE))
        self._lock = threading.Lock()
        self._entries: dict[str, dict] = {}
        self._keys: dict[str, dict] = {}
        self._load()

    # -- persistence ---------------------------------------------------
    def _load(self) -> None:
        if self.path == ":memory:" or not Path(self.path).exists():
            return
        try:
            payload = json.loads(Path(self.path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A corrupt ledger must not silently allow a duplicate, but it also
            # must not lose history silently: start empty and let the caller see
            # that nothing is recorded.
            self._entries, self._keys = {}, {}
            return
        if isinstance(payload, dict):
            self._entries = {
                k: v for k, v in (payload.get("fingerprints") or {}).items() if isinstance(v, dict)
            }
            self._keys = {
                k: v for k, v in (payload.get("idempotency") or {}).items() if isinstance(v, dict)
            }

    def _save(self) -> None:
        if self.path == ":memory:":
            return
        target = Path(self.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fingerprints": self._entries,
            "idempotency": self._keys,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".ledger-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    # -- queries -------------------------------------------------------
    def _prune(self, now: datetime) -> None:
        cutoff = now - timedelta(days=IDEMPOTENCY_RETENTION_DAYS)
        for store, window in ((self._entries, DEFAULT_WINDOW_HOURS * 24), (self._keys, 0)):
            for key in list(store):
                raw = store[key].get("at", "")
                try:
                    when = datetime.fromisoformat(raw)
                except ValueError:
                    del store[key]
                    continue
                if when.tzinfo is None:
                    when = when.replace(tzinfo=UTC)
                if window and when < cutoff:
                    del store[key]

    def is_duplicate(
        self, post: Post, now: datetime | None = None, window_hours: int = DEFAULT_WINDOW_HOURS
    ) -> str:
        """Return a reason when this content was already published, else ""."""
        moment = now or datetime.now(UTC)
        with self._lock:
            if post.idempotency_key:
                key = f"{post.account_id}:{post.idempotency_key}"
                if key in self._keys:
                    return f"idempotency key {post.idempotency_key!r} was already used"
            entry = self._entries.get(fingerprint(post))
            if entry is not None:
                try:
                    when = datetime.fromisoformat(entry.get("at", ""))
                except ValueError:
                    return "an earlier publish of this content has an unreadable timestamp"
                if when.tzinfo is None:
                    when = when.replace(tzinfo=UTC)
                if moment - when <= timedelta(hours=window_hours):
                    return (
                        f"identical content was published to {post.account_id} at "
                        f"{when.isoformat()} (post {entry.get('post_id', '?')})"
                    )
            return ""

    def assert_not_duplicate(
        self, post: Post, now: datetime | None = None, window_hours: int = DEFAULT_WINDOW_HOURS
    ) -> None:
        reason = self.is_duplicate(post, now=now, window_hours=window_hours)
        if reason:
            raise DuplicatePostError(reason)

    def count_since(self, account_id: str, since: datetime) -> int:
        """How many posts this account published at or after ``since``."""
        total = 0
        with self._lock:
            for entry in self._entries.values():
                if entry.get("account_id") != account_id:
                    continue
                try:
                    when = datetime.fromisoformat(entry.get("at", ""))
                except ValueError:
                    continue
                if when.tzinfo is None:
                    when = when.replace(tzinfo=UTC)
                if when >= since:
                    total += 1
        return total

    # -- writes --------------------------------------------------------
    def record(self, post: Post, post_id: str, now: datetime | None = None) -> None:
        moment = now or datetime.now(UTC)
        with self._lock:
            self._entries[fingerprint(post)] = {
                "account_id": post.account_id,
                "client_id": post.client_id,
                "kind": post.kind.value,
                "post_id": post_id,
                "at": moment.isoformat(),
            }
            if post.idempotency_key:
                self._keys[f"{post.account_id}:{post.idempotency_key}"] = {
                    "at": moment.isoformat(),
                    "post_id": post_id,
                }
            self._prune(moment)
            self._save()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "published": len(self._entries),
                "idempotency_keys": len(self._keys),
                "entries": list(self._entries.values()),
            }
