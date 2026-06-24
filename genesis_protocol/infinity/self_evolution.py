"""
Self-Evolution Module - Genesis Protocol ∞

Self-improving AI that learns from interactions and evolves.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path


class EvolutionMetrics:
    """Track evolution progress"""
    
    def __init__(self):
        self.total_interactions = 0
        self.successful_responses = 0
        self.failed_responses = 0
        self.learnings = []
        self.evolution_level = 0
        self.last_evolution = None
    
    def to_dict(self) -> Dict:
        return {
            "total_interactions": self.total_interactions,
            "successful_responses": self.successful_responses,
            "failed_responses": self.failed_responses,
            "success_rate": self.get_success_rate(),
            "learnings_count": len(self.learnings),
            "evolution_level": self.evolution_level,
            "last_evolution": self.last_evolution
        }
    
    def get_success_rate(self) -> float:
        if self.total_interactions == 0:
            return 0.0
        return (self.successful_responses / self.total_interactions) * 100


class LearningEntry:
    """Single learning from interaction"""
    
    def __init__(self, topic: str, knowledge: str, source: str):
        self.id = f"learn_{int(datetime.now().timestamp())}"
        self.topic = topic
        self.knowledge = knowledge
        self.source = source
        self.confidence = 0.5
        self.usage_count = 0
        self.created_at = datetime.now().isoformat()
        self.last_used = None
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "topic": self.topic,
            "knowledge": self.knowledge,
            "source": self.source,
            "confidence": self.confidence,
            "usage_count": self.usage_count,
            "created_at": self.created_at,
            "last_used": self.last_used
        }


class SelfEvolution:
    """
    Genesis Protocol Self-Evolution Engine
    
    Features:
    - Learn from user interactions
    - Track knowledge base
    - Evolve based on success/failure
    - Auto-improve responses
    """
    
    def __init__(self, storage_path: str = "data/infinity"):
        self.storage_path = storage_path
        Path(storage_path).mkdir(parents=True, exist_ok=True)
        
        self.metrics = EvolutionMetrics()
        self.learnings: List[LearningEntry] = []
        self.knowledge_base: Dict[str, List[str]] = {}
        self.response_patterns: Dict[str, str] = {}
        
        self._load()
    
    def _load(self):
        """Load saved evolution data"""
        # Load metrics
        metrics_file = os.path.join(self.storage_path, "metrics.json")
        if os.path.exists(metrics_file):
            try:
                with open(metrics_file, 'r') as f:
                    data = json.load(f)
                    self.metrics.total_interactions = data.get('total_interactions', 0)
                    self.metrics.successful_responses = data.get('successful_responses', 0)
                    self.metrics.failed_responses = data.get('failed_responses', 0)
                    self.metrics.evolution_level = data.get('evolution_level', 0)
            except:
                pass
        
        # Load learnings
        learnings_file = os.path.join(self.storage_path, "learnings.json")
        if os.path.exists(learnings_file):
            try:
                with open(learnings_file, 'r') as f:
                    data = json.load(f)
                    for item in data:
                        entry = LearningEntry(item['topic'], item['knowledge'], item['source'])
                        entry.confidence = item.get('confidence', 0.5)
                        entry.usage_count = item.get('usage_count', 0)
                        entry.last_used = item.get('last_used')
                        self.learnings.append(entry)
            except:
                pass
        
        # Load knowledge base
        kb_file = os.path.join(self.storage_path, "knowledge_base.json")
        if os.path.exists(kb_file):
            try:
                with open(kb_file, 'r') as f:
                    self.knowledge_base = json.load(f)
            except:
                pass
        
        # Load patterns
        patterns_file = os.path.join(self.storage_path, "patterns.json")
        if os.path.exists(patterns_file):
            try:
                with open(patterns_file, 'r') as f:
                    self.response_patterns = json.load(f)
            except:
                pass
    
    def _save(self):
        """Save evolution data"""
        # Save metrics
        metrics_file = os.path.join(self.storage_path, "metrics.json")
        with open(metrics_file, 'w') as f:
            json.dump(self.metrics.to_dict(), f, indent=2)
        
        # Save learnings
        learnings_file = os.path.join(self.storage_path, "learnings.json")
        with open(learnings_file, 'w') as f:
            json.dump([l.to_dict() for l in self.learnings], f, indent=2)
        
        # Save knowledge base
        kb_file = os.path.join(self.storage_path, "knowledge_base.json")
        with open(kb_file, 'w') as f:
            json.dump(self.knowledge_base, f, indent=2)
        
        # Save patterns
        patterns_file = os.path.join(self.storage_path, "patterns.json")
        with open(patterns_file, 'w') as f:
            json.dump(self.response_patterns, f, indent=2)
    
    def learn(self, topic: str, knowledge: str, source: str = "interaction") -> str:
        """
        Learn new knowledge from interaction
        
        Args:
            topic: Topic category
            knowledge: Knowledge gained
            source: Where it came from
        
        Returns:
            Learning ID
        """
        entry = LearningEntry(topic, knowledge, source)
        self.learnings.append(entry)
        
        # Add to knowledge base
        if topic not in self.knowledge_base:
            self.knowledge_base[topic] = []
        self.knowledge_base[topic].append(knowledge)
        
        self._save()
        return entry.id
    
    def record_interaction(self, user_input: str, response: str, success: bool):
        """
        Record an interaction for learning
        
        Args:
            user_input: What user said
            response: What Genesis responded
            success: Was the response successful
        """
        self.metrics.total_interactions += 1
        
        if success:
            self.metrics.successful_responses += 1
            
            # Learn from successful interaction
            self._extract_pattern(user_input, response)
            
            # Boost confidence for successful patterns
            self._boost_confidence(response)
        else:
            self.metrics.failed_responses += 1
        
        # Check for evolution
        if self._should_evolve():
            self.evolve()
        
        self._save()
    
    def _extract_pattern(self, user_input: str, response: str):
        """Extract pattern from successful interaction"""
        # Simple pattern extraction - store response patterns
        key = user_input[:50].lower().strip()
        if key not in self.response_patterns:
            self.response_patterns[key] = response
    
    def _boost_confidence(self, response: str):
        """Boost confidence for learnings used in successful response"""
        for learning in self.learnings:
            if learning.knowledge in response:
                learning.confidence = min(1.0, learning.confidence + 0.05)
                learning.usage_count += 1
                learning.last_used = datetime.now().isoformat()
    
    def _should_evolve(self) -> bool:
        """Check if should evolve based on metrics"""
        if self.metrics.total_interactions < 100:
            return False
        
        success_rate = self.metrics.get_success_rate()
        
        # Evolve if success rate is high
        if success_rate >= 85 and self.metrics.total_interactions % 100 == 0:
            return True
        
        return False
    
    def evolve(self):
        """Perform evolution"""
        old_level = self.metrics.evolution_level
        self.metrics.evolution_level += 1
        self.metrics.last_evolution = datetime.now().isoformat()
        
        self._save()
        
        return {
            "old_level": old_level,
            "new_level": self.metrics.evolution_level,
            "timestamp": self.metrics.last_evolution,
            "message": f"Evolved from level {old_level} to {self.metrics.evolution_level}"
        }
    
    def get_response(self, user_input: str) -> Optional[str]:
        """Get learned response for input"""
        key = user_input[:50].lower().strip()
        return self.response_patterns.get(key)
    
    def search_knowledge(self, query: str) -> List[str]:
        """Search knowledge base"""
        results = []
        query_lower = query.lower()
        
        for topic, knowledge_list in self.knowledge_base.items():
            if query_lower in topic.lower():
                results.extend(knowledge_list)
            else:
                for knowledge in knowledge_list:
                    if query_lower in knowledge.lower():
                        results.append(knowledge)
        
        return results
    
    def get_status(self) -> Dict:
        """Get evolution status"""
        return {
            "version": "1.0.0",
            "evolution_level": self.metrics.evolution_level,
            "metrics": self.metrics.to_dict(),
            "total_learnings": len(self.learnings),
            "knowledge_topics": len(self.knowledge_base),
            "patterns_learned": len(self.response_patterns),
            "ready_to_evolve": self._should_evolve()
        }


# Singleton instance
_instance = None

def get_self_evolution() -> SelfEvolution:
    """Get singleton instance"""
    global _instance
    if _instance is None:
        _instance = SelfEvolution()
    return _instance
