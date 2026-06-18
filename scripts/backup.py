#!/usr/bin/env python3
"""
Genesis Protocol - Backup Script

Creates backups of:
- SQLite database (genesis.db)
- Chat history export (JSON)

Usage:
    python scripts/backup.py [--output ./backups]
"""

import os
import sys
import json
import sqlite3
import argparse
from datetime import datetime
from pathlib import Path


def backup_sqlite(db_path: str, output_dir: Path) -> str:
    """Backup SQLite database."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = output_dir / f"genesis_db_{timestamp}.sqlite"
    
    # Use SQLite backup API
    conn = sqlite3.connect(db_path)
    backup_conn = sqlite3.connect(str(backup_file))
    conn.backup(backup_conn)
    backup_conn.close()
    conn.close()
    
    return str(backup_file)


def export_chat_history(db_path: str, output_dir: Path) -> str:
    """Export chat history to JSON."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_file = output_dir / f"chat_history_{timestamp}.json"
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all chat history
    cursor.execute("""
        SELECT h.*, u.username 
        FROM chat_history h
        JOIN users u ON h.user_id = u.id
        ORDER BY h.created_at DESC
    """)
    
    history = [dict(row) for row in cursor.fetchall()]
    
    # Get metadata
    cursor.execute("SELECT COUNT(*) as total_users FROM users")
    cursor.execute("SELECT COUNT(*) as total_messages FROM chat_history")
    
    metadata = {
        "export_date": datetime.now().isoformat(),
        "total_users": cursor.fetchone()["total_users"],
        "total_messages": cursor.fetchall()[0]["total_messages"],
        "history": history
    }
    
    conn.close()
    
    with open(export_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    return str(export_file)


def main():
    parser = argparse.ArgumentParser(description="Genesis Protocol Backup Tool")
    parser.add_argument("--db", default="genesis.db", help="Path to SQLite database")
    parser.add_argument("--output", default="./backups", help="Output directory for backups")
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 50)
    print("Genesis Protocol - Backup Tool")
    print("=" * 50)
    print()
    
    results = {}
    
    # Backup SQLite
    print("📦 Creating SQLite backup...")
    try:
        db_backup = backup_sqlite(args.db, output_dir)
        results['sqlite'] = db_backup
        print(f"   ✅ Saved: {db_backup}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results['sqlite'] = None
    
    # Export chat history
    print("📄 Exporting chat history...")
    try:
        history_export = export_chat_history(args.db, output_dir)
        results['history'] = history_export
        print(f"   ✅ Saved: {history_export}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results['history'] = None
    
    print()
    print("=" * 50)
    print("Backup Complete!")
    print("=" * 50)
    print(f"Output directory: {output_dir}")
    
    return 0 if results['sqlite'] else 1


if __name__ == "__main__":
    sys.exit(main())
