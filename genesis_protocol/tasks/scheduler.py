"""Task Scheduler - Genesis Protocol v1.1"""

import threading
import time
from typing import Callable, Dict, Any
from datetime import datetime, timedelta
from .task_queue import TaskQueue, TaskStatus


class TaskScheduler:
    """Background scheduler for recurring tasks and reminders."""
    
    def __init__(self, task_queue: TaskQueue = None):
        self.task_queue = task_queue or TaskQueue()
        self._running = False
        self._thread = None
        self._reminders: Dict[str, Callable] = {}
    
    def start(self):
        """Start the scheduler background thread."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
    
    def _run_loop(self):
        """Main scheduler loop."""
        while self._running:
            try:
                self._process_pending_tasks()
                self._check_scheduled_tasks()
            except Exception:
                pass
            time.sleep(1)  # Check every second
    
    def _process_pending_tasks(self):
        """Process pending tasks."""
        pending = self.task_queue.get_pending_tasks()
        for task in pending:
            # Sort by priority
            pending.sort(key=lambda t: t.priority, reverse=True)
        
        # Process highest priority task
        if pending:
            task = pending[0]
            self._execute_task(task)
    
    def _check_scheduled_tasks(self):
        """Check for scheduled tasks that should run."""
        # This would integrate with a cron-like system
        pass
    
    def _execute_task(self, task):
        """Execute a task."""
        from genesis_protocol.utils.logger import get_logger
        logger = get_logger("scheduler")
        
        self.task_queue.update_status(task.id, TaskStatus.RUNNING)
        logger.info(f"Executing task: {task.name}")
        
        try:
            # Execute the task function
            result = self._call_function(task.func_name, task.func_args)
            self.task_queue.update_status(
                task.id, 
                TaskStatus.COMPLETED,
                result=result
            )
        except Exception as e:
            logger.error(f"Task failed: {task.name} - {str(e)}")
            if task.retry_count < task.max_retries:
                self.task_queue.retry_task(task.id)
            else:
                self.task_queue.update_status(
                    task.id,
                    TaskStatus.FAILED,
                    error=str(e)
                )
    
    def _call_function(self, func_name: str, func_args: Dict[str, Any]) -> Any:
        """Call a registered function by name."""
        # This would be expanded to call actual functions
        return {"status": "executed", "function": func_name}
    
    def schedule_reminder(
        self,
        user_id: int,
        message: str,
        delay_seconds: int,
        task_name: str = "Reminder"
    ) -> str:
        """Schedule a reminder for a user."""
        from datetime import timedelta
        scheduled_at = datetime.now() + timedelta(seconds=delay_seconds)
        
        return self.task_queue.add_task(
            name=task_name,
            func_name="send_reminder",
            func_args={"user_id": user_id, "message": message},
            description=f"Reminder: {message}",
            scheduled_at=scheduled_at,
            user_id=user_id
        )
    
    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status."""
        return {
            'running': self._running,
            'stats': self.task_queue.get_stats()
        }
