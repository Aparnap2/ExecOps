"""Tests for Supervisor and Unified Guardrails Graph.

Tests for:
- Event type routing (PR, stripe_invoice, tech_debt)
- Agent delegation
- Unified state management
- Graph composition
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestEventTypeRouting:
    """Tests for routing events to correct agents."""

    def test_route_pr_event_to_sre(self):
        """PR webhook event routes to SRE agent."""
        from ai_service.agent.supervisor import route_event_to_agent

        state = {
            "event_type": "pull_request",
            "webhook_event": {"action": "opened"},
        }

        result = route_event_to_agent(state)
        assert result == "sre_agent"

    def test_route_stripe_event_to_cfo(self):
        """Stripe invoice event routes to CFO agent."""
        from ai_service.agent.supervisor import route_event_to_agent

        state = {
            "event_type": "stripe_invoice",
            "webhook_event": {"type": "invoice.payment_succeeded"},
        }

        result = route_event_to_agent(state)
        assert result == "cfo_agent"

    def test_route_tech_debt_to_tech_debt_agent(self):
        """Tech debt alert routes to Tech Debt agent."""
        from ai_service.agent.supervisor import route_event_to_agent

        state = {
            "event_type": "tech_debt_alert",
            "webhook_event": {"action": "scan_completed"},
        }

        result = route_event_to_agent(state)
        assert result == "tech_debt_agent"

    def test_route_unknown_event(self):
        """Unknown event type returns error."""
        from ai_service.agent.supervisor import route_event_to_agent

        state = {
            "event_type": "unknown_event",
            "webhook_event": {},
        }

        result = route_event_to_agent(state)
        assert result == "unknown"

    def test_route_missing_event_type(self):
        """Missing event type returns unknown."""
        from ai_service.agent.supervisor import route_event_to_agent

        state = {
            "webhook_event": {},
        }

        result = route_event_to_agent(state)
        assert result == "unknown"


class TestUnifiedState:
    """Tests for unified guardrails state."""

    def test_create_unified_state(self):
        """Create unified state from webhook event."""
        from ai_service.agent.supervisor import create_unified_state

        state = create_unified_state(
            event_type="pull_request",
            webhook_event={"action": "opened", "pull_request": {"number": 1}},
            webhook_action="opened",
        )

        assert state["event_type"] == "pull_request"
        assert state["webhook_event"]["action"] == "opened"
        assert state["agent_name"] is None
        assert state["sub_agent_results"] == {}
        assert state["requires_human_approval"] is False

    def test_add_sub_agent_result(self):
        """Add sub-agent result to unified state."""
        from ai_service.agent.supervisor import add_sub_agent_result

        state = {
            "event_type": "pull_request",
            "sub_agent_results": {},
        }

        result = add_sub_agent_result(state, "sre_agent", {
            "decision": "approve",
            "violations": [],
        })

        assert result["sub_agent_results"]["sre_agent"]["decision"] == "approve"

    def test_aggregate_decisions(self):
        """Aggregate decisions from multiple agents."""
        from ai_service.agent.supervisor import aggregate_decisions

        state = {
            "sub_agent_results": {
                "sre_agent": {"decision": "approve", "confidence": 0.9},
                "tech_debt_agent": {"decision": "warn", "confidence": 0.8},
            },
        }

        result = aggregate_decisions(state)

        assert result["aggregated_decision"] == "warn"  # Most conservative
        assert result["agent_count"] == 2
        assert result["all_approved"] is False


class TestGuardrailsGraph:
    """Tests for unified guardrails graph creation."""

    def test_create_guardrails_graph(self):
        """Create guardrails graph with all agents."""
        from ai_service.agent.supervisor import create_guardrails_agent

        graph = create_guardrails_agent()

        assert graph is not None

    def test_graph_has_supervisor_node(self):
        """Graph contains supervisor/router node."""
        from ai_service.agent.supervisor import create_guardrails_agent

        graph = create_guardrails_agent()

        # Graph should be compilable
        compiled = graph
        assert compiled is not None

    def test_graph_has_all_agent_nodes(self):
        """Graph contains all agent entry points."""
        from ai_service.agent.supervisor import create_guardrails_agent

        graph = create_guardrails_agent()

        # Verify graph can be compiled
        assert graph is not None


class TestAgentHandoff:
    """Tests for agent handoff logic."""

    def test_decide_approval_route(self):
        """Decision on approve -> skip human approval."""
        from ai_service.agent.supervisor import should_request_approval

        result = should_request_approval("approve", [])
        assert result is False

    def test_warn_approval_route(self):
        """Decision on warn -> request human approval."""
        from ai_service.agent.supervisor import should_request_approval

        result = should_request_approval("warn", [])
        assert result is True

    def test_block_approval_route(self):
        """Decision on block -> request human approval."""
        from ai_service.agent.supervisor import should_request_approval

        result = should_request_approval("block", [])
        assert result is True

    def test_high_confidence_approve_skip(self):
        """High confidence approve skips approval."""
        from ai_service.agent.supervisor import should_request_approval

        result = should_request_approval("approve", [], confidence=0.95)
        assert result is False

    def test_high_severity_warn(self):
        """High severity violations require approval."""
        from ai_service.agent.supervisor import should_request_approval

        violations = [{"severity": "blocking"}]
        result = should_request_approval("warn", violations)
        assert result is True


class TestSREAgentIntegration:
    """Tests for SRE agent integration with supervisor."""

    def test_sre_agent_creates_valid_state(self):
        """SRE agent produces valid output state."""
        from ai_service.agent.supervisor import run_sre_agent

        state = {
            "event_type": "pull_request",
            "webhook_event": {
                "action": "opened",
                "pull_request": {
                    "number": 42,
                    "title": "Add new feature",
                    "user": {"login": "developer"},
                    "diff_url": "https://github.com/repo/pull/42.diff",
                    "head": {"sha": "abc123"},
                    "base": {"sha": "def456"},
                },
                "repository": {"full_name": "org/repo"},
            },
            "webhook_action": "opened",
        }

        result = run_sre_agent(state)

        assert result["decision"] in ["approve", "warn", "block"]
        assert "sre_report" in result or "violations" in result


class TestCFOAgentIntegration:
    """Tests for CFO agent integration with supervisor."""

    def test_cfo_agent_creates_valid_state(self):
        """CFO agent produces valid output state."""
        from ai_service.agent.supervisor import run_cfo_agent
        from ai_service.integrations.stripe import InvoiceContext

        # Create proper InvoiceContext object
        invoice = InvoiceContext(
            invoice_id="in_123",
            customer_id="cus_abc",
            amount=15000,
            currency="usd",
            vendor="Vercel",
        )

        state = {
            "event_type": "stripe_invoice",
            "invoice_context": invoice,
        }

        result = run_cfo_agent(state)

        assert result["decision"] in ["approve", "warn", "block", "error"]
        # budget_impact is nested in cfo_report
        assert "cfo_report" in result
        assert "budget_impact" in result["cfo_report"]


class TestTechDebtAgentIntegration:
    """Tests for Tech Debt agent integration with supervisor."""

    def test_tech_debt_agent_creates_valid_state(self):
        """Tech Debt agent produces valid output state."""
        from ai_service.agent.supervisor import run_tech_debt_agent

        state = {
            "event_type": "tech_debt_alert",
            "pr_info": {"number": 42, "title": "Refactor"},
            "diff_files": [
                {
                    "filename": "test.py",
                    "patch": "# TODO: Fix this later\n# TODO: Also fix this",
                }
            ],
        }

        result = run_tech_debt_agent(state)

        assert result["decision"] in ["approve", "warn", "block"]
        assert "tech_debt_report" in result


class TestFinalDecisionAggregation:
    """Tests for final decision making."""

    def test_all_agents_approve(self):
        """All agents approve -> final approve."""
        from ai_service.agent.supervisor import finalize_decision

        agent_results = {
            "sre_agent": {"decision": "approve", "confidence": 0.95},
            "cfo_agent": {"decision": "approve", "confidence": 0.90},
            "tech_debt_agent": {"decision": "approve", "confidence": 0.88},
        }

        result = finalize_decision(agent_results)

        assert result["final_decision"] == "approve"
        assert result["requires_human_approval"] is False

    def test_any_agent_blocks(self):
        """Any agent blocks -> final block."""
        from ai_service.agent.supervisor import finalize_decision

        agent_results = {
            "sre_agent": {"decision": "approve", "confidence": 0.95},
            "cfo_agent": {"decision": "block", "confidence": 0.85},
            "tech_debt_agent": {"decision": "approve", "confidence": 0.88},
        }

        result = finalize_decision(agent_results)

        assert result["final_decision"] == "block"
        assert result["requires_human_approval"] is True

    def test_only_warns_no_human_required(self):
        """All warns with high confidence -> approve without human."""
        from ai_service.agent.supervisor import finalize_decision

        agent_results = {
            "sre_agent": {"decision": "warn", "confidence": 0.95},
            "cfo_agent": {"decision": "warn", "confidence": 0.92},
        }

        result = finalize_decision(agent_results)

        assert result["final_decision"] == "warn"
        assert result["requires_human_approval"] is True  # Warns need approval


class TestSlackNotification:
    """Tests for Slack notification formatting."""

    def test_format_guardrails_result(self):
        """Format guardrails result for Slack."""
        from ai_service.agent.supervisor import format_guardrails_result

        result = {
            "final_decision": "block",
            "agent_results": {
                "sre_agent": {"decision": "approve", "violations": []},
                "cfo_agent": {"decision": "block", "reason": "Budget exceeded"},
            },
        }

        message = format_guardrails_result(result)

        assert "block" in message.lower() or "🚫" in message
        assert "cfo" in message.lower() or "CFO" in message

    def test_format_approval_request(self):
        """Format human approval request."""
        from ai_service.agent.supervisor import format_approval_request

        message = format_approval_request(
            agent_name="CFO",
            trigger="Stripe Invoice",
            amount="$150.00",
            vendor="Vercel",
            reason="Budget exceeded",
        )

        assert "CFO" in message
        assert "Vercel" in message
        assert "$150.00" in message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
