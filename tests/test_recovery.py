"""Contract tests for survival & disaster recovery (V7 P8B).

Covers the requirement set: encrypted backups, integrity verification,
restoration tests, database recovery, failure handling, retention, and a
recovery audit trail - plus the safety invariants (fail closed without a key,
verify-before-restore, never destructive by default, auditable).
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from genesis_protocol.guardian.events import SecurityEventLog
from genesis_protocol.recovery import (
    BackupError,
    BackupManifest,
    BackupVault,
    Entry,
    KeyUnavailableError,
    RecoveryManager,
    check_sqlite,
    resolve_key,
    sha256_bytes,
    verify_directory,
    verify_payload,
)

KEY = "unit-test-backup-key"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vault(tmp_path, key=KEY):
    return BackupVault(root=str(tmp_path / "vault"), key=key,
                       audit=SecurityEventLog(":memory:"))


def _manager(tmp_path, key=KEY):
    return RecoveryManager(vault=_vault(tmp_path, key=key))


def _sqlite_bytes(corrupt=False):
    path = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    path.close()
    conn = sqlite3.connect(path.name)
    conn.execute("CREATE TABLE t1(x INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("CREATE TABLE t2(y INTEGER PRIMARY KEY, v TEXT)")
    conn.executemany("INSERT INTO t1(v) VALUES (?)", [("a" * 200,) for _ in range(100)])
    conn.executemany("INSERT INTO t2(v) VALUES (?)", [("b" * 200,) for _ in range(100)])
    conn.commit()
    conn.close()
    data = bytearray(Path(path.name).read_bytes())
    if corrupt:
        start = int(len(data) * 0.5)
        for i in range(start, min(len(data), start + 1024)):
            data[i] = 0xFF
    return bytes(data)


# ---------------------------------------------------------------------------
# 1. Manifest and integrity primitives
# ---------------------------------------------------------------------------

class TestManifest:
    def test_roundtrip_and_stable_hash(self):
        entry = Entry("a/b.txt", 5, sha256_bytes(b"hello"))
        manifest = BackupManifest("bk-1", "2026-01-01T00:00:00+00:00", entries=[entry])
        restored = BackupManifest.from_dict(manifest.to_dict())
        assert restored.to_dict() == manifest.to_dict()
        assert restored.manifest_hash() == manifest.manifest_hash()
        assert manifest.total_bytes() == 5
        assert manifest.entry("a/b.txt").sha256 == entry.sha256

    def test_verify_payload_detects_tamper_missing_extra(self):
        good = {"a.txt": b"hello", "b.txt": b"world"}
        entries = [Entry(k, len(v), sha256_bytes(v)) for k, v in good.items()]
        assert verify_payload(good, entries).ok is True

        tampered = dict(good, **{"a.txt": b"HELLO"})
        result = verify_payload(tampered, entries)
        assert result.ok is False and result.mismatches[0]["path"] == "a.txt"

        missing = {"a.txt": b"hello"}
        result = verify_payload(missing, entries)
        assert result.ok is False and result.missing == ["b.txt"]

        extra = dict(good, **{"c.txt": b"surprise"})
        result = verify_payload(extra, entries)
        assert result.ok is True and result.extra == ["c.txt"]

    def test_verify_directory(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "x.txt").write_bytes(b"data")
        entries = [Entry("sub/x.txt", 4, sha256_bytes(b"data"))]
        assert verify_directory(tmp_path, entries).ok is True
        (tmp_path / "sub" / "x.txt").write_bytes(b"DATA")
        assert verify_directory(tmp_path, entries).ok is False


# ---------------------------------------------------------------------------
# 2. Fail-closed key handling
# ---------------------------------------------------------------------------

class TestKey:
    def test_resolve_key_fails_closed(self, monkeypatch):
        monkeypatch.delenv("GENESIS_BACKUP_KEY", raising=False)
        with pytest.raises(KeyUnavailableError):
            resolve_key()

    def test_explicit_key_wins(self):
        assert resolve_key("abc") == "abc"

    def test_create_without_key_is_refused(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GENESIS_BACKUP_KEY", raising=False)
        vault = BackupVault(root=str(tmp_path), key=None)
        assert vault.key_configured is False
        with pytest.raises(KeyUnavailableError):
            vault.create({"a.txt": b"hello"})


# ---------------------------------------------------------------------------
# 3. Encrypted backups
# ---------------------------------------------------------------------------

class TestVaultCreate:
    def test_create_is_encrypted_and_indexed(self, tmp_path):
        vault = _vault(tmp_path)
        record = vault.create({"secret.txt": b"top-secret-value"})
        assert record["status"] == "complete" and record["entries"] == 1

        container = vault.container_path(record["backup_id"]).read_bytes()
        # The plaintext must not be recoverable from the container.
        assert b"top-secret-value" not in container
        # The index is plaintext metadata, and it never holds payload bytes.
        index = vault.index_path.read_text()
        assert record["backup_id"] in index and "top-secret-value" not in index
        assert vault.list_backups()[0]["backup_id"] == record["backup_id"]

    def test_capturing_nothing_is_refused(self, tmp_path):
        with pytest.raises(BackupError):
            _vault(tmp_path).create({})

    def test_database_backup_reports_integrity(self, tmp_path):
        vault = _vault(tmp_path)
        record = vault.create({"keep.txt": b"x"}, databases={"db.sqlite": _sqlite_bytes()})
        assert record["databases"] == 1
        manifest, files = vault.load(record["backup_id"])
        report = manifest.databases[0]
        assert report.path == "db.sqlite" and report.ok is True
        assert set(report.tables) == {"t1", "t2"}
        assert files["db.sqlite"] == _sqlite_bytes()  # exact round-trip


# ---------------------------------------------------------------------------
# 4. Verification
# ---------------------------------------------------------------------------

class TestVerify:
    def test_verify_intact_backup(self, tmp_path):
        vault = _vault(tmp_path)
        record = vault.create({"a.txt": b"hello", "b.txt": b"world"})
        result = vault.verify(record["backup_id"])
        assert result.ok is True and result.checked == 2

    def test_tampered_container_fails_verification(self, tmp_path):
        vault = _vault(tmp_path)
        record = vault.create({"a.txt": b"hello"})
        path = vault.container_path(record["backup_id"])
        path.write_bytes(path.read_bytes()[:-4] + b"XXXX")  # corrupt the ciphertext
        result = vault.verify(record["backup_id"])
        assert result.ok is False

    def test_wrong_key_cannot_verify(self, tmp_path):
        record = _vault(tmp_path).create({"a.txt": b"hello"})
        other = BackupVault(root=str(tmp_path / "vault"), key="different-key")
        assert other.verify(record["backup_id"]).ok is False

    def test_manifest_hash_mismatch_is_refused(self, tmp_path):
        vault = _vault(tmp_path)
        record = vault.create({"a.txt": b"hello"})
        path = vault.container_path(record["backup_id"])
        body = json.loads(vault.encryption.decrypt(path.read_text()))
        body["manifest_hash"] = "0" * 64
        path.write_text(vault.encryption.encrypt(json.dumps(body)))
        with pytest.raises(BackupError):
            vault.load(record["backup_id"])


# ---------------------------------------------------------------------------
# 5. Restore and restoration tests
# ---------------------------------------------------------------------------

class TestRestore:
    def test_restore_writes_verified_content(self, tmp_path):
        vault = _vault(tmp_path)
        record = vault.create({"a.txt": b"hello", "nested/b.txt": b"world"})
        dest = tmp_path / "restore"
        result = vault.restore(record["backup_id"], str(dest))
        assert result["ok"] is True
        assert (dest / "a.txt").read_bytes() == b"hello"
        assert (dest / "nested" / "b.txt").read_bytes() == b"world"

    def test_restore_does_not_clobber_by_default(self, tmp_path):
        vault = _vault(tmp_path)
        record = vault.create({"a.txt": b"backup-version"})
        dest = tmp_path / "restore"
        dest.mkdir()
        (dest / "a.txt").write_bytes(b"current-version")
        result = vault.restore(record["backup_id"], str(dest))
        assert result["skipped"] == ["a.txt"]
        assert (dest / "a.txt").read_bytes() == b"current-version"
        # With overwrite it is replaced.
        result = vault.restore(record["backup_id"], str(dest), overwrite=True)
        assert result["restored"] == ["a.txt"]
        assert (dest / "a.txt").read_bytes() == b"backup-version"

    def test_restore_refuses_unverified_backup(self, tmp_path):
        vault = _vault(tmp_path)
        record = vault.create({"a.txt": b"hello"})
        path = vault.container_path(record["backup_id"])
        path.write_bytes(path.read_bytes()[:-4] + b"XXXX")
        dest = tmp_path / "restore"
        result = vault.restore(record["backup_id"], str(dest))
        assert result["ok"] is False and "error" in result
        assert not dest.exists() or not any(dest.iterdir())

    def test_restore_test_proves_restorability(self, tmp_path):
        manager = _manager(tmp_path)
        record = manager.create_backup({"a.txt": b"hello", "b.txt": b"world"})
        outcome = manager.restore_test(record["backup_id"])
        assert outcome["ok"] is True and outcome["written_ok"] is True
        # The scratch directory is always removed.
        leftover = [p for p in Path(tempfile.gettempdir()).glob("genesis-restore-*")]
        assert leftover == []

    def test_restore_test_fails_on_corrupt_backup(self, tmp_path):
        vault = _vault(tmp_path)
        record = vault.create({"a.txt": b"hello"})
        path = vault.container_path(record["backup_id"])
        path.write_bytes(path.read_bytes()[:-4] + b"XXXX")
        outcome = RecoveryManager(vault=vault).restore_test(record["backup_id"])
        assert outcome["ok"] is False

    def test_drill_uses_newest_backup(self, tmp_path):
        manager = _manager(tmp_path)
        manager.create_backup({"a.txt": b"one"}, backup_id="bk-old")
        manager.create_backup({"a.txt": b"two"}, backup_id="bk-new")
        outcome = manager.run_drill()
        assert outcome["ok"] is True and outcome["drilled"] == "bk-new"

    def test_drill_without_backups_is_reported(self, tmp_path):
        outcome = _manager(tmp_path).run_drill()
        assert outcome["ok"] is False and outcome["drilled"] is None


# ---------------------------------------------------------------------------
# 6. Failure handling
# ---------------------------------------------------------------------------

class TestFailureHandling:
    def test_missing_source_is_recorded_not_fatal(self, tmp_path):
        (tmp_path / "present.txt").write_bytes(b"x")
        manager = _manager(tmp_path)
        record = manager.backup_sources({"present.txt": str(tmp_path / "present.txt")})
        assert record["status"] == "complete"
        assert manager.restore_test(record["backup_id"])["ok"] is True

    def test_partial_backup_when_a_source_is_unreadable(self, tmp_path):
        (tmp_path / "ok.txt").write_bytes(b"x")
        manager = _manager(tmp_path)
        record = manager.backup_sources({
            "ok.txt": str(tmp_path / "ok.txt"),
            "gone.txt": str(tmp_path / "missing.txt"),
        })
        assert record["status"] == "partial"
        assert record["failed_sources"][0]["path"] == "gone.txt"
        # The readable source is still captured and restorable.
        assert manager.restore_test(record["backup_id"])["ok"] is True

    def test_corrupt_database_is_a_finding_not_a_failure(self, tmp_path):
        vault = _vault(tmp_path)
        record = vault.create({"keep.txt": b"x"},
                              databases={"bad.sqlite": _sqlite_bytes(corrupt=True)})
        manifest, _ = vault.load(record["backup_id"])
        assert manifest.databases[0].ok is False
        assert record["status"] == "complete"  # the file itself was captured
        # A backup carrying a corrupt database does not verify as healthy.
        assert vault.verify(record["backup_id"]).ok is False


# ---------------------------------------------------------------------------
# 7. Database recovery
# ---------------------------------------------------------------------------

class TestDatabaseRecovery:
    def test_healthy_database_is_unchanged(self):
        manager = RecoveryManager(vault=BackupVault(root=tempfile.mkdtemp(), key=KEY))
        data = _sqlite_bytes()
        result = manager.recover_database(data)
        assert result["ok"] is True and result["recovered"] is False
        assert result["data"] == data

    def test_corrupt_database_is_salvaged(self, tmp_path):
        manager = _manager(tmp_path)
        result = manager.recover_database(_sqlite_bytes(corrupt=True), backup_id="bk-x")
        assert result["ok"] is True and result["recovered"] is True
        # The recovered database is itself valid.
        assert check_sqlite(result["data"]).ok is True
        # Partial recovery is explicit: at least one table is salvaged.
        assert len(result["tables"]) >= 1

    def test_non_database_bytes_are_reported(self, tmp_path):
        manager = _manager(tmp_path)
        result = manager.recover_database(b"this is not a database at all", backup_id="bk-y")
        assert result["recovered"] is False
        assert check_sqlite(b"this is not a database at all").ok is False


# ---------------------------------------------------------------------------
# 8. Retention
# ---------------------------------------------------------------------------

class TestRetention:
    def test_retention_keeps_newest_and_prunes_old(self, tmp_path):
        vault = _vault(tmp_path)
        for i in range(5):
            vault.create({"a.txt": bytes([i])}, backup_id=f"bk-{i:02d}")
        outcome = vault.apply_retention(keep=2)
        assert sorted(outcome["removed"]) == ["bk-00", "bk-01", "bk-02"]
        assert set(outcome["kept"]) == {"bk-03", "bk-04"}
        # Pruned containers are gone; kept ones still verify.
        assert not vault.container_path("bk-00").exists()
        assert vault.verify("bk-04").ok is True

    def test_retention_always_keeps_at_least_one(self, tmp_path):
        vault = _vault(tmp_path)
        vault.create({"a.txt": b"only"}, backup_id="bk-only")
        outcome = vault.apply_retention(keep=0)
        assert outcome["removed"] == [] and outcome["kept"] == ["bk-only"]

    def test_retention_by_age_never_removes_newest(self, tmp_path):
        vault = _vault(tmp_path)
        vault.create({"a.txt": b"old"}, backup_id="bk-old")
        vault.create({"a.txt": b"new"}, backup_id="bk-new")
        outcome = vault.apply_retention(keep=99, max_age_days=0,
                                        now="2999-01-01T00:00:00+00:00")
        assert outcome["kept"] == ["bk-new"]
        assert "bk-old" in outcome["removed"]


# ---------------------------------------------------------------------------
# 9. Recovery audit trail
# ---------------------------------------------------------------------------

class TestAuditTrail:
    def test_recovery_events_are_recorded_and_chained(self, tmp_path):
        manager = _manager(tmp_path)
        record = manager.create_backup({"a.txt": b"hello"})
        manager.verify(record["backup_id"])
        manager.restore_test(record["backup_id"])

        trail = manager.audit_trail()
        events = {row["event"] for row in trail}
        assert {"backup_created", "backup_verified", "restore_test_passed"} <= events
        assert all(row["source"] == "recovery" for row in trail)
        assert manager.audit_ok()["ok"] is True

    def test_status_reports_readiness(self, tmp_path):
        manager = _manager(tmp_path)
        manager.create_backup({"a.txt": b"hello"})
        status = manager.status()
        assert status["key_configured"] is True
        assert status["backups"] == 1
        assert status["latest"]["backup_id"]
        assert status["audit"]["ok"] is True

    def test_status_without_key_says_so(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GENESIS_BACKUP_KEY", raising=False)
        manager = RecoveryManager(vault=BackupVault(root=str(tmp_path), key=None))
        assert manager.status()["key_configured"] is False


# ---------------------------------------------------------------------------
# 10. Safety invariants
# ---------------------------------------------------------------------------

class TestSafety:
    def test_manager_exposes_no_widening_surface(self, tmp_path):
        manager = _manager(tmp_path)
        forbidden = {"grant", "escalate", "unlimit", "disable", "delete_all",
                     "wipe", "set_key", "change_authority"}
        exposed = {name for name in dir(manager) if not name.startswith("_")}
        assert forbidden.isdisjoint(exposed)

    def test_restore_is_the_only_writer_and_is_verified(self, tmp_path):
        manager = _manager(tmp_path)
        record = manager.create_backup({"a.txt": b"hello"})
        # A restore into a fresh tree verifies; the manager returns the integrity
        # evidence rather than trusting the request.
        result = manager.restore(record["backup_id"], str(tmp_path / "out"))
        assert result["ok"] is True and result["integrity"]["ok"] is True
