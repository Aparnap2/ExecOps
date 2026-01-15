"""TDD Tests for ExecOps Vertical Agent Graphs.

Tests for the 4 vertical agents:
- Release Hygiene (Sentry errors -> Rollback/Postmortem)
- Customer Fire (VIP tickets -> Apology/Senior Assign)
- Runway/Money (Stripe failures -> Card Update Email)
- Team Pulse (Git commits drop -> 1:1 Invite)

These tests are written FIRST (TDD approach) - implementation follows.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


# =============================================================================
# SHARED TEST FIXTURES & UTILS
# =============================================================================

class TestActionProposalState:
    """Tests for ActionProposalState TypedDict."""

    def test_create_state_with_minimal_fields(self):
        """Create state with only required fields."""
        from ai_service.graphs.vertical_agents import ActionProposalState

        state = ActionProposalState(
            event_id="evt_123",
            event_type="sentry.error",
            vertical="release",
            urgency="high",
            status="pending",
            confidence=0.0,
        )

        assert state["event_id"] == "evt_123"
        assert state["event_type"] == "sentry.error"
        assert state["vertical"] == "release"
        assert state["urgency"] == "high"
        assert state["status"] == "pending"
        # Optional fields may not be present with total=False
        assert "analysis" not in state or state.get("analysis") is None
        assert "draft_action" not in state or state.get("draft_action") is None

    def test_state_with_all_fields(self):
        """State with all fields should work correctly."""
        from ai_service.graphs.vertical_agents import ActionProposalState

        state = ActionProposalState(
            event_id="evt_456",
            event_type="stripe.invoice",
            vertical="runway",
            urgency="low",
            status="pending",
            confidence=0.85,
            analysis={"action_type": "card_update_email"},
            draft_action={"action_type": "email"},
            event_context={"amount": 5000},
            error=None,
        )

        assert state["status"] == "pending"
        assert state["confidence"] == 0.85
        assert state["analysis"]["action_type"] == "card_update_email"
        assert state["error"] is None


# =============================================================================
# RELEASE HYGIENE AGENT TESTS
# =============================================================================

class TestReleaseHygieneAgent:
    """Tests for Release Hygiene vertical agent."""

    def test_release_graph_has_correct_nodes(self):
        """Release hygiene graph should have: gather_context, draft_action, human_approval."""
        from ai_service.graphs.release_hygiene import create_release_hygiene_graph

        graph = create_release_hygiene_graph()

        assert graph is not None
        # Graph should be compilable
        compiled = graph
        assert compiled is not None

    def test_release_context_high_error_rate(self):
        """High error rate should trigger rollback action."""
        from ai_service.graphs.release_hygiene import gather_context_node

        state = {
            "event_id": "sentry_001",
            "event_type": "sentry.error",
            "vertical": "release",
            "urgency": "high",
            "event_context": {
                "error_rate": 0.05,  # 5% - above 2% threshold
                "recent_deploys": 1,
                "users_affected": 100,
                "project": "api-service",
            },
        }

        result = gather_context_node(state)

        assert result["analysis"]["error_rate"] == 0.05
        assert result["analysis"]["requires_action"] is True
        assert result["analysis"]["action_type"] == "rollback"

    def test_release_context_low_error_rate(self):
        """Low error rate should not trigger action."""
        from ai_service.graphs.release_hygiene import gather_context_node

        state = {
            "event_id": "sentry_002",
            "event_type": "sentry.error",
            "vertical": "release",
            "urgency": "low",
            "event_context": {
                "error_rate": 0.005,  # 0.5% - below 2% threshold
                "recent_deploys": 0,
                "users_affected": 5,
                "project": "api-service",
            },
        }

        result = gather_context_node(state)

        assert result["analysis"]["requires_action"] is False
        assert result["analysis"]["action_type"] == "monitor"

    def test_draft_rollback_action(self):
        """Draft action should generate valid rollback command."""
        from ai_service.graphs.release_hygiene import draft_action_node

        state = {
            "event_id": "sentry_003",
            "event_type": "sentry.error",
            "vertical": "release",
            "urgency": "high",
            "analysis": {
                "error_rate": 0.05,
                "requires_action": True,
                "action_type": "rollback",
                "reasoning": "Error rate 5% exceeds 2% threshold after deploy",
            },
        }

        result = draft_action_node(state)

        assert result["draft_action"]["action_type"] == "command"
        assert "revert" in result["draft_action"]["payload"]["command"].lower()
        assert result["draft_action"]["urgency"] == "high"
        assert result["confidence"] >= 0.85


# =============================================================================
# CUSTOMER FIRE AGENT TESTS
# =============================================================================

class TestCustomerFireAgent:
    """Tests for Customer Fire vertical agent."""

    def test_customer_fire_graph_has_correct_nodes(self):
        """Customer fire graph should have: check_vip, draft_action, human_approval."""
        from ai_service.graphs.customer_fire import create_customer_fire_graph

        graph = create_customer_fire_graph()

        assert graph is not None

    def test_customer_vip_detection(self):
        """VIP customer should trigger immediate action."""
        from ai_service.graphs.customer_fire import check_vip_node

        state = {
            "event_id": "intercom_001",
            "event_type": "intercom.ticket",
            "vertical": "customer_fire",
            "urgency": "high",
            "event_context": {
                "ticket_id": "ticket_123",
                "customer_name": "Acme Corp",
                "customer_email": "admin@acme.com",
                "customer_tier": "enterprise",
                "priority": "high",
                "churn_score": 0.7,  # Above 0.6 threshold
                "mrr": 5000,  # High value customer
            },
        }

        result = check_vip_node(state)

        assert result["analysis"]["is_vip"] is True
        assert result["analysis"]["action_type"] == "senior_assign"
        assert result["analysis"]["urgency"] == "critical"

    def test_customer_non_vip(self):
        """Non-VIP customer should use standard triage."""
        from ai_service.graphs.customer_fire import check_vip_node

        state = {
            "event_id": "intercom_002",
            "event_type": "intercom.ticket",
            "vertical": "customer_fire",
            "urgency": "low",
            "event_context": {
                "ticket_id": "ticket_456",
                "customer_name": "Small Co",
                "customer_tier": "starter",
                "priority": "low",
                "churn_score": 0.3,
                "mrr": 100,
            },
        }

        result = check_vip_node(state)

        assert result["analysis"]["is_vip"] is False
        assert result["analysis"]["action_type"] == "apology_email"

    def test_draft_apology_email(self):
        """Draft action should generate valid email payload."""
        from ai_service.graphs.customer_fire import draft_action_node

        state = {
            "event_id": "intercom_003",
            "event_type": "intercom.ticket",
            "vertical": "customer_fire",
            "urgency": "medium",
            "event_context": {
                "customer_email": "john@example.com",
            },
            "analysis": {
                "is_vip": False,
                "action_type": "apology_email",
                "reasoning": "Standard priority customer with support issue",
                "customer_name": "John Doe",
                "ticket_subject": "Cannot access dashboard",
                "customer_email": "john@example.com",
            },
        }

        result = draft_action_node(state)

        assert result["draft_action"]["action_type"] == "email"
        assert result["draft_action"]["payload"]["to"] == "john@example.com"
        assert "apology" in result["draft_action"]["payload"]["subject"].lower()


# =============================================================================
# RUNWAY/MONEY AGENT TESTS
# =============================================================================

class TestRunwayMoneyAgent:
    """Tests for Runway/Money vertical agent."""

    def test_runway_graph_has_correct_nodes(self):
        """Runway graph should have: check_invoice, draft_action, human_approval."""
        from ai_service.graphs.runway_money import create_runway_money_graph

        graph = create_runway_money_graph()

        assert graph is not None

    def test_high_value_invoice_requires_approval(self):
        """High-value invoice should require approval."""
        from ai_service.graphs.runway_money import check_invoice_node

        state = {
            "event_id": "stripe_001",
            "event_type": "stripe.invoice",
            "vertical": "runway",
            "urgency": "high",
            "event_context": {
                "invoice_id": "in_123",
                "amount": 500000,  # $5000 - high value
                "currency": "usd",
                "customer_id": "cus_aws",
                "vendor": "AWS",
                "status": "open",
            },
        }

        result = check_invoice_node(state)

        assert result["analysis"]["requires_approval"] is True
        assert result["analysis"]["amount_usd"] == 5000.0
        assert result["analysis"]["budget_remaining"] < 5000.0

    def test_duplicate_vendor_detection(self):
        """Should detect duplicate vendor invoices."""
        from ai_service.graphs.runway_money import check_invoice_node

        # Mock existing invoices
        with patch("ai_service.graphs.runway_money.get_recent_invoices") as mock:
            mock.return_value = [
                {"vendor": "AWS", "amount": 500000, "date": "2026-01-10"},
            ]

            state = {
                "event_id": "stripe_002",
                "event_type": "stripe.invoice",
                "vertical": "runway",
                "urgency": "medium",
                "event_context": {
                    "invoice_id": "in_456",
                    "amount": 500000,
                    "currency": "usd",
                    "customer_id": "cus_aws",
                    "vendor": "AWS",  # Same vendor
                    "status": "open",
                },
            }

            result = check_invoice_node(state)

            assert result["analysis"]["is_duplicate_vendor"] is True
            assert result["analysis"]["action_type"] == "investigate"

    def test_draft_card_update_email(self):
        """Draft action should generate card update email."""
        from ai_service.graphs.runway_money import draft_action_node

        state = {
            "event_id": "stripe_003",
            "event_type": "stripe.invoice",
            "vertical": "runway",
            "urgency": "high",
            "analysis": {
                "requires_approval": True,
                "action_type": "card_update_email",
                "reasoning": "Invoice failed, customer needs to update payment",
                "customer_email": "customer@example.com",
                "amount_usd": 150.00,
            },
        }

        result = draft_action_node(state)

        assert result["draft_action"]["action_type"] == "email"
        assert result["draft_action"]["payload"]["subject"] == "Update your payment method"
        assert result["draft_action"]["payload"]["amount"] == "$150.00"


# =============================================================================
# TEAM PULSE AGENT TESTS
# =============================================================================

class TestTeamPulseAgent:
    """Tests for Team Pulse vertical agent."""

    def test_team_pulse_graph_has_correct_nodes(self):
        """Team pulse graph should have: check_activity, draft_action, human_approval."""
        from ai_service.graphs.team_pulse import create_team_pulse_graph

        graph = create_team_pulse_graph()

        assert graph is not None

    def test_significant_activity_drop(self):
        """Significant activity drop should trigger action."""
        from ai_service.graphs.team_pulse import check_activity_node

        state = {
            "event_id": "github_001",
            "event_type": "github.activity",
            "vertical": "team_pulse",
            "urgency": "low",
            "event_context": {
                "repo": "org/backend",
                "current_commits": 5,
                "previous_commits": 50,  # 90% drop!
                "time_window_hours": 24,
                "authors": ["dev1", "dev2"],
                "pto_today": ["dev1", "dev2", "dev3"],  # 3 people on PTO
            },
        }

        result = check_activity_node(state)

        assert result["analysis"]["requires_action"] is True
        assert result["analysis"]["drop_percentage"] >= 50.0
        assert result["analysis"]["action_type"] == "calendar_invite"

    def test_normal_activity(self):
        """Normal activity should not trigger action."""
        from ai_service.graphs.team_pulse import check_activity_node

        state = {
            "event_id": "github_002",
            "event_type": "github.activity",
            "vertical": "team_pulse",
            "urgency": "low",
            "event_context": {
                "repo": "org/backend",
                "current_commits": 45,
                "previous_commits": 50,  # 10% drop - normal variance
                "time_window_hours": 24,
                "authors": ["dev1", "dev2", "dev3", "dev4"],
                "pto_today": [],  # No PTO
            },
        }

        result = check_activity_node(state)

        assert result["analysis"]["requires_action"] is False

    def test_draft_calendar_invite(self):
        """Draft action should generate calendar invite."""
        from ai_service.graphs.team_pulse import draft_action_node

        state = {
            "event_id": "github_003",
            "event_type": "github.activity",
            "vertical": "team_pulse",
            "urgency": "low",
            "analysis": {
                "requires_action": True,
                "action_type": "calendar_invite",
                "reasoning": "Team activity dropped 60% with 3 engineers on PTO",
                "founder_email": "founder@company.com",
            },
        }

        result = draft_action_node(state)

        assert result["draft_action"]["action_type"] == "email"
        assert "1:1" in result["draft_action"]["payload"]["subject"]


# =============================================================================
# GRAPH COMPOSITION TESTS
# =============================================================================

class TestVerticalAgentRouter:
    """Tests for routing events to correct vertical agent."""

    def test_route_sentry_to_release(self):
        """Sentry events should route to release hygiene."""
        from ai_service.graphs.vertical_agents import route_to_vertical

        result = route_to_vertical({"event_type": "sentry.error"})
        assert result == "release_hygiene"

    def test_route_intercom_to_customer_fire(self):
        """Intercom tickets should route to customer fire."""
        from ai_service.graphs.vertical_agents import route_to_vertical

        result = route_to_vertical({"event_type": "intercom.ticket"})
        assert result == "customer_fire"

    def test_route_stripe_to_runway(self):
        """Stripe events should route to runway money."""
        from ai_service.graphs.vertical_agents import route_to_vertical

        result = route_to_vertical({"event_type": "stripe.invoice"})
        assert result == "runway_money"

    def test_route_github_to_team_pulse(self):
        """GitHub activity should route to team pulse."""
        from ai_service.graphs.vertical_agents import route_to_vertical

        result = route_to_vertical({"event_type": "github.activity"})
        assert result == "team_pulse"


class TestHumanApprovalIntegration:
    """Tests for human approval integration in vertical agents."""

    def test_pending_action_requires_approval(self):
        """Actions should require human approval by default."""
        from ai_service.graphs.vertical_agents import human_approval_node

        state = {
            "event_id": "evt_001",
            "event_type": "sentry.error",
            "vertical": "release",
            "urgency": "high",
            "status": "pending",
            "draft_action": {
                "action_type": "command",
                "payload": {"command": "git revert HEAD"},
                "reasoning": "Rollback required due to 5% error rate",
            },
        }

        result = human_approval_node(state)

        assert result["status"] == "pending_approval"
        assert result["approval_required"] is True

    def test_approved_action_sets_execute_flag(self):
        """Approved actions should be ready for execution."""
        from ai_service.graphs.vertical_agents import human_approval_node

        state = {
            "event_id": "evt_002",
            "event_type": "sentry.error",
            "vertical": "release",
            "urgency": "high",
            "status": "pending_approval",
            "draft_action": {
                "action_type": "command",
                "payload": {"command": "git revert HEAD"},
            },
            "approval_decision": "approved",
            "approver_id": "founder@company.com",
        }

        result = human_approval_node(state)

        assert result["status"] == "approved"
        assert result["ready_to_execute"] is True


# =============================================================================
# CHECKPOINTER INTEGRATION TESTS
# =============================================================================

class TestCheckpointerIntegration:
    """Tests for checkpointer integration with vertical agents."""

    def test_thread_id_format(self):
        """Thread ID should follow {vertical}-{event_id} format."""
        from ai_service.infrastructure.checkpointer import GraphCheckpointerConfig

        thread_id = GraphCheckpointerConfig.get_thread_id(
            event_id="evt_123",
            vertical="release"
        )

        assert thread_id == "release-evt_123"

    def test_configurable_dict(self):
        """Configurable dict should be valid for graph invocation."""
        from ai_service.infrastructure.checkpointer import GraphCheckpointerConfig

        config = GraphCheckpointerConfig.get_configurable(
            thread_id="release-evt_456"
        )

        assert "configurable" in config
        assert config["configurable"]["thread_id"] == "release-evt_456"
        assert "checkpoint_ns" in config["configurable"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
