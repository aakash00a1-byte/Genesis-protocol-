"""Genesis Protocol - Observability Module

OpenTelemetry integration for tracing, metrics, and debugging.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum

logger = logging.getLogger("observability")


class TraceStatus(Enum):
    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class Span:
    name: str
    trace_id: str
    span_id: str
    parent_id: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    status: TraceStatus = TraceStatus.OK
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class ObservabilityManager:
    """
    Central observability manager for Genesis Protocol.
    
    Features:
    - Distributed tracing
    - Metrics collection
    - Error tracking
    - Performance monitoring
    """
    
    def __init__(self, service_name: str = "genesis-protocol"):
        self._service_name = service_name
        self._traces: List[Span] = []
        self._metrics: List[Dict] = []
        self._spans_stack: List[Span] = []
        self._trace_counter = 0
        self._span_counter = 0
        self._otel_tracer = None
        self._init_otel()
        logger.info(f"Observability initialized for {service_name}")
    
    def _init_otel(self):
        """Initialize OpenTelemetry if available."""
        try:
            from opentelemetry import trace, metrics
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.resources import Resource
            
            resource = Resource.create({"service.name": self._service_name})
            tracer_provider = TracerProvider(resource=resource)
            trace.set_tracer_provider(tracer_provider)
            self._otel_tracer = trace.get_tracer(self._service_name)
            logger.info("OpenTelemetry initialized")
        except ImportError:
            logger.warning("OpenTelemetry not installed. Using basic tracing.")
        except Exception as e:
            logger.error(f"OpenTelemetry init failed: {e}")
    
    def start_trace(self, name: str, attributes: Dict[str, Any] = None) -> str:
        """Start a new trace."""
        self._trace_counter += 1
        trace_id = f"trace_{self._trace_counter:06d}"
        
        span = Span(
            name=name,
            trace_id=trace_id,
            span_id=f"span_{self._span_counter:06d}",
            attributes=attributes or {}
        )
        
        self._traces.append(span)
        self._spans_stack.append(span)
        logger.debug(f"Started trace: {trace_id} - {name}")
        return trace_id
    
    def end_trace(self, trace_id: str, status: TraceStatus = TraceStatus.OK):
        """End a trace."""
        for span in self._traces:
            if span.trace_id == trace_id and span.end_time is None:
                span.end_time = time.time()
                span.status = status
                duration = (span.end_time - span.start_time) * 1000
                logger.debug(f"Ended trace: {trace_id} - {span.name} ({duration:.2f}ms)")
                
                if self._spans_stack and self._spans_stack[-1].trace_id == trace_id:
                    self._spans_stack.pop()
                break
    
    def add_span(self, name: str, attributes: Dict[str, Any] = None) -> str:
        """Add a child span to current trace."""
        if not self._spans_stack:
            return self.start_trace(name, attributes)
        
        self._span_counter += 1
        parent = self._spans_stack[-1]
        
        span = Span(
            name=name,
            trace_id=parent.trace_id,
            span_id=f"span_{self._span_counter:06d}",
            parent_id=parent.span_id,
            attributes=attributes or {}
        )
        
        self._traces.append(span)
        self._spans_stack.append(span)
        return span.span_id
    
    def end_span(self, span_id: str, status: TraceStatus = TraceStatus.OK):
        """End a span."""
        for span in reversed(self._spans_stack):
            if span.span_id == span_id:
                span.end_time = time.time()
                span.status = status
                self._spans_stack.pop()
                break
    
    def record_event(self, name: str, attributes: Dict[str, Any] = None):
        """Record an event in current span."""
        if self._spans_stack:
            span = self._spans_stack[-1]
            span.events.append({
                "name": name,
                "timestamp": time.time(),
                "attributes": attributes or {}
            })
    
    def record_error(self, error: str):
        """Record an error in current span."""
        if self._spans_stack:
            span = self._spans_stack[-1]
            span.errors.append(error)
            span.status = TraceStatus.ERROR
            logger.error(f"Error in {span.name}: {error}")
    
    def record_metric(self, name: str, value: float, unit: str = "",
                      labels: Dict[str, str] = None):
        """Record a metric."""
        self._metrics.append({
            "name": name,
            "value": value,
            "unit": unit,
            "timestamp": time.time(),
            "labels": labels or {}
        })
    
    def increment(self, name: str, labels: Dict[str, str] = None):
        """Increment a counter metric."""
        self.record_metric(name, 1, "count", labels)
    
    class Timer:
        """Context manager for timing operations."""
        def __init__(self, obs, name: str, metric_name: str = None):
            self._obs = obs
            self._name = name
            self._metric_name = metric_name or name
            self._start = None
        
        def __enter__(self):
            self._start = time.time()
            self._span_id = self._obs.add_span(self._name)
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            duration = (time.time() - self._start) * 1000
            self._obs.record_metric(self._metric_name, duration, "ms")
            self._obs.end_span(self._span_id)
            if exc_type:
                self._obs.record_error(str(exc_val))
            return False
    
    def timer(self, name: str, metric_name: str = None) -> Timer:
        """Create a timer context manager."""
        return self.Timer(self, name, metric_name)
    
    def get_traces(self, limit: int = 100) -> List[Dict]:
        """Get recent traces."""
        completed = [s for s in self._traces if s.end_time and s.parent_id is None]
        return [
            {
                "trace_id": s.trace_id,
                "name": s.name,
                "duration_ms": int((s.end_time - s.start_time) * 1000),
                "status": s.status.value,
                "errors": len(s.errors)
            }
            for s in completed[-limit:]
        ]
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        summary = {}
        for m in self._metrics:
            name = m["name"]
            if name not in summary:
                summary[name] = {"count": 0, "total": 0}
            summary[name]["count"] += 1
            summary[name]["total"] += m["value"]
        for name, data in summary.items():
            data["avg"] = data["total"] / data["count"] if data["count"] > 0 else 0
        return summary
    
    def get_errors(self, limit: int = 50) -> List[Dict]:
        """Get recent errors."""
        errors = []
        for span in self._traces:
            if span.errors:
                for error in span.errors:
                    errors.append({
                        "trace_id": span.trace_id,
                        "name": span.name,
                        "error": error,
                        "timestamp": span.start_time
                    })
        return errors[-limit:]
    
    def clear(self):
        """Clear all data."""
        self._traces.clear()
        self._metrics.clear()


_observability: Optional[ObservabilityManager] = None


def get_observability(service_name: str = "genesis-protocol") -> ObservabilityManager:
    """Get global observability manager."""
    global _observability
    if _observability is None:
        _observability = ObservabilityManager(service_name)
    return _observability
