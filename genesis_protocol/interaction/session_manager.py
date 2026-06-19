"""Session Manager - Genesis Protocol v1.4
Session continuity and state restoration."""

import json
import os
from typing import Dict, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger("interaction.session")


@dataclass
class SessionState:
    """State of a session."""
    session_id: str
    user_id: int
    persona: str = "normal"
    mood: str = "calm"
    pending_tasks: int = 0
    recent_context: str = ""
    last_interaction: datetime = None
    created_at: datetime = None


class SessionManager:
    """Manages session continuity."""
    
    def __init__(self, storage_path: str = "./data/sessions"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._current_session: Optional[SessionState] = None
        self._sessions: Dict[str, SessionState] = {}
    
    def create_session(self, user_id: int) -> SessionState:
        """Create a new session."""
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        session = SessionState(
            session_id=session_id,
            user_id=user_id,
            created_at=datetime.now(),
            last_interaction=datetime.now()
        )
        
        self._current_session = session
        self._sessions[session_id] = session
        
        # Restore previous session if exists
        self._restore_previous_session(user_id)
        
        logger.info(f"Session created: {session_id}")
        return session
    
    def _restore_previous_session(self, user_id: int):
        """Restore state from previous session."""
        session_file = self.storage_path / f"user_{user_id}_session.json"
        
        if session_file.exists():
            try:
                with open(session_file, 'r') as f:
                    data = json.load(f)
                
                # Restore persona
                if data.get('persona'):
                    try:
                        from genesis_protocol.personality import get_personality_engine, Persona
                        engine = get_personality_engine(user_id)
                        engine.set_persona(Persona(data['persona']))
                    except Exception as e:
                        logger.warning(f"Failed to restore persona: {e}")
                
                # Restore mood
                if data.get('mood'):
                    try:
                        from genesis_protocol.autonomous import get_mood_engine, Mood
                        mood_engine = get_mood_engine(user_id)
                        mood_engine.set_mood(Mood(data['mood']), "Restored from previous session")
                    except Exception as e:
                        logger.warning(f"Failed to restore mood: {e}")
                
                # Restore recent context
                if self._current_session:
                    self._current_session.recent_context = data.get('recent_context', '')
                    self._current_session.pending_tasks = data.get('pending_tasks', 0)
                
                logger.info(f"Session restored for user {user_id}")
                
            except Exception as e:
                logger.error(f"Failed to restore session: {e}")
    
    def save_session(self, user_id: int):
        """Save current session state."""
        if not self._current_session:
            return
        
        session_file = self.storage_path / f"user_{user_id}_session.json"
        
        try:
            # Get current states
            try:
                from genesis_protocol.personality import get_personality_engine
                engine = get_personality_engine(user_id)
                persona = engine.current_persona.value
            except:
                persona = self._current_session.persona
            
            try:
                from genesis_protocol.autonomous import get_mood_engine
                mood_engine = get_mood_engine(user_id)
                mood = mood_engine.current_mood.value
            except:
                mood = self._current_session.mood
            
            try:
                from genesis_protocol.tasks import TaskQueue
                queue = TaskQueue()
                stats = queue.get_stats()
                pending_tasks = stats.get('pending', 0)
            except:
                pending_tasks = self._current_session.pending_tasks
            
            data = {
                'session_id': self._current_session.session_id,
                'user_id': user_id,
                'persona': persona,
                'mood': mood,
                'pending_tasks': pending_tasks,
                'recent_context': self._current_session.recent_context,
                'last_interaction': datetime.now().isoformat()
            }
            
            with open(session_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"Session saved: {self._current_session.session_id}")
            
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
    
    def get_current_session(self) -> Optional[SessionState]:
        """Get current session."""
        return self._current_session
    
    def get_session_info(self) -> Dict[str, Any]:
        """Get session info."""
        if not self._current_session:
            return {'active': False}
        
        return {
            'active': True,
            'session_id': self._current_session.session_id,
            'user_id': self._current_session.user_id,
            'persona': self._current_session.persona,
            'mood': self._current_session.mood,
            'pending_tasks': self._current_session.pending_tasks,
            'session_duration_seconds': (
                datetime.now() - self._current_session.created_at
            ).total_seconds() if self._current_session.created_at else 0
        }
    
    def end_session(self, user_id: int):
        """End current session."""
        if self._current_session:
            self.save_session(user_id)
            logger.info(f"Session ended: {self._current_session.session_id}")
            self._current_session = None


# Global singleton
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get global session manager."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
