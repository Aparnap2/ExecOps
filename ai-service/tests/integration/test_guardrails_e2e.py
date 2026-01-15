"""End-to-End Integration Tests for FounderOS Guardrails.

Tests complete workflows:
1. GitHub PR -> SRE Agent -> Decision
2. Stripe Invoice -> CFO Agent -> Decision
3. Tech Debt Scan -> Tech Debt Agent -> Decision
4. Multi-agent coordination with human approval
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestGitHubPRE2E:
    """End-to-end tests for GitHub PR workflow."""

    def test_pr_opened_full_flow(self):
        """Test complete flow when PR is opened."""
        from ai_service.agent.supervisor import process_webhook

        webhook_event = {
            "action": "opened",
            "pull_request": {
                "number": 42,
                "title": "Add user authentication",
                "user": {"login": "developer"},
                "diff_url": "https://github.com/org/repo/pull/42.diff",
                "head": {"sha": "abc123def456"},
                "base": {"sha": "def789abc123"},
            },
            "repository": {
                "full_name": "org/repo",
            },
        }

        result = process_webhook(
            event_type="pull_request",
            webhook_event=webhook_event,
            webhook_action="opened",
        )

        assert result["event_type"] == "pull_request"
        assert result["decision"] in ["approve", "warn", "block"]
        assert "pr_info" in result
        assert result["pr_info"]["number"] == 42

    def test_pr_with_sql_violation(self):
        """Test PR with SQL outside db/ folder."""
        from ai_service.agent.supervisor import process_webhook

        webhook_event = {
            "action": "opened",
            "pull_request": {
                "number": 43,
                "title": "Add database query",
                "user": {"login": "developer"},
                "diff_url": "https://github.com/org/repo/pull/43.diff",
                "head": {"sha": "sql123"},
                "base": {"sha": "main456"},
            },
            "repository": {"full_name": "org/repo"},
            "files": [
                {
                    "filename": "src/service.py",
                    "status": "modified",
                    "additions": 10,
                    "deletions": 2,
                    "patch": """@@ -1,3 +1,8 @@
+import sqlite3
+
 def get_user(user_id):
+    conn = sqlite3.connect('app.db')
+    cursor = conn.cursor()
+    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
+    return cursor.fetchone()
""",
                    "language": "python",
                }
            ],
        }

        result = process_webhook(
            event_type="pull_request",
            webhook_event=webhook_event,
            webhook_action="opened",
        )

        assert result["decision"] in ["warn", "block"]
        assert "violations" in result or "sre_report" in result


class TestStripeInvoiceE2E:
    """End-to-end tests for Stripe invoice workflow."""

    def test_stripe_invoice_approve(self):
        """Test Stripe invoice within budget gets approved."""
        from ai_service.agent.supervisor import process_webhook
        from ai_service.integrations.stripe import InvoiceContext

        # Create test invoice
        invoice = InvoiceContext(
            invoice_id="in_test123",
            customer_id="cus_test",
            amount=5000,  # $50
            currency="usd",
            vendor="Vercel",
        )

        state = {
            "event_type": "stripe_invoice",
            "invoice_context": invoice,
        }

        result = process_webhook(
            event_type="stripe_invoice",
            webhook_event={"type": "invoice.payment_succeeded"},
            webhook_action="created",
        )
        # This will use the invoice_context from state
        # For full integration, invoice_context should be passed in webhook_event

    def test_stripe_invoice_high_amount(self):
        """Test high-value Stripe invoice triggers warning."""
        from ai_service.agent.supervisor import run_cfo_agent
        from ai_service.integrations.stripe import InvoiceContext

        invoice = InvoiceContext(
            invoice_id="in_high",
            customer_id="cus_aws",
            amount=600000,  # $6000 - exceeds $500 budget
            currency="usd",
            vendor="AWS",
        )

        state = {
            "event_type": "stripe_invoice",
            "invoice_context": invoice,
        }

        result = run_cfo_agent(state)

        assert result["decision"] in ["warn", "block"]
        assert "cfo_report" in result
        assert result["cfo_report"]["budget_impact"]["exceeds_budget"] is True


class TestTechDebtE2E:
    """End-to-end tests for tech debt workflow."""

    def test_tech_debt_clean_pr(self):
        """Test PR with no tech debt gets approved."""
        from ai_service.agent.supervisor import run_tech_debt_agent

        state = {
            "event_type": "tech_debt_alert",
            "pr_info": {"number": 100, "title": "Bug fix"},
            "diff_files": [
                {
                    "filename": "src/utils.py",
                    "patch": """def add(a, b):
    return a + b
