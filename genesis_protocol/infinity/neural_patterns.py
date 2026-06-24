"""
Neural Pattern Engine - Genesis Protocol ∞

Pattern recognition and neural-like processing.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path
from collections import defaultdict
import re


class NeuralPattern:
    """Individual neural pattern"""
    
    def __init__(self, pattern_id: str, pattern_type: str, data: Any):
        self.id = pattern_id
        self.type = pattern_type
        self.data = data
        self.activation_count = 0
        self.strength = 0.5
        self.created_at = datetime.now().isoformat()
        self.last_activated = None
    
    def activate(self):
        """Activate this pattern"""
        self.activation_count += 1
        self.strength = min(1.0, self.strength + 0.1)
        self.last_activated = datetime.now().isoformat()
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "type": self.type,
            "data": self.data,
            "activation_count": self.activation_count,
            "strength": self.strength,
            "created_at": self.created_at,
            "last_activated": self.last_activated
        }


class PatternCluster:
    """Cluster of related patterns"""
    
    def __init__(self, name: str):
        self.name = name
        self.patterns: List[NeuralPattern] = []
        self.connections: List[str] = []  # IDs of connected clusters
        self.weight = 1.0
    
    def add_pattern(self, pattern: NeuralPattern):
        """Add pattern to cluster"""
        self.patterns.append(pattern)
    
    def get_active_patterns(self) -> List[NeuralPattern]:
        """Get patterns sorted by activation"""
        return sorted(self.patterns, key=lambda p: p.activation_count, reverse=True)


class NeuralPatternEngine:
    """
    Genesis Protocol Neural Pattern Engine
    
    Features:
    - Pattern recognition
    - Neural-like clustering
    - Memory associations
    - Predictive processing
    """
    
    def __init__(self, storage_path: str = "data/infinity/neural"):
        self.storage_path = storage_path
        Path(storage_path).mkdir(parents=True, exist_ok=True)
        
        self.clusters: Dict[str, PatternCluster] = {}
        self.associations: Dict[str, List[str]] = defaultdict(list)
        self.patterns: List[NeuralPattern] = []
        self.input_history: List[str] = []
        
        self._load()
    
    def _load(self):
        """Load saved patterns"""
        patterns_file = os.path.join(self.storage_path, "patterns.json")
        if os.path.exists(patterns_file):
            try:
                with open(patterns_file, 'r') as f:
                    data = json.load(f)
                    
                    # Load clusters
                    for name, cluster_data in data.get('clusters', {}).items():
                        cluster = PatternCluster(name)
                        cluster.weight = cluster_data.get('weight', 1.0)
                        cluster.connections = cluster_data.get('connections', [])
                        self.clusters[name] = cluster
                    
                    # Load patterns
                    for p_data in data.get('patterns', []):
                        pattern = NeuralPattern(p_data['id'], p_data['type'], p_data['data'])
                        pattern.activation_count = p_data.get('activation_count', 0)
                        pattern.strength = p_data.get('strength', 0.5)
                        pattern.last_activated = p_data.get('last_activated')
                        self.patterns.append(pattern)
                        
                        # Add to cluster
                        if p_data['type'] in self.clusters:
                            self.clusters[p_data['type']].add_pattern(pattern)
                        else:
                            cluster = PatternCluster(p_data['type'])
                            cluster.add_pattern(pattern)
                            self.clusters[p_data['type']] = cluster
                    
                    self.associations = defaultdict(list, data.get('associations', {}))
                    self.input_history = data.get('input_history', [])
            except Exception as e:
                print(f"Error loading patterns: {e}")
    
    def _save(self):
        """Save patterns"""
        clusters_data = {}
        for name, cluster in self.clusters.items():
            clusters_data[name] = {
                "weight": cluster.weight,
                "connections": cluster.connections,
                "pattern_count": len(cluster.patterns)
            }
        
        data = {
            "clusters": clusters_data,
            "patterns": [p.to_dict() for p in self.patterns],
            "associations": dict(self.associations),
            "input_history": self.input_history[-100:]  # Keep last 100
        }
        
        patterns_file = os.path.join(self.storage_path, "patterns.json")
        with open(patterns_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def register_pattern(self, pattern_type: str, data: Any, content: str = "") -> str:
        """
        Register a new pattern
        
        Args:
            pattern_type: Type of pattern (emotion, topic, intent, etc.)
            data: Pattern data
            content: Text content for association
        
        Returns:
            Pattern ID
        """
        pattern_id = f"np_{pattern_type}_{len(self.patterns)}_{int(datetime.now().timestamp())}"
        
        pattern = NeuralPattern(pattern_id, pattern_type, data)
        self.patterns.append(pattern)
        
        # Add to cluster
        if pattern_type not in self.clusters:
            self.clusters[pattern_type] = PatternCluster(pattern_type)
        self.clusters[pattern_type].add_pattern(pattern)
        
        # Create associations with recent inputs
        if content:
            self._create_associations(pattern_id, content)
        
        self._save()
        return pattern_id
    
    def recognize(self, content: str) -> List[NeuralPattern]:
        """
        Recognize patterns in content
        
        Args:
            content: Text content to analyze
        
        Returns:
            List of recognized patterns
        """
        recognized = []
        content_lower = content.lower()
        
        for pattern in self.patterns:
            if pattern.type == "keyword":
                if isinstance(pattern.data, str) and pattern.data.lower() in content_lower:
                    pattern.activate()
                    recognized.append(pattern)
            elif pattern.type == "emotion":
                if isinstance(pattern.data, dict):
                    emotion_keywords = pattern.data.get('keywords', [])
                    if any(kw.lower() in content_lower for kw in emotion_keywords):
                        pattern.activate()
                        recognized.append(pattern)
            elif pattern.type == "intent":
                if isinstance(pattern.data, dict):
                    intent_keywords = pattern.data.get('keywords', [])
                    if any(kw.lower() in content_lower for kw in intent_keywords):
                        pattern.activate()
                        recognized.append(pattern)
        
        # Record in history
        self.input_history.append(content)
        if len(self.input_history) > 100:
            self.input_history = self.input_history[-100:]
        
        self._save()
        return recognized
    
    def _create_associations(self, pattern_id: str, content: str):
        """Create associations between patterns"""
        words = re.findall(r'\w+', content.lower())
        
        for word in words:
            if len(word) > 3:  # Skip short words
                if word not in self.associations:
                    self.associations[word] = []
                if pattern_id not in self.associations[word]:
                    self.associations[word].append(pattern_id)
    
    def predict_next(self, partial_input: str) -> List[str]:
        """Predict next words/patterns based on partial input"""
        words = re.findall(r'\w+', partial_input.lower())
        
        if not words:
            return []
        
        last_word = words[-1] if words else ""
        
        # Find patterns associated with last word
        associated = self.associations.get(last_word, [])
        
        predictions = []
        for pattern_id in associated[:5]:  # Top 5
            for pattern in self.patterns:
                if pattern.id == pattern_id:
                    if isinstance(pattern.data, str):
                        predictions.append(pattern.data)
                    elif isinstance(pattern.data, dict):
                        suggestions = pattern.data.get('suggestions', [])
                        predictions.extend(suggestions[:2])
        
        return list(set(predictions))[:5]
    
    def get_clusters(self) -> Dict[str, int]:
        """Get all clusters with pattern counts"""
        return {
            name: len(cluster.patterns) 
            for name, cluster in self.clusters.items()
        }
    
    def strengthen_pattern(self, pattern_id: str, amount: float = 0.1):
        """Strengthen a pattern"""
        for pattern in self.patterns:
            if pattern.id == pattern_id:
                pattern.strength = min(1.0, pattern.strength + amount)
                pattern.activate()
                break
        self._save()
    
    def get_status(self) -> Dict:
        """Get neural engine status"""
        return {
            "total_patterns": len(self.patterns),
            "clusters": self.get_clusters(),
            "associations": sum(len(v) for v in self.associations.values()),
            "input_history_size": len(self.input_history),
            "top_patterns": [
                {
                    "id": p.id,
                    "type": p.type,
                    "strength": p.strength,
                    "activations": p.activation_count
                }
                for p in sorted(self.patterns, key=lambda x: x.activation_count, reverse=True)[:5]
            ]
        }


# Singleton instance
_instance = None

def get_neural_engine() -> NeuralPatternEngine:
    """Get singleton instance"""
    global _instance
    if _instance is None:
        _instance = NeuralPatternEngine()
    return _instance
