"""Integration tests for observability module.

These tests verify the observability features:
1. Metrics collection and reporting
2. Tracing span creation
3. Logging configuration
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch


class TestSentinelMetrics:
    """Tests for metrics collection."""

    def test_metrics_defaults(self):
        """Metrics have correct default values."""
        from ai_service.observability import SentinelMetrics

        metrics = SentinelMetrics()

        assert metrics.prs_processed == 0
        assert metrics.prs_approved == 0
        assert metrics.prs_warned == 0
        assert metrics.prs_blocked == 0
        assert metrics.violations_found == 0
        assert metrics.avg_processing_time == 0.0

    def test_to_dict(self):
        """Metrics convert to dictionary."""
        from ai_service.observability import SentinelMetrics

        metrics = SentinelMetrics()
        metrics.prs_processed = 10
        metrics.prs_approved = 5
        metrics.prs_warned = 3
        metrics.prs_blocked = 2

        data = metrics.to_dict()

        assert data["prs_processed"] == 10
        assert data["prs_approved"] == 5
        assert data["prs_warned"] == 3
        assert data["prs_blocked"] == 2

    def test_record_pr_decision(self):
        """Recording PR decisions updates metrics."""
        from ai_service.observability import (
            SentinelMetrics,
            record_pr_decision,
            get_metrics,
        )

        # Reset metrics
        global _metrics
        import ai_service.observability

        ai_service.observability._metrics = SentinelMetrics()

        record_pr_decision("approve", 1.5)
        record_pr_decision("block", 2.0)
        record_pr_decision("warn", 1.0)

        metrics = get_metrics()
        assert metrics.prs_processed == 3
        assert metrics.prs_approved == 1
        assert metrics.prs_blocked == 1
        assert metrics.prs_warned == 1
        assert metrics.total_processing_time == 4.5
        assert metrics.avg_processing_time == 1.5

    def test_record_violations(self):
        """Recording violations updates counter."""
        from ai_service.observability import (
            SentinelMetrics,
            record_violations,
            get_metrics,
        )

        import ai_service.observability

        ai_service.observability._metrics = SentinelMetrics()

        record_violations(3)

        metrics = get_metrics()
        assert metrics.violations_found == 3

    def test_record_recommendations(self):
        """Recording recommendations updates counter."""
        from ai_service.observability import (
            SentinelMetrics,
            record_recommendations,
            get_metrics,
        )

        import ai_service.observability

        ai_service.observability._metrics = SentinelMetrics()

        record_recommendations(5)

        metrics = get_metrics()
        assert metrics.recommendations_generated == 5

    def test_record_budget_impact(self):
        """Recording budget impact updates metrics."""
        from ai_service.observability import (
            SentinelMetrics,
            record_budget_impact,
            get_metrics,
        )

        import ai_service.observability

        ai_service.observability._metrics = SentinelMetrics()

        record_budget_impact(100.0, False)
        record_budget_impact(500.0, True)

        metrics = get_metrics()
        assert metrics.total_estimated_cost == 600.0
        assert metrics.budgets_exceeded == 1


class TestSentinelTracer:
    """Tests for LangFuse tracing."""

    def test_tracer_setup_no_keys(self):
        """Tracer handles missing keys gracefully."""
        from ai_service.observability import SentinelTracer

        tracer = SentinelTracer()
        result = tracer.setup()

        assert result is False
        assert tracer.get_tracer() is None

    def test_tracer_setup_with_keys(self):
        """Tracer sets up with valid keys."""
        import ai_service.observability as obs_module

        # Reset the lazy import cache
        obs_module._LangfuseTracer = None
        obs_module._Langfuse = None

        from ai_service.observability import SentinelTracer

        # Create mock instance that will be returned when Langfuse() is called
        mock_instance = MagicMock()

        # Create a mock class that returns mock_instance when instantiated
        mock_langfuse_class = MagicMock(return_value=mock_instance)

        # Patch the lazy import function to return mock types
        with patch.object(obs_module, "_get_langfuse_types") as mock_get_types:
            mock_tracer = MagicMock()
            mock_get_types.return_value = (mock_tracer, mock_langfuse_class)

            tracer = SentinelTracer(
                public_key="pk-test",
                secret_key="sk-test",
                host="https://cloud.langfuse.com",
            )
            result = tracer.setup()

            assert result is True
            mock_langfuse_class.assert_called_once_with(
                public_key="pk-test",
                secret_key="sk-test",
                host="https://cloud.langfuse.com",
            )

    def test_create_generation_no_langfuse(self):
        """Create generation returns None when not configured."""
        from ai_service.observability import SentinelTracer

        tracer = SentinelTracer()
        generation = tracer.create_generation("test", {"input": "data"})

        assert generation is None

    def test_tracer_shutdown(self):
        """Tracer shutdown flushes traces."""
        import ai_service.observability as obs_module

        # Reset the lazy import cache
        obs_module._LangfuseTracer = None
        obs_module._Langfuse = None

        from ai_service.observability import SentinelTracer

        # Create mock instance that will be returned when Langfuse() is called
        mock_instance = MagicMock()

        # Create a mock class that returns mock_instance when instantiated
        mock_langfuse_class = MagicMock(return_value=mock_instance)

        # Patch the lazy import function to return mock types
        with patch.object(obs_module, "_get_langfuse_types") as mock_get_types:
            mock_tracer = MagicMock()
            mock_get_types.return_value = (mock_tracer, mock_langfuse_class)

            tracer = SentinelTracer(public_key="pk", secret_key="sk")
            tracer.setup()
            tracer.shutdown()

            # Verify that Langfuse was instantiated with correct args
            mock_langfuse_class.assert_called_once_with(
                public_key="pk", secret_key="sk", host="https://cloud.langfuse.com"
            )

            # Verify shutdown called flush and shutdown on the instance
            mock_instance.flush.assert_called_once()
            mock_instance.shutdown.assert_called_once()


class TestTraceSpan:
    """Tests for tracing span context manager."""

    @pytest.mark.asyncio
    async def test_trace_span_yields_output(self):
        """Trace span yields output dictionary."""
        from ai_service.observability import trace_span

        async with trace_span("test_operation", {"input": "value"}) as output:
            output["result"] = "success"

        assert output["result"] == "success"
        assert "duration_seconds" in output
        assert "completed_at" in output

    @pytest.mark.asyncio
    async def test_trace_span_records_duration(self):
        """Trace span records duration in output."""
        from ai_service.observability import trace_span
        import asyncio

        async with trace_span("slow_operation") as output:
            await asyncio.sleep(0.1)

        assert output["duration_seconds"] >= 0.1


class TestLoggingSetup:
    """Tests for logging configuration."""

    def test_setup_logging_json(self):
        """Setup logging with JSON format."""
        from ai_service.observability import setup_logging

        # Should not raise
        setup_logging(level="DEBUG", format="json")

    def test_setup_logging_text(self):
        """Setup logging with text format."""
        from ai_service.observability import setup_logging

        # Should not raise
        setup_logging(level="INFO", format="text")


class TestSentinelObservability:
    """Tests for main observability class."""

    def test_create_observability(self):
        """Create observability instance."""
        from ai_service.observability import create_observability

        obs = create_observability(log_level="DEBUG")

        assert obs is not None
        assert obs.config.log_level == "DEBUG"

    def test_observability_initialize(self):
        """Initialize observability components."""
        from ai_service.observability import SentinelObservability, ObservabilityConfig

        config = ObservabilityConfig(log_level="WARNING")
        obs = SentinelObservability(config)

        # Should not raise
        obs.initialize()

    def test_get_metrics(self):
        """Get metrics from observability."""
        from ai_service.observability import SentinelObservability, SentinelMetrics

        obs = SentinelObservability()
        metrics = obs.get_metrics()

        assert metrics is not None
        assert isinstance(metrics, SentinelMetrics)


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_get_tracer(self):
        """Get tracer returns global instance."""
        from ai_service.observability import get_tracer, SentinelTracer

        # Reset global
        import ai_service.observability

        ai_service.observability._tracer_instance = None

        tracer = get_tracer()
        assert tracer is not None
        assert isinstance(tracer, SentinelTracer)

    def test_setup_tracing(self):
        """Setup tracing configures global tracer."""
        from ai_service.observability import setup_tracing

        import ai_service.observability as obs_module

        # Reset globals
        obs_module._tracer_instance = None
        obs_module._LangfuseTracer = None
        obs_module._Langfuse = None

        # Create mock instance that will be returned when Langfuse() is called
        mock_instance = MagicMock()
        mock_tracer = MagicMock()

        # Create a mock class that returns mock_instance when instantiated
        mock_langfuse_class = MagicMock(return_value=mock_instance)

        # Patch the lazy import function
        with patch.object(obs_module, "_get_langfuse_types") as mock_get_types:
            mock_get_types.return_value = (mock_tracer, mock_langfuse_class)

            tracer = setup_tracing(
                public_key="pk-test",
                secret_key="sk-test",
                host="https://cloud.langfuse.com",
            )

            assert tracer is not None
            assert tracer.get_tracer() is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