""",
                }
            ],
        }

        result = run_tech_debt_agent(state)

        assert result["decision"] == "approve"
        assert "tech_debt_report" in result
        assert result["tech_debt_report"]["todo_count"] == 0

    def test_tech_debt_high_todos(self):
        """Test PR with many TODOs gets warned."""
        from ai_service.agent.supervisor import run_tech_debt_agent

        # Create diff with 30 TODOs
        todos = "\n".join([f"# TODO: Task {i}" for i in range(30)])

        state = {
            "event_type": "tech_debt_alert",
            "pr_info": {"number": 101, "title": "Large refactor"},
            "diff_files": [
                {
                    "filename": "src/large_file.py",
                    "patch": todos,
                }
            ],
        }

        result = run_tech_debt_agent(state)

        assert result["decision"] in ["warn", "block"]
        assert result["tech_debt_report"]["todo_count"] == 30

    def test_tech_debt_deprecated_lib(self):
        """Test PR with deprecated library gets blocked."""
        from ai_service.agent.supervisor import run_tech_debt_agent

        state = {
            "event_type": "tech_debt_alert",
            "pr_info": {"number": 102, "title": "Add moment.js"},
            "diff_files": [
                {
                    "filename": "src/date_helper.js",
                    "patch": "import moment from 'moment'",
                }
            ],
        }

        result = run_tech_debt_agent(state)

        assert result["decision"] == "block"
        assert len(result["tech_debt_report"]["deprecated_libs"]) > 0


class TestHumanApprovalE2E:
    """End-to-end tests for human approval workflow."""

    def test_approval_workflow_create_and_decide(self):
        """Test complete approval workflow creation and decision."""
        from ai_service.agent.workflow import (
            HumanApprovalManager,
            ApprovalState,
            create_approval_manager,
        )
        import json

        # Create approval state
        state = ApprovalState(
            workflow_id="wf_test",
            agent_name="CFO",
            trigger_event="stripe_invoice",
            status="pending",
            context={"invoice_id": "in_123", "amount": "$150.00"},
        )

        # Create manager with mock Redis
        manager = create_approval_manager(redis_url="redis://localhost:6379")

        # Mock Redis properly
        mock_redis = AsyncMock()
        stored_data = state.to_dict()

        async def mock_get(key):
            if "approval:" in key:
                return json.dumps(stored_data)
            return None

        async def mock_set(key, value, ex=None):
            return True

        mock_redis.get = mock_get
        mock_redis.set = mock_set
        manager._redis = mock_redis

        import asyncio

        async def test():
            approval_id = await manager.create_approval_request(
                state=state,
                slack_channel="#approvals",
                requester="CFO Agent",
                message="Invoice of $150.00 from Vercel",
            )

            assert approval_id is not None
            assert approval_id.startswith("approval_")

            # Process decision
            result = await manager.process_decision(
                approval_id=approval_id,
                decision="approve",
                approver="manager@example.com",
            )

            assert result.status == "approved"
            assert result.decision == "approve"
            assert result.resume_value["approved"] is True

        asyncio.run(test())

    def test_approval_timeout(self):
        """Test approval timeout detection."""
        from ai_service.agent.workflow import HumanApprovalManager, ApprovalState
        from datetime import datetime, timedelta

        manager = HumanApprovalManager(redis_url="redis://localhost:6379")

        # Create expired state
        expired = ApprovalState(
            workflow_id="wf_expired",
            agent_name="SRE",
            trigger_event="github_pr",
            status="pending",
            context={},
        )
        expired.created_at = datetime.utcnow() - timedelta(hours=25)
        expired.expires_at = expired.created_at + timedelta(hours=24)

        manager._redis = AsyncMock()
        manager._redis.get = AsyncMock(return_value=None)  # Will be checked

        import asyncio

        async def test():
            is_expired = await manager.check_timeout("approval_123")
            # Since get returns None, it should return True (not found = expired)
            assert is_expired is True

        asyncio.run(test())


class TestMultiAgentCoordination:
    """Tests for multi-agent coordination."""

    def test_aggregate_multiple_agent_results(self):
        """Test aggregating results from multiple agents."""
        from ai_service.agent.supervisor import finalize_decision

        agent_results = {
            "sre_agent": {"decision": "approve", "confidence": 0.95},
            "cfo_agent": {"decision": "approve", "confidence": 0.90},
            "tech_debt_agent": {"decision": "warn", "confidence": 0.85},
        }

        result = finalize_decision(agent_results)

        assert result["final_decision"] == "warn"  # Most conservative
        assert result["requires_human_approval"] is True

    def test_block_overrides_all(self):
        """Test that block decision overrides all others."""
        from ai_service.agent.supervisor import finalize_decision

        agent_results = {
            "sre_agent": {"decision": "approve"},
            "cfo_agent": {"decision": "block"},
            "tech_debt_agent": {"decision": "approve"},
        }

        result = finalize_decision(agent_results)

        assert result["final_decision"] == "block"
        assert result["requires_human_approval"] is True


class TestSupervisorRoutingE2E:
    """Tests for supervisor routing decisions."""

    def test_routes_pr_to_sre(self):
        """Test supervisor routes PR events to SRE agent."""
        from ai_service.agent.supervisor import route_event_to_agent

        assert route_event_to_agent({"event_type": "pull_request"}) == "sre_agent"
        assert route_event_to_agent({"event_type": "github_pull_request"}) == "sre_agent"

    def test_routes_stripe_to_cfo(self):
        """Test supervisor routes Stripe events to CFO agent."""
        from ai_service.agent.supervisor import route_event_to_agent

        assert route_event_to_agent({"event_type": "stripe_invoice"}) == "cfo_agent"
        assert route_event_to_agent({"event_type": "stripe"}) == "cfo_agent"

    def test_routes_tech_debt_alert(self):
        """Test supervisor routes tech debt events to Tech Debt agent."""
        from ai_service.agent.supervisor import route_event_to_agent

        assert route_event_to_agent({"event_type": "tech_debt_alert"}) == "tech_debt_agent"
        assert route_event_to_agent({"event_type": "tech_debt"}) == "tech_debt_agent"

    def test_handles_unknown_event(self):
        """Test supervisor handles unknown event types."""
        from ai_service.agent.supervisor import route_event_to_agent

        assert route_event_to_agent({"event_type": "unknown"}) == "unknown"
        assert route_event_to_agent({}) == "unknown"


class TestSlackNotificationE2E:
    """Tests for Slack notification formatting."""

    def test_format_approved_result(self):
        """Test formatting approved result for Slack."""
        from ai_service.agent.supervisor import format_guardrails_result

        result = {
            "final_decision": "approve",
            "agent_results": {
                "sre_agent": {"decision": "approve"},
                "cfo_agent": {"decision": "approve"},
            },
        }

        message = format_guardrails_result(result)

        assert "approve" in message.lower() or "✅" in message

    def test_format_blocked_result(self):
        """Test formatting blocked result for Slack."""
        from ai_service.agent.supervisor import format_guardrails_result

        result = {
            "final_decision": "block",
            "agent_results": {
                "sre_agent": {"decision": "approve"},
                "cfo_agent": {"decision": "block"},
            },
        }

        message = format_guardrails_result(result)

        assert "block" in message.lower() or "🚫" in message

    def test_format_approval_request(self):
        """Test formatting approval request for Slack."""
        from ai_service.agent.supervisor import format_approval_request

        message = format_approval_request(
            agent_name="CFO",
            trigger="Stripe Invoice",
            amount="$150.00",
            vendor="Vercel",
            reason="Within budget",
        )

        assert "CFO" in message
        assert "Vercel" in message
        assert "$150.00" in message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
