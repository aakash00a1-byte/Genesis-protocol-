"""Genesis Protocol - Conversation State Management

Pause, Resume, and Fork capabilities for conversations.
Based on OpenHands pause/resume pattern.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

logger = logging.getLogger("conversation_state")


class ConversationState(Enum):
    """Conversation execution states."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ConversationSnapshot:
    """Snapshot of conversation state for pause/resume."""
    snapshot_id: str
    conversation_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    messages: List[Dict[str, str]] = field(default_factory=list)
    current_step: int = 0
    pending_tools: List[Dict] = field(default_factory=list)
    memory_context: str = ""
    variables: Dict[str, Any] = field(default_factory=dict)
    state: ConversationState = ConversationState.IDLE
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationCheckpoint:
    """A checkpoint within a conversation."""
    checkpoint_id: str
    snapshot_id: str
    step_number: int
    created_at: datetime = field(default_factory=datetime.utcnow)
    messages: List[Dict[str, str]]
    variables: Dict[str, Any]
    description: str = ""


class ConversationStateManager:
    """
    Manages conversation state for pause/resume/fork.
    
    Features:
    - Pause ongoing conversations
    - Resume from paused state
    - Fork conversations for experimentation
    - Save checkpoints
    - Restore from checkpoints
    """
    
    def __init__(self, storage_path: str = None):
        """
        Initialize conversation state manager.
        
        Args:
            storage_path: Optional path for persisting state
        """
        self._storage_path = storage_path
        self._active_conversations: Dict[str, ConversationSnapshot] = {}
        self._snapshots: Dict[str, List[ConversationSnapshot]] = {}
        self._checkpoints: Dict[str, List[ConversationCheckpoint]] = {}
        logger.info("ConversationStateManager initialized")
    
    def create_conversation(self, conversation_id: str, 
                           initial_messages: List[Dict[str, str]] = None,
                           metadata: Dict[str, Any] = None) -> ConversationSnapshot:
        """
        Create a new conversation snapshot.
        
        Args:
            conversation_id: Unique conversation ID
            initial_messages: Optional initial messages
            
        Returns:
            ConversationSnapshot
        """
        snapshot = ConversationSnapshot(
            snapshot_id=str(uuid.uuid4())[:8],
            conversation_id=conversation_id,
            messages=initial_messages or [],
            metadata=metadata or {}
        )
        
        self._active_conversations[conversation_id] = snapshot
        self._snapshots[conversation_id] = [snapshot]
        
        logger.info(f"Created conversation: {conversation_id}")
        return snapshot
    
    def pause_conversation(self, conversation_id: str) -> Optional[ConversationSnapshot]:
        """
        Pause an ongoing conversation.
        
        Args:
            conversation_id: Conversation to pause
            
        Returns:
            Snapshot of paused state, or None if not found
        """
        if conversation_id not in self._active_conversations:
            logger.warning(f"Conversation not found: {conversation_id}")
            return None
        
        snapshot = self._active_conversations[conversation_id]
        snapshot.state = ConversationState.PAUSED
        
        # Save to storage if configured
        if self._storage_path:
            self._save_snapshot(snapshot)
        
        logger.info(f"Paused conversation: {conversation_id}")
        return snapshot
    
    def resume_conversation(self, conversation_id: str) -> Optional[ConversationSnapshot]:
        """
        Resume a paused conversation.
        
        Args:
            conversation_id: Conversation to resume
            
        Returns:
            Resumed snapshot, or None if not found
        """
        if conversation_id not in self._active_conversations:
            logger.warning(f"Conversation not found: {conversation_id}")
            return None
        
        snapshot = self._active_conversations[conversation_id]
        
        if snapshot.state != ConversationState.PAUSED:
            logger.warning(f"Conversation not paused: {conversation_id}")
            return None
        
        snapshot.state = ConversationState.RUNNING
        logger.info(f"Resumed conversation: {conversation_id}")
        return snapshot
    
    def fork_conversation(self, conversation_id: str, 
                          fork_id: str = None) -> Optional[ConversationSnapshot]:
        """
        Fork a conversation for experimentation.
        
        Args:
            conversation_id: Source conversation
            fork_id: Optional custom fork ID
            
        Returns:
            New forked snapshot
        """
        if conversation_id not in self._active_conversations:
            logger.warning(f"Conversation not found: {conversation_id}")
            return None
        
        original = self._active_conversations[conversation_id]
        
        fork_id = fork_id or f"{conversation_id}_fork_{uuid.uuid4()[:4]}"
        
        forked = ConversationSnapshot(
            snapshot_id=str(uuid.uuid4())[:8],
            conversation_id=fork_id,
            created_at=datetime.utcnow(),
            messages=original.messages.copy(),
            current_step=original.current_step,
            pending_tools=original.pending_tools.copy(),
            memory_context=original.memory_context,
            variables=original.variables.copy(),
            state=ConversationState.IDLE,
            metadata={**original.metadata, "forked_from": conversation_id}
        )
        
        self._active_conversations[fork_id] = forked
        self._snapshots[fork_id] = [forked]
        
        logger.info(f"Forked conversation: {conversation_id} -> {fork_id}")
        return forked
    
    def create_checkpoint(self, conversation_id: str, 
                         description: str = "") -> Optional[ConversationCheckpoint]:
        """
        Create a checkpoint within a conversation.
        
        Args:
            conversation_id: Conversation ID
            description: Optional checkpoint description
            
        Returns:
            Created checkpoint
        """
        if conversation_id not in self._active_conversations:
            return None
        
        snapshot = self._active_conversations[conversation_id]
        
        checkpoint = ConversationCheckpoint(
            checkpoint_id=str(uuid.uuid4())[:8],
            snapshot_id=snapshot.snapshot_id,
            step_number=snapshot.current_step,
            messages=snapshot.messages.copy(),
            variables=snapshot.variables.copy(),
            description=description
        )
        
        if conversation_id not in self._checkpoints:
            self._checkpoints[conversation_id] = []
        
        self._checkpoints[conversation_id].append(checkpoint)
        
        logger.info(f"Created checkpoint: {checkpoint.checkpoint_id} for {conversation_id}")
        return checkpoint
    
    def restore_checkpoint(self, conversation_id: str, 
                          checkpoint_id: str) -> Optional[ConversationSnapshot]:
        """
        Restore conversation to a checkpoint.
        
        Args:
            conversation_id: Conversation ID
            checkpoint_id: Checkpoint to restore
            
        Returns:
            Restored snapshot
        """
        if conversation_id not in self._checkpoints:
            return None
        
        checkpoint = None
        for cp in self._checkpoints[conversation_id]:
            if cp.checkpoint_id == checkpoint_id:
                checkpoint = cp
                break
        
        if not checkpoint:
            return None
        
        # Create new snapshot from checkpoint
        snapshot = self._active_conversations.get(conversation_id)
        if snapshot:
            snapshot.messages = checkpoint.messages.copy()
            snapshot.current_step = checkpoint.step_number
            snapshot.variables = checkpoint.variables.copy()
            snapshot.state = ConversationState.IDLE
            
            logger.info(f"Restored to checkpoint: {checkpoint_id}")
            return snapshot
        
        return None
    
    def update_state(self, conversation_id: str, 
                    messages: List[Dict[str, str]] = None,
                    current_step: int = None,
                    pending_tools: List[Dict] = None,
                    variables: Dict[str, Any] = None):
        """Update conversation state."""
        if conversation_id not in self._active_conversations:
            return
        
        snapshot = self._active_conversations[conversation_id]
        
        if messages is not None:
            snapshot.messages = messages
        if current_step is not None:
            snapshot.current_step = current_step
        if pending_tools is not None:
            snapshot.pending_tools = pending_tools
        if variables is not None:
            snapshot.variables = variables
    
    def get_state(self, conversation_id: str) -> Optional[ConversationSnapshot]:
        """Get current state of a conversation."""
        return self._active_conversations.get(conversation_id)
    
    def get_checkpoints(self, conversation_id: str) -> List[ConversationCheckpoint]:
        """Get all checkpoints for a conversation."""
        return self._checkpoints.get(conversation_id, [])
    
    def list_active(self) -> List[str]:
        """List all active conversation IDs."""
        return list(self._active_conversations.keys())
    
    def close_conversation(self, conversation_id: str):
        """Close and cleanup a conversation."""
        if conversation_id in self._active_conversations:
            snapshot = self._active_conversations[conversation_id]
            snapshot.state = ConversationState.COMPLETED
            logger.info(f"Closed conversation: {conversation_id}")
    
    def _save_snapshot(self, snapshot: ConversationSnapshot):
        """Save snapshot to disk."""
        if not self._storage_path:
            return
        
        try:
            import os
            path = os.path.join(self._storage_path, f"{snapshot.conversation_id}.json")
            with open(path, 'w') as f:
                json.dump({
                    "snapshot_id": snapshot.snapshot_id,
                    "conversation_id": snapshot.conversation_id,
                    "created_at": snapshot.created_at.isoformat(),
                    "messages": snapshot.messages,
                    "current_step": snapshot.current_step,
                    "pending_tools": snapshot.pending_tools,
                    "memory_context": snapshot.memory_context,
                    "variables": snapshot.variables,
                    "state": snapshot.state.value,
                    "metadata": snapshot.metadata
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save snapshot: {e}")
    
    def _load_snapshot(self, conversation_id: str) -> Optional[ConversationSnapshot]:
        """Load snapshot from disk."""
        if not self._storage_path:
            return None
        
        try:
            import os
            path = os.path.join(self._storage_path, f"{conversation_id}.json")
            if os.path.exists(path):
                with open(path, 'r') as f:
                    data = json.load(f)
                    return ConversationSnapshot(
                        snapshot_id=data["snapshot_id"],
                        conversation_id=data["conversation_id"],
                        created_at=datetime.fromisoformat(data["created_at"]),
                        messages=data["messages"],
                        current_step=data["current_step"],
                        pending_tools=data["pending_tools"],
                        memory_context=data.get("memory_context", ""),
                        variables=data.get("variables", {}),
                        state=ConversationState(data.get("state", "idle")),
                        metadata=data.get("metadata", {})
                    )
        except Exception as e:
            logger.error(f"Failed to load snapshot: {e}")
        
        return None


# Singleton
_state_manager: Optional[ConversationStateManager] = None


def get_state_manager(storage_path: str = None) -> ConversationStateManager:
    """Get global conversation state manager."""
    global _state_manager
    if _state_manager is None:
        _state_manager = ConversationStateManager(storage_path)
    return _state_manager
