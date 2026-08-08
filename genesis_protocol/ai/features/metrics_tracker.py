"""Genesis Protocol - Metrics & Cost Tracker

Track usage, costs, tokens, and performance metrics.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger("metrics")


@dataclass
class LLMUsage:
    """LLM usage record."""
    timestamp: datetime
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: float
    latency_ms: int
    success: bool
    error: Optional[str] = None


@dataclass
class TokenUsage:
    """Token usage breakdown."""
    date: str  # YYYY-MM-DD
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost: float


@dataclass
class CostSummary:
    """Cost summary for a period."""
    period: str
    total_cost: float
    total_tokens: int
    total_requests: int
    by_provider: Dict[str, float]
    by_model: Dict[str, float]
    daily_average: float


class MetricsTracker:
    """
    Track and analyze LLM usage, costs, and performance.
    
    Features:
    - Track every LLM call with tokens, cost, latency
    - Aggregate by day/week/month
    - Cost breakdown by provider/model
    - Performance metrics (latency, success rate)
    - Budget alerts
    """
    
    # Token pricing per 1M tokens (approximate)
    TOKEN_PRICING = {
        "groq": {
            "llama-3.1-70b-versatile": {"input": 0.59, "output": 0.79},
            "llama-3.1-8b-instant": {"input": 0.04, "output": 0.04},
            "mixtral-8x7b-32768": {"input": 0.24, "output": 0.24},
        },
        "openai": {
            "gpt-4o": {"input": 2.50, "output": 10.00},
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            "gpt-4-turbo": {"input": 10.00, "output": 30.00},
        },
        "anthropic": {
            "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
            "claude-3-opus": {"input": 15.00, "output": 75.00},
        },
        "gemini": {
            "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
            "gemini-1.5-flash": {"input": 0.035, "output": 0.14},
        },
        "deepseek": {
            "deepseek-chat": {"input": 0.14, "output": 0.28},
        },
        "mistral": {
            "mistral-large": {"input": 2.00, "output": 6.00},
        }
    }
    
    def __init__(self, monthly_budget: float = None):
        """
        Initialize metrics tracker.
        
        Args:
            monthly_budget: Optional monthly budget limit
        """
        self._monthly_budget = monthly_budget
        self._usage_records: List[LLMUsage] = []
        self._daily_usage: Dict[str, List[TokenUsage]] = defaultdict(list)
        self._provider_stats: Dict[str, Dict] = defaultdict(lambda: {
            "requests": 0, "tokens": 0, "cost": 0, "errors": 0
        })
        self._model_stats: Dict[str, Dict] = defaultdict(lambda: {
            "requests": 0, "tokens": 0, "cost": 0, "errors": 0
        })
        self._latencies: Dict[str, List[int]] = defaultdict(list)
        logger.info("MetricsTracker initialized")
    
    def record_usage(self, provider: str, model: str,
                    input_tokens: int, output_tokens: int,
                    latency_ms: int, success: bool = True,
                    error: str = None):
        """
        Record an LLM usage event.
        
        Args:
            provider: Provider name (groq, openai, etc.)
            model: Model name
            input_tokens: Input token count
            output_tokens: Output token count
            latency_ms: Request latency in milliseconds
            success: Whether request succeeded
            error: Optional error message
        """
        total_tokens = input_tokens + output_tokens
        cost = self._calculate_cost(provider, model, input_tokens, output_tokens)
        
        usage = LLMUsage(
            timestamp=datetime.utcnow(),
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost=cost,
            latency_ms=latency_ms,
            success=success,
            error=error
        )
        
        self._usage_records.append(usage)
        
        # Update daily usage
        date_key = usage.timestamp.strftime("%Y-%m-%d")
        self._daily_usage[date_key].append(TokenUsage(
            date=date_key,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost=cost
        ))
        
        # Update provider stats
        stats = self._provider_stats[provider]
        stats["requests"] += 1
        stats["tokens"] += total_tokens
        stats["cost"] += cost
        if not success:
            stats["errors"] += 1
        
        # Update model stats
        model_key = f"{provider}.{model}"
        model_stats = self._model_stats[model_key]
        model_stats["requests"] += 1
        model_stats["tokens"] += total_tokens
        model_stats["cost"] += cost
        if not success:
            model_stats["errors"] += 1
        
        # Track latencies
        self._latencies[provider].append(latency_ms)
        if len(self._latencies[provider]) > 1000:
            self._latencies[provider] = self._latencies[provider][-1000:]
        
        logger.debug(f"Recorded usage: {provider}/{model} - {total_tokens} tokens, ${cost:.4f}")
        
        # Check budget
        if self._monthly_budget:
            monthly_cost = self.get_cost_summary("monthly")["total_cost"]
            if monthly_cost > self._monthly_budget:
                logger.warning(f"Monthly budget exceeded: ${monthly_cost:.2f} > ${self._monthly_budget:.2f}")
    
    def _calculate_cost(self, provider: str, model: str,
                       input_tokens: int, output_tokens: int) -> float:
        """Calculate cost for a request."""
        pricing = self.TOKEN_PRICING.get(provider, {}).get(model, {})
        
        input_rate = pricing.get("input", 0.50) / 1_000_000
        output_rate = pricing.get("output", 0.50) / 1_000_000
        
        return (input_tokens * input_rate) + (output_tokens * output_rate)
    
    def get_cost_summary(self, period: str = "daily") -> CostSummary:
        """
        Get cost summary for a period.
        
        Args:
            period: "daily", "weekly", "monthly", or "all"
            
        Returns:
            CostSummary with aggregated data
        """
        now = datetime.utcnow()
        
        if period == "daily":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "weekly":
            start = now - timedelta(days=7)
        elif period == "monthly":
            start = now - timedelta(days=30)
        else:
            start = datetime.min
        
        # Filter usage records
        filtered = [u for u in self._usage_records if u.timestamp >= start]
        
        if not filtered:
            return CostSummary(
                period=period,
                total_cost=0,
                total_tokens=0,
                total_requests=0,
                by_provider={},
                by_model={},
                daily_average=0
            )
        
        total_cost = sum(u.cost for u in filtered)
        total_tokens = sum(u.total_tokens for u in filtered)
        total_requests = len(filtered)
        
        # By provider
        by_provider = defaultdict(float)
        for u in filtered:
            by_provider[u.provider] += u.cost
        
        # By model
        by_model = defaultdict(float)
        for u in filtered:
            model_key = f"{u.provider}.{u.model}"
            by_model[model_key] += u.cost
        
        # Calculate daily average
        if period in ["weekly", "monthly"]:
            days = (now - start).days or 1
            daily_avg = total_cost / days
        else:
            daily_avg = total_cost
        
        return CostSummary(
            period=period,
            total_cost=total_cost,
            total_tokens=total_tokens,
            total_requests=total_requests,
            by_provider=dict(by_provider),
            by_model=dict(by_model),
            daily_average=daily_avg
        )
    
    def get_token_usage(self, days: int = 7) -> Dict[str, Any]:
        """
        Get token usage breakdown.
        
        Args:
            days: Number of days to include
            
        Returns:
            Token usage statistics
        """
        start = datetime.utcnow() - timedelta(days=days)
        filtered = [u for u in self._usage_records if u.timestamp >= start]
        
        if not filtered:
            return {"total": 0, "daily": {}, "by_model": {}}
        
        total = sum(u.total_tokens for u in filtered)
        
        # Daily breakdown
        daily = defaultdict(int)
        for u in filtered:
            daily[u.timestamp.strftime("%Y-%m-%d")] += u.total_tokens
        
        # By model
        by_model = defaultdict(int)
        for u in filtered:
            model_key = f"{u.provider}.{u.model}"
            by_model[model_key] += u.total_tokens
        
        return {
            "total": total,
            "daily": dict(daily),
            "by_model": dict(by_model),
            "average_per_day": total / days if days > 0 else 0
        }
    
    def get_performance_stats(self, provider: str = None) -> Dict[str, Any]:
        """
        Get performance statistics.
        
        Args:
            provider: Optional provider filter
            
        Returns:
            Performance metrics
        """
        if provider:
            filtered = [u for u in self._usage_records if u.provider == provider]
            latencies = self._latencies.get(provider, [])
        else:
            filtered = self._usage_records
            latencies = [l for lat_list in self._latencies.values() for l in lat_list]
        
        if not filtered:
            return {
                "total_requests": 0,
                "success_rate": 0,
                "avg_latency_ms": 0,
                "p50_latency_ms": 0,
                "p95_latency_ms": 0,
                "p99_latency_ms": 0
            }
        
        success_count = sum(1 for u in filtered if u.success)
        success_rate = success_count / len(filtered) if filtered else 0
        
        sorted_latencies = sorted(latencies)
        n = len(sorted_latencies)
        
        def percentile(p):
            idx = int(n * p)
            return sorted_latencies[min(idx, n - 1)]
        
        return {
            "total_requests": len(filtered),
            "success_rate": success_rate,
            "avg_latency_ms": sum(latencies) / n if n > 0 else 0,
            "p50_latency_ms": percentile(0.50),
            "p95_latency_ms": percentile(0.95),
            "p99_latency_ms": percentile(0.99),
            "min_latency_ms": min(latencies) if latencies else 0,
            "max_latency_ms": max(latencies) if latencies else 0
        }
    
    def get_provider_breakdown(self) -> List[Dict[str, Any]]:
        """Get breakdown by provider."""
        result = []
        
        for provider, stats in self._provider_stats.items():
            success_rate = (
                (stats["requests"] - stats["errors"]) / stats["requests"]
                if stats["requests"] > 0 else 0
            )
            
            latencies = self._latencies.get(provider, [])
            avg_latency = sum(latencies) / len(latencies) if latencies else 0
            
            result.append({
                "provider": provider,
                "requests": stats["requests"],
                "tokens": stats["tokens"],
                "cost": stats["cost"],
                "errors": stats["errors"],
                "success_rate": success_rate,
                "avg_latency_ms": avg_latency
            })
        
        # Sort by cost descending
        result.sort(key=lambda x: x["cost"], reverse=True)
        return result
    
    def estimate_monthly_cost(self) -> float:
        """Estimate monthly cost based on current usage."""
        daily = self.get_cost_summary("daily")
        return daily.daily_average * 30
    
    def get_budget_status(self) -> Dict[str, Any]:
        """Get budget status if configured."""
        if not self._monthly_budget:
            return {"budget_configured": False}
        
        monthly = self.get_cost_summary("monthly")
        remaining = self._monthly_budget - monthly.total_cost
        percentage = (monthly.total_cost / self._monthly_budget * 100) if self._monthly_budget > 0 else 0
        
        return {
            "budget_configured": True,
            "monthly_budget": self._monthly_budget,
            "spent": monthly.total_cost,
            "remaining": remaining,
            "percentage_used": percentage,
            "over_budget": remaining < 0,
            "estimated_monthly": self.estimate_monthly_cost()
        }
    
    def export_csv(self) -> str:
        """Export usage records as CSV."""
        if not self._usage_records:
            return ""
        
        lines = ["timestamp,provider,model,input_tokens,output_tokens,total_tokens,cost,latency_ms,success,error"]
        
        for u in self._usage_records:
            lines.append(
                f"{u.timestamp.isoformat()},{u.provider},{u.model},"
                f"{u.input_tokens},{u.output_tokens},{u.total_tokens},"
                f"{u.cost:.6f},{u.latency_ms},{u.success},\"{u.error or ''}\""
            )
        
        return "\n".join(lines)
    
    def clear_old_records(self, older_than_days: int = 90):
        """Clear usage records older than specified days."""
        cutoff = datetime.utcnow() - timedelta(days=older_than_days)
        self._usage_records = [u for u in self._usage_records if u.timestamp >= cutoff]
        logger.info(f"Cleared records older than {older_than_days} days")


# Singleton
_metrics_tracker: Optional[MetricsTracker] = None


def get_metrics_tracker(monthly_budget: float = None) -> MetricsTracker:
    """Get global metrics tracker."""
    global _metrics_tracker
    if _metrics_tracker is None:
        _metrics_tracker = MetricsTracker(monthly_budget)
    return _metrics_tracker
