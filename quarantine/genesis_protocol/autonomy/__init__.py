"""
Genesis Protocol - Autonomy Module
Self-improving AI system with GitHub integration, memory, and scheduling.
"""

from .github_agent import GitHubAgent, GitHubOperationResult, autonomous_github_update
from .memory_agent import MemoryAgent, MemoryEntry, get_memory_agent
from .scheduler_agent import SchedulerAgent, ScheduledTask, get_scheduler_agent
from .genesis_autonomy_controller import GenesisAutonomyController, get_genesis_autonomy_controller

__all__ = [
    'GitHubAgent',
    'GitHubOperationResult',
    'autonomous_github_update',
    'MemoryAgent',
    'MemoryEntry',
    'get_memory_agent',
    'SchedulerAgent',
    'ScheduledTask',
    'get_scheduler_agent',
    'GenesisAutonomyController',
    'get_genesis_autonomy_controller',
]
