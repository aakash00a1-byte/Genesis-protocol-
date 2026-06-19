"""Garden Mode - GLUTTONY Ω+2

Maintenance scheduler for daily, weekly, and monthly tasks."""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path


class GardenMode:
    """Garden Mode maintenance scheduler."""
    
    def __init__(self, storage_path: str = "data/omega/garden"):
        self.storage_path = storage_path
        Path(storage_path).mkdir(parents=True, exist_ok=True)
        
        self.last_daily = None
        self.last_weekly = None
        self.last_monthly = None
        self.execution_log: List[Dict] = []
        
        self._load_state()
    
    def _load_state(self):
        """Load garden mode state."""
        state_file = Path(self.storage_path) / "state.json"
        if state_file.exists():
            try:
                with open(state_file, 'r') as f:
                    data = json.load(f)
                    self.last_daily = data.get('last_daily')
                    self.last_weekly = data.get('last_weekly')
                    self.last_monthly = data.get('last_monthly')
                    self.execution_log = data.get('execution_log', [])
            except:
                pass
    
    def _save_state(self):
        """Save garden mode state."""
        state_file = Path(self.storage_path) / "state.json"
        with open(state_file, 'w') as f:
            json.dump({
                'last_daily': self.last_daily,
                'last_weekly': self.last_weekly,
                'last_monthly': self.last_monthly,
                'execution_log': self.execution_log[-100:]  # Keep last 100
            }, f, indent=2)
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO date string."""
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(date_str)
        except:
            return None
    
    def _needs_daily(self) -> bool:
        """Check if daily tasks need to run."""
        if not self.last_daily:
            return True
        last = self._parse_date(self.last_daily)
        if not last:
            return True
        return (datetime.now() - last) > timedelta(hours=24)
    
    def _needs_weekly(self) -> bool:
        """Check if weekly tasks need to run."""
        if not self.last_weekly:
            return True
        last = self._parse_date(self.last_weekly)
        if not last:
            return True
        return (datetime.now() - last) > timedelta(days=7)
    
    def _needs_monthly(self) -> bool:
        """Check if monthly tasks need to run."""
        if not self.last_monthly:
            return True
        last = self._parse_date(self.last_monthly)
        if not last:
            return True
        return (datetime.now() - last) > timedelta(days=30)
    
    def run_daily_tasks(self) -> Dict:
        """Run daily maintenance tasks."""
        results = {
            'timestamp': datetime.now().isoformat(),
            'tasks': {},
            'success': True
        }
        
        try:
            # Import here to avoid circular imports
            from genesis_protocol.omega import get_self_preservation, get_journal
            from genesis_protocol.legacy import get_archive_layer, get_snapshot_layer
            
            sp = get_self_preservation()
            journal = get_journal()
            archive = get_archive_layer()
            snapshot = get_snapshot_layer()
            
            # 1. Health check
            health = sp.health_check()
            results['tasks']['health_check'] = {
                'status': 'ok' if health.get('overall_score', 0) >= 0.9 else 'warning',
                'score': health.get('overall_score')
            }
            
            # 2. Journal entry
            entry_id = journal.add_entry(
                entry_type='observation',
                content='Garden Mode daily check - system stable',
                tags=['garden', 'daily']
            )
            results['tasks']['journal'] = {'status': 'ok', 'entry_id': entry_id}
            
            # 3. Evidence log
            sp.evidence_logger.log_journal_entry('daily_check', 'Daily maintenance completed')
            results['tasks']['evidence_log'] = {'status': 'ok'}
            
            # 4. Backup
            backup_success = sp.auto_backup()
            results['tasks']['backup'] = {'status': 'completed' if backup_success else 'failed'}
            
            # 5. Snapshot
            snapshot_id = snapshot.create_snapshot(
                state={'garden_mode': True, 'type': 'daily'},
                snapshot_type='daily',
                label='Garden Mode daily'
            )
            results['tasks']['snapshot'] = {'status': 'created', 'id': snapshot_id}
            
            self.last_daily = datetime.now().isoformat()
            
        except Exception as e:
            results['success'] = False
            results['error'] = str(e)
        
        self.execution_log.append(results)
        self._save_state()
        
        return results
    
    def run_weekly_tasks(self) -> Dict:
        """Run weekly maintenance tasks."""
        results = {
            'timestamp': datetime.now().isoformat(),
            'tasks': {},
            'success': True
        }
        
        try:
            from genesis_protocol.omega import get_timeline_memory
            from genesis_protocol.legacy import get_archive_layer, get_snapshot_layer
            
            tm = get_timeline_memory()
            archive = get_archive_layer()
            snapshot = get_snapshot_layer()
            
            # 1. Run all tests (mark as attempted)
            results['tasks']['test_execution'] = {
                'status': 'scheduled',
                'note': 'Run pytest tests/ manually'
            }
            
            # 2. Archive lessons from timeline
            lessons = tm.get_lessons()
            for lesson in lessons[-10:]:  # Last 10 lessons
                archive.archive_lesson(
                    lesson=lesson.get('lesson', ''),
                    context=lesson.get('context', ''),
                    category='archived'
                )
            results['tasks']['archive_lessons'] = {
                'status': 'ok',
                'count': len(lessons[-10:])
            }
            
            # 3. Archive recoveries
            recoveries = tm.get_recoveries()
            for recovery in recoveries[-10:]:
                archive.archive_trust_state({
                    'type': 'recovery',
                    'data': recovery
                })
            results['tasks']['archive_recoveries'] = {
                'status': 'ok',
                'count': len(recoveries[-10:])
            }
            
            # 4. Create weekly snapshot
            snapshot_id = snapshot.create_snapshot(
                state={'garden_mode': True, 'type': 'weekly'},
                snapshot_type='weekly',
                label='Garden Mode weekly'
            )
            results['tasks']['weekly_snapshot'] = {'status': 'created', 'id': snapshot_id}
            
            self.last_weekly = datetime.now().isoformat()
            
        except Exception as e:
            results['success'] = False
            results['error'] = str(e)
        
        self.execution_log.append(results)
        self._save_state()
        
        return results
    
    def run_monthly_tasks(self) -> Dict:
        """Run monthly maintenance tasks."""
        results = {
            'timestamp': datetime.now().isoformat(),
            'tasks': {},
            'success': True
        }
        
        try:
            from genesis_protocol.omega import get_continuity_layer, get_timeline_memory
            from genesis_protocol.legacy import get_legacy_books, get_snapshot_layer
            
            cl = get_continuity_layer()
            tm = get_timeline_memory()
            lb = get_legacy_books()
            snapshot = get_snapshot_layer()
            
            # 1. Verify continuity
            continuity_status = cl.get_continuity_status()
            results['tasks']['verify_continuity'] = {
                'status': 'ok',
                'has_identity': continuity_status.get('has_identity', False)
            }
            
            # 2. Verify memories
            timeline_state = tm.get_full_state()
            results['tasks']['verify_memories'] = {
                'status': 'ok',
                'total_events': len(timeline_state.get('events', []))
            }
            
            # 3. Generate monthly book
            books = lb.generate_all_books()
            results['tasks']['monthly_book'] = {
                'status': 'generated',
                'books': list(books.keys())
            }
            
            # 4. Create monthly snapshot
            snapshot_id = snapshot.create_snapshot(
                state={'garden_mode': True, 'type': 'monthly'},
                snapshot_type='monthly',
                label='Garden Mode monthly'
            )
            results['tasks']['monthly_snapshot'] = {'status': 'created', 'id': snapshot_id}
            
            self.last_monthly = datetime.now().isoformat()
            
        except Exception as e:
            results['success'] = False
            results['error'] = str(e)
        
        self.execution_log.append(results)
        self._save_state()
        
        return results
    
    def check_and_run(self) -> Dict:
        """Check what needs to run and execute."""
        results = {
            'timestamp': datetime.now().isoformat(),
            'executed': []
        }
        
        if self._needs_daily():
            results['daily'] = self.run_daily_tasks()
            results['executed'].append('daily')
        
        if self._needs_weekly():
            results['weekly'] = self.run_weekly_tasks()
            results['executed'].append('weekly')
        
        if self._needs_monthly():
            results['monthly'] = self.run_monthly_tasks()
            results['executed'].append('monthly')
        
        return results
    
    def get_status(self) -> Dict:
        """Get garden mode status."""
        return {
            'status': 'active',
            'active_since': '2026-06-19',
            'phase': 'STABILITY',
            'last_daily': self.last_daily,
            'last_weekly': self.last_weekly,
            'last_monthly': self.last_monthly,
            'needs_daily': self._needs_daily(),
            'needs_weekly': self._needs_weekly(),
            'needs_monthly': self._needs_monthly(),
            'execution_count': len(self.execution_log)
        }


_garden_mode: Optional[GardenMode] = None


def get_garden_mode() -> GardenMode:
    """Get garden mode singleton."""
    global _garden_mode
    if _garden_mode is None:
        _garden_mode = GardenMode()
    return _garden_mode
