"""Survival & disaster recovery (V7 P8B).

Backups you can prove are restorable, and recovery you can audit.

* ``manifest`` - the self-describing backup manifest and the integrity checks
                 (SHA-256 per entry, manifest hash, SQLite integrity report).
* ``vault``    - encrypted backup containers (Fernet), fail-closed on a missing
                 key, with verify / restore / retention and an append-only index.
* ``manager``  - orchestration: backup sources, verified restore, restoration
                 tests (drills), best-effort database recovery, a recovery audit
                 trail and a readiness summary.

Rules this package holds to:

* **Fail closed.** No durable key means no backup is written - a backup nobody
  can decrypt is worse than none.
* **Verify before restore.** A backup that does not re-hash to its manifest is
  refused; restoring it is a refusal, not a best-effort guess.
* **Never destructive by default.** Restore does not overwrite existing files
  unless explicitly told to; the only deletion is backup pruning under an
  explicit retention policy, which always keeps the newest backup.
* **Auditable.** Every backup, verify, restore, drill and recovery writes to the
  canonical hash-chained ``SecurityEventLog`` under source ``recovery``.
"""
from genesis_protocol.recovery.manager import RecoveryManager
from genesis_protocol.recovery.manifest import (
    KIND_DATABASE,
    KIND_FILE,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_PARTIAL,
    BackupManifest,
    DatabaseReport,
    Entry,
    IntegrityResult,
    sha256_bytes,
    sha256_file,
    verify_directory,
    verify_payload,
)
from genesis_protocol.recovery.vault import (
    BackupError,
    BackupVault,
    KeyUnavailableError,
    check_sqlite,
    resolve_key,
)

__all__ = [
    "RecoveryManager",
    "BackupVault",
    "BackupError",
    "KeyUnavailableError",
    "resolve_key",
    "check_sqlite",
    "BackupManifest",
    "Entry",
    "DatabaseReport",
    "IntegrityResult",
    "verify_payload",
    "verify_directory",
    "sha256_bytes",
    "sha256_file",
    "STATUS_COMPLETE",
    "STATUS_PARTIAL",
    "STATUS_FAILED",
    "KIND_FILE",
    "KIND_DATABASE",
]
