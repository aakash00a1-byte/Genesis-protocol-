"""Genesis Protocol - Autonomous Mode System

Controls system operation mode:
- NORMAL: Standard chat behavior
- AUTONOMOUS: Full agent behavior with planning, tools, self-correction
"""

import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from genesis_protocol.utils.logger import get_logger

logger = get_logger("ai.autonomous_mode")


class OperationMode(Enum):
    """System operation modes."""
    NORMAL = "normal"
    AUTONOMOUS = "autonomous"


@dataclass
class ModeConfig:
    """Configuration for each mode."""
    planning_enabled: bool
    tool_usage_auto: bool
    self_correction_enabled: bool
    memory_active: bool
    quality_judge_active: bool
    max_iterations: int
    description: str


class AutonomousModeManager:
    """
    Manages system operation modes and transitions.
    
    NORMAL mode: Standard chat, fast responses, no planning
    AUTONOMOUS mode: Full agent behavior with all features
    """
    
    MODE_CONFIGS: Dict[OperationMode, ModeConfig] = {
        OperationMode.NORMAL: ModeConfig(
            planning_enabled=False,
            tool_usage_auto=False,
            self_correction_enabled=False,
            memory_active=True,
            quality_judge_active=False,
            max_iterations=1,
            description="Standard chat mode. Fast responses, no planning."
        ),
        OperationMode.AUTONOMOUS: ModeConfig(
            planning_enabled=True,
            tool_usage_auto=True,
            self_correction_enabled=True,
            memory_active=True,
            quality_judge_active=True,
            max_iterations=5,
            description="Full agent mode. Planning, tools, self-correction enabled."
        )
    }
    
    # Keywords to trigger autonomous mode
    AUTONOMOUS_TRIGGERS = [
        "build", "create", "make", "develop", "design",
        "implement", "setup", "configure", "deploy",
        "automate", "schedule", "set up",
        "research", "find all", "search for",
        "analyze", "investigate", "compare",
        "write code", "create bot", "make app",
        "build website", "develop project"
    ]
    
    def __init__(self):
        """Initialize autonomous mode manager."""
        self._current_mode = OperationMode.NORMAL
        self._mode_history: list = []
        self.logger = logging.getLogger("ai.autonomous_mode")
    
    @property
    def current_mode(self) -> OperationMode:
        """Get current operation mode."""
        return self._current_mode
    
    @property
    def config(self) -> ModeConfig:
        """Get current mode configuration."""
        return self.MODE_CONFIGS[self._current_mode]
    
    def set_mode(self, mode: OperationMode) -> bool:
        """
        Set operation mode.
        
        Args:
            mode: New operation mode
            
        Returns:
            True if mode changed
        """
        if mode == self._current_mode:
            return False
        
        old_mode = self._current_mode
        self._current_mode = mode
        
        # Record transition
        self._mode_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "from": old_mode.value,
            "to": mode.value
        })
        
        self.logger.info(f"Mode changed: {old_mode.value} → {mode.value}")
        
        # Keep only last 50 transitions
        if len(self._mode_history) > 50:
            self._mode_history = self._mode_history[-50:]
        
        return True
    
    def should_use_autonomous(self, query: str) -> bool:
        """
        Determine if query should trigger autonomous mode.
        
        Args:
            query: User query
            
        Returns:
            True if autonomous mode should be used
        """
        query_lower = query.lower()
        
        # Check trigger keywords
        for trigger in self.AUTONOMOUS_TRIGGERS:
            if trigger in query_lower:
                return True
        
        # Check for multi-step indicators
        step_markers = ["first", "then", "next", "step", "steps", "sequence"]
        if any(marker in query_lower for marker in step_markers):
            return True
        
        # Check for complexity (long queries)
        if len(query) > 300:
            return True
        
        # Check for multiple questions
        if query.count('?') > 1 or query.count(' and ') > 2:
            return True
        
        return False
    
    def auto_switch_mode(self, query: str) -> OperationMode:
        """
        Automatically determine and switch mode based on query.
        
        Args:
            query: User query
            
        Returns:
            Recommended operation mode
        """
        if self.should_use_autonomous(query):
            self.set_mode(OperationMode.AUTONOMOUS)
            return OperationMode.AUTONOMOUS
        else:
            self.set_mode(OperationMode.NORMAL)
            return OperationMode.NORMAL
    
    def enable_autonomous(self):
        """Enable autonomous mode."""
        self.set_mode(OperationMode.AUTONOMOUS)
    
    def disable_autonomous(self):
        """Disable autonomous mode (switch to normal)."""
        self.set_mode(OperationMode.NORMAL)
    
    def toggle_mode(self) -> OperationMode:
        """Toggle between NORMAL and AUTONOMOUS modes."""
        if self._current_mode == OperationMode.NORMAL:
            self.set_mode(OperationMode.AUTONOMOUS)
        else:
            self.set_mode(OperationMode.NORMAL)
        
        return self._current_mode
    
    def is_autonomous(self) -> bool:
        """Check if currently in autonomous mode."""
        return self._current_mode == OperationMode.AUTONOMOUS
    
    def is_normal(self) -> bool:
        """Check if currently in normal mode."""
        return self._current_mode == OperationMode.NORMAL
    
    def reset_to_normal(self):
        """Reset mode to NORMAL - called at start of each request."""
        self._current_mode = OperationMode.NORMAL
    
    def get_capabilities(self) -> Dict[str, bool]:
        """Get current capabilities based on mode."""
        config = self.config
        return {
            "planning": config.planning_enabled,
            "tool_usage": config.tool_usage_auto,
            "self_correction": config.self_correction_enabled,
            "memory": config.memory_active,
            "quality_judge": config.quality_judge_active
        }
    
    def get_mode_info(self) -> Dict[str, Any]:
        """Get detailed mode information."""
        return {
            "current_mode": self._current_mode.value,
            "config": {
                "planning_enabled": self.config.planning_enabled,
                "tool_usage_auto": self.config.tool_usage_auto,
                "self_correction_enabled": self.config.self_correction_enabled,
                "memory_active": self.config.memory_active,
                "quality_judge_active": self.config.quality_judge_active,
                "max_iterations": self.config.max_iterations,
                "description": self.config.description
            },
            "is_autonomous": self.is_autonomous(),
            "capabilities": self.get_capabilities(),
            "mode_history": self._mode_history[-5:]
        }


# Singleton
_mode_manager: Optional[AutonomousModeManager] = None


def get_mode_manager() -> AutonomousModeManager:
    """Get or create mode manager singleton."""
    global _mode_manager
    if _mode_manager is None:
        _mode_manager = AutonomousModeManager()
    return _mode_manager


# Convenience functions
def get_current_mode() -> OperationMode:
    """Get current operation mode."""
    return get_mode_manager().current_mode


def is_autonomous_mode() -> bool:
    """Check if in autonomous mode."""
    return get_mode_manager().is_autonomous()


def enable_autonomous_mode():
    """Enable autonomous mode."""
    get_mode_manager().enable_autonomous()


def disable_autonomous_mode():
    """Disable autonomous mode."""
    get_mode_manager().disable_autonomous()


def auto_mode_switch(query: str) -> OperationMode:
    """Auto-switch mode based on query."""
    return get_mode_manager().auto_switch_mode(query)