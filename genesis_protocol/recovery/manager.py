"""Survival & disaster recovery orchestration (V7 P8B).

Ties the encrypted vault to the things an operator actually needs:

* **backup**   - capture files and databases (from memory or from disk), with a
                 missing source recorded as a finding rather than an abort;
* **restore**  - verified, non-destructive by default (no clobbering);
* **drill**    - a *restoration test*: prove a backup really can be restored by
                 restoring it into a scratch directory and re-hashing it. This is
                 the only honest evidence that a backup is usable;
* **recover**  - best-effort recovery of a corrupt SQLite database (salvage what
                 is readable into a fresh, valid database and report what was
                 lost);
* **audit**    - a recovery audit trail read from the canonical, hash-chained
                 ``SecurityEventLog`` (source ``recovery``), so recovery is
                 inspectable after the fact and tamper-evident;
* **status**   - a read-only disaster-recovery readiness summary.

Recovery never widens authority and never deletes anything except backup
containers under an explicit retention policy (see ``BackupVault.apply_retention``).
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from genesis_protocol.recovery.manifest import utcnow
from genesis_protocol.recovery.vault import BackupVault, check_sqlite


class RecoveryManager:
    """Backup, verify, restore, drill and audit for Genesis state."""

    def __init__(self, vault: Optional[BackupVault] = None, audit: Optional[Any] = None):
        self.vault = vault or BackupVault()
        self._audit = audit

    @property
    def audit(self) -> Any:
        if self._audit is None:
            self._audit = self.vault.audit
        return self._audit

    # -- backup ---------------------------------------------------------------

    def create_backup(self, items: Dict[str, bytes],
                      databases: Optional[Dict[str, bytes]] = None,
                      backup_id: Optional[str] = None, note: str = "") -> Dict[str, Any]:
        return self.vault.create(items, databases, backup_id=backup_id, note=note)

    def backup_sources(self, files: Dict[str, str], databases: Optional[Dict[str, str]] = None,
                       backup_id: Optional[str] = None, note: str = "") -> Dict[str, Any]:
        """Capture files/databases from disk.

        ``files`` maps the relative path stored in the backup to the source path
        on disk (same for ``databases``). An unreadable source is recorded as a
        failure and the backup proceeds with everything else.
        """
        items: Dict[str, bytes] = {}
        failures: List[Dict[str, str]] = []
        for rel, src in (files or {}).items():
            try:
                items[rel] = Path(src).read_bytes()
            except Exception as exc:  # noqa: BLE001
                failures.append({"path": rel, "error": f"{type(exc).__name__}: {exc}"})

        dbs: Dict[str, bytes] = {}
        for rel, src in (databases or {}).items():
            try:
                dbs[rel] = Path(src).read_bytes()
            except Exception as exc:  # noqa: BLE001
                failures.append({"path": rel, "error": f"{type(exc).__name__}: {exc}"})

        record = self.vault.create(items, dbs, backup_id=backup_id, note=note,
                                   failures=failures)
        if failures:
            record = dict(record)
            record["failed_sources"] = failures
        return record

    # -- verify / restore -----------------------------------------------------

    def verify(self, backup_id: str):
        return self.vault.verify(backup_id)

    def restore(self, backup_id: str, dest_root: str, overwrite: bool = False,
                verify: bool = True) -> Dict[str, Any]:
        return self.vault.restore(backup_id, dest_root, overwrite=overwrite, verify=verify)

    def restore_test(self, backup_id: str) -> Dict[str, Any]:
        """Prove a backup is restorable: verify, restore to scratch, re-hash.

        The scratch directory is always removed, so this never touches production
        data. A backup that fails here is not a backup.
        """
        result: Dict[str, Any] = {"backup_id": backup_id, "ok": False}
        integrity = self.vault.verify(backup_id)
        result["integrity"] = integrity.to_dict()
        if not integrity.ok:
            result["error"] = f"integrity check failed: {integrity.detail}"
            self._record("restore_test_failed", severity="high", backup_id=backup_id,
                         reason=result["error"])
            return result

        scratch = tempfile.mkdtemp(prefix="genesis-restore-")
        try:
            restored = self.vault.restore(backup_id, scratch, overwrite=True, verify=True)
            result["restore"] = restored
            # Re-verify the files that were actually written to disk.
            manifest, _ = self.vault.load(backup_id)
            from genesis_protocol.recovery.manifest import verify_directory

            written = verify_directory(scratch, manifest.entries)
            result["written_ok"] = written.ok
            result["ok"] = bool(restored.get("ok")) and written.ok
            if not result["ok"]:
                result["error"] = written.detail or restored.get("error", "restore incomplete")
        finally:
            _rmtree(scratch)

        self._record("restore_test_passed" if result["ok"] else "restore_test_failed",
                     severity="info" if result["ok"] else "high",
                     backup_id=backup_id, ok=result["ok"])
        return result

    def run_drill(self) -> Dict[str, Any]:
        """Restoration test on the newest backup (disaster-recovery drill)."""
        backups = self.vault.list_backups()
        if not backups:
            self._record("drill_skipped", severity="medium", reason="no backups")
            return {"ok": False, "error": "no backups available", "drilled": None}
        newest = backups[0]["backup_id"]
        outcome = self.restore_test(newest)
        outcome["drilled"] = newest
        return outcome

    # -- database recovery ----------------------------------------------------

    def recover_database(self, data: bytes, backup_id: str = "") -> Dict[str, Any]:
        """Best-effort recovery of a SQLite database.

        A healthy database is returned unchanged. A corrupt one is salvaged: every
        readable table is copied into a fresh, valid database and the rows that
        could not be read are reported, so partial recovery is explicit.
        """
        report = check_sqlite(data)
        if report.ok:
            return {"ok": True, "recovered": False, "data": data,
                    "tables": report.tables, "detail": "database already intact"}

        recovered, salvaged, lost = _salvage_sqlite(data)
        if recovered is None:
            self._record("database_recovery_failed", severity="high",
                         backup_id=backup_id, detail=report.detail)
            return {"ok": False, "recovered": False, "data": None,
                    "tables": [], "lost": lost, "detail": report.detail}

        # The salvaged database must itself pass integrity_check to count.
        check = check_sqlite(recovered)
        ok = check.ok
        self._record("database_recovered" if ok else "database_recovery_failed",
                     severity="info" if ok else "high", backup_id=backup_id,
                     tables=salvaged, lost=len(lost))
        return {"ok": ok, "recovered": True, "data": recovered,
                "tables": salvaged, "lost": lost, "detail": check.detail}

    # -- audit trail ----------------------------------------------------------

    def audit_trail(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Recovery events from the canonical tamper-evident security log."""
        log = self.audit
        if log is None:
            return []
        try:
            entries = log.entries(limit)
        except Exception:
            return []
        rows = [e for e in entries if e.get("source") == "recovery"]
        if limit is not None:
            rows = rows[-limit:]
        return rows

    def audit_ok(self) -> Dict[str, Any]:
        """Verify the hash chain of the log the trail is read from."""
        log = self.audit
        if log is None:
            return {"ok": False, "detail": "no security log configured"}
        try:
            return log.verify()
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}

    # -- status ---------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Read-only disaster-recovery readiness summary."""
        backups = self.vault.list_backups()
        latest = backups[0] if backups else None
        return {
            "vault": str(self.vault.root),
            "key_configured": self.vault.key_configured,
            "backups": len(backups),
            "latest": latest,
            "retention": self._retention_policy(),
            "audit": self.audit_ok(),
            "checked_at": utcnow(),
        }

    def _retention_policy(self) -> Dict[str, Any]:
        return {
            "keep": int(os.environ.get("GENESIS_BACKUP_KEEP", "7") or "7"),
            "max_age_days": _optional_int(os.environ.get("GENESIS_BACKUP_MAX_AGE_DAYS")),
        }

    def apply_retention(self, keep: Optional[int] = None,
                        max_age_days: Optional[int] = None) -> Dict[str, Any]:
        policy = self._retention_policy()
        return self.vault.apply_retention(
            keep=keep if keep is not None else policy["keep"],
            max_age_days=max_age_days if max_age_days is not None else policy["max_age_days"],
        )

    # -- internal -------------------------------------------------------------

    def _record(self, event: str, severity: str = "info", **evidence: Any) -> None:
        log = self.audit
        if log is None:
            return
        try:
            log.record("integrity", event, severity=severity, subject="recovery",
                       evidence=evidence, source="recovery")
        except Exception:
            pass


