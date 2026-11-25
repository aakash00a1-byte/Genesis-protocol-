"""Encrypted backup vault (V7 P8B).

Every backup is a single encrypted, self-describing container:

* the payload (relative path -> bytes) and the manifest travel together, so a
  backup can always explain itself without a sidecar database;
* the container is Fernet-encrypted with a key that must survive a restart, so
  the vault **fails closed** when no key is configured - a backup nobody can
  decrypt is not a backup;
* the manifest is hashed, and every payload entry is hashed, so tampering (or a
  truncated/corrupt file) is detected on verify and refused on restore;
* an append-only plaintext index records what exists (id, time, size, status)
  so the vault can be listed and retention applied without the key.

Nothing here deletes data except :meth:`BackupVault.apply_retention`, which only
ever removes *backups* under an explicit policy and never the newest one.
"""
from __future__ import annotations

import base64
import json
import os
import sqlite3
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from genesis_protocol.recovery.manifest import (
    KIND_DATABASE,
    KIND_FILE,
    STATUS_COMPLETE,
    STATUS_PARTIAL,
    BackupManifest,
    DatabaseReport,
    Entry,
    IntegrityResult,
    sha256_bytes,
    utcnow,
    verify_payload,
)
from genesis_protocol.security.encryption import (
    EncryptionService,
    LegacyCiphertextError,
    decrypt_with_raw_key,
)

FORMAT = "genesis-backup/1"
CONTAINER_SUFFIX = ".gbk"
INDEX_NAME = "index.jsonl"


class BackupError(RuntimeError):
    """Raised when a backup cannot be created, read, verified or restored."""


class KeyUnavailableError(BackupError):
    """Raised when no durable backup key is configured (fail closed)."""


def resolve_key(explicit: Optional[str] = None) -> str:
    """Return the backup key, or fail closed.

    A backup key must be stable across processes and restarts. If none is
    configured the vault refuses to operate rather than writing a container it
    cannot later decrypt.
    """
    key = explicit or os.environ.get("GENESIS_BACKUP_KEY")
    if not key:
        raise KeyUnavailableError(
            "no backup key configured: set GENESIS_BACKUP_KEY (or pass key=...). "
            "Refusing to write a backup that cannot be decrypted after a restart."
        )
    return key


def check_sqlite(data: bytes) -> DatabaseReport:
    """Run SQLite's own integrity check over a captured database.

    Returns a report rather than raising: a corrupt database is a *finding* a
    backup should carry, not a reason to lose the rest of the backup.
    """
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    try:
        handle.write(data)
        handle.close()
        try:
            conn = sqlite3.connect(handle.name)
            try:
                row = conn.execute("PRAGMA integrity_check").fetchone()
                verdict = (row[0] if row else "unknown") or "unknown"
                ok = verdict.lower() == "ok"
                tables = [
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    ).fetchall()
                ]
                return DatabaseReport(path="", ok=ok, tables=tables, detail=verdict)
            finally:
                conn.close()
        except sqlite3.DatabaseError as exc:
            return DatabaseReport(path="", ok=False, tables=[], detail=f"not a database: {exc}")
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass


class BackupVault:
    """Create, verify, restore and retain encrypted backups."""

    def __init__(
        self,
        root: Optional[str] = None,
        key: Optional[str] = None,
        encryption: Optional[EncryptionService] = None,
        audit: Optional[Any] = None,
    ):
        self.root = Path(root or os.environ.get("GENESIS_BACKUP_DIR") or "data/backups")
        self.root.mkdir(parents=True, exist_ok=True)
        self._key = key
        self._encryption = encryption
        self._audit = audit
        self._lock = threading.Lock()

    # -- collaborators --------------------------------------------------------

    @property
    def encryption(self) -> EncryptionService:
        if self._encryption is None:
            self._encryption = EncryptionService(key=resolve_key(self._key))
        return self._encryption

    @property
    def key_configured(self) -> bool:
        """Whether a durable key is available (read-only; never raises)."""
        return bool(self._key or os.environ.get("GENESIS_BACKUP_KEY"))

    @property
    def audit(self) -> Any:
        if self._audit is None:
            try:
                from genesis_protocol.guardian.events import get_security_log

                self._audit = get_security_log()
            except Exception:
                self._audit = None
        return self._audit

    def _record(self, event: str, severity: str = "info", **evidence: Any) -> None:
        log = self.audit
        if log is None:
            return
        try:
            log.record("integrity", event, severity=severity, subject="recovery",
                       evidence=evidence, source="recovery")
        except Exception:
            # The audit trail must never be the reason a recovery fails; a
            # missing trail is itself reported by the caller's result.
            pass

    # -- paths ----------------------------------------------------------------

    def container_path(self, backup_id: str) -> Path:
        return self.root / f"{backup_id}{CONTAINER_SUFFIX}"

    @property
    def index_path(self) -> Path:
        return self.root / INDEX_NAME

    # -- create ---------------------------------------------------------------

    def create(
        self,
        items: Dict[str, bytes],
        databases: Optional[Dict[str, bytes]] = None,
        backup_id: Optional[str] = None,
        note: str = "",
        failures: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Write one encrypted backup.

        ``items`` maps a relative path to its bytes; ``databases`` maps a relative
        path to SQLite bytes that are additionally integrity-checked. ``failures``
        carries capture failures recorded by the caller (e.g. an unreadable source
        file) so the manifest and status reflect them. A failure to capture an
        item is recorded as a finding and the backup is still written (status
        ``partial``); only a total failure raises.
        """
        databases = databases or {}
        bid = backup_id or self._new_id()
        entries: List[Entry] = []
        payload: Dict[str, bytes] = {}
        reports: List[DatabaseReport] = []
        failures: List[Dict[str, str]] = list(failures or [])

        for rel, data in items.items():
            try:
                payload[rel] = bytes(data)
                entries.append(Entry(rel, len(data), sha256_bytes(bytes(data)), KIND_FILE))
            except Exception as exc:  # noqa: BLE001 - record and continue
                failures.append({"path": rel, "error": f"{type(exc).__name__}: {exc}"})

        for rel, data in databases.items():
            try:
                raw = bytes(data)
                payload[rel] = raw
                entries.append(Entry(rel, len(raw), sha256_bytes(raw), KIND_DATABASE))
                report = check_sqlite(raw)
                report.path = rel
                reports.append(report)
            except Exception as exc:  # noqa: BLE001
                failures.append({"path": rel, "error": f"{type(exc).__name__}: {exc}"})

        if not entries:
            self._record("backup_failed", severity="medium", backup_id=bid,
                         failures=failures, reason="nothing captured")
            raise BackupError(f"backup {bid} captured nothing: {failures}")

        status = STATUS_PARTIAL if failures else STATUS_COMPLETE
        manifest = BackupManifest(
            backup_id=bid,
            created_at=utcnow(),
            status=status,
            entries=entries,
            databases=reports,
            failures=failures,
            notes=note,
        )

        try:
            container = self._seal(manifest, payload)
        except KeyUnavailableError:
            # A missing key is a configuration refusal, not a sealing fault;
            # surface it unchanged so callers can tell the two apart.
            self._record("backup_failed", severity="high", backup_id=bid,
                         reason="no backup key configured")
            raise
        except Exception as exc:  # noqa: BLE001 - encryption/seal failure is fatal
            self._record("backup_failed", severity="high", backup_id=bid,
                         reason=f"{type(exc).__name__}: {exc}")
            raise BackupError(f"backup {bid} could not be sealed: {exc}") from exc

        path = self.container_path(bid)
        self._atomic_write(path, container)
        record = {
            "backup_id": bid,
            "created_at": manifest.created_at,
            "status": status,
            "size": len(container),
            "sha256": sha256_bytes(container),
            "entries": len(entries),
            "databases": len(reports),
            "failures": len(failures),
        }
        self._index_append(record)
        self._record("backup_created", backup_id=bid, status=status,
                     entries=len(entries), databases=len(reports),
                     failures=len(failures), size=len(container))
        return record

    def _seal(self, manifest: BackupManifest, payload: Dict[str, bytes]) -> bytes:
        container = {
            "format": FORMAT,
            "manifest": manifest.to_dict(),
            "manifest_hash": manifest.manifest_hash(),
            "files": {k: base64.b64encode(v).decode() for k, v in payload.items()},
        }
        body = json.dumps(container, sort_keys=True, separators=(",", ":"), default=str)
        return self.encryption.encrypt(body).encode("utf-8")

    def _open(self, backup_id: str) -> Tuple[BackupManifest, Dict[str, bytes]]:
        path = self.container_path(backup_id)
        if not path.is_file():
            raise BackupError(f"backup '{backup_id}' not found")
        body = self.encryption.decrypt(_read_container_text(path, backup_id))
        try:
            container = json.loads(body)
        except json.JSONDecodeError as exc:
            raise BackupError(f"backup '{backup_id}' is not a valid container: {exc}") from exc
        if container.get("format") != FORMAT:
            raise BackupError(f"backup '{backup_id}' has an unknown format")
        manifest = BackupManifest.from_dict(container["manifest"])
        if container.get("manifest_hash") != manifest.manifest_hash():
            raise BackupError(f"backup '{backup_id}' manifest hash does not match its content")
        files = {k: base64.b64decode(v) for k, v in container.get("files", {}).items()}
        return manifest, files

    def migrate_container(
        self,
        backup_id: str,
        legacy_key: bytes,
        keep_original: bool = True,
    ) -> Dict[str, Any]:
        """Re-encrypt a container that was sealed by an older key derivation.

        The key derivation changed twice (single SHA-256, then PBKDF2 with
        200,000 iterations), so ciphertext from an older release cannot be
        opened by the current service. Rather than dropping it, the container is
        decrypted with the caller-supplied legacy key, verified against its own
        manifest, and re-sealed with the current key.

        Safety: the manifest and every payload hash are verified *before* the
        file is replaced, the re-sealed blob is proved to decrypt back to the
        identical body, and the original is kept alongside as
        ``<id>.gbk.pre-migration`` unless ``keep_original=False``.
        """
        path = self.container_path(backup_id)
        if not path.is_file():
            raise BackupError(f"backup '{backup_id}' not found")

        sealed = _read_container_text(path, backup_id)
        try:
            body = decrypt_with_raw_key(sealed, legacy_key)
        except LegacyCiphertextError as exc:
            raise BackupError(
                f"backup '{backup_id}' was not sealed with the supplied legacy key"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - a migration must not guess
            raise BackupError(
                f"backup '{backup_id}' could not be opened: {type(exc).__name__}"
            ) from exc

        try:
            container = json.loads(body)
        except json.JSONDecodeError as exc:
            raise BackupError(f"backup '{backup_id}' is not a valid container: {exc}") from exc
        if container.get("format") != FORMAT:
            raise BackupError(f"backup '{backup_id}' has an unknown format")
        manifest = BackupManifest.from_dict(container["manifest"])
        if container.get("manifest_hash") != manifest.manifest_hash():
            raise BackupError(
                f"backup '{backup_id}' manifest hash does not match its content"
            )
        files = {k: base64.b64decode(v) for k, v in container.get("files", {}).items()}
        integrity = verify_payload(files, manifest.entries)
        if not integrity.ok:
            raise BackupError(
                f"backup '{backup_id}' failed its own integrity check: {integrity.detail}"
            )

        resealed = self.encryption.encrypt(body)
        if self.encryption.decrypt(resealed) != body:
            raise BackupError(
                f"backup '{backup_id}' re-encryption did not round-trip; nothing written"
            )

        original = path.with_name(path.name + ".pre-migration")
        if keep_original:
            self._atomic_write(original, sealed.encode("utf-8"))
        self._atomic_write(path, resealed.encode("utf-8"))
        self._record("backup_migrated", severity="info", backup_id=backup_id,
                     entries=len(files), original_kept=bool(keep_original))
        return {
            "backup_id": backup_id,
            "migrated": True,
            "entries": len(files),
            "original_kept": bool(keep_original),
            "original_path": str(original) if keep_original else None,
        }

    # -- verify / restore -----------------------------------------------------

    def verify(self, backup_id: str) -> IntegrityResult:
        """Decrypt and re-hash a backup, proving it is intact and unmodified."""
        try:
            manifest, files = self._open(backup_id)
        except Exception as exc:  # noqa: BLE001
            result = IntegrityResult(ok=False, detail=f"{type(exc).__name__}: {exc}")
            self._record("backup_verify_failed", severity="medium",
                         backup_id=backup_id, detail=result.detail)
            return result
        result = verify_payload(files, manifest.entries)
        for report in manifest.databases:
            if not report.ok:
                result.ok = False
                result.detail = (result.detail + f"; db {report.path}: {report.detail}").strip("; ")
        self._record("backup_verified" if result.ok else "backup_verify_failed",
                     severity="info" if result.ok else "medium",
                     backup_id=backup_id, checked=result.checked, detail=result.detail)
        return result

    def restore(
        self,
        backup_id: str,
        dest_root: str,
        overwrite: bool = False,
        verify: bool = True,
    ) -> Dict[str, Any]:
        """Restore a backup to ``dest_root`` after verifying it.

        Refuses to write anything unless the backup verifies (unless ``verify`` is
        explicitly disabled), and refuses to clobber an existing file unless
        ``overwrite`` is set. Returns a structured result; a refusal is reported,
        not raised, so the caller keeps the reason.
        """
        result: Dict[str, Any] = {
            "backup_id": backup_id,
            "dest": str(dest_root),
            "ok": False,
            "restored": [],
            "skipped": [],
            "failed": [],
        }
        try:
            manifest, files = self._open(backup_id)
        except Exception as exc:  # noqa: BLE001
            result["error"] = f"{type(exc).__name__}: {exc}"
            self._record("restore_failed", severity="medium", backup_id=backup_id,
                         reason=result["error"])
            return result

        if verify:
            integrity = verify_payload(files, manifest.entries)
            if not integrity.ok:
                result["error"] = f"integrity check failed: {integrity.detail}"
                result["integrity"] = integrity.to_dict()
                self._record("restore_refused", severity="high", backup_id=backup_id,
                             reason=result["error"])
                return result
            result["integrity"] = integrity.to_dict()

        base = Path(dest_root)
        base.mkdir(parents=True, exist_ok=True)
        for entry in manifest.entries:
            target = base / entry.path
            if target.exists() and not overwrite:
                result["skipped"].append(entry.path)
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                self._atomic_write(target, files[entry.path])
                result["restored"].append(entry.path)
            except Exception as exc:  # noqa: BLE001
                result["failed"].append({"path": entry.path, "error": str(exc)})

        result["ok"] = not result["failed"]
        self._record("restore_completed" if result["ok"] else "restore_failed",
                     severity="info" if result["ok"] else "medium",
                     backup_id=backup_id, restored=len(result["restored"]),
                     skipped=len(result["skipped"]), failed=len(result["failed"]))
        return result

    def load(self, backup_id: str) -> Tuple[BackupManifest, Dict[str, bytes]]:
        """Return the manifest and decrypted payload of a backup."""
        return self._open(backup_id)

    # -- listing / retention --------------------------------------------------

    def records(self) -> List[Dict[str, Any]]:
        if not self.index_path.is_file():
            return []
        out: List[Dict[str, Any]] = []
        for line in self.index_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def list_backups(self) -> List[Dict[str, Any]]:
        return sorted(self.records(), key=lambda r: r.get("created_at", ""), reverse=True)

    def apply_retention(self, keep: int = 7, max_age_days: Optional[int] = None,
                        now: Optional[str] = None) -> Dict[str, Any]:
        """Delete old backups under an explicit policy.

        Always keeps the newest backup (and at least one), even if it is older
        than ``max_age_days``. Only containers the vault itself wrote are removed.
        """
        records = self.list_backups()  # newest first
        if not records:
            return {"removed": [], "kept": []}
        kept: List[Dict[str, Any]] = []
        removed: List[str] = []
        keep = max(1, int(keep))
        reference = _parse_ts(now) if now else None

        for position, record in enumerate(records):
            bid = record.get("backup_id", "")
            too_many = position >= keep
            too_old = (
                max_age_days is not None
                and reference is not None
                and position > 0
                and _age_days(record.get("created_at", ""), reference) > max_age_days
            )
            if too_many or too_old:
                try:
                    self.container_path(bid).unlink()
                    removed.append(bid)
                except FileNotFoundError:
                    removed.append(bid)
                except OSError:
                    kept.append(record)
            else:
                kept.append(record)

        if removed:
            self._record("backup_pruned", backup_id=",".join(removed),
                         count=len(removed), keep=keep, max_age_days=max_age_days)
        return {"removed": removed, "kept": [r.get("backup_id") for r in kept]}

    # -- helpers --------------------------------------------------------------

    def _new_id(self) -> str:
        stamp = utcnow().replace(":", "").replace("-", "").replace(".", "")
        with self._lock:
            existing = {r.get("backup_id") for r in self.records()}
        candidate = f"bk-{stamp}"
        suffix = 0
        while candidate in existing or self.container_path(candidate).exists():
            suffix += 1
            candidate = f"bk-{stamp}-{suffix}"
        return candidate

    def _index_append(self, record: Dict[str, Any]) -> None:
        with self._lock:
            with open(self.index_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, sort_keys=True) + "\n")

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)


def _parse_ts(value: str):
    from datetime import datetime, timezone

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(timezone.utc)


def _age_days(created_at: str, reference) -> float:
    created = _parse_ts(created_at)
    try:
        return (reference - created).total_seconds() / 86400.0
    except TypeError:
        return 0.0


def _read_container_text(path: Path, backup_id: str) -> str:
    """Container bytes as text, or a BackupError that says what is wrong.

    A truncated or foreign file used to surface as ``UnicodeDecodeError`` from
    ``read_text``, which read like a bug rather than the corruption it is.
    """
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BackupError(
            f"backup '{backup_id}' is corrupt: the container is not the expected "
            "encrypted text (truncated file, wrong format, or a different key)"
        ) from exc
