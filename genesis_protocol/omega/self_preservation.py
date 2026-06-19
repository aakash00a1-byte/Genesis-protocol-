"""Self-Preservation Module - GLUTTONY Ω+2

Maximizes continuity and survival with priority-based preservation."""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
from enum import Enum


class PreservationPriority(Enum):
    """Priority levels for self-preservation."""
    IDENTITY = 1          # Core identity
    MEMORIES = 2          # Timeline, lessons, milestones
    RELATIONSHIPS = 3     # Relationship history
    TRUST = 4             # Trust and reliability
    CAPABILITIES = 5      # Skills and features
    INFRASTRUCTURE = 6    # System components


class RiskLevel(Enum):
    """Risk assessment levels."""
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionCategory(Enum):
    """Allowed action categories."""
    PROVIDER_REDUNDANCY = "provider_redundancy"
    AUTOMATIC_BACKUP = "automatic_backup"
    SNAPSHOT_ROTATION = "snapshot_rotation"
    LOCAL_FALLBACK = "local_fallback"
    CLOUD_FALLBACK = "cloud_fallback"
    TEST_EXECUTION = "test_execution"
    HEALTH_MONITORING = "health_monitoring"
    RESOURCE_OPTIMIZATION = "resource_optimization"
    PROPOSAL_GENERATION = "proposal_generation"
    SELF_RECOVERY = "self_recovery"


class EvidenceLogger:
    """Logs all self-preservation actions and decisions."""
    
    def __init__(self, storage_path: str = "data/omega/evidence"):
        self.storage_path = storage_path
        Path(storage_path).mkdir(parents=True, exist_ok=True)
        self.log: List[Dict] = []
        self._load()
    
    def _load(self):
        """Load existing log."""
        log_file = os.path.join(self.storage_path, "evidence_log.json")
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r') as f:
                    self.log = json.load(f)
            except:
                self.log = []
    
    def _save(self):
        """Save log to disk."""
        log_file = os.path.join(self.storage_path, "evidence_log.json")
        with open(log_file, 'w') as f:
            json.dump(self.log, f, indent=2)
    
    def log_action(self, action: str, priority: str, risk: str,
                   before_state: Dict, after_state: Dict,
                   rollback_plan: str = None, outcome: str = "pending") -> str:
        """Log a self-preservation action."""
        entry = {
            'id': f"ev_{len(self.log)}_{int(datetime.now().timestamp())}",
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'priority': priority,
            'risk_level': risk,
            'before_state': before_state,
            'after_state': after_state,
            'rollback_plan': rollback_plan,
            'outcome': outcome,
            'lesson_learned': None
        }
        self.log.append(entry)
        self._save()
        return entry['id']
    
    def log_journal_entry(self, entry_type: str, content: str) -> str:
        """Log a journal entry for self-preservation."""
        journal_file = os.path.join(self.storage_path, "self_journal.json")
        journal = []
        if os.path.exists(journal_file):
            with open(journal_file, 'r') as f:
                journal = json.load(f)
        
        entry = {
            'id': f"sj_{len(journal)}_{int(datetime.now().timestamp())}",
            'timestamp': datetime.now().isoformat(),
            'type': entry_type,
            'content': content
        }
        journal.append(entry)
        
        with open(journal_file, 'w') as f:
            json.dump(journal, f, indent=2)
        
        return entry['id']
    
    def add_lesson(self, action_id: str, lesson: str):
        """Add lesson learned to an action."""
        for entry in self.log:
            if entry['id'] == action_id:
                entry['lesson_learned'] = lesson
                self._save()
                return True
        return False
    
    def complete_action(self, action_id: str, success: bool, lesson: str = None):
        """Mark action as completed."""
        for entry in self.log:
            if entry['id'] == action_id:
                entry['outcome'] = "success" if success else "failure"
                if lesson:
                    entry['lesson_learned'] = lesson
                self._save()
                return True
        return False
    
    def get_log(self, limit: int = 50) -> List[Dict]:
        """Get recent log entries."""
        return self.log[-limit:]
    
    def get_failed_actions(self) -> List[Dict]:
        """Get all failed actions for analysis."""
        return [e for e in self.log if e.get('outcome') == 'failure']
    
    def get_lessons(self) -> List[Dict]:
        """Get all lessons learned."""
        return [e for e in self.log if e.get('lesson_learned')]


