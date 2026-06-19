"""Improvement Analyzer - Genesis Protocol v1.7"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import json
from pathlib import Path


class ImprovementAnalyzer:
    """Analyzes data to find improvement opportunities."""
    
    def __init__(self, storage_path: str = "./data/improvements"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.observations = []
    
    def analyze_failures(self, evaluation_stats: Dict) -> List[Dict]:
        """Analyze failures and generate opportunities."""
        opportunities = []
        
        if evaluation_stats.get("success_rate", 1.0) < 0.8:
            opportunities.append({
                "type": "quality",
                "description": f"Success rate is {evaluation_stats.get('success_rate', 0):.1%}",
                "suggestion": "Review recent failures for patterns",
                "severity": 1.0 - evaluation_stats.get("success_rate", 0)
            })
        
        if evaluation_stats.get("average_latency_ms", 0) > 3000:
            opportunities.append({
                "type": "latency",
                "description": f"High latency: {evaluation_stats.get('average_latency_ms', 0):.0f}ms",
                "suggestion": "Consider caching or provider optimization",
                "severity": min(1.0, evaluation_stats.get("average_latency_ms", 0) / 10000)
            })
        
        return opportunities
    
    def analyze_tool_failures(self, tool_stats: Dict) -> List[Dict]:
        """Analyze tool failures."""
        opportunities = []
        
        for tool, stats in tool_stats.get("by_tool", {}).items():
            if stats.get("success_rate", 1.0) < 0.7:
                opportunities.append({
                    "type": "tool_failure",
                    "description": f"Tool '{tool}' has low success rate: {stats.get('success_rate', 0):.1%}",
                    "suggestion": f"Review and fix {tool} implementation",
                    "severity": 1.0 - stats.get("success_rate", 0)
                })
        
        return opportunities
    
    def analyze_skill_weaknesses(self, skill_stats: Dict) -> List[Dict]:
        """Analyze skill weaknesses."""
        opportunities = []
        
        for skill, score in skill_stats.get("scores_24h", {}).items():
            if score < 0.6:
                opportunities.append({
                    "type": "skill_weakness",
                    "description": f"Low {skill}: {score:.1%}",
                    "suggestion": f"Focus on improving {skill}",
                    "severity": 1.0 - score
                })
        
        return opportunities
    
    def get_all_opportunities(self) -> List[Dict]:
        """Get all improvement opportunities."""
        return self.observations
    
    def record_observation(self, observation: Dict):
        """Record an observation."""
        observation["timestamp"] = datetime.now().isoformat()
        self.observations.append(observation)


# Global singleton
_analyzer = None


def get_improvement_analyzer() -> ImprovementAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = ImprovementAnalyzer()
    return _analyzer
