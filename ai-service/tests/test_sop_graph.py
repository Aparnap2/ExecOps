"""
Unit tests for SOP graph logic.

Tests validate the core SOP workflows:
- SOP-001 Lead Hygiene
- SOP-010 Support Triage
- SOP-015 Ops Hygiene
"""

from datetime import datetime, timedelta

import pytest

from ai_service.schemas.sop import DecisionRequest, EventPayload, EventSource
from ai_service.graphs.sop_graph import (
    SopState,
    create_sop_graph,
    validate_leads,
    analyze_support_tickets,
    check_data_quality,
    lead_hygiene_decision,
    triage_decision,
    hygiene_decision,
)


class TestLeadHygieneSOP:
    """Tests for SOP-001 Lead Hygiene."""

    @pytest.fixture
    def fresh_leads_events(self) -> list[EventPayload]:
        """Fresh leads with valid status."""
        now = datetime.utcnow()
        return [
            EventPayload(
                source=EventSource.HUBSPOT,
                occurred_at=now,
                external_id="lead_1",
                data={
                    "contact_id": "c1",
                    "email": "lead1@example.com",
                    "status": "qualified",
                    "last_contacted": now.isoformat(),
                },
            ),
            EventPayload(
                source=EventSource.HUBSPOT,
                occurred_at=now,
                external_id="lead_2",
                data={
                    "contact_id": "c2",
                    "email": "lead2@example.com",
                    "status": "contacted",
                    "last_contacted": (now - timedelta(hours=24)).isoformat(),
                },
            ),
        ]

    @pytest.fixture
    def stale_leads_events(self) -> list[EventPayload]:
        """Mix of stale and missing status leads."""
        now = datetime.utcnow()
        stale_time = now - timedelta(hours=72)
        return [
            EventPayload(
                source=EventSource.HUBSPOT,
                occurred_at=now,
                external_id="lead_1",
                data={"contact_id": "c1", "email": "stale@example.com", "status": "new"},
            ),
            EventPayload(
                source=EventSource.HUBSPOT,
                occurred_at=now,
                external_id="lead_2",
                data={"contact_id": "c2", "email": "no_status@example.com"},
            ),
            EventPayload(
                source=EventSource.HUBSPOT,
                occurred_at=now,
                external_id="lead_3",
                data={
                    "contact_id": "c3",
                    "email": "old@example.com",
                    "status": "qualified",
                    "last_contacted": stale_time.isoformat(),
                },
            ),
        ]

    def test_validate_leads_fresh(self, fresh_leads_events):
        """No stale leads detected."""
        state = SopState(
            request_id="test_1",
            objective="lead_hygiene",
            events=fresh_leads_events,
            constraints={"stale_threshold_hours": 48},
        )

        result = validate_leads(state)

        assert result["stale_leads"] == []
        assert result["data_completeness"] == 1.0

    def test_validate_leads_stale(self, stale_leads_events):
        """Stale leads detected correctly."""
        state = SopState(
            request_id="test_2",
            objective="lead_hygiene",
            events=stale_leads_events,
            constraints={"stale_threshold_hours": 48},
        )

        result = validate_leads(state)

        assert len(result["stale_leads"]) == 3
        assert result["data_completeness"] < 1.0

    def test_lead_hygiene_decision_confident(self, fresh_leads_events):
        """CONFIDENT state when no stale leads."""
        state = SopState(
            request_id="test_3",
            objective="lead_hygiene",
            events=fresh_leads_events,
            constraints={"stale_threshold_hours": 48},
            stale_leads=[],
            summary="All leads fresh",
            executed_sops=[],
            escalations=[],
        )

        result = lead_hygiene_decision(state)

        assert result["decision_state"] == "CONFIDENT"
        assert "sop_001_lead_hygiene" in result["executed_sops"]

    def test_lead_hygiene_decision_escalate(self, stale_leads_events):
        """ESCALATE state when stale leads exist."""
        state = SopState(
            request_id="test_4",
            objective="lead_hygiene",
            events=stale_leads_events,
            constraints={"stale_threshold_hours": 48},
            stale_leads=stale_leads_events,
            summary="Found stale leads",
            executed_sops=[],
            escalations=[],
        )

        result = lead_hygiene_decision(state)

        assert result["decision_state"] == "ESCALATE"
        assert len(result["escalations"]) > 0
        assert result["escalations"][0].severity == "medium"


