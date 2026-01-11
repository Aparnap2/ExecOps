"""Observability integration for GitHub Sentinel.

This module provides:
- LangFuse tracing integration (optional)
- Metrics collection and reporting
- Structured logging setup
"""

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncGenerator

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Lazy imports for optional dependencies
_LangfuseTracer = None
_Langfuse = None


def _get_langfuse_types():
    """Get LangFuse types, importing lazily."""
    global _LangfuseTracer, _Langfuse
    if _LangfuseTracer is None:
        try:
            from langfuse.langchain import LangfuseTracer
            from langfuse import Langfuse

            _LangfuseTracer = LangfuseTracer
            _Langfuse = Langfuse
        except ImportError:
            pass
    return _LangfuseTracer, _Langfuse


@dataclass
class SentinelMetrics:
    """Application metrics for monitoring."""

    # Counters
    prs_processed: int = 0
    prs_approved: int = 0
    prs_warned: int = 0
    prs_blocked: int = 0
    violations_found: int = 0
    recommendations_generated: int = 0

    # Timings (in seconds)
    avg_processing_time: float = 0.0
    total_processing_time: float = 0.0

    # Budget
    total_estimated_cost: float = 0.0
    budgets_exceeded: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "prs_processed": self.prs_processed,
            "prs_approved": self.prs_approved,
            "prs_warned": self.prs_warned,
            "prs_blocked": self.prs_blocked,
            "violations_found": self.violations_found,
            "recommendations_generated": self.recommendations_generated,
            "avg_processing_time": self.avg_processing_time,
            "total_processing_time": self.total_processing_time,
            "total_estimated_cost": self.total_estimated_cost,
            "budgets_exceeded": self.budgets_exceeded,
        }


class ObservabilityConfig(BaseModel):
    """Configuration for observability features."""

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    log_level: str = "INFO"
    log_format: str = "json"


class SentinelTracer:
    """LangFuse tracer for GitHub Sentinel.

    Provides distributed tracing for PR analysis workflows.
    """

    def __init__(
        self,
        public_key: str | None = None,
        secret_key: str | None = None,
        host: str = "https://cloud.langfuse.com",
    ) -> None:
        """Initialize the tracer.

        Args:
            public_key: Langfuse public key
            secret_key: Langfuse secret key
            host: Langfuse server URL
        """
        self._tracer: Any = None  # LangfuseTracer or None
        self._langfuse: Any = None  # Langfuse or None
        self._public_key = public_key
        self._secret_key = secret_key
        self._host = host

    def setup(self) -> bool:
        """Set up the LangFuse tracer.

        Returns:
            True if tracer was set up successfully
        """
        if not self._public_key or not self._secret_key:
            logger.debug("LangFuse keys not configured, skipping tracer setup")
            return False

        try:
            LangfuseTracer, Langfuse = _get_langfuse_types()
            if Langfuse is None:
                logger.warning("Langfuse not installed, skipping tracer setup")
                return False

            self._langfuse = Langfuse(
                public_key=self._public_key,
                secret_key=self._secret_key,
                host=self._host,
            )
            self._tracer = LangfuseTracer()
            logger.info("LangFuse tracer initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize LangFuse tracer: {e}")
            return False

    def get_tracer(self) -> Any:
        """Get the LangFuse tracer instance.

        Returns:
            LangfuseTracer or None if not configured
        """
        return self._tracer

    def create_generation(
        self,
        name: str,
        input_data: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ):
        """Create a new generation for tracing.

        Args:
            name: Name of the generation
            input_data: Input data for the generation
            metadata: Optional metadata
        """
        if not self._langfuse:
            return None

        return self._langfuse.generation(
            name=name,
            input=input_data,
            metadata=metadata,
        )

    def flush(self) -> None:
        """Flush pending traces to LangFuse."""
        if self._langfuse:
            self._langfuse.flush()

    def shutdown(self) -> None:
        """Shutdown the tracer and flush pending traces."""
        self.flush()
        if self._langfuse:
            self._langfuse.shutdown()


# Global tracer instance
_tracer_instance: SentinelTracer | None = None


def get_tracer() -> SentinelTracer:
    """Get the global tracer instance."""
    global _tracer_instance
    if _tracer_instance is None:
        _tracer_instance = SentinelTracer()
    return _tracer_instance


def setup_tracing(
    public_key: str | None = None,
    secret_key: str | None = None,
    host: str = "https://cloud.langfuse.com",
) -> SentinelTracer:
    """Set up global tracing with LangFuse.

    Args:
        public_key: Langfuse public key
        secret_key: Langfuse secret key
        host: Langfuse server URL

    Returns:
        Configured SentinelTracer instance
    """
    global _tracer_instance
    _tracer_instance = SentinelTracer(public_key, secret_key, host)
    _tracer_instance.setup()
    return _tracer_instance


