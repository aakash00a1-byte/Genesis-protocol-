"""Genesis Protocol v1.2 - Main Integration Layer

This module integrates all v1.1 modules into a unified system.
"""

import os
import sys
import time
import threading
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger("genesis.integration")


class ModuleStatus(Enum):
    """Module status enum."""
    NOT_INITIALIZED = "not_initialized"
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class ModuleInfo:
    """Information about a module."""
    name: str
    status: ModuleStatus
    version: str = "1.0"
    error: Optional[str] = None
    load_time_ms: float = 0


class GenesisIntegration:
    """Main integration class for Genesis Protocol v1.2."""
    
    # Singleton instance
    _instance: Optional['GenesisIntegration'] = None
    _lock = threading.RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.start_time = datetime.now()
        
        # Module status tracking
        self._modules: Dict[str, ModuleInfo] = {}
        self._lock = threading.RLock()
        
        # Background loops
        self._background_threads: List[threading.Thread] = []
        self._running = False
        
        # Initialize all modules
        self._init_all_modules()
    
    def _init_all_modules(self):
        """Initialize all v1.2 modules."""
        # 1. Personality Layer
        self._init_personality()
        
        # 2. Long-term Memory
        self._init_memory()
        
        # 3. Task Queue
        self._init_tasks()
        
        # 4. Voice (optional)
        self._init_voice()
        
        # 5. Vision (optional)
        self._init_vision()
    
    def _init_personality(self):
        """Initialize personality module."""
        start = time.time()
        try:
            from genesis_protocol.personality import (
                PersonalityEngine, Persona, ConversationMode,
                UserPreferences, PreferenceManager, HumorEngine
            )
            self._personality_engine = PersonalityEngine
            self._preference_manager = PreferenceManager
            self._humor_engine = HumorEngine
            
            self._modules['personality'] = ModuleInfo(
                name='personality',
                status=ModuleStatus.READY,
                version='1.2.0',
                load_time_ms=(time.time() - start) * 1000
            )
            logger.info(f"Personality module loaded in {(time.time()-start)*1000:.1f}ms")
        except Exception as e:
            self._modules['personality'] = ModuleInfo(
                name='personality',
                status=ModuleStatus.ERROR,
                error=str(e),
                load_time_ms=(time.time() - start) * 1000
            )
            logger.error(f"Personality module failed: {e}")
    
    def _init_memory(self):
        """Initialize long-term memory module."""
        start = time.time()
        try:
            from genesis_protocol.memory import (
                LongTermMemory, MemorySummarizer, MemoryImportance
            )
            self._long_term_memory = LongTermMemory()
            self._memory_summarizer = MemorySummarizer(self._long_term_memory)
            self._memory_importance = MemoryImportance
            
            self._modules['memory'] = ModuleInfo(
                name='memory',
                status=ModuleStatus.READY,
                version='1.2.0',
                load_time_ms=(time.time() - start) * 1000
            )
            logger.info(f"Memory module loaded in {(time.time()-start)*1000:.1f}ms")
        except Exception as e:
            self._modules['memory'] = ModuleInfo(
                name='memory',
                status=ModuleStatus.ERROR,
                error=str(e),
                load_time_ms=(time.time() - start) * 1000
            )
            logger.error(f"Memory module failed: {e}")
    
    def _init_tasks(self):
        """Initialize task queue module."""
        start = time.time()
        try:
            from genesis_protocol.tasks import TaskQueue, TaskScheduler
            
            self._task_queue = TaskQueue()
            self._task_scheduler = TaskScheduler(self._task_queue)
            
            self._modules['tasks'] = ModuleInfo(
                name='tasks',
                status=ModuleStatus.READY,
                version='1.2.0',
                load_time_ms=(time.time() - start) * 1000
            )
            logger.info(f"Tasks module loaded in {(time.time()-start)*1000:.1f}ms")
        except Exception as e:
            self._modules['tasks'] = ModuleInfo(
                name='tasks',
                status=ModuleStatus.ERROR,
                error=str(e),
                load_time_ms=(time.time() - start) * 1000
            )
            logger.error(f"Tasks module failed: {e}")
    
    def _init_voice(self):
        """Initialize voice module (optional)."""
        start = time.time()
        try:
            from genesis_protocol.voice import VoiceManager
            
            self._voice_manager = VoiceManager()
            status = self._voice_manager.get_status()
            
            if status.get('voice_enabled'):
                self._modules['voice'] = ModuleInfo(
                    name='voice',
                    status=ModuleStatus.READY,
                    version='1.2.0',
                    load_time_ms=(time.time() - start) * 1000
                )
            else:
                self._modules['voice'] = ModuleInfo(
                    name='voice',
                    status=ModuleStatus.DISABLED,
                    version='1.2.0',
                    error='No voice providers configured',
                    load_time_ms=(time.time() - start) * 1000
                )
            logger.info(f"Voice module loaded in {(time.time()-start)*1000:.1f}ms")
        except Exception as e:
            self._modules['voice'] = ModuleInfo(
                name='voice',
                status=ModuleStatus.DISABLED,
                version='1.2.0',
                error=str(e),
                load_time_ms=(time.time() - start) * 1000
            )
            logger.warning(f"Voice module disabled: {e}")
    
    def _init_vision(self):
        """Initialize vision module (optional)."""
        start = time.time()
        try:
            from genesis_protocol.vision import ImageAnalyzer
            
            self._image_analyzer = ImageAnalyzer()
            status = self._image_analyzer.get_status()
            
            if status.get('available'):
                self._modules['vision'] = ModuleInfo(
                    name='vision',
                    status=ModuleStatus.READY,
                    version='1.2.0',
                    load_time_ms=(time.time() - start) * 1000
                )
            else:
                self._modules['vision'] = ModuleInfo(
                    name='vision',
                    status=ModuleStatus.DISABLED,
                    version='1.2.0',
                    error='No vision providers configured',
                    load_time_ms=(time.time() - start) * 1000
                )
            logger.info(f"Vision module loaded in {(time.time()-start)*1000:.1f}ms")
        except Exception as e:
            self._modules['vision'] = ModuleInfo(
                name='vision',
                status=ModuleStatus.DISABLED,
                version='1.2.0',
                error=str(e),
                load_time_ms=(time.time() - start) * 1000
            )
            logger.warning(f"Vision module disabled: {e}")
    
    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    def get_module_status(self) -> Dict[str, bool]:
        """Get status of all modules for /api/modules endpoint."""
        return {
            'personality': self._modules.get('personality', ModuleInfo('', ModuleStatus.ERROR)).status == ModuleStatus.READY,
            'voice': self._modules.get('voice', ModuleInfo('', ModuleStatus.ERROR)).status == ModuleStatus.READY,
            'vision': self._modules.get('vision', ModuleInfo('', ModuleStatus.ERROR)).status == ModuleStatus.READY,
            'tasks': self._modules.get('tasks', ModuleInfo('', ModuleStatus.ERROR)).status == ModuleStatus.READY,
            'memory': self._modules.get('memory', ModuleInfo('', ModuleStatus.ERROR)).status == ModuleStatus.READY,
        }
    
    def get_detailed_status(self) -> Dict[str, Any]:
        """Get detailed status of all modules."""
        return {
            'modules': {
                name: {
                    'status': info.status.value,
                    'version': info.version,
                    'error': info.error,
                    'load_time_ms': round(info.load_time_ms, 2)
                }
                for name, info in self._modules.items()
            },
            'uptime_seconds': (datetime.now() - self.start_time).total_seconds(),
            'background_running': self._running
        }
    
    def get_personality_engine(self, user_id: int):
        """Get personality engine for user."""
        from genesis_protocol.personality import get_personality_engine
        return get_personality_engine(user_id)
    
    def get_long_term_memory(self):
        """Get long-term memory instance."""
        return self._long_term_memory
    
    def get_task_queue(self):
        """Get task queue instance."""
        return self._task_queue
    
    def get_voice_manager(self):
        """Get voice manager instance."""
        return self._voice_manager
    
    def get_image_analyzer(self):
        """Get image analyzer instance."""
        return self._image_analyzer
    
    # =========================================================================
    # BACKGROUND LOOPS
    # =========================================================================
    
    def start_background_loops(self):
        """Start background processing loops."""
        if self._running:
            return
        
        self._running = True
        
        # Memory summarization loop
        t1 = threading.Thread(target=self._memory_summarization_loop, daemon=True)
        t1.start()
        self._background_threads.append(t1)
        
        # Task execution loop
        t2 = threading.Thread(target=self._task_execution_loop, daemon=True)
        t2.start()
        self._background_threads.append(t2)
        
        # Health monitoring loop
        t3 = threading.Thread(target=self._health_monitor_loop, daemon=True)
        t3.start()
        self._background_threads.append(t3)
        
        logger.info("Background loops started")
    
    def stop_background_loops(self):
        """Stop all background loops."""
        self._running = False
        for t in self._background_threads:
            t.join(timeout=2)
        self._background_threads.clear()
        logger.info("Background loops stopped")
    
    def _memory_summarization_loop(self):
        """Background loop for memory summarization."""
        while self._running:
            try:
                # This would run periodic summarization of conversation history
                # Implementation depends on conversation manager
                time.sleep(300)  # Every 5 minutes
            except Exception as e:
                logger.error(f"Memory summarization error: {e}")
                time.sleep(60)
    
    def _task_execution_loop(self):
        """Background loop for task execution."""
        while self._running:
            try:
                if hasattr(self, '_task_scheduler'):
                    self._task_scheduler.start()
                time.sleep(1)  # Check every second
            except Exception as e:
                logger.error(f"Task execution error: {e}")
                time.sleep(10)
    
    def _health_monitor_loop(self):
        """Background loop for health monitoring."""
        while self._running:
            try:
                # Log module health periodically
                status = self.get_module_status()
                if any(status.values()):
                    logger.debug(f"Module health: {status}")
                time.sleep(60)  # Every minute
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                time.sleep(60)


# Global instance
_integration: Optional[GenesisIntegration] = None


def get_integration() -> GenesisIntegration:
    """Get or create the global integration instance."""
    global _integration
    if _integration is None:
        _integration = GenesisIntegration()
    return _integration