class TestSupportTriageSOP:
    """Tests for SOP-010 Support Triage."""

    @pytest.fixture
    def normal_tickets(self) -> list[EventPayload]:
        """Non-urgent support tickets."""
        return [
            EventPayload(
                source=EventSource.SLACK,
                occurred_at=datetime.utcnow(),
                data={"content": "How do I reset my password?", "channel": "support"},
            ),
            EventPayload(
                source=EventSource.GMAIL,
                occurred_at=datetime.utcnow(),
                data={"subject": "Question about integration", "content": "Can you help with API?"},
            ),
        ]

    @pytest.fixture
    def urgent_tickets(self) -> list[EventPayload]:
        """Urgent support tickets."""
        return [
            EventPayload(
                source=EventSource.SLACK,
                occurred_at=datetime.utcnow(),
                data={"content": "URGENT: System is down, nothing works!", "channel": "support"},
            ),
            EventPayload(
                source=EventSource.SLACK,
                occurred_at=datetime.utcnow(),
                data={"content": "ASAP: Critical bug blocking production", "channel": "support"},
            ),
            EventPayload(
                source=EventSource.SLACK,
                occurred_at=datetime.utcnow(),
                data={"content": "URGENT: Data loss reported", "channel": "support"},
            ),
        ]

    def test_analyze_tickets_normal(self, normal_tickets):
        """Normal tickets have low urgency."""
        state = SopState(
            request_id="test_5",
            objective="support_triage",
            events=normal_tickets,
            constraints={},
        )

        result = analyze_support_tickets(state)

        assert result["support_tickets"] is not None
        urgent_count = sum(1 for t in result["support_tickets"] if t.get("is_urgent", False))
        assert urgent_count == 0

    def test_analyze_tickets_urgent(self, urgent_tickets):
        """Urgent tickets detected."""
        state = SopState(
            request_id="test_6",
            objective="support_triage",
            events=urgent_tickets,
            constraints={},
        )

        result = analyze_support_tickets(state)

        urgent_count = sum(1 for t in result["support_tickets"] if t.get("is_urgent", False))
        assert urgent_count == 2

    def test_triage_decision_confident(self, normal_tickets):
        """CONFIDENT when no urgent tickets."""
        state = SopState(
            request_id="test_7",
            objective="support_triage",
            events=normal_tickets,
            support_tickets=[
                {"ticket_id": "1", "urgency_score": 0, "sentiment": "neutral"},
                {"ticket_id": "2", "urgency_score": 0, "sentiment": "neutral"},
            ],
            recommendations=[],
            escalations=[],
            executed_sops=[],
        )

        result = triage_decision(state)

        assert result["decision_state"] == "CONFIDENT"

    def test_triage_decision_escalate(self, urgent_tickets):
        """ESCALATE when many urgent tickets."""
        state = SopState(
            request_id="test_8",
            objective="support_triage",
            events=urgent_tickets,
            support_tickets=[
                {"ticket_id": "1", "urgency_score": 3, "is_urgent": True},
                {"ticket_id": "2", "urgency_score": 3, "is_urgent": True},
                {"ticket_id": "3", "urgency_score": 3, "is_urgent": True},
            ],
            recommendations=[],
            escalations=[],
            executed_sops=[],
        )

        result = triage_decision(state)

        assert result["decision_state"] == "ESCALATE"
        assert result["escalations"][0].severity == "high"


