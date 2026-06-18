# Backup and Recovery Guide

## Overview

This document describes the backup and recovery procedures for Genesis Protocol.

## What Gets Backed Up

1. **SQLite Database** (`genesis.db`)
   - User accounts
   - Chat history
   - Usage statistics

2. **Chat History Export** (JSON)
   - All conversations with metadata
   - User information
   - Timestamps

## Creating Backups

### Manual Backup

```bash
# From project root
python scripts/backup.py --output ./backups

# Custom database location
python scripts/backup.py --db /path/to/genesis.db --output ./backups
```

### Automated Backup (Railway)

Add a cron job or use Railway's scheduled deployments:

```bash
# In Railway shell or cron
0 2 * * * cd /app && python scripts/backup.py --db genesis.db --output /app/backups
```

### GitHub Actions (Recommended)

Create `.github/workflows/backup.yml`:

```yaml
name: Database Backup

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM
  workflow_dispatch:

jobs:
  backup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run backup
        run: python scripts/backup.py --output ./backups
      - name: Upload to cloud storage
        # Add your preferred storage (S3, GCS, etc.)
```

## Restoring from Backup

### Restore SQLite Database

```bash
# Restore from backup file
python scripts/restore.py --sqlite ./backups/genesis_db_20260618_020000.sqlite

# Restore to custom location
python scripts/restore.py --sqlite ./backups/genesis_db_20260618_020000.sqlite --target genesis_new.db
```

### Import Chat History

```python
import json
import sqlite3

with open('chat_history_20260618_020000.json') as f:
    data = json.load(f)

conn = sqlite3.connect('genesis.db')
cursor = conn.cursor()

for item in data['history']:
    cursor.execute('''
        INSERT INTO chat_history (user_id, message, response, model_used, provider, quality_score, mode, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        item['user_id'],
        item['message'],
        item['response'],
        item.get('model_used'),
        item.get('provider'),
        item.get('quality_score'),
        item.get('mode'),
        item.get('created_at')
    ))

conn.commit()
conn.close()
```

## Recovery Point Objective (RPO)

- **Recommended**: Daily backups
- **Minimum**: Weekly backups
- **RPO**: 24 hours maximum data loss

## Recovery Time Objective (RTO)

- **Estimated**: 5-15 minutes for restore
- **Factors**: Backup size, network speed

## Disaster Recovery Checklist

1. [ ] Regular backups are running
2. [ ] Backups are stored in separate location
3. [ ] Restore procedure is tested
4. [ ] Documentation is up to date
5. [ ] Team knows how to restore

## Cloud Storage Options

### Amazon S3

```bash
pip install boto3
aws s3 cp backups/ s3://your-bucket/backups/ --recursive
```

### Google Cloud Storage

```bash
pip install google-cloud-storage
gsutil cp backups/ gs://your-bucket/backups/ --recursive
```

### GitHub Secrets

Store backup files in a private repository or use GitHub Actions artifacts.

## Monitoring

Check backup success via `/api/diagnostics` endpoint:

```bash
curl https://genesis-protocol-00a1.up.railway.app/api/diagnostics
```

Look for:
- `database.history_count` - Total conversations
- `database.user_count` - Total users