def _salvage_sqlite(data: bytes):
    """Copy every readable table from a (possibly corrupt) DB into a fresh one."""
    src_handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    dst_handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    salvaged: List[str] = []
    lost: List[Dict[str, str]] = []
    try:
        src_handle.write(data)
        src_handle.close()
        dst_handle.close()

        try:
            src = sqlite3.connect(src_handle.name)
        except sqlite3.DatabaseError as exc:
            return None, salvaged, [{"table": "*", "error": str(exc)}]

        dst = sqlite3.connect(dst_handle.name)
        try:
            try:
                names = [
                    r[0]
                    for r in src.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
                    ).fetchall()
                ]
            except sqlite3.DatabaseError as exc:
                return None, salvaged, [{"table": "*", "error": str(exc)}]

            for name in names:
                try:
                    schema_row = src.execute(
                        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                        (name,),
                    ).fetchone()
                    if not schema_row or not schema_row[0]:
                        lost.append({"table": name, "error": "no schema"})
                        continue
                    dst.execute(schema_row[0])
                    rows = src.execute(f'SELECT * FROM "{name}"').fetchall()
                    if rows:
                        placeholders = ",".join("?" * len(rows[0]))
                        dst.executemany(
                            f'INSERT INTO "{name}" VALUES ({placeholders})', rows
                        )
                    dst.commit()
                    salvaged.append(name)
                except sqlite3.DatabaseError as exc:
                    lost.append({"table": name, "error": str(exc)})
            dst.commit()
        finally:
            dst.close()
            src.close()

        recovered = Path(dst_handle.name).read_bytes()
        return recovered, salvaged, lost
    finally:
        for handle in (src_handle, dst_handle):
            try:
                __import__("os").unlink(handle.name)
            except OSError:
                pass


def _optional_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _rmtree(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)