class TestOpsHygieneSOP:
    """Tests for SOP-015 Ops Hygiene."""

    @pytest.fixture
    def clean_data(self) -> list[EventPayload]:
        """Data with no quality issues."""
        return [
            EventPayload(
                source=EventSource.HUBSPOT,
                occurred_at=datetime.utcnow(),
                data={"entity_type": "deal", "status": "closed", "value": 10000, "close_date": "2025-01-01"},
            ),
        ]

    @pytest.fixture
    def dirty_data(self) -> list[EventPayload]:
        """Data with quality issues."""
        return [
            EventPayload(
                source=EventSource.HUBSPOT,
                occurred_at=datetime.utcnow(),
                data={
                    "entity_type": "deal",
                    "id": "deal_1",
                    "value": 5000,
                    # Missing: status
                },
            ),
            EventPayload(
                source=EventSource.HUBSPOT,
                occurred_at=datetime.utcnow(),
                data={
                    "entity_type": "invoice",
                    "id": "inv_1",
                    # Missing: amount, status, link
                    "sync_error": "Connection timeout",
                },
            ),
        ]

    def test_check_quality_clean(self, clean_data):
        """No issues with clean data."""
        state = SopState(
            request_id="test_9",
            objective="ops_hygiene",
            events=clean_data,
            constraints={},
        )

        result = check_data_quality(state)

        assert result["data_quality_issues"] == []

    def test_check_quality_dirty(self, dirty_data):
        """Issues detected in dirty data."""
        state = SopState(
            request_id="test_10",
            objective="ops_hygiene",
            events=dirty_data,
            constraints={},
        )

        result = check_data_quality(state)

        assert len(result["data_quality_issues"]) > 0
        critical_count = sum(1 for i in result["data_quality_issues"] if i.get("severity") == "high")
        assert critical_count > 0

    def test_hygiene_decision_confident(self, clean_data):
        """CONFIDENT when no issues."""
        state = SopState(
            request_id="test_11",
            objective="ops_hygiene",
            events=clean_data,
            data_quality_issues=[],
            executed_sops=[],
            escalations=[],
        )

        result = hygiene_decision(state)

        assert result["decision_state"] == "CONFIDENT"
        assert result["processed_at"] is not None

    def test_hygiene_decision_escalate(self, dirty_data):
        """ESCALATE when critical issues."""
        state = SopState(
            request_id="test_12",
            objective="ops_hygiene",
            events=dirty_data,
            data_quality_issues=[
                {"type": "missing_field", "severity": "high"},
                {"type": "sync_error", "severity": "high"},
            ],
            executed_sops=[],
            escalations=[],
        )

        result = hygiene_decision(state)

        assert result["decision_state"] == "ESCALATE"


class TestGraphFactory:
    """Tests for graph creation."""

    def test_create_lead_hygiene_graph(self):
        """Lead hygiene graph has correct nodes."""
        graph = create_sop_graph("lead_hygiene")
        assert graph is not None

    def test_create_support_triage_graph(self):
        """Support triage graph has correct nodes."""
        graph = create_sop_graph("support_triage")
        assert graph is not None

    def test_create_ops_hygiene_graph(self):
        """Ops hygiene graph has correct nodes."""
        graph = create_sop_graph("ops_hygiene")
        assert graph is not None

    def test_create_composite_graph(self):
        """Composite graph includes all SOPs."""
        graph = create_sop_graph("all")
        assert graph is not None


class TestDecisionRequest:
    """Tests for DecisionRequest schema."""

    def test_valid_request(self):
        """Valid request creation."""
        req = DecisionRequest(
            request_id="req_123",
            objective="lead_hygiene",
            events=[
                EventPayload(
                    source=EventSource.HUBSPOT,
                    occurred_at=datetime.utcnow(),
                    data={"contact_id": "c1"},
                )
            ],
        )
        assert req.request_id == "req_123"
        assert req.objective == "lead_hygiene"
        assert len(req.events) == 1

    def test_request_with_constraints(self):
        """Request with custom constraints."""
        req = DecisionRequest(
            request_id="req_456",
            objective="support_triage",
            events=[],
            constraints={"stale_threshold_hours": 72},
        )
        assert req.constraints["stale_threshold_hours"] == 72


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