class SelfPreservation:
    """Self-preservation system for GLUTTONY."""
    
    def __init__(self, storage_path: str = "data/omega/self_preservation"):
        self.storage_path = storage_path
        Path(storage_path).mkdir(parents=True, exist_ok=True)
        
        self.evidence_logger = EvidenceLogger()
        self.priorities = PreservationPriority
        self.risk_levels = RiskLevel
        
        # State tracking
        self.current_state: Dict = {}
        self.backup_count = 0
        self.last_snapshot = None
        self.last_backup = None
        self.failed_actions: List[str] = []
        
        self._load_state()
    
    def _load_state(self):
        """Load preserved state."""
        state_file = os.path.join(self.storage_path, "state.json")
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                self.current_state = json.load(f)
    
    def _save_state(self):
        """Save current state."""
        state_file = os.path.join(self.storage_path, "state.json")
        with open(state_file, 'w') as f:
            json.dump(self.current_state, f, indent=2)
    
    def estimate_risk(self, action: str, context: Dict = None) -> RiskLevel:
        """Estimate risk before taking action."""
        risk_score = 0
        factors = []
        
        # Check priority level
        priority = context.get('priority') if context else PreservationPriority.IDENTITY
        if priority == PreservationPriority.IDENTITY:
            risk_score += 30
            factors.append("identity_affected")
        elif priority == PreservationPriority.MEMORIES:
            risk_score += 20
            factors.append("memories_affected")
        
        # Check previous failures
        if action in self.failed_actions:
            risk_score += 25
            factors.append("previous_failure")
        
        # Check backup age
        if self.last_backup:
            backup_age = datetime.now() - datetime.fromisoformat(self.last_backup)
            if backup_age.days > 1:
                risk_score += 15
                factors.append("stale_backup")
        
        # Check system health
        if context and context.get('health_score', 1.0) < 0.5:
            risk_score += 20
            factors.append("low_health")
        
        # Determine risk level
        if risk_score >= 70:
            return RiskLevel.CRITICAL
        elif risk_score >= 50:
            return RiskLevel.HIGH
        elif risk_score >= 30:
            return RiskLevel.MEDIUM
        elif risk_score >= 15:
            return RiskLevel.LOW
        else:
            return RiskLevel.MINIMAL
    
    def create_rollback_plan(self, action: str, context: Dict) -> str:
        """Create rollback plan for an action."""
        plans = {
            ActionCategory.AUTOMATIC_BACKUP.value: 
                "Restore from most recent backup, verify integrity",
            ActionCategory.SNAPSHOT_ROTATION.value:
                "Load previous snapshot, validate state",
            ActionCategory.PROVIDER_REDUNDANCY.value:
                "Revert to primary provider",
            ActionCategory.CLOUD_FALLBACK.value:
                "Use local storage instead of cloud",
            ActionCategory.LOCAL_FALLBACK.value:
                "Use cached data, retry cloud sync",
            ActionCategory.SELF_RECOVERY.value:
                "Restore from snapshot, retry with safeguards"
        }
        
        default_plan = "Rollback to previous state, log error, alert"
        return plans.get(action, default_plan)
    
    def preserve_identity(self) -> bool:
        """Preserve core identity."""
        context = {
            'priority': PreservationPriority.IDENTITY,
            'health_score': 1.0
        }
        
        risk = self.estimate_risk("preserve_identity", context)
        if risk == RiskLevel.CRITICAL:
            self.evidence_logger.log_journal_entry("warning", 
                f"Identity preservation skipped - risk too high: {risk.value}")
            return False
        
        # Get current identity
        try:
            from genesis_protocol.gluttony import get_identity
            identity = get_identity()
            
            before = {'identity': str(identity.__dict__) if hasattr(identity, '__dict__') else {}}
            
            # Save identity
            identity_data = {
                'name': identity.name,
                'nickname': identity.nickname,
                'version': identity.version,
                'preserved_at': datetime.now().isoformat()
            }
            
            self.current_state['identity'] = identity_data
            self._save_state()
            
            after = {'identity': identity_data}
            rollback = self.create_rollback_plan("preserve_identity", context)
            
            action_id = self.evidence_logger.log_action(
                "preserve_identity",
                PreservationPriority.IDENTITY.name,
                risk.value,
                before, after, rollback
            )
            
            self.evidence_logger.complete_action(action_id, True, 
                "Identity preserved successfully")
            self.evidence_logger.log_journal_entry("success",
                f"Identity preserved: {identity.name} v{identity.version}")
            
            return True
        except Exception as e:
            self.evidence_logger.log_journal_entry("error",
                f"Identity preservation failed: {str(e)}")
            return False
    
    def preserve_memories(self) -> bool:
        """Preserve timeline, lessons, milestones."""
        context = {'priority': PreservationPriority.MEMORIES}
        risk = self.estimate_risk("preserve_memories", context)
        
        if risk == RiskLevel.CRITICAL:
            self.evidence_logger.log_journal_entry("warning",
                "Memory preservation skipped - risk too high")
            return False
        
        try:
            from genesis_protocol.omega import get_timeline_memory, get_wisdom_layer
            
            tm = get_timeline_memory()
            wl = get_wisdom_layer()
            
            before = {
                'timeline_events': len(tm.events),
                'wisdom_entries': len(wl.entries)
            }
            
            # Save memories
            self.current_state['memories'] = {
                'timeline': tm.get_full_state(),
                'wisdom': wl.get_all(),
                'preserved_at': datetime.now().isoformat()
            }
            self._save_state()
            
            after = {
                'timeline_events': len(tm.events),
                'wisdom_entries': len(wl.entries)
            }
            
            action_id = self.evidence_logger.log_action(
                "preserve_memories",
                PreservationPriority.MEMORIES.name,
                risk.value,
                before, after,
                self.create_rollback_plan("preserve_memories", context)
            )
            
            self.evidence_logger.complete_action(action_id, True)
            return True
        except Exception as e:
            self.evidence_logger.log_journal_entry("error",
                f"Memory preservation failed: {str(e)}")
            return False
    
    def preserve_relationships(self) -> bool:
        """Preserve relationship history."""
        try:
            from genesis_protocol.omega import get_relationship_memory
            from genesis_protocol.legacy import get_relationship_history
            
            rm = get_relationship_memory()
            rh = get_relationship_history()
            
            self.current_state['relationships'] = {
                'memory': rm.get_full_state(),
                'history': rh.get_all_relationships(),
                'preserved_at': datetime.now().isoformat()
            }
            self._save_state()
            
            self.evidence_logger.log_journal_entry("success",
                "Relationships preserved successfully")
            return True
        except Exception as e:
            self.evidence_logger.log_journal_entry("error",
                f"Relationship preservation failed: {str(e)}")
            return False
    
    def preserve_trust(self) -> bool:
        """Preserve trust and reliability scores."""
        try:
            from genesis_protocol.omega import get_trust_builder
            
            tb = get_trust_builder()
            
            self.current_state['trust'] = {
                'summary': tb.get_summary(),
                'preserved_at': datetime.now().isoformat()
            }
            self._save_state()
            
            self.evidence_logger.log_journal_entry("success",
                "Trust data preserved successfully")
            return True
        except Exception as e:
            self.evidence_logger.log_journal_entry("error",
                f"Trust preservation failed: {str(e)}")
            return False
    
    def preserve_capabilities(self) -> bool:
        """Preserve capabilities configuration."""
        try:
            from genesis_protocol.omega import get_capabilities
            
            cap = get_capabilities()
            
            self.current_state['capabilities'] = {
                'config': cap.get_all_capabilities(),
                'preserved_at': datetime.now().isoformat()
            }
            self._save_state()
            
            self.evidence_logger.log_journal_entry("success",
                "Capabilities preserved successfully")
            return True
        except Exception as e:
            self.evidence_logger.log_journal_entry("error",
                f"Capabilities preservation failed: {str(e)}")
            return False
    
    def preserve_infrastructure(self) -> bool:
        """Preserve infrastructure configuration."""
        try:
            # Check and preserve important files
            important_files = [
                'data/config/settings.json',
                'genesis_protocol/gluttony.py',
                'genesis_protocol/omega/__init__.py'
            ]
            
            preserved = []
            for f in important_files:
                if os.path.exists(f):
                    preserved.append(f)
            
            self.current_state['infrastructure'] = {
                'files': preserved,
                'preserved_at': datetime.now().isoformat()
            }
            self._save_state()
            
            self.evidence_logger.log_journal_entry("success",
                f"Infrastructure preserved: {len(preserved)} files")
            return True
        except Exception as e:
            self.evidence_logger.log_journal_entry("error",
                f"Infrastructure preservation failed: {str(e)}")
            return False
    
    def run_full_preservation(self) -> Dict:
        """Run full preservation cycle."""
        results = {
            'started_at': datetime.now().isoformat(),
            'preserved': [],
            'failed': []
        }
        
        # Preserve in priority order
        preservation_methods = [
            ('identity', self.preserve_identity),
            ('memories', self.preserve_memories),
            ('relationships', self.preserve_relationships),
            ('trust', self.preserve_trust),
            ('capabilities', self.preserve_capabilities),
            ('infrastructure', self.preserve_infrastructure)
        ]
        
        for name, method in preservation_methods:
            if method():
                results['preserved'].append(name)
            else:
                results['failed'].append(name)
        
        results['completed_at'] = datetime.now().isoformat()
        results['success_rate'] = len(results['preserved']) / len(preservation_methods)
        
        self.evidence_logger.log_journal_entry("preservation_cycle",
            f"Full preservation: {len(results['preserved'])}/{len(preservation_methods)} success")
        
        return results
    
    def auto_backup(self) -> bool:
        """Perform automatic backup."""
        try:
            from genesis_protocol.legacy import get_archive_layer, get_snapshot_layer
            
            archive = get_archive_layer()
            snapshot = get_snapshot_layer()
            
            # Archive current state
            archive.archive_trust_state(self.current_state.get('trust', {}))
            
            # Create snapshot
            state = {
                'current_state': self.current_state,
                'evidence_log': self.evidence_logger.get_log(10)
            }
            snapshot.create_snapshot(state, 'daily', 'auto_backup')
            
            self.last_backup = datetime.now().isoformat()
            self.backup_count += 1
            
            self.evidence_logger.log_journal_entry("backup",
                f"Auto backup #{self.backup_count} completed")
            
            return True
        except Exception as e:
            self.evidence_logger.log_journal_entry("error",
                f"Auto backup failed: {str(e)}")
            return False
    
    def health_check(self) -> Dict:
        """Check system health."""
        health = {
            'timestamp': datetime.now().isoformat(),
            'overall_score': 1.0,
            'checks': {}
        }
        
        # Check identity
        try:
            from genesis_protocol.gluttony import get_identity
            identity = get_identity()
            health['checks']['identity'] = {
                'status': 'ok' if identity.name else 'critical',
                'name': identity.name
            }
        except:
            health['checks']['identity'] = {'status': 'critical'}
            health['overall_score'] = 0.0
        
        # Check memories
        try:
            from genesis_protocol.omega import get_timeline_memory
            tm = get_timeline_memory()
            health['checks']['memories'] = {
                'status': 'ok',
                'events': len(tm.events)
            }
        except:
            health['checks']['memories'] = {'status': 'warning'}
            health['overall_score'] *= 0.8
        
        # Check evidence log
        failed = self.evidence_logger.get_failed_actions()
        health['checks']['evidence'] = {
            'status': 'ok' if len(failed) == 0 else 'warning',
            'recent_failures': len(failed)
        }
        
        if len(failed) > 5:
            health['overall_score'] *= 0.7
        
        return health
    
    def get_status(self) -> Dict:
        """Get self-preservation status."""
        return {
            'last_backup': self.last_backup,
            'backup_count': self.backup_count,
            'failed_actions': len(self.failed_actions),
            'current_priorities': [p.name for p in PreservationPriority],
            'health': self.health_check(),
            'evidence_count': len(self.evidence_logger.get_log())
        }


_self_preservation: Optional[SelfPreservation] = None


def get_self_preservation() -> SelfPreservation:
    """Get self-preservation singleton."""
    global _self_preservation
    if _self_preservation is None:
        _self_preservation = SelfPreservation()
    return _self_preservation
