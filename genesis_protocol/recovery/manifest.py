"""Backup manifest and integrity primitives (V7 P8B).

A backup is only worth as much as the ability to prove it is intact. This module
defines the manifest that travels *inside* every backup (so a backup is
self-describing) and the checks that prove a restored payload matches it.

Nothing here writes outside the paths it is given; the manifest is data, and the
verifiers are read-only.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

CHUNK = 1 << 20

# A backup that recorded no failures is ``complete``; one that recorded some but
# still captured data is ``partial``; one that captured nothing is ``failed``.
STATUS_COMPLETE = "complete"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"

KIND_FILE = "file"
KIND_DATABASE = "database"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Any) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class Entry:
    """One item captured by a backup."""

    path: str  # relative path inside the backup
    size: int
    sha256: str
    kind: str = KIND_FILE

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Entry":
        return cls(
            path=data["path"],
            size=int(data.get("size", 0)),
            sha256=data.get("sha256", ""),
            kind=data.get("kind", KIND_FILE),
        )


@dataclass
class DatabaseReport:
    """Result of the integrity check run on a captured database."""

    path: str
    ok: bool
    tables: List[str] = field(default_factory=list)
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DatabaseReport":
        return cls(
            path=data["path"],
            ok=bool(data.get("ok", False)),
            tables=list(data.get("tables", [])),
            detail=data.get("detail", ""),
        )


@dataclass
class BackupManifest:
    """Self-describing record of what a backup contains and how it was checked."""

    backup_id: str
    created_at: str
    generator: str = "genesis-recovery"
    status: str = STATUS_COMPLETE
    entries: List[Entry] = field(default_factory=list)
    databases: List[DatabaseReport] = field(default_factory=list)
    failures: List[Dict[str, str]] = field(default_factory=list)
    notes: str = ""
    version: int = 1

    def canonical(self) -> str:
        """Deterministic JSON, so the manifest hash is stable across runs."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), default=str)

    def manifest_hash(self) -> str:
        return sha256_bytes(self.canonical().encode("utf-8"))

    def total_bytes(self) -> int:
        return sum(e.size for e in self.entries)

    def entry(self, path: str) -> Optional[Entry]:
        for e in self.entries:
            if e.path == path:
                return e
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "created_at": self.created_at,
            "generator": self.generator,
            "status": self.status,
            "version": self.version,
            "notes": self.notes,
            "entries": [e.to_dict() for e in self.entries],
            "databases": [d.to_dict() for d in self.databases],
            "failures": list(self.failures),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BackupManifest":
        return cls(
            backup_id=data["backup_id"],
            created_at=data.get("created_at", ""),
            generator=data.get("generator", "genesis-recovery"),
            status=data.get("status", STATUS_COMPLETE),
            version=int(data.get("version", 1)),
            notes=data.get("notes", ""),
            entries=[Entry.from_dict(e) for e in data.get("entries", [])],
            databases=[DatabaseReport.from_dict(d) for d in data.get("databases", [])],
            failures=list(data.get("failures", [])),
        )


@dataclass
class IntegrityResult:
    """Outcome of re-hashing a payload against a manifest."""

    ok: bool
    checked: int = 0
    missing: List[str] = field(default_factory=list)
    mismatches: List[Dict[str, Any]] = field(default_factory=list)
    extra: List[str] = field(default_factory=list)
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "checked": self.checked,
            "missing": list(self.missing),
            "mismatches": list(self.mismatches),
            "extra": list(self.extra),
            "detail": self.detail,
        }


def _compare(name: str, expected: Entry, size: int, digest: str) -> Optional[Dict[str, Any]]:
    if size != expected.size or digest != expected.sha256:
        return {
            "path": name,
            "expected_size": expected.size,
            "actual_size": size,
            "expected_sha256": expected.sha256,
            "actual_sha256": digest,
        }
    return None


def verify_payload(files: Dict[str, bytes], entries: List[Entry]) -> IntegrityResult:
    """Verify an in-memory payload (path -> bytes) against its manifest."""
    result = IntegrityResult(ok=True)
    for expected in entries:
        data = files.get(expected.path)
        if data is None:
            result.missing.append(expected.path)
            continue
        result.checked += 1
        bad = _compare(expected.path, expected, len(data), sha256_bytes(data))
        if bad is not None:
            result.mismatches.append(bad)
    declared = {e.path for e in entries}
    result.extra = sorted(p for p in files if p not in declared)
    result.ok = not (result.missing or result.mismatches)
    if not result.ok:
        result.detail = (
            f"{len(result.mismatches)} mismatch(es), {len(result.missing)} missing"
        )
    return result


def verify_directory(root: Any, entries: List[Entry]) -> IntegrityResult:
    """Verify files on disk under ``root`` against their manifest entries."""
    base = Path(root)
    result = IntegrityResult(ok=True)
    for expected in entries:
        target = base / expected.path
        if not target.is_file():
            result.missing.append(expected.path)
            continue
        result.checked += 1
        bad = _compare(expected.path, expected, target.stat().st_size, sha256_file(target))
        if bad is not None:
            result.mismatches.append(bad)
    result.ok = not (result.missing or result.mismatches)
    if not result.ok:
        result.detail = (
            f"{len(result.mismatches)} mismatch(es), {len(result.missing)} missing"
        )
    return result
