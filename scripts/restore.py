#!/usr/bin/env python3
"""
Genesis Protocol - Restore Script

Restores from backups created by backup.py

Usage:
    python scripts/restore.py --sqlite backup_file.sqlite
"""

import os
import sys
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path


def restore_sqlite(backup_file: str, target_db: str) -> bool:
    """Restore SQLite database from backup."""
    if not os.path.exists(backup_file):
        print(f"❌ Backup file not found: {backup_file}")
        return False
    
    # Create backup of current DB if it exists
    if os.path.exists(target_db):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pre_backup = f"{target_db}.pre_restore_{timestamp}"
        print(f"📦 Creating pre-restore backup: {pre_backup}")
        conn = sqlite3.connect(target_db)
        backup_conn = sqlite3.connect(pre_backup)
        conn.backup(backup_conn)
        backup_conn.close()
        conn.close()
    
    # Restore from backup
    print(f"🔄 Restoring database from {backup_file}...")
    conn = sqlite3.connect(backup_file)
    target_conn = sqlite3.connect(target_db)
    conn.backup(target_conn)
    target_conn.close()
    conn.close()
    
    return True


def main():
    parser = argparse.ArgumentParser(description="Genesis Protocol Restore Tool")
    parser.add_argument("--sqlite", required=True, help="Path to SQLite backup file")
    parser.add_argument("--target", default="genesis.db", help="Target database file")
    args = parser.parse_args()
    
    print("=" * 50)
    print("Genesis Protocol - Restore Tool")
    print("=" * 50)
    print()
    
    if restore_sqlite(args.sqlite, args.target):
        print()
        print("✅ Restore complete!")
        return 0
    else:
        print()
        print("❌ Restore failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
