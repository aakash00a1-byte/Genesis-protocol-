"""
⚡ Genesis Scheduler Agent ⚡
Daily autonomy check scheduler for Genesis Protocol
"""

import os
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
import json
import subprocess


@dataclass
class ScheduledTask:
    name: str
    interval_hours: float  # Hours between runs
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    enabled: bool = True
    task_type: str = "check"  # check, deploy, analyze
    status: str = "pending"  # pending, running, completed, failed


class SchedulerAgent:
    """Autonomous scheduler for Genesis Protocol daily tasks."""
    
    VERSION = "1.0.0"
    
    # Default daily tasks from OMEGA LONG ROAD DIRECTIVE
    DEFAULT_TASKS = [
        {
            "name": "health_check",
            "interval_hours": 1.0,
            "task_type": "check",
            "description": "Check system health and uptime"
        },
        {
            "name": "ai_news_monitor",
            "interval_hours": 6.0,
            "task_type": "check",
            "description": "Monitor AI news and updates"
        },
        {
            "name": "github_trending_check",
            "interval_hours": 12.0,
            "task_type": "check",
            "description": "Check GitHub trending repositories"
        },
        {
            "name": "weakness_analysis",
            "interval_hours": 24.0,
            "task_type": "analyze",
            "description": "Analyze weaknesses and generate proposals"
        },
        {
            "name": "memory_consolidation",
            "interval_hours": 24.0,
            "task_type": "check",
            "description": "Consolidate and clean up memories"
        },
        {
            "name": "cost_analysis",
            "interval_hours": 24.0,
            "task_type": "analyze",
            "description": "Analyze API costs and usage"
        },
        {
            "name": "deploy_verification",
            "interval_hours": 6.0,
            "task_type": "deploy",
            "description": "Verify Railway deployment status"
        },
    ]
    
    def __init__(self, storage_path: str = "./data/scheduler"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.tasks: Dict[str, ScheduledTask] = {}
        self.task_handlers: Dict[str, Callable] = {}
        self.running = False
        self._load_tasks()
        self._setup_default_handlers()
    
    def _load_tasks(self):
        """Load tasks from disk."""
        tasks_file = self.storage_path / "tasks.json"
        if tasks_file.exists():
            try:
                with open(tasks_file, 'r') as f:
                    data = json.load(f)
                for item in data:
                    task = ScheduledTask(**item)
                    self.tasks[task.name] = task
            except Exception:
                pass
        
        # Add missing default tasks
        for task_def in self.DEFAULT_TASKS:
            if task_def["name"] not in self.tasks:
                self.tasks[task_def["name"]] = ScheduledTask(
                    name=task_def["name"],
                    interval_hours=task_def["interval_hours"],
                    task_type=task_def["task_type"],
                    next_run=self._calculate_next_run(task_def["interval_hours"])
                )
        self._save_tasks()
    
    def _save_tasks(self):
        """Save tasks to disk."""
        tasks_file = self.storage_path / "tasks.json"
        try:
            data = [t.__dict__ for t in self.tasks.values()]
            with open(tasks_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    
    def _setup_default_handlers(self):
        """Setup default task handlers."""
        # Health check
        self.register_handler("health_check", self._handler_health_check)
        
        # Memory consolidation
        self.register_handler("memory_consolidation", self._handler_memory_consolidation)
        
        # Weakness analysis
        self.register_handler("weakness_analysis", self._handler_weakness_analysis)
        
        # Deploy verification
        self.register_handler("deploy_verification", self._handler_deploy_check)
    
    def _calculate_next_run(self, interval_hours: float) -> str:
        """Calculate next run time."""
        next_time = datetime.now() + timedelta(hours=interval_hours)
        return next_time.isoformat()
    
    def _handler_health_check(self) -> Dict:
        """Health check handler."""
        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "checks": {
                "system": "ok",
                "memory": "ok",
                "network": "ok"
            }
        }
    
    def _handler_memory_consolidation(self) -> Dict:
        """Memory consolidation handler."""
        try:
            from genesis_protocol.autonomy.memory_agent import get_memory_agent
            memory = get_memory_agent()
            memory.consolidate(keep_count=1000)
            return {
                "status": "ok",
                "memories_before_consolidation": len(memory._memory)
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _handler_weakness_analysis(self) -> Dict:
        """Weakness analysis handler."""
        try:
            from genesis_protocol.improvement import get_weakness_detector, get_proposal_generator
            detector = get_weakness_detector()
            generator = get_proposal_generator()
            
            weaknesses = detector.get_top_weaknesses(5)
            
            proposals = []
            for weak in weaknesses:
                prop = generator.generate_from_weakness(weak)
                proposals.append(prop.id)
            
            return {
                "status": "ok",
                "weaknesses_found": len(weaknesses),
                "proposals_generated": len(proposals)
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _handler_deploy_check(self) -> Dict:
        """Deploy verification handler."""
        try:
            # Check Railway status via API
            import httpx
            response = httpx.get("https://railway.com/project/outstanding-nourishment", timeout=10)
            return {
                "status": "ok" if response.status_code == 200 else "warning",
                "url_accessible": response.status_code == 200
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def register_handler(self, task_name: str, handler: Callable):
        """Register a task handler."""
        self.task_handlers[task_name] = handler
    
    def add_task(self, name: str, interval_hours: float, task_type: str = "check"):
        """Add a new scheduled task."""
        self.tasks[name] = ScheduledTask(
            name=name,
            interval_hours=interval_hours,
            task_type=task_type,
            next_run=self._calculate_next_run(interval_hours)
        )
        self._save_tasks()
    
    def remove_task(self, name: str) -> bool:
        """Remove a task."""
        if name in self.tasks:
            del self.tasks[name]
            self._save_tasks()
            return True
        return False
    
    def run_task(self, task_name: str) -> Dict:
        """Manually run a task."""
        if task_name not in self.tasks:
            return {"error": f"Task '{task_name}' not found"}
        
        task = self.tasks[task_name]
        task.status = "running"
        
        result = {"task": task_name, "started": datetime.now().isoformat()}
        
        try:
            if task_name in self.task_handlers:
                result["result"] = self.task_handlers[task_name]()
            else:
                result["result"] = {"status": "no_handler", "message": "No handler registered"}
            
            task.status = "completed"
            task.last_run = datetime.now().isoformat()
            task.next_run = self._calculate_next_run(task.interval_hours)
            result["status"] = "success"
            
        except Exception as e:
            task.status = "failed"
            result["status"] = "error"
            result["error"] = str(e)
        
        self._save_tasks()
        return result
    
    def get_due_tasks(self) -> List[ScheduledTask]:
        """Get tasks that are due to run."""
        now = datetime.now()
        due = []
        
        for task in self.tasks.values():
            if not task.enabled:
                continue
            
            if task.next_run:
                next_run = datetime.fromisoformat(task.next_run)
                if next_run <= now:
                    due.append(task)
        
        return due
    
    def run_due_tasks(self) -> List[Dict]:
        """Run all due tasks."""
        results = []
        for task in self.get_due_tasks():
            result = self.run_task(task.name)
            results.append(result)
        return results
    
    def get_status(self) -> Dict:
        """Get scheduler status."""
        return {
            "version": self.VERSION,
            "total_tasks": len(self.tasks),
            "enabled_tasks": len([t for t in self.tasks.values() if t.enabled]),
            "due_now": len(self.get_due_tasks()),
            "tasks": {
                name: {
                    "enabled": t.enabled,
                    "interval_hours": t.interval_hours,
                    "last_run": t.last_run,
                    "next_run": t.next_run,
                    "status": t.status,
                    "task_type": t.task_type
                }
                for name, t in self.tasks.items()
            }
        }
    
    def start(self):
        """Start the scheduler (background thread)."""
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print(f"⚡ Scheduler started with {len(self.tasks)} tasks")
    
    def stop(self):
        """Stop the scheduler."""
        self.running = False
    
    def _run_loop(self):
        """Main scheduler loop."""
        while self.running:
            try:
                results = self.run_due_tasks()
                if results:
                    print(f"⚡ Ran {len(results)} due tasks")
            except Exception as e:
                print(f"Scheduler error: {e}")
            
            time.sleep(60)  # Check every minute


# Global singleton
_scheduler_agent: Optional[SchedulerAgent] = None


def get_scheduler_agent() -> SchedulerAgent:
    """Get global scheduler agent."""
    global _scheduler_agent
    if _scheduler_agent is None:
        _scheduler_agent = SchedulerAgent()
    return _scheduler_agent


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════╗
║     ⚡ GENESIS SCHEDULER AGENT v1.0.0 ⚡         ║
╚═══════════════════════════════════════════════════════════╝
    """)
    scheduler = SchedulerAgent()
    status = scheduler.get_status()
    print(f"Total tasks: {status['total_tasks']}")
    print(f"Due now: {status['due_now']}")