def setup_logging(level: str = "INFO", format: str = "json") -> None:
    """Configure structured logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        format: Log format (json, text)
    """
    import json

    log_level = getattr(logging, level.upper(), logging.INFO)

    # Configure root logger
    logging.basicConfig(level=log_level)

    # Create custom formatter
    class StructuredFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            log_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "message": record.getMessage(),
                "logger": record.name,
            }

            # Add exception info if present
            if record.exc_info:
                log_data["exception"] = self.formatException(record.exc_info)

            # Add extra attributes
            if hasattr(record, "trace_id"):
                log_data["trace_id"] = record.trace_id
            if hasattr(record, "pr_number"):
                log_data["pr_number"] = record.pr_number

            if format == "json":
                return json.dumps(log_data)
            else:
                return (
                    f"[{log_data['timestamp']}] {log_data['level']}: "
                    f"{log_data['message']}"
                )

    # Apply formatter to handlers
    for handler in logging.root.handlers:
        handler.setFormatter(StructuredFormatter())


# Metrics tracking
_metrics: SentinelMetrics = SentinelMetrics()


def get_metrics() -> SentinelMetrics:
    """Get the global metrics instance."""
    return _metrics


def record_pr_decision(decision: str, processing_time: float) -> None:
    """Record a PR decision for metrics.

    Args:
        decision: The decision made (approve, warn, block)
        processing_time: Time taken to process in seconds
    """
    global _metrics

    _metrics.prs_processed += 1
    _metrics.total_processing_time += processing_time
    _metrics.avg_processing_time = (
        _metrics.total_processing_time / _metrics.prs_processed
    )

    if decision == "approve":
        _metrics.prs_approved += 1
    elif decision == "warn":
        _metrics.prs_warned += 1
    elif decision == "block":
        _metrics.prs_blocked += 1


def record_violations(count: int) -> None:
    """Record violations found.

    Args:
        count: Number of violations found
    """
    global _metrics
    _metrics.violations_found += count


def record_recommendations(count: int) -> None:
    """Record recommendations generated.

    Args:
        count: Number of recommendations generated
    """
    global _metrics
    _metrics.recommendations_generated += count


def record_budget_impact(estimated_cost: float, exceeds_budget: bool) -> None:
    """Record budget impact.

    Args:
        estimated_cost: Estimated monthly cost
        exceeds_budget: Whether budget was exceeded
    """
    global _metrics
    _metrics.total_estimated_cost += estimated_cost
    if exceeds_budget:
        _metrics.budgets_exceeded += 1


@asynccontextmanager
async def trace_span(
    name: str,
    input_data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Create a tracing span for an operation.

    Args:
        name: Name of the span
        input_data: Input data for the span
        metadata: Optional metadata

    Yields:
        Span output data
    """
    tracer = get_tracer()
    generation = None

    if tracer and input_data:
        generation = tracer.create_generation(name, input_data, metadata)

    start_time = datetime.utcnow()
    output = {}

    try:
        yield output
    finally:
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        output["duration_seconds"] = duration
        output["completed_at"] = end_time.isoformat()

        if generation:
            generation.end(output=output)


class SentinelObservability:
    """Main observability class for GitHub Sentinel.

    Provides a unified interface for all observability features.
    """

    def __init__(
        self,
        config: ObservabilityConfig | None = None,
    ) -> None:
        """Initialize observability.

        Args:
            config: Optional observability configuration
        """
        self.config = config or ObservabilityConfig()
        self._tracer: SentinelTracer | None = None

    def initialize(self) -> None:
        """Initialize all observability components."""
        # Setup logging
        setup_logging(
            level=self.config.log_level,
            format=self.config.log_format,
        )

        # Setup tracing if configured
        if self.config.langfuse_public_key and self.config.langfuse_secret_key:
            self._tracer = setup_tracing(
                public_key=self.config.langfuse_public_key,
                secret_key=self.config.langfuse_secret_key,
                host=self.config.langfuse_host,
            )
            logger.info("Observability initialized with LangFuse tracing")
        else:
            logger.info("Observability initialized without LangFuse (not configured)")

    def get_tracer(self) -> SentinelTracer | None:
        """Get the configured tracer."""
        return self._tracer

    def get_metrics(self) -> SentinelMetrics:
        """Get application metrics."""
        return get_metrics()

    def flush(self) -> None:
        """Flush all pending traces."""
        if self._tracer:
            self._tracer.flush()


# Convenience function
def create_observability(
    langfuse_public_key: str | None = None,
    langfuse_secret_key: str | None = None,
    log_level: str = "INFO",
) -> SentinelObservability:
    """Create and initialize observability.

    Args:
        langfuse_public_key: Langfuse public key
        langfuse_secret_key: Langfuse secret key
        log_level: Log level

    Returns:
        Initialized SentinelObservability instance
    """
    config = ObservabilityConfig(
        langfuse_public_key=langfuse_public_key,
        langfuse_secret_key=langfuse_secret_key,
        log_level=log_level,
    )
    observability = SentinelObservability(config)
    observability.initialize()
    return observability
