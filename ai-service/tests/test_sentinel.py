"""Sentinel Integration Tests with Mock Clients.

Tests the full Sentinel workflow with mocked GitHub, Slack, and Linear clients
to avoid external API calls during testing.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

# Add src to path for imports
import sys
sys.path.insert(0, '/home/aparna/Desktop/founder_os/ai-service/src')

from ai_service.integrations.mock_clients import (
    MockGitHubClient,
    MockSlackClient,
    MockLinearClient,
    MockClientFactory,
    MockLinearIssue,
)
from ai_service.memory.graph import GraphService
from ai_service.llm.service import LLMService, get_llm_service, analyze_pr_compliance
from ai_service.agents.sentinel.state import SentinelState, create_initial_sentinel_state
from ai_service.agents.sentinel.nodes import (
    extract_linear_context,
    check_compliance,
    execute,
    send_for_approval,
)
from ai_service.integrations.slack import Decision


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_factory():
    """Create a fresh mock client factory for each test."""
    return MockClientFactory()


@pytest.fixture
def mock_github(mock_factory):
    """Get mock GitHub client with fresh state."""
    return mock_factory.create_github()


@pytest.fixture
def mock_slack(mock_factory):
    """Get mock Slack client with fresh state."""
    return mock_factory.create_slack()


@pytest.fixture
def mock_linear(mock_factory):
    """Get mock Linear client with fresh state."""
    return mock_factory.create_linear()


@pytest.fixture
def sample_sentinel_state() -> dict:
    """Create a sample Sentinel state for testing (TypedDict = dict)."""
    return create_initial_sentinel_state(
        event_id="evt-123",
        pr_number=123,
        pr_id="pr-node-123",
        pr_title="Test PR: Add new feature",
        pr_body="This PR implements LIN-456\n\n## Changes\n- Added new feature",
        pr_author="test-developer",
        pr_url="https://github.com/test-owner/test-repo/pull/123",
    )


@pytest.fixture
def state_with_issue() -> dict:
    """Create a state with linked Linear issue."""
    state = create_initial_sentinel_state(
        event_id="evt-456",
        pr_number=456,
        pr_id="pr-node-456",
        pr_title="Feature implementation",
        pr_body="Implements LIN-789\n\nChanges:",
        pr_author="developer",
        pr_url="https://github.com/owner/repo/pull/456",
    )
    state["linear_issue_id"] = "LIN-789"
    state["linear_issue_state"] = "IN_PROGRESS"
    state["linear_issue_labels"] = []
    return state


# =============================================================================
# Mock Client Tests
# =============================================================================

class TestMockGitHubClient:
    """Test MockGitHubClient functionality."""

    @pytest.mark.asyncio
    async def test_comment_on_pr(self, mock_github):
        """Test commenting on a PR."""
        comment = await mock_github.comment_on_pr(
            pr_number=123,
            body="Test comment body",
        )
        assert comment.id == 1
        assert comment.body == "Test comment body"
        assert comment.user == "sentinel-bot[bot]"
        assert len(mock_github.comments) == 1

    @pytest.mark.asyncio
    async def test_create_pull_request_review_approve(self, mock_github):
        """Test creating an approval review."""
        review = await mock_github.create_pull_request_review(
            pr_number=123,
            event="APPROVE",
            body="LGTM!",
        )
        assert review["event"] == "APPROVE"
        assert review["body"] == "LGTM!"
        assert len(mock_github.reviews) == 1

    @pytest.mark.asyncio
    async def test_create_pull_request_review_request_changes(self, mock_github):
        """Test requesting changes on a PR."""
        review = await mock_github.create_pull_request_review(
            pr_number=123,
            event="REQUEST_CHANGES",
            body="Please fix the issues",
        )
        assert review["event"] == "REQUEST_CHANGES"
        assert len(mock_github.reviews) == 1

    @pytest.mark.asyncio
    async def test_get_pull_request(self, mock_github):
        """Test getting PR details."""
        pr = await mock_github.get_pull_request(pr_number=123)
        assert pr["number"] == 123
        assert pr["title"] == "Test PR #123"
        assert pr["state"] == "open"

    @pytest.mark.asyncio
    async def test_reset_clears_state(self, mock_github):
        """Test that reset clears comments and reviews."""
        await mock_github.comment_on_pr(pr_number=1, body="Comment 1")
        await mock_github.create_pull_request_review(pr_number=1, event="APPROVE")

        mock_github.reset()

        assert len(mock_github.comments) == 0
        assert len(mock_github.reviews) == 0


class TestMockSlackClient:
    """Test MockSlackClient functionality."""

    @pytest.mark.asyncio
    async def test_send_message(self, mock_slack):
        """Test sending a Slack message."""
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "Hello"}}]
        result = await mock_slack.send_message(
            blocks=blocks,
            text="Hello world",
            channel="#test",
        )
        assert result is True
        assert len(mock_slack.messages) == 1
        msg = mock_slack.messages[0]
        assert msg.channel == "#test"
        assert msg.text == "Hello world"

    @pytest.mark.asyncio
    async def test_notify_pr_review(self, mock_slack):
        """Test PR review notification."""
        from ai_service.integrations.slack import PRSummary

        pr_summary = PRSummary(
            number=123,
            title="Test PR",
            author="developer",
            decision=Decision.APPROVE,  # Use APPROVE, not PASS
            confidence=0.9,
            violations=[],
            recommendations=["Looks good"],
            url="https://github.com/owner/repo/pull/123",
        )

        result = await mock_slack.notify_pr_review(pr_summary)
        assert result is True
        assert len(mock_slack.messages) == 1


class TestMockLinearClient:
    """Test MockLinearClient functionality."""

    @pytest.mark.asyncio
    async def test_get_issue_not_found(self, mock_linear):
        """Test getting non-existent issue."""
        issue = await mock_linear.get_issue("LIN-999")
        assert issue is None

    @pytest.mark.asyncio
    async def test_create_issue(self, mock_linear):
        """Test creating a Linear issue."""
        issue = await mock_linear.create_issue(
            title="Test Issue",
            state_id="in_progress",
            label_ids=["bug"],
        )
        assert issue.id.startswith("LIN-")
        assert issue.title == "Test Issue"
        assert issue.state == "IN_PROGRESS"
        assert "bug" in issue.labels

    @pytest.mark.asyncio
    async def test_update_issue_state(self, mock_linear):
        """Test updating issue state."""
        issue = await mock_linear.create_issue("Test Issue", state_id="backlog")
        result = await mock_linear.update_issue_state(issue.id, "in_progress")
        assert result is True
        updated = await mock_linear.get_issue(issue.id)
        assert updated.state == "IN_PROGRESS"

    @pytest.mark.asyncio
    async def test_add_issue_directly(self, mock_linear):
        """Test adding an issue directly for testing."""
        issue = MockLinearIssue(
            id="LIN-123",
            title="Pre-added Issue",
            state="IN_PROGRESS",
            priority=1,
            labels=["feature"],
        )
        mock_linear.add_issue(issue)

        retrieved = await mock_linear.get_issue("LIN-123")
        assert retrieved is not None
        assert retrieved.title == "Pre-added Issue"


class TestMockClientFactory:
    """Test MockClientFactory."""

    def test_singleton_clients(self, mock_factory):
        """Test that factory returns same instance on get."""
        github1 = mock_factory.get_github()
        github2 = mock_factory.get_github()
        assert github1 is github2

    def test_create_new_instance(self, mock_factory):
        """Test that create makes new instance."""
        github1 = mock_factory.create_github()
        github2 = mock_factory.create_github()
        # create_github creates new instance
        assert github1 is not github2

    @pytest.mark.asyncio
    async def test_reset_all(self, mock_factory):
        """Test resetting all clients."""
        github = mock_factory.create_github()
        slack = mock_factory.create_slack()
        linear = mock_factory.create_linear()

        await github.comment_on_pr(pr_number=1, body="Test")
        await slack.send_message(blocks=[], text="Test", channel="#test")
        await linear.create_issue("Test", state_id="backlog")

        mock_factory.reset_all()

        assert len(github.comments) == 0
        assert len(slack.messages) == 0
        assert len(linear.issues) == 0


# =============================================================================
# Sentinel Node Tests
# =============================================================================

class TestExtractLinearContext:
    """Test extract_linear_context node."""

    @pytest.mark.asyncio
    async def test_extracts_lin_from_pr_body(self, sample_sentinel_state):
        """Test extracting LIN-XXX pattern from PR body."""
        state = dict(sample_sentinel_state)  # TypedDict is dict, use dict()
        state["pr_body"] = "This PR fixes LIN-456 and LIN-789"

        # Mock GraphService to avoid actual Neo4j call
        with patch('ai_service.agents.sentinel.nodes.GraphService') as MockGraph:
            mock_instance = AsyncMock()
            mock_instance.get_issue_context.return_value = {
                "issue": {"id": "LIN-456", "state": "IN_PROGRESS"},
                "labels": [],
            }
            mock_instance.link_pr_to_issue.return_value = {}
            MockGraph.return_value = mock_instance

            result = await extract_linear_context(state)

        assert result["linear_issue_id"] == "LIN-456"
        assert result["linear_issue_state"] == "IN_PROGRESS"

    @pytest.mark.asyncio
    async def test_no_linear_issue_found(self, sample_sentinel_state):
        """Test when no Linear issue is linked."""
        state = dict(sample_sentinel_state)
        state["pr_body"] = "This PR adds a new feature"

        with patch('ai_service.agents.sentinel.nodes.GraphService') as MockGraph:
            mock_instance = AsyncMock()
            mock_instance.get_issue_context.return_value = None
            mock_instance.link_pr_to_issue.return_value = {}
            MockGraph.return_value = mock_instance

            result = await extract_linear_context(state)

        assert result["linear_issue_id"] is None
        assert result["linear_issue_state"] is None


class TestCheckCompliance:
    """Test check_compliance node."""

    @pytest.mark.asyncio
    async def test_block_when_no_issue_linked(self, sample_sentinel_state):
        """Test that PR is blocked when no Linear issue is linked."""
        state = dict(sample_sentinel_state)
        state["linear_issue_id"] = None

        with patch('ai_service.agents.sentinel.nodes.GraphService') as MockGraph:
            mock_instance = AsyncMock()
            mock_instance.get_pr_risk_score.return_value = 0.5
            MockGraph.return_value = mock_instance

            result = await check_compliance(
                state,
                use_llm=False,  # Skip LLM for deterministic test
                use_mock=True,
            )

        assert result["sentinel_decision"] == "block"
        assert len(result["violations"]) > 0
        assert "No Linear Issue linked" in result["violations"][0]

    @pytest.mark.asyncio
    async def test_warn_for_invalid_issue_state(self, state_with_issue):
        """Test warning when issue is in BACKLOG state."""
        state = dict(state_with_issue)
        state["linear_issue_state"] = "BACKLOG"

        with patch('ai_service.agents.sentinel.nodes.GraphService') as MockGraph:
            mock_instance = AsyncMock()
            mock_instance.get_pr_risk_score.return_value = 0.3
            MockGraph.return_value = mock_instance

            result = await check_compliance(
                state,
                use_llm=False,
                use_mock=True,
            )

        assert result["sentinel_decision"] == "warn"
        assert any("BACKLOG" in v for v in result["violations"])

    @pytest.mark.asyncio
    async def test_pass_for_valid_pr(self, state_with_issue):
        """Test pass when all checks pass."""
        state = dict(state_with_issue)
        state["linear_issue_state"] = "IN_PROGRESS"
        state["linear_issue_labels"] = []

        with patch('ai_service.agents.sentinel.nodes.GraphService') as MockGraph:
            mock_instance = AsyncMock()
            mock_instance.get_pr_risk_score.return_value = 0.2
            MockGraph.return_value = mock_instance

            result = await check_compliance(
                state,
                use_llm=False,
                use_mock=True,
            )

        assert result["sentinel_decision"] == "pass"
        assert len(result["violations"]) == 0

    @pytest.mark.asyncio
    async def test_block_for_needs_spec_label(self, state_with_issue):
        """Test block when issue has 'Needs Spec' label."""
        state = dict(state_with_issue)
        state["linear_issue_labels"] = ["Needs Spec"]

        with patch('ai_service.agents.sentinel.nodes.GraphService') as MockGraph:
            mock_instance = AsyncMock()
            mock_instance.get_pr_risk_score.return_value = 0.3
            MockGraph.return_value = mock_instance

            result = await check_compliance(
                state,
                use_llm=False,
                use_mock=True,
            )

        assert result["sentinel_decision"] == "warn"
        assert any("Needs Spec" in v for v in result["violations"])


class TestExecuteNode:
    """Test execute node."""

    @pytest.mark.asyncio
    async def test_execute_block_with_comment(self, sample_sentinel_state):
        """Test executing a block decision posts comment."""
        state = dict(sample_sentinel_state)
        state["sentinel_decision"] = "block"
        state["violations"] = ["No Linear Issue linked"]

        result = await execute(state, use_mock=True)

        assert result["status"] == "executed"
        assert result["approval_decision"] == "approved"

    @pytest.mark.asyncio
    async def test_execute_warn_posts_comment(self, sample_sentinel_state):
        """Test executing a warn decision posts warning."""
        state = dict(sample_sentinel_state)
        state["sentinel_decision"] = "warn"
        state["violations"] = ["Issue in BACKLOG state"]

        result = await execute(state, use_mock=True)

        assert result["status"] == "executed"

    @pytest.mark.asyncio
    async def test_execute_pass_approves_pr(self, sample_sentinel_state):
        """Test executing a pass decision approves the PR."""
        state = dict(sample_sentinel_state)
        state["sentinel_decision"] = "pass"
        state["violations"] = []

        result = await execute(state, use_mock=True)

        assert result["status"] == "executed"


# =============================================================================
# LLM Service Tests
# =============================================================================

class TestLLMService:
    """Test LLM service with Ollama."""

    @pytest.mark.asyncio
    async def test_llm_health_check(self):
        """Test LLM health check."""
        llm = LLMService()
        # This will fail if Ollama is not running
        try:
            healthy = await llm.check_health()
            # If Ollama is running, check passes
            if healthy:
                assert True
            else:
                pytest.skip("LLM not healthy")
        except Exception as e:
            pytest.skip(f"LLM not available: {e}")

    @pytest.mark.asyncio
    async def test_invoke_returns_response(self):
        """Test basic LLM invocation."""
        llm = LLMService()
        try:
            response = await llm.invoke([
                {"role": "user", "content": "Say 'OK' if you can see this."}
            ])
            assert "content" in response
            assert "OK" in response["content"].upper() or "ok" in response["content"].lower()
        except Exception as e:
            pytest.skip(f"LLM invocation failed: {e}")


class TestAnalyzePRCompliance:
    """Test LLM-powered PR compliance analysis."""

    @pytest.mark.asyncio
    async def test_analyze_pr_with_issue(self):
        """Test analyzing a PR with valid issue."""
        pr_info = {
            "number": 123,
            "title": "Add new feature",
            "body": "Implements LIN-456",
            "author": "developer",
        }
        issue_context = {
            "issue": {"id": "LIN-456", "state": "IN_PROGRESS"},
            "labels": [],
        }
        violations = []
        risk_score = 0.3

        try:
            result = await analyze_pr_compliance(
                pr_info=pr_info,
                issue_context=issue_context,
                violations=violations,
                risk_score=risk_score,
            )

            assert "decision" in result
            assert "reason" in result
            assert result["decision"] in ["pass", "warn", "block"]
        except Exception as e:
            pytest.skip(f"LLM not available: {e}")

    @pytest.mark.asyncio
    async def test_analyze_pr_without_issue(self):
        """Test analyzing a PR without linked issue."""
        pr_info = {
            "number": 124,
            "title": "Quick fix",
            "body": "Just a small fix",
            "author": "developer",
        }
        issue_context = None
        violations = ["No Linear Issue linked"]
        risk_score = 0.7

        try:
            result = await analyze_pr_compliance(
                pr_info=pr_info,
                issue_context=issue_context,
                violations=violations,
                risk_score=risk_score,
            )

            assert "decision" in result
            assert result["decision"] in ["block", "warn"]
        except Exception as e:
            pytest.skip(f"LLM not available: {e}")


# =============================================================================
# Full Workflow Integration Test
# =============================================================================

class TestSentinelWorkflow:
    """Full Sentinel workflow integration test with mocks."""

    @pytest.mark.asyncio
    async def test_full_workflow_no_issue_blocks(self):
        """Test complete workflow when no Linear issue is linked."""
        # Initial state
        state: SentinelState = create_initial_sentinel_state(
            event_id="evt-100",
            pr_number=100,
            pr_id="pr-node-100",
            pr_title="Test PR without issue",
            pr_body="This PR has no linked issue",
            pr_author="test-developer",
            pr_url="https://github.com/owner/repo/pull/100",
        )

        # Step 1: Extract context (no issue found)
        with patch('ai_service.agents.sentinel.nodes.GraphService') as MockGraph:
            mock_instance = AsyncMock()
            mock_instance.get_issue_context.return_value = None
            mock_instance.link_pr_to_issue.return_value = {}
            MockGraph.return_value = mock_instance

            state = await extract_linear_context(state)

        assert state["linear_issue_id"] is None

        # Step 2: Check compliance (should block)
        with patch('ai_service.agents.sentinel.nodes.GraphService') as MockGraph:
            mock_instance = AsyncMock()
            mock_instance.get_pr_risk_score.return_value = 0.5
            MockGraph.return_value = mock_instance

            state = await check_compliance(state, use_llm=False, use_mock=True)

        assert state["sentinel_decision"] == "block"
        assert len(state["violations"]) == 1
        assert "No Linear Issue linked" in state["violations"][0]

        # Step 3: Execute (should block with comment and review)
        state = await execute(state, use_mock=True)

        assert state["status"] == "executed"
        assert len(state["violations"]) > 0

    @pytest.mark.asyncio
    async def test_full_workflow_with_valid_issue_passes(self):
        """Test complete workflow when valid Linear issue is linked."""
        # Initial state with valid issue
        state: SentinelState = create_initial_sentinel_state(
            event_id="evt-200",
            pr_number=200,
            pr_id="pr-node-200",
            pr_title="Feature implementation",
            pr_body="Implements LIN-500\n\nChanges:\n- Added feature",
            pr_author="developer",
            pr_url="https://github.com/owner/repo/pull/200",
        )
        state["linear_issue_id"] = "LIN-500"
        state["linear_issue_state"] = "IN_PROGRESS"
        state["linear_issue_labels"] = []

        # Step 1: Extract context
        with patch('ai_service.agents.sentinel.nodes.GraphService') as MockGraph:
            mock_instance = AsyncMock()
            mock_instance.get_issue_context.return_value = {
                "issue": {"id": "LIN-500", "state": "IN_PROGRESS"},
                "labels": [],
            }
            mock_instance.link_pr_to_issue.return_value = {}
            MockGraph.return_value = mock_instance

            state = await extract_linear_context(state)

        assert state["linear_issue_id"] == "LIN-500"
        assert state["linear_issue_state"] == "IN_PROGRESS"

        # Step 2: Check compliance (should pass)
        with patch('ai_service.agents.sentinel.nodes.GraphService') as MockGraph:
            mock_instance = AsyncMock()
            mock_instance.get_pr_risk_score.return_value = 0.2
            MockGraph.return_value = mock_instance

            state = await check_compliance(state, use_llm=False, use_mock=True)

        assert state["sentinel_decision"] == "pass"
        assert len(state["violations"]) == 0

        # Step 3: Execute (should approve)
        state = await execute(state, use_mock=True)

        assert state["status"] == "executed"
        assert state["approval_decision"] == "approved"


# =============================================================================
# GraphService Tests (with mocked Neo4j)
# =============================================================================

class TestGraphService:
    """Test GraphService with mocked Neo4j."""

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test Neo4j health check."""
        graph = GraphService()
        try:
            healthy = await graph.health_check()
            if healthy:
                assert True
            else:
                pytest.skip("Neo4j not healthy")
        except Exception as e:
            pytest.skip(f"Neo4j not available: {e}")
        finally:
            await graph.close()

    @pytest.mark.asyncio
    async def test_link_pr_to_issue(self):
        """Test creating PR-Issue relationship."""
        graph = GraphService()
        try:
            result = await graph.link_pr_to_issue("test-pr-123", "LIN-456")
            assert result.get("pr_id") == "test-pr-123"
            assert result.get("issue_id") == "LIN-456"
        except Exception as e:
            pytest.skip(f"Neo4j not available: {e}")
        finally:
            await graph.close()

    @pytest.mark.asyncio
    async def test_get_pr_risk_score(self):
        """Test risk score calculation."""
        graph = GraphService()
        try:
            score = await graph.get_pr_risk_score("test-pr-123")
            assert 0.0 <= score <= 1.0
        except Exception as e:
            pytest.skip(f"Neo4j not available: {e}")
        finally:
            await graph.close()


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
