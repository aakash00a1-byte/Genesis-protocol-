"""Genesis Protocol - Scoring Engine

Dynamic scoring-based model selection system.
Scores each model based on query intent and selects highest score.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger("ai.scoring")


@dataclass
class ModelScore:
    """Model with calculated score."""
    provider: str
    model_name: str
    score: float
    reasons: List[str] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class IntentAnalysis:
    """Analyzed query intent."""
    primary_intent: str
    sub_intents: List[str]
    complexity: float  # 0.0 to 1.0
    urgency: str  # 'high', 'medium', 'low'
    context_needed: bool
    tools_needed: List[str] = field(default_factory=list)


class ScoringEngine:
    """
    Dynamic scoring engine for model selection.
    
    Evaluates each model against query requirements and returns
    scored list of models. Highest score wins.
    """
    
    # Model capabilities and costs
    MODEL_CATALOG: Dict[str, Dict] = {
        # OpenAI
        "gpt-4o": {
            "provider": "openai",
            "capabilities": ["coding", "reasoning", "vision", "creative", "analysis"],
            "strengths": ["code_generation", "complex_reasoning", "creative_writing", "analysis"],
            "weaknesses": ["cost", "speed"],
            "context_window": 128000,
            "cost_tier": 3,  # 1=cheap, 3=expensive
            "speed_tier": 2,
            "max_tokens": 32000,
        },
        "gpt-4-turbo": {
            "provider": "openai",
            "capabilities": ["coding", "reasoning", "vision", "creative"],
            "strengths": ["code_generation", "reasoning", "creative"],
            "weaknesses": ["cost"],
            "context_window": 128000,
            "cost_tier": 2,
            "speed_tier": 2,
            "max_tokens": 16000,
        },
        "gpt-4o-mini": {
            "provider": "openai",
            "capabilities": ["coding", "reasoning", "fast"],
            "strengths": ["code_generation", "fast_responses", "cost_effective"],
            "weaknesses": ["complex_tasks"],
            "context_window": 128000,
            "cost_tier": 1,
            "speed_tier": 1,
            "max_tokens": 16000,
        },
        
        # Google Gemini
        "gemini-2.0-flash": {
            "provider": "gemini",
            "capabilities": ["fast", "reasoning", "vision", "long_context"],
            "strengths": ["fast_responses", "reasoning", "cost_effective", "long_context"],
            "weaknesses": ["creative_writing"],
            "context_window": 1000000,
            "cost_tier": 1,
            "speed_tier": 1,
            "max_tokens": 8192,
        },
        "gemini-1.5-pro": {
            "provider": "gemini",
            "capabilities": ["reasoning", "vision", "long_context", "analysis"],
            "strengths": ["long_context", "complex_reasoning", "analysis"],
            "weaknesses": ["speed"],
            "context_window": 2000000,
            "cost_tier": 2,
            "speed_tier": 2,
            "max_tokens": 8192,
        },
        "gemini-1.5-flash": {
            "provider": "gemini",
            "capabilities": ["fast", "vision", "reasoning"],
            "strengths": ["fast_responses", "cost_effective", "vision"],
            "weaknesses": ["creative_writing"],
            "context_window": 1000000,
            "cost_tier": 1,
            "speed_tier": 1,
            "max_tokens": 8192,
        },
        
        # Anthropic Claude
        "claude-sonnet-4-20250514": {
            "provider": "claude",
            "capabilities": ["creative", "reasoning", "coding", "analysis"],
            "strengths": ["creative_writing", "complex_reasoning", "analysis", "nuanced"],
            "weaknesses": ["speed"],
            "context_window": 200000,
            "cost_tier": 2,
            "speed_tier": 2,
            "max_tokens": 8192,
        },
        "claude-3-5-sonnet-20241022": {
            "provider": "claude",
            "capabilities": ["creative", "reasoning", "coding", "analysis"],
            "strengths": ["creative_writing", "reasoning", "coding"],
            "weaknesses": ["speed"],
            "context_window": 200000,
            "cost_tier": 2,
            "speed_tier": 2,
            "max_tokens": 8192,
        },
        "claude-3-haiku-20240307": {
            "provider": "claude",
            "capabilities": ["fast", "creative", "cost_effective"],
            "strengths": ["fast_responses", "creative", "cost_effective"],
            "weaknesses": ["complex_reasoning"],
            "context_window": 200000,
            "cost_tier": 1,
            "speed_tier": 1,
            "max_tokens": 4096,
        },
        
        # Groq (Fast & Cheap)
        "llama-3.3-70b-versatile": {
            "provider": "groq",
            "capabilities": ["fast", "reasoning", "coding", "cost_effective"],
            "strengths": ["fast_responses", "cost_effective", "reasoning", "coding"],
            "weaknesses": ["creative_writing", "nuanced_analysis"],
            "context_window": 32768,
            "cost_tier": 1,
            "speed_tier": 1,
            "max_tokens": 4096,
        },
        "mixtral-8x7b-32768": {
            "provider": "groq",
            "capabilities": ["fast", "cost_effective", "reasoning"],
            "strengths": ["fast_responses", "cost_effective"],
            "weaknesses": ["complex_tasks", "creative"],
            "context_window": 32768,
            "cost_tier": 1,
            "speed_tier": 1,
            "max_tokens": 4096,
        },
    }
    
    # Intent weights for scoring
    INTENT_WEIGHTS: Dict[str, Dict] = {
        "coding": {
            "gpt-4o": 0.95, "gpt-4-turbo": 0.90, "gpt-4o-mini": 0.75,
            "claude-3-5-sonnet-20241022": 0.85, "claude-sonnet-4-20250514": 0.90,
            "gemini-1.5-flash": 0.70, "gemini-2.0-flash": 0.75,
            "llama-3.3-70b-versatile": 0.80, "mixtral-8x7b-32768": 0.70,
        },
        "creative": {
            "claude-3-5-sonnet-20241022": 0.95, "claude-sonnet-4-20250514": 0.98,
            "gpt-4o": 0.90, "gpt-4-turbo": 0.85,
            "gemini-1.5-flash": 0.65, "gemini-2.0-flash": 0.70,
            "llama-3.3-70b-versatile": 0.60, "mixtral-8x7b-32768": 0.50,
        },
        "reasoning": {
            "gemini-1.5-pro": 0.95, "gpt-4o": 0.90,
            "claude-3-5-sonnet-20241022": 0.88, "claude-sonnet-4-20250514": 0.92,
            "gemini-2.0-flash": 0.85, "llama-3.3-70b-versatile": 0.75,
        },
        "fast": {
            "gemini-2.0-flash": 0.98, "gemini-1.5-flash": 0.95,
            "llama-3.3-70b-versatile": 0.95, "mixtral-8x7b-32768": 0.90,
            "gpt-4o-mini": 0.85, "claude-3-haiku-20240307": 0.85,
        },
        "long_context": {
            "gemini-1.5-pro": 0.98, "gemini-2.0-flash": 0.90,
            "claude-3-5-sonnet-20241022": 0.85, "claude-sonnet-4-20250514": 0.88,
            "gpt-4o": 0.80, "llama-3.3-70b-versatile": 0.60,
        },
        "vision": {
            "gpt-4o": 0.95, "gemini-1.5-pro": 0.95, "gemini-1.5-flash": 0.90,
            "claude-3-5-sonnet-20241022": 0.85, "gemini-2.0-flash": 0.88,
        },
        "analysis": {
            "claude-sonnet-4-20250514": 0.95, "gpt-4o": 0.92,
            "gemini-1.5-pro": 0.90, "claude-3-5-sonnet-20241022": 0.88,
            "gemini-2.0-flash": 0.80, "llama-3.3-70b-versatile": 0.70,
        },
    }
    
    # Simple query patterns for bypass
    SIMPLE_PATTERNS = [
        r'^(hi|hello|hey|namaste|hola)$',
        r'^(thanks|thank you|thx|dhanyavad)$',
        r'^(ok|okay|cool|nice|yeah|haan|nahi)$',
        r'^kya\s+haal\s+hai',
        r'^how\s+are\s+you',
        r'^what[\'\s]?s?up',
        r'^(bye|see\s+you|thanks\s+bye)$',
    ]
    
    def __init__(self):
        """Initialize scoring engine."""
        self.logger = logging.getLogger("ai.scoring")
        self._routing_log: List[Dict] = []
        self._claude_available = True  # Will be updated on first check
    
    def set_claude_availability(self, available: bool):
        """Update Claude availability status."""
        self._claude_available = available
        self.logger.info(f"Claude availability: {available}")
    
    def is_provider_available(self, provider: str, available_providers: List[str]) -> bool:
        """Check if provider is available."""
        return provider in available_providers
    
    def analyze_intent(self, query: str) -> IntentAnalysis:
        """
        Analyze query intent.
        
        Args:
            query: User query
            
        Returns:
            IntentAnalysis with detected intents
        """
        query_lower = query.lower()
        primary_intent = "general"
        sub_intents = []
        complexity = 0.5
        tools_needed = []
        
        # Detect coding intent
        coding_patterns = [
            r'\b(code|programming|python|javascript|java|c\+\+|rust|go|html|css)\b',
            r'\b(debug|function|class|api|sql|git|bug|error|algorithm)\b',
            r'\b(write|create|build|make)\s+(a\s+)?(code|program|script|function|app)\b',
            r'```\w*',  # Code blocks
        ]
        if any(re.search(p, query_lower) for p in coding_patterns):
            primary_intent = "coding"
            sub_intents.append("coding")
        
        # Detect creative intent
        creative_patterns = [
            r'\b(story|write|poem|song|creative|imagine|storytelling|narrative)\b',
            r'\b(brainstorm|ideas|generate|creative)\b',
            r'\b(essay|article|blog|content|marketing|copy)\b',
        ]
        if any(re.search(p, query_lower) for p in creative_patterns):
            if primary_intent == "coding":
                sub_intents.append("creative")
            else:
                primary_intent = "creative"
                sub_intents.append("creative")
        
        # Detect reasoning intent
        reasoning_patterns = [
            r'\b(explain|why|how|reason|logic|analyze|analyse|compare)\b',
            r'\b(what\s+is|define|meaning|understand|learn)\b',
            r'\b(because|therefore|since|hence|thus)\b',
        ]
        if any(re.search(p, query_lower) for p in reasoning_patterns):
            if primary_intent not in ["coding", "creative"]:
                primary_intent = "reasoning"
            sub_intents.append("reasoning")
        
        # Detect long context
        long_patterns = [
            r'\b(long|extended|detailed|comprehensive|thorough)\b',
            r'\b(summarize|summary|overview|document|paper|report)\b',
            r'\b(history|background|context|previous)\b',
        ]
        if any(re.search(p, query_lower) for p in long_patterns):
            sub_intents.append("long_context")
        
        # Detect vision
        vision_patterns = [
            r'\b(image|photo|picture|visual|see|look|analyze)\b',
            r'\b(describe|what\s+is\s+in)\b',
        ]
        if any(re.search(p, query_lower) for p in vision_patterns):
            sub_intents.append("vision")
        
        # Detect tools needed
        if any(kw in query_lower for kw in ["search", "find", "latest", "news", "current"]):
            tools_needed.append("web_search")
        if any(kw in query_lower for kw in ["remember", "recall", "past", "before"]):
            tools_needed.append("memory_recall")
        if any(kw in query_lower for kw in ["save", "remember this", "store"]):
            tools_needed.append("memory_store")
        
        # Calculate complexity
        complexity = min(1.0, len(query) / 500 + len(sub_intents) * 0.15)
        
        # Determine urgency
        urgency = "low"
        if any(kw in query_lower for kw in ["urgent", "asap", "immediately", "quick"]):
            urgency = "high"
        elif complexity > 0.7:
            urgency = "medium"
        
        return IntentAnalysis(
            primary_intent=primary_intent,
            sub_intents=sub_intents,
            complexity=complexity,
            urgency=urgency,
            context_needed=complexity > 0.6,
            tools_needed=tools_needed
        )
    
    def is_simple_query(self, query: str) -> bool:
        """Check if query is simple enough to bypass planning."""
        query_lower = query.lower().strip()
        return any(re.match(p, query_lower) for p in self.SIMPLE_PATTERNS)
    
    def score_models(self, query: str, intent: IntentAnalysis,
                     available_providers: List[str]) -> List[ModelScore]:
        """
        Score all available models for the query.
        
        Args:
            query: User query
            intent: Analyzed intent
            available_providers: List of configured provider names
            
        Returns:
            List of ModelScore sorted by score (highest first)
        """
        scores = []
        
        for model_name, model_info in self.MODEL_CATALOG.items():
            # Skip if provider not available
            if model_info["provider"] not in available_providers:
                continue
            
            # Handle Claude unavailability - redistribute weight
            if model_info["provider"] == "claude" and not self._claude_available:
                continue  # Skip Claude models entirely
            
            score = 0.0
            reasons = []
            
            # Base score from intent weights
            base_score = self.INTENT_WEIGHTS.get(intent.primary_intent, {}).get(model_name, 0.5)
            
            # If Claude not available, boost alternative models for creative tasks
            if not self._claude_available and intent.primary_intent == "creative":
                if model_info["provider"] == "openai":
                    base_score += 0.15  # Boost OpenAI for creative when Claude unavailable
                elif model_info["provider"] == "gemini":
                    base_score += 0.10
            
            score += base_score * 0.6  # 60% weight on intent match
            
            # Capability match bonus
            for capability in intent.sub_intents:
                if capability in model_info["capabilities"]:
                    score += 0.08
                    reasons.append(f"capable:{capability}")
            
            # Speed bonus for high urgency
            if intent.urgency == "high" and model_info["speed_tier"] == 1:
                score += 0.15
                reasons.append("fast_response")
            
            # Cost penalty for complex queries (prefer cheaper models)
            if intent.complexity < 0.4 and model_info["cost_tier"] == 1:
                score += 0.1
                reasons.append("cost_effective")
            
            # Context window check
            if "long_context" in intent.sub_intents:
                if model_info["context_window"] >= 1000000:
                    score += 0.1
                    reasons.append("long_context_support")
            
            # Creative bonus for creative tasks
            if intent.primary_intent == "creative":
                if "creative_writing" in model_info.get("strengths", []):
                    score += 0.12
                    reasons.append("creative_strength")
            
            # Normalize to 0-1 range
            score = min(1.0, score)
            
            scores.append(ModelScore(
                provider=model_info["provider"],
                model_name=model_name,
                score=score,
                reasons=reasons,
                confidence=min(1.0, len(reasons) * 0.1 + 0.5)
            ))
        
        # Sort by score (highest first)
        scores.sort(key=lambda x: x.score, reverse=True)
        
        return scores
    
    def select_model(self, query: str, available_providers: List[str]) -> Tuple[str, str, float, IntentAnalysis]:
        """
        Select best model using scoring engine.
        
        Args:
            query: User query
            available_providers: List of available providers
            
        Returns:
            Tuple of (provider, model_name, score, intent_analysis)
        """
        # Analyze intent
        intent = self.analyze_intent(query)
        
        # Check for simple query bypass
        if self.is_simple_query(query):
            # Use fastest model for simple queries
            fast_model = "gemini-2.0-flash" if "gemini" in available_providers else "llama-3.3-70b-versatile"
            self.logger.info(f"Simple query - bypassing planning, using {fast_model}")
            return ("gemini" if "gemini" in available_providers else "groq", fast_model, 0.95, intent)
        
        # Score all models
        scored_models = self.score_models(query, intent, available_providers)
        
        if not scored_models:
            # Fallback to Groq
            return ("groq", "llama-3.3-70b-versatile", 0.5, intent)
        
        # Select best model
        best = scored_models[0]
        
        # Log selection
        self._log_routing(query, intent, best, scored_models[:3])
        
        return (best.provider, best.model_name, best.score, intent)
    
    def _log_routing(self, query: str, intent: IntentAnalysis, 
                     selected: ModelScore, alternatives: List[ModelScore]):
        """Log routing decision for analysis."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "query": query[:100],
            "intent": intent.primary_intent,
            "complexity": intent.complexity,
            "selected_provider": selected.provider,
            "selected_model": selected.model_name,
            "selected_score": selected.score,
            "alternatives": [(a.provider, a.model_name, a.score) for a in alternatives],
        }
        self._routing_log.append(log_entry)
        self.logger.info(f"Routing: {selected.model_name} (score: {selected.score:.2f}) for {intent.primary_intent}")
    
    def get_fallback_chain(self, primary_model: str, available_providers: List[str]) -> List[str]:
        """
        Get fallback chain based on primary selection.
        
        Returns models in order: second best, third, Groq final fallback
        """
        scored = self.score_models("general query", 
                                   IntentAnalysis("general", [], 0.5, "low", False, []),
                                   available_providers)
        
        chain = []
        for model_score in scored:
            if model_score.model_name != primary_model:
                chain.append(model_score.model_name)
            if len(chain) >= 3:
                break
        
        # Ensure Groq is last fallback
        if "llama-3.3-70b-versatile" not in chain:
            chain.append("llama-3.3-70b-versatile")
        
        return chain
    
    def get_routing_history(self) -> List[Dict]:
        """Get routing history for analysis."""
        return self._routing_log
    
    def update_weights(self, model: str, success: bool, latency: float):
        """
        Update weights based on results (for future improvement).
        
        This would be called after each request to improve routing.
        """
        # Placeholder for learning-based updates
        self.logger.debug(f"Would update weights for {model}: success={success}, latency={latency}ms")


# Singleton
_scoring_engine: Optional[ScoringEngine] = None


def get_scoring_engine() -> ScoringEngine:
    """Get or create scoring engine singleton."""
    global _scoring_engine
    if _scoring_engine is None:
        _scoring_engine = ScoringEngine()
    return _scoring_engine