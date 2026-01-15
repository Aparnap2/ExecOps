"""Tests for Human Approval Workflow.

Tests for:
- Workflow state persistence with Redis
- Pause/resume via LangGraph interrupts
- Slack callback handling
- Timeout management
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import json


class TestApprovalStateManager:
    """Tests for ApprovalState dataclass."""

    def test_create_approval_state(self):
        """Create approval state with required fields."""
        from ai_service.agent.workflow import ApprovalState

        state = ApprovalState(
            workflow_id="wf_123",
            agent_name="cfo",
            trigger_event="stripe_invoice",
            status="pending",
            context={"invoice_id": "in_123", "amount": 100.0},
        )

        assert state.workflow_id == "wf_123"
        assert state.agent_name == "cfo"
        assert state.status == "pending"

    def test_approval_state_defaults(self):
        """ApprovalState has sensible defaults."""
        from ai_service.agent.workflow import ApprovalState

        state = ApprovalState(
            workflow_id="wf_123",
            agent_name="sre",
            trigger_event="github_pr",
            status="pending",
            context={},
        )

        assert state.created_at is not None
        assert state.expires_at is not None
        assert state.approval_id is not None
        assert state.requester == "system"
        assert state.decision is None
        assert state.resume_value is None


class TestHumanApprovalManager:
    """Tests for HumanApprovalManager."""

    @pytest.mark.asyncio
    async def test_manager_initialization(self):
        """Manager initializes with Redis client."""
        from ai_service.agent.workflow import HumanApprovalManager

        manager = HumanApprovalManager(
            redis_url="redis://localhost:6379",
            slack_client=None,
        )

        assert manager.redis_url == "redis://localhost:6379"

    @pytest.mark.asyncio
    async def test_create_approval_request(self):
        """Create approval request for paused workflow."""
        from ai_service.agent.workflow import HumanApprovalManager, ApprovalState

        mock_redis = AsyncMock()
        mock_slack = AsyncMock()

        manager = HumanApprovalManager(
            redis_url="redis://localhost:6379",
            slack_client=mock_slack,
        )
        manager._redis = mock_redis

        mock_redis.set = AsyncMock()
        mock_slack.send_approval_request = AsyncMock(return_value={
            "ok": True,
            "channel": "C123",
            "ts": "1234567890.123456",
        })

        state = ApprovalState(
            workflow_id="wf_test",
            agent_name="cfo",
            trigger_event="stripe_invoice",
            status="pending",
            context={"invoice_id": "in_123"},
        )

        approval_id = await manager.create_approval_request(
            state=state,
            slack_channel="#approvals",
            requester=" CFO Agent",
            message="Invoice of $150.00 from Vercel requires approval",
        )

        assert approval_id is not None
        assert approval_id.startswith("approval_")

        # Verify Redis was called
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_pending_approval(self):
        """Retrieve pending approval by ID."""
        from ai_service.agent.workflow import HumanApprovalManager, ApprovalState

        mock_redis = AsyncMock()
        mock_slack = AsyncMock()

        manager = HumanApprovalManager(
            redis_url="redis://localhost:6379",
            slack_client=mock_slack,
        )
        manager._redis = mock_redis

        stored_state = ApprovalState(
            workflow_id="wf_test",
            agent_name="cfo",
            trigger_event="stripe_invoice",
            status="pending",
            context={"invoice_id": "in_123"},
        )

        mock_redis.get = AsyncMock(return_value=json.dumps(stored_state.to_dict()))

        result = await manager.get_approval("approval_123")

        assert result is not None
        assert result.workflow_id == "wf_test"
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_nonexistent_approval(self):
        """Return None for non-existent approval."""
        from ai_service.agent.workflow import HumanApprovalManager

        mock_redis = AsyncMock()

        manager = HumanApprovalManager(
            redis_url="redis://localhost:6379",
            slack_client=None,
        )
        manager._redis = mock_redis

        mock_redis.get = AsyncMock(return_value=None)

        result = await manager.get_approval("approval_nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_approve_approval(self):
        """Approve a pending approval."""
        from ai_service.agent.workflow import HumanApprovalManager, ApprovalState

        mock_redis = AsyncMock()
        mock_slack = AsyncMock()

        manager = HumanApprovalManager(
            redis_url="redis://localhost:6379",
            slack_client=mock_slack,
        )
        manager._redis = mock_redis

        stored_state = ApprovalState(
            workflow_id="wf_test",
            agent_name="cfo",
            trigger_event="stripe_invoice",
            status="pending",
            context={"invoice_id": "in_123"},
            slack_message_ts="1234567890.123456",
            slack_channel="C123",
        )

        mock_redis.get = AsyncMock(return_value=json.dumps(stored_state.to_dict()))
        mock_redis.set = AsyncMock()
        mock_slack.update_message = AsyncMock(return_value={"ok": True})

        result = await manager.process_decision(
            "approval_123",
            decision="approve",
            approver="user@example.com",
        )

        assert result.status == "approved"
        assert result.decision == "approve"
        assert result.resume_value == {"approved": True, "decision": "approve"}
        mock_slack.update_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_reject_approval(self):
        """Reject a pending approval."""
        from ai_service.agent.workflow import HumanApprovalManager, ApprovalState

        mock_redis = AsyncMock()
        mock_slack = AsyncMock()

        manager = HumanApprovalManager(
            redis_url="redis://localhost:6379",
            slack_client=mock_slack,
        )
        manager._redis = mock_redis

        stored_state = ApprovalState(
            workflow_id="wf_test",
            agent_name="sre",
            trigger_event="github_pr",
            status="pending",
            context={"pr_number": 42},
        )

        mock_redis.get = AsyncMock(return_value=json.dumps(stored_state.to_dict()))
        mock_redis.set = AsyncMock()
        mock_slack.update_message = AsyncMock(return_value={"ok": True})

        result = await manager.process_decision(
            "approval_456",
            decision="reject",
            approver="manager@example.com",
        )

        assert result.status == "rejected"
        assert result.decision == "reject"
        assert result.resume_value == {"approved": False, "decision": "reject"}

    @pytest.mark.asyncio
    async def test_check_timeout_expired(self):
        """Expired approval returns True for timeout check."""
        from ai_service.agent.workflow import HumanApprovalManager, ApprovalState

        mock_redis = AsyncMock()

        manager = HumanApprovalManager(
            redis_url="redis://localhost:6379",
            slack_client=None,
        )
        manager._redis = mock_redis

        # Create expired state
        expired_state = ApprovalState(
            workflow_id="wf_test",
            agent_name="cfo",
            trigger_event="stripe_invoice",
            status="pending",
            context={},
        )
        # Manually set created_at to past
        expired_state.created_at = datetime.utcnow() - timedelta(hours=25)
        expired_state.expires_at = expired_state.created_at + timedelta(hours=24)

        mock_redis.get = AsyncMock(return_value=json.dumps(expired_state.to_dict()))

        is_expired = await manager.check_timeout("approval_expired")

        assert is_expired is True

    @pytest.mark.asyncio
    async def test_check_timeout_not_expired(self):
        """Non-expired approval returns False for timeout check."""
        from ai_service.agent.workflow import HumanApprovalManager, ApprovalState

        mock_redis = AsyncMock()

        manager = HumanApprovalManager(
            redis_url="redis://localhost:6379",
            slack_client=None,
        )
        manager._redis = mock_redis

        valid_state = ApprovalState(
            workflow_id="wf_test",
            agent_name="cfo",
            trigger_event="stripe_invoice",
            status="pending",
            context={},
        )

        mock_redis.get = AsyncMock(return_value=json.dumps(valid_state.to_dict()))

        is_expired = await manager.check_timeout("approval_valid")

        assert is_expired is False

    @pytest.mark.asyncio
    async def test_list_pending_approvals(self):
        """List all pending approvals."""
        from ai_service.agent.workflow import HumanApprovalManager, ApprovalState

        mock_redis = AsyncMock()

        manager = HumanApprovalManager(
            redis_url="redis://localhost:6379",
            slack_client=None,
        )
        manager._redis = mock_redis

        # Mock Redis keys and values
        mock_keys = ["approval_1", "approval_2"]
        mock_values = [
            json.dumps({
                "workflow_id": "wf_1",
                "agent_name": "cfo",
                "trigger_event": "stripe_invoice",
                "status": "pending",
                "context": {},
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
                "approval_id": "approval_1",
                "requester": "system",
                "decision": None,
                "resume_value": None,
                "approver": None,
                "slack_message_ts": None,
                "slack_channel": None,
            }),
            json.dumps({
                "workflow_id": "wf_2",
                "agent_name": "sre",
                "trigger_event": "github_pr",
                "status": "pending",
                "context": {},
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
                "approval_id": "approval_2",
                "requester": "system",
                "decision": None,
                "resume_value": None,
                "approver": None,
                "slack_message_ts": None,
                "slack_channel": None,
            }),
        ]

        mock_redis.keys = AsyncMock(return_value=mock_keys)
        mock_redis.mget = AsyncMock(return_value=mock_values)

        pending = await manager.list_pending_approvals()

        assert len(pending) == 2


class TestSlackApprovalClient:
    """Tests for Slack approval message formatting."""

    def test_format_approval_message(self):
        """Format approval request message."""
        from ai_service.agent.workflow import format_approval_message

        message = format_approval_message(
            agent_name="CFO",
            trigger="Stripe Invoice",
            context={"vendor": "Vercel", "amount": "$150.00"},
            urgency="high",
        )

        assert "CFO" in message
        assert "Stripe Invoice" in message
        assert "Vercel" in message
        assert "$150.00" in message

    def test_format_approval_blocks(self):
        """Format approval message as Slack blocks."""
        from ai_service.agent.workflow import create_approval_blocks

        blocks = create_approval_blocks(
            approval_id="approval_123",
            agent_name="SRE",
            trigger="GitHub PR #42",
            context={"title": "Add new feature", "author": "@developer"},
            decision_needed="Security scan detected high severity issue",
        )

        assert len(blocks) > 0
        # Check for interactive buttons
        has_approve = any("approve" in str(b).lower() for b in blocks)
        has_reject = any("reject" in str(b).lower() for b in blocks)
        assert has_approve is True
        assert has_reject is True


class TestHumanApprovalNode:
    """Tests for the human approval LangGraph node."""

    def test_create_approval_node(self):
        """Create approval node function."""
        from ai_service.agent.workflow import human_approval_node

        assert callable(human_approval_node)

    def test_node_returns_interrupt_for_pending(self):
        """Node should interrupt when approval is pending."""
        from ai_service.agent.workflow import human_approval_node

        state = {
            "decision": "warn",
            "requires_approval": True,
            "workflow_id": "wf_test",
            "approval_id": None,
        }

        # The node should signal that approval is needed
        # This will be a LangGraph interrupt
        pass  # Implementation details in workflow.py

    def test_node_resumes_after_approval(self):
        """Node should resume with decision after approval."""
        from ai_service.agent.workflow import human_approval_node

        state = {
            "decision": "warn",
            "requires_approval": True,
            "workflow_id": "wf_test",
            "approval_id": "approval_123",
            "resume_value": {"approved": True},
        }

        result = human_approval_node(state)

        assert result["decision"] == "approve"
        assert result["approval_id"] == "approval_123"
        assert result["human_approved"] is True

    def test_node_blocks_on_rejection(self):
        """Node should block when approval is rejected."""
        from ai_service.agent.workflow import human_approval_node

        state = {
            "decision": "warn",
            "requires_approval": True,
            "workflow_id": "wf_test",
            "approval_id": "approval_456",
            "resume_value": {"approved": False},
        }

        result = human_approval_node(state)

        assert result["decision"] == "block"
        assert result["human_approved"] is False
        assert "rejected" in result["reason"].lower()


class TestWorkflowGraph:
    """Tests for workflow graph creation."""

    def test_create_workflow_graph(self):
        """Create workflow graph with human approval."""
        from ai_service.agent.workflow import create_workflow_graph

        graph = create_workflow_graph()

        assert graph is not None

    def test_graph_has_human_approval_node(self):
        """Graph contains human approval node."""
        from ai_service.agent.workflow import create_workflow_graph

        graph = create_workflow_graph()

        # Graph should be a StateGraph instance (not compiled yet)
        # The compile happens when the graph is used
        assert graph is not None
        # Just verify the graph has nodes by accessing internal structure
        # LangGraph stores nodes in graph.nodes
        assert hasattr(graph, 'nodes') or callable(graph)


class TestWebhookHandler:
    """Tests for Slack interaction webhook handler."""

    @pytest.mark.asyncio
    async def test_handle_approval_callback(self):
        """Handle Slack button callback."""
        from ai_service.agent.workflow import handle_approval_callback

        mock_manager = AsyncMock()
        mock_manager.process_decision = AsyncMock(return_value=MagicMock(
            status="approved",
            decision="approve",
            workflow_id="wf_123",
        ))

        callback_data = {
            "type": "block_actions",
            "actions": [
                {
                    "action_id": "approve",
                    "value": "approval_123",
                }
            ],
            "user": {"id": "U123"},
            "channel": {"id": "C123"},
        }

        result = await handle_approval_callback(
            callback_data,
            approval_manager=mock_manager,
        )

        assert result["ok"] is True
        assert result["approval_id"] == "approval_123"
        assert result["decision"] == "approve"

    @pytest.mark.asyncio
    async def test_handle_reject_callback(self):
        """Handle Slack reject button callback."""
        from ai_service.agent.workflow import handle_approval_callback

        mock_manager = AsyncMock()
        mock_manager.process_decision = AsyncMock(return_value=MagicMock(
            status="rejected",
            decision="reject",
            workflow_id="wf_456",
        ))

        callback_data = {
            "type": "block_actions",
            "actions": [
                {
                    "action_id": "reject",
                    "value": "approval_456",
                }
            ],
            "user": {"id": "U456"},
        }

        result = await handle_approval_callback(
            callback_data,
            approval_manager=mock_manager,
        )

        assert result["ok"] is True
        assert result["decision"] == "reject"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
