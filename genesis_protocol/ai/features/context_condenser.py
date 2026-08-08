"""Genesis Protocol - Context Condenser

Compresses long conversations to save tokens while preserving key information.
Based on OpenHands Context Condenser pattern.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger("ai.context_condenser")


@dataclass
class CondensedMessage:
    """A condensed version of a message or group of messages."""
    role: str
    content: str
    is_summary: bool = False
    original_count: int = 1


@dataclass
class CondensationResult:
    """Result of context condensation."""
    condensed_messages: List[CondensedMessage]
    original_count: int
    condensed_count: int
    tokens_saved: int
    summary: str


class ContextCondenser:
    """
    Condenses conversation history to save tokens.
    
    Strategy:
    - Keep system prompt and recent messages intact
    - Summarize older messages into key points
    - Maintain conversation flow and context
    """
    
    # Keep last N messages completely
    RECENT_KEEP = 6
    
    # After this many tokens, start condensing
    TOKEN_THRESHOLD = 8000
    
    # How many old messages to summarize together
    SUMMARIZE_BATCH = 10
    
    def __init__(self, llm_callable=None):
        """
        Initialize condenser.
        
        Args:
            llm_callable: Function to call LLM for summarization
        """
        self._llm = llm_callable
    
    def should_condense(self, messages: List[Dict[str, str]]) -> bool:
        """Check if conversation should be condensed."""
        total_tokens = sum(len(m.get("content", "").split()) * 1.3 for m in messages)
        return total_tokens > self.TOKEN_THRESHOLD
    
    def condense(self, messages: List[Dict[str, str]], 
                 max_tokens: int = 12000) -> CondensationResult:
        """
        Condense conversation history.
        
        Args:
            messages: Full conversation history
            max_tokens: Target max tokens after condensation
            
        Returns:
            CondensationResult with condensed messages
        """
        if len(messages) <= self.RECENT_KEEP:
            return CondensationResult(
                condensed_messages=[CondensedMessage(m["role"], m["content"]) for m in messages],
                original_count=len(messages),
                condensed_count=len(messages),
                tokens_saved=0,
                summary="No condensation needed"
            )
        
        # Split: recent (keep) vs old (summarize)
        recent = messages[-self.RECENT_KEEP:]
        old = messages[:-self.RECENT_KEEP]
        
        condensed = []
        
        # Keep system message first
        if old and old[0].get("role") == "system":
            condensed.append(CondensedMessage("system", old[0]["content"]))
            old = old[1:]
        
        # Summarize old messages in batches
        if self._llm and old:
            summarized = self._summarize_batch(old)
            condensed.extend(summarized)
        else:
            # Simple truncation if no LLM
            for msg in old[-self.SUMMARIZE_BATCH:]:
                condensed.append(CondensedMessage(msg["role"], msg["content"], is_summary=True))
        
        # Add recent messages
        for msg in recent:
            condensed.append(CondensedMessage(msg["role"], msg["content"]))
        
        original_tokens = sum(len(m.get("content", "").split()) * 1.3 for m in messages)
        condensed_tokens = sum(len(m.content.split()) * 1.3 for m in condensed)
        
        logger.info(
            f"Context condensed: {len(messages)} → {len(condensed)} messages, "
            f"~{original_tokens:.0f} → ~{condensed_tokens:.0f} tokens"
        )
        
        return CondensationResult(
            condensed_messages=condensed,
            original_count=len(messages),
            condensed_count=len(condensed),
            tokens_saved=int(original_tokens - condensed_tokens),
            summary=f"Summarized {len(old)} old messages"
        )
    
    def _summarize_batch(self, messages: List[Dict[str, str]]) -> List[CondensedMessage]:
        """Summarize a batch of messages using LLM."""
        if not self._llm or not messages:
            return []
        
        # Combine messages into context
        context = "\n".join([
            f"{m['role']}: {m['content']}" for m in messages
        ])
        
        prompt = f"""Summarize this conversation history into key points. 
Keep the most important information, decisions, and context.

CONVERSATION:
{context}

SUMMARY (in same language as conversation):"""
        
        try:
            response = self._llm([{"role": "user", "content": prompt}])
            summary = response if isinstance(response, str) else response.get("content", "")
            
            return [CondensedMessage(
                role="system",
                content=f"[Earlier conversation summary]: {summary}",
                is_summary=True,
                original_count=len(messages)
            )]
        except Exception as e:
            logger.error(f"Failed to summarize: {e}")
            # Fallback: just keep last few
            return [
                CondensedMessage(m["role"], m["content"], is_summary=True)
                for m in messages[-5:]
            ]
    
    def to_dict_list(self, result: CondensationResult) -> List[Dict[str, str]]:
        """Convert condensation result to message dict list for API."""
        return [
            {"role": m.role, "content": m.content}
            for m in result.condensed_messages
        ]


# Singleton
_condenser: Optional[ContextCondenser] = None


def get_condenser(llm_callable=None) -> ContextCondenser:
    """Get global context condenser instance."""
    global _condenser
    if _condenser is None:
        _condenser = ContextCondenser(llm_callable)
    return _condenser
