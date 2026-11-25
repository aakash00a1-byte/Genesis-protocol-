#!/usr/bin/env python3
"""Re-encrypt backup-vault containers sealed by an older key derivation.

The vault key derivation has changed twice:

* pre-v7: ``sha256(password)``
* v7 PR #87 first pass: PBKDF2-HMAC-SHA256, 200,000 iterations
* v7 PR #87 final: PBKDF2-HMAC-SHA256, 600,000 iterations

Ciphertext from an older build cannot be opened by the current
``EncryptionService``. This tool is the migration path: it opens each container
with the *legacy key* you supply, verifies the container against its own
manifest, and re-seals it with the current key.

The legacy key is derived outside this tool on purpose - the repository does not
carry a weak-hash call on a password, and the derivation for an old build is a
one-liner in ``docs/security/V7_SECURITY_RECOVERY.md``.

Usage::

    export GENESIS_BACKUP_KEY='...'                    # the CURRENT key
    export LEGACY_BACKUP_KEY_HEX=$(python3 -c '...')   # see the docs
    python3 scripts/migrate_backup_vault.py --vault-dir data/backups           # dry run
    python3 scripts/migrate_backup_vault.py --vault-dir data/backups --apply

Nothing is written without ``--apply``. The original container is kept next to
the migrated one as ``<id>.gbk.pre-migration`` unless ``--drop-original`` is
passed. Every migrated container is verified before the command reports success.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genesis_protocol.recovery.vault import CONTAINER_SUFFIX, BackupVault
from genesis_protocol.security.encryption import (
    EncryptionService,
    LegacyCiphertextError,
)

LEGACY_SUFFIX = CONTAINER_SUFFIX + ".pre-migration"


def _containers(vault_dir: str) -> list[str]:
    try:
        names = os.listdir(vault_dir)
    except OSError as exc:
        raise SystemExit(f"cannot read vault dir {vault_dir!r}: {exc.strerror}") from exc
    ids = []
    for name in sorted(names):
        if not name.endswith(CONTAINER_SUFFIX) or name.endswith(LEGACY_SUFFIX):
            continue
        ids.append(name[: -len(CONTAINER_SUFFIX)])
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vault-dir", default=os.environ.get("GENESIS_BACKUP_DIR", "data/backups"))
    parser.add_argument("--new-key", default=os.environ.get("GENESIS_BACKUP_KEY", ""),
                        help="current vault key (defaults to GENESIS_BACKUP_KEY)")
    parser.add_argument("--legacy-key-hex", default=os.environ.get("LEGACY_BACKUP_KEY_HEX", ""),
                        help="the old 32-byte key as 64 hex characters")
    parser.add_argument("--apply", action="store_true", help="write the migrated containers")
    parser.add_argument("--drop-original", action="store_true",
                        help="delete the .pre-migration copy after a verified migration")
    args = parser.parse_args(argv)

    if not args.new_key:
        print("no current key: set GENESIS_BACKUP_KEY or pass --new-key")
        return 2
    try:
        legacy_key = bytes.fromhex(args.legacy_key_hex.strip())
    except ValueError:
        print("--legacy-key-hex must be 64 hex characters (a 32-byte key)")
        return 2
    if len(legacy_key) != 32:
        print("--legacy-key-hex must decode to exactly 32 bytes")
        return 2

    ids = _containers(args.vault_dir)
    print(f"vault: {args.vault_dir}")
    print(f"containers: {len(ids)}")
    if not ids:
        return 0

    current = EncryptionService(key=args.new_key)
    vault = BackupVault(root=args.vault_dir, key=args.new_key)
    todo: list[str] = []
    for backup_id in ids:
        path = vault.container_path(backup_id)
        try:
            sealed = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"  {backup_id}: UNREADABLE ({type(exc).__name__}) - left untouched")
            return 1
        try:
            current.decrypt(sealed)
        except LegacyCiphertextError:
            todo.append(backup_id)
            print(f"  {backup_id}: legacy ciphertext - needs migration")
        except Exception as exc:  # noqa: BLE001
            print(f"  {backup_id}: cannot inspect ({type(exc).__name__}) - left untouched")
            return 1
        else:
            print(f"  {backup_id}: already readable with the current key - skipped")

    if not todo:
        print("nothing to migrate")
        return 0

    if not args.apply:
        print(f"\ndry run: {len(todo)} container(s) would be re-encrypted; pass --apply")
        return 0

    failures = 0
    for backup_id in todo:
        try:
            report = vault.migrate_container(
                backup_id, legacy_key, keep_original=not args.drop_original
            )
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"  {backup_id}: MIGRATION FAILED ({type(exc).__name__}: {exc})")
            failures += 1
            continue
        check = vault.verify(backup_id)
        if not check.ok:
            print(f"  {backup_id}: migrated but verification FAILED ({check.detail})")
            failures += 1
            continue
        kept = report["original_path"] if report["original_kept"] else "no"
        print(f"  {backup_id}: migrated + verified ({report['entries']} entries, original kept: {kept})")

    print(f"\nmigrated: {len(todo) - failures}/{len(todo)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
