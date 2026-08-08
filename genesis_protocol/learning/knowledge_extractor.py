"""Knowledge Extractor - Genesis Protocol v1.5
Automatically extracts facts, preferences, topics from conversations."""

from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime
import re


@dataclass
class ExtractedKnowledge:
    """Extracted knowledge item."""
    knowledge_type: str  # 'fact', 'preference', 'topic', 'event'
    content: str
    confidence: float  # 0.0 - 1.0
    source: str  # conversation_id or 'manual'
    importance: int  # 1-5
    timestamp: datetime
    user_id: int = 0


class KnowledgeExtractor:
    """Extracts knowledge from conversations automatically."""
    
    def __init__(self):
        self.fact_patterns = [
            (r"my name is (\w+)", "fact_name"),
            (r"i live in (.+)", "fact_location"),
            (r"i work (?:as|at|in) (.+)", "fact_work"),
            (r"i like (.+)", "preference_like"),
            (r"i prefer (.+)", "preference"),
            (r"i'm (\w+)", "fact_identity"),
            (r"call me (\w+)", "fact_name"),
        ]
        
        self.topic_keywords = {
            'coding': ['code', 'python', 'javascript', 'programming', 'bug', 'function', 'api', 'debug'],
            'music': ['song', 'music', 'band', 'singer', 'album', 'listen'],
            'sports': ['cricket', 'football', 'game', 'match', 'player', 'team'],
            'movies': ['movie', 'film', 'actor', 'director', 'watch', 'series'],
            'tech': ['ai', 'computer', 'phone', 'app', 'software', 'startup', 'tech'],
            'food': ['food', 'eat', 'cook', 'recipe', 'restaurant', 'pizza'],
            'travel': ['travel', 'trip', 'flight', 'hotel', 'visit', 'country'],
            'science': ['science', 'research', 'study', 'experiment', 'data'],
            'business': ['business', 'startup', 'money', 'invest', 'company', 'revenue'],
        }
        
        self.event_keywords = ['tomorrow', 'next week', 'meeting', 'deadline', 'event', 'conference', 'birthday']
    
    def extract_from_message(self, message: str, user_id: int = 0, conversation_id: str = "") -> List[ExtractedKnowledge]:
        """Extract knowledge from a user message."""
        knowledge = []
        message_lower = message.lower()
        
        # Extract named entities/facts
        for pattern, ktype in self.fact_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                content = match.group(1).strip()
                confidence = 0.8 if len(content) > 2 else 0.5
                
                knowledge.append(ExtractedKnowledge(
                    knowledge_type=ktype,
                    content=content,
                    confidence=confidence,
                    source=conversation_id,
                    importance=3 if 'name' in ktype else 2,
                    timestamp=datetime.now(),
                    user_id=user_id
                ))
        
        # Extract topics
        for topic, keywords in self.topic_keywords.items():
            if any(kw in message_lower for kw in keywords):
                # Check confidence based on how many keywords matched
                matches = sum(1 for kw in keywords if kw in message_lower)
                confidence = min(0.9, 0.5 + (matches * 0.1))
                
                # Avoid duplicates
                if not any(k.knowledge_type == f"topic_{topic}" and k.content == topic for k in knowledge):
                    knowledge.append(ExtractedKnowledge(
                        knowledge_type=f"topic_{topic}",
                        content=topic,
                        confidence=confidence,
                        source=conversation_id,
                        importance=2,
                        timestamp=datetime.now(),
                        user_id=user_id
                    ))
        
        # Extract events
        for event_word in self.event_keywords:
            if event_word in message_lower:
                # Try to extract the event description
                event_match = re.search(rf'{event_word}[\s,]+([^.]+)', message, re.IGNORECASE)
                if event_match:
                    event_content = event_match.group(1).strip()
                    knowledge.append(ExtractedKnowledge(
                        knowledge_type="event",
                        content=f"{event_word}: {event_content}",
                        confidence=0.7,
                        source=conversation_id,
                        importance=4,
                        timestamp=datetime.now(),
                        user_id=user_id
                    ))
                break
        
        # Extract preferences (from response patterns too)
        preference_patterns = [
            (r"(?:don't|do not) like (.+)", "preference_dislike"),
            (r"(?:love|adore) (.+)", "preference_love"),
            (r"(?:hate|detest) (.+)", "preference_hate"),
        ]
        
        for pattern, ktype in preference_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                content = match.group(1).strip()
                importance = 4 if ktype == "preference_love" else 3
                
                knowledge.append(ExtractedKnowledge(
                    knowledge_type=ktype,
                    content=content,
                    confidence=0.75,
                    source=conversation_id,
                    importance=importance,
                    timestamp=datetime.now(),
                    user_id=user_id
                ))
        
        return knowledge
    
    def extract_from_conversation(self, message: str, response: str, user_id: int = 0, conv_id: str = "") -> List[ExtractedKnowledge]:
        """Extract knowledge from full conversation."""
        # Extract from both message and response
        knowledge = self.extract_from_message(message, user_id, conv_id)
        knowledge.extend(self.extract_from_message(response, user_id, conv_id))
        return knowledge
    
    def calculate_importance(self, knowledge_type: str, confidence: float, frequency: int = 1) -> int:
        """Calculate importance score 1-5."""
        base_scores = {
            'fact_name': 5,
            'preference_love': 5,
            'fact_work': 3,
            'topic': 2,
            'event': 4,
            'preference': 3,
        }
        
        base = base_scores.get(knowledge_type, 2)
        confidence_boost = int(confidence * 2)
        frequency_boost = min(2, frequency // 3)
        
        return min(5, base + confidence_boost + frequency_boost)


# Global singleton
_knowledge_extractor: Optional[KnowledgeExtractor] = None


def get_knowledge_extractor() -> KnowledgeExtractor:
    """Get global knowledge extractor."""
    global _knowledge_extractor
    if _knowledge_extractor is None:
        _knowledge_extractor = KnowledgeExtractor()
    return _knowledge_extractor
