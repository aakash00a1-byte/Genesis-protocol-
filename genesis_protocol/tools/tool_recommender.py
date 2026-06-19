"""Tool Recommender - Genesis Protocol v1.6
Suggest tools based on context."""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ToolRecommendation:
    """A tool recommendation."""
    tool_name: str
    reason: str
    confidence: float  # 0.0 - 1.0


class ToolRecommender:
    """Recommends tools based on context."""
    
    def __init__(self):
        self.context_patterns = {
            "calculation": {
                "patterns": ["calculate", "math", "number", "+-*/", "what is", "solve"],
                "tools": ["calculator"]
            },
            "search": {
                "patterns": ["search", "find", "what is", "who is", "where is", "when did"],
                "tools": ["web_search"]
            },
            "memory": {
                "patterns": ["remember", "earlier", "before", "previous", "last time", "forgot"],
                "tools": ["memory_search"]
            },
            "task": {
                "patterns": ["remind", "task", "todo", "remember to", "don't forget"],
                "tools": ["task_manager"]
            },
            "file": {
                "patterns": ["read file", "show me", "open", "contents of"],
                "tools": ["file_reader"]
            },
            "note": {
                "patterns": ["save", "remember", "note", "write down", "store"],
                "tools": ["notes"]
            },
            "history": {
                "patterns": ["discussed", "talked about", "conversation", "history"],
                "tools": ["history_search"]
            },
            "image": {
                "patterns": ["image", "picture", "photo", "analyze", "describe this"],
                "tools": ["image_analyzer"]
            }
        }
    
    def recommend(self, message: str, context: Dict[str, Any] = None) -> List[ToolRecommendation]:
        """Recommend tools based on message and context."""
        recommendations = []
        message_lower = message.lower()
        
        for category, config in self.context_patterns.items():
            # Check pattern matches
            for pattern in config["patterns"]:
                if pattern.lower() in message_lower:
                    for tool in config["tools"]:
                        recommendations.append(ToolRecommendation(
                            tool_name=tool,
                            reason=f"Message contains '{pattern}'",
                            confidence=0.8
                        ))
                    break
        
        # Check persona/mood context
        if context:
            if context.get("mood") == "developer" or context.get("persona") == "jarvis":
                if "calculator" not in [r.tool_name for r in recommendations]:
                    recommendations.append(ToolRecommendation(
                        tool_name="calculator",
                        reason="Developer mode active - suggest technical tools",
                        confidence=0.6
                    ))
            
            if context.get("task_context"):
                if "task_manager" not in [r.tool_name for r in recommendations]:
                    recommendations.append(ToolRecommendation(
                        tool_name="task_manager",
                        reason="Task context detected",
                        confidence=0.7
                    ))
        
        # Deduplicate and sort by confidence
        seen = set()
        unique_recs = []
        for r in recommendations:
            if r.tool_name not in seen:
                seen.add(r.tool_name)
                unique_recs.append(r)
        
        return sorted(unique_recs, key=lambda x: x.confidence, reverse=True)
    
    def get_suggestion(self, message: str, context: Dict[str, Any] = None) -> str:
        """Get a single best tool suggestion."""
        recs = self.recommend(message, context)
        if recs:
            return f"Use '{recs[0].tool_name}' - {recs[0].reason}"
        return ""


# Global singleton
_recommender: Optional[ToolRecommender] = None


def get_tool_recommender() -> ToolRecommender:
    """Get global tool recommender."""
    global _recommender
    if _recommender is None:
        _recommender = ToolRecommender()
    return _recommender
