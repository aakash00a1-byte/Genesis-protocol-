"""Task Queue - Genesis Protocol v1.1"""

import json
import threading
import time
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
import uuid


class TaskStatus(Enum):
    """Task status enum."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """A task in the queue."""
    id: str
    name: str
    description: str
    func_name: str
    func_args: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0
    max_retries: int = 3
    retry_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Optional[Any] = None
    user_id: Optional[int] = None


class TaskQueue:
    """Thread-safe task queue with persistence."""
    
    def __init__(self, storage_path: str = "./data/tasks"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._tasks: Dict[str, Task] = {}
        self._lock = threading.RLock()
        self._callbacks: Dict[str, Callable] = {}
        self._load_tasks()
    
    def _get_file_path(self) -> Path:
        """Get tasks file path."""
        return self.storage_path / "tasks.json"
    
    def _load_tasks(self):
        """Load tasks from disk."""
        file_path = self._get_file_path()
        if file_path.exists():
            with open(file_path, 'r') as f:
                data = json.load(f)
            for task_data in data:
                task_data['status'] = TaskStatus(task_data['status'])
                task_data['created_at'] = datetime.fromisoformat(task_data['created_at'])
                if task_data.get('scheduled_at'):
                    task_data['scheduled_at'] = datetime.fromisoformat(task_data['scheduled_at'])
                if task_data.get('started_at'):
                    task_data['started_at'] = datetime.fromisoformat(task_data['started_at'])
                if task_data.get('completed_at'):
                    task_data['completed_at'] = datetime.fromisoformat(task_data['completed_at'])
                task = Task(**task_data)
                self._tasks[task.id] = task
    
    def _save_tasks(self):
        """Save tasks to disk."""
        data = []
        for task in self._tasks.values():
            task_dict = asdict(task)
            task_dict['status'] = task.status.value
            task_dict['created_at'] = task.created_at.isoformat()
            if task.scheduled_at:
                task_dict['scheduled_at'] = task.scheduled_at.isoformat()
            if task.started_at:
                task_dict['started_at'] = task.started_at.isoformat()
            if task.completed_at:
                task_dict['completed_at'] = task.completed_at.isoformat()
            data.append(task_dict)
        
        with open(self._get_file_path(), 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_task(
        self,
        name: str,
        func_name: str,
        func_args: Dict[str, Any] = None,
        description: str = "",
        priority: int = 0,
        scheduled_at: Optional[datetime] = None,
        user_id: Optional[int] = None
    ) -> str:
        """Add a new task to the queue."""
        with self._lock:
            task_id = str(uuid.uuid4())[:8]
            task = Task(
                id=task_id,
                name=name,
                description=description,
                func_name=func_name,
                func_args=func_args or {},
                priority=priority,
                scheduled_at=scheduled_at,
                user_id=user_id
            )
            self._tasks[task_id] = task
            self._save_tasks()
            return task_id
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        with self._lock:
            return self._tasks.get(task_id)
    
    def get_pending_tasks(self) -> List[Task]:
        """Get all pending tasks."""
        with self._lock:
            now = datetime.now()
            return [
                t for t in self._tasks.values()
                if t.status == TaskStatus.PENDING
                and (not t.scheduled_at or t.scheduled_at <= now)
            ]
    
    def get_user_tasks(self, user_id: int) -> List[Task]:
        """Get all tasks for a user."""
        with self._lock:
            return [
                t for t in self._tasks.values()
                if t.user_id == user_id
            ]
    
    def update_status(
        self, 
        task_id: str, 
        status: TaskStatus,
        error: Optional[str] = None,
        result: Optional[Any] = None
    ):
        """Update task status."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = status
                if status == TaskStatus.RUNNING:
                    task.started_at = datetime.now()
                elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                    task.completed_at = datetime.now()
                if error:
                    task.error = error
                if result:
                    task.result = result
                self._save_tasks()
    
    def retry_task(self, task_id: str) -> bool:
        """Retry a failed task."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status == TaskStatus.FAILED:
                if task.retry_count < task.max_retries:
                    task.status = TaskStatus.PENDING
                    task.retry_count += 1
                    task.error = None
                    self._save_tasks()
                    return True
            return False
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                self._save_tasks()
                return True
            return False
    
    def delete_task(self, task_id: str):
        """Delete a task."""
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                self._save_tasks()
    
    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics."""
        with self._lock:
            stats = {
                'total': len(self._tasks),
                'pending': 0,
                'running': 0,
                'completed': 0,
                'failed': 0,
                'cancelled': 0
            }
            for task in self._tasks.values():
                stats[task.status.value] = stats.get(task.status.value, 0) + 1
            return stats
