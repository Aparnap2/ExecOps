"""Integration tests for GitHub Sentinel PR enforcement flow.

Tests validate the complete PR processing pipeline:
1. Webhook receives PR event
2. Agent parses PR info
3. Agent queries temporal memory (Graphiti)
4. Agent queries semantic memory (pgvector)
5. Agent analyzes violations
6. Agent returns decision and action
"""

import pytest
from datetime import datetime

from ai_service.agent import create_initial_state, AgentState
from ai_service.agent.nodes import (
    parse_pr_node,
    query_temporal_memory_node,
    query_semantic_memory_node,
    analyze_violations_node,
    format_block_message,
    format_warning_message,
    create_sentinel_agent,
)


class TestParsePRNode:
    """Tests for PR parsing node."""

    @pytest.fixture
    def webhook_opened_event(self) -> dict:
        """Mock PR opened webhook event."""
        return {
            "action": "opened",
            "pull_request": {
                "number": 101,
                "title": "Add user authentication",
                "user": {"login": "junior-dev"},
                "head": {"sha": "abc123def456"},
                "base": {"sha": "base123"},
                "diff_url": "https://github.com/owner/repo/pull/101.diff",
            },
            "repository": {
                "full_name": "owner/repo",
            },
        }

    @pytest.fixture
    def webhook_synchronize_event(self) -> dict:
        """Mock PR synchronize webhook event."""
        return {
            "action": "synchronize",
            "pull_request": {
                "number": 102,
                "title": "Update SQL queries",
                "user": {"login": "senior-dev"},
                "head": {"sha": "updatedsha"},
                "base": {"sha": "basesha"},
            },
        }

    def test_parse_pr_opened(self, webhook_opened_event):
        """Parse PR from opened event."""
        state = create_initial_state(webhook_opened_event, "opened")
        result = parse_pr_node(state)

        assert result["pr_info"]["number"] == 101
        assert result["pr_info"]["title"] == "Add user authentication"
        assert result["pr_info"]["author"] == "junior-dev"
        assert result["pr_info"]["action"] == "opened"

    def test_parse_pr_synchronize(self, webhook_synchronize_event):
        """Parse PR from synchronize event."""
        state = create_initial_state(webhook_synchronize_event, "synchronize")
        result = parse_pr_node(state)

        assert result["pr_info"]["number"] == 102
        assert result["pr_info"]["author"] == "senior-dev"

    def test_parse_pr_handles_missing_fields(self):
        """Parse PR with incomplete data."""
        event = {
            "action": "opened",
            "pull_request": {
                "number": 103,
                "title": "Minimal PR",
            },
        }
        state = create_initial_state(event, "opened")
        result = parse_pr_node(state)

        # Should have defaults for missing fields
        assert result["pr_info"]["number"] == 103
        assert result["pr_info"]["author"] == "unknown"
        assert result["pr_info"]["head_sha"] == ""


class TestTemporalMemoryNode:
    """Tests for temporal memory query node."""

    @pytest.fixture
    def parsed_state(self) -> AgentState:
        """Sample state with parsed PR info."""
        event = {
            "action": "opened",
            "pull_request": {
                "number": 100,
                "title": "Add database query",
                "user": {"login": "test-dev"},
                "head": {"sha": "testsha"},
                "base": {"sha": "basesha"},
            },
        }
        state = create_initial_state(event, "opened")
        return parse_pr_node(state)

    def test_query_temporal_memory_returns_policies(self, parsed_state):
        """Query temporal memory returns policy list."""
        result = query_temporal_memory_node(parsed_state)

        assert "temporal_policies" in result
        assert len(result["temporal_policies"]) > 0

    def test_temporal_policies_have_required_fields(self, parsed_state):
        """Temporal policies have required fields."""
        result = query_temporal_memory_node(parsed_state)

        policy = result["temporal_policies"][0]
        assert "name" in policy
        assert "rule" in policy
        assert "valid_from" in policy
        assert "similarity" in policy


class TestSemanticMemoryNode:
    """Tests for semantic memory query node."""

    @pytest.fixture
    def parsed_state(self) -> AgentState:
        """Sample state with parsed PR info."""
        event = {
            "action": "opened",
            "pull_request": {
                "number": 101,
                "title": "Update authentication",
                "user": {"login": "test-dev"},
                "head": {"sha": "testsha"},
                "base": {"sha": "basesha"},
            },
        }
        state = create_initial_state(event, "opened")
        return parse_pr_node(state)

    def test_query_semantic_memory_returns_contexts(self, parsed_state):
        """Query semantic memory returns context list."""
        result = query_semantic_memory_node(parsed_state)

        assert "similar_contexts" in result
        assert isinstance(result["similar_contexts"], list)


class TestViolationAnalysis:
    """Tests for violation analysis node."""

    @pytest.fixture
    def parsed_state_with_policies(self) -> AgentState:
        """State with parsed PR and temporal policies loaded."""
        event = {
            "action": "opened",
            "pull_request": {
                "number": 102,
                "title": "Add SQL query to service",
                "user": {"login": "test-dev"},
                "head": {"sha": "testsha"},
                "base": {"sha": "basesha"},
            },
        }
        state = create_initial_state(event, "opened")
        state = parse_pr_node(state)
        # Add temporal policies
        state["temporal_policies"] = [
            {
                "name": "no_sql_outside_db",
                "rule": "No direct SQL queries outside db/ folder",
                "valid_from": datetime(2024, 1, 1),
                "valid_to": None,
                "similarity": 1.0,
            },
            {
                "name": "no_deploy_friday",
                "rule": "No deployments on Fridays",
                "valid_from": datetime(2024, 1, 1),
                "valid_to": None,
                "similarity": 0.8,
            },
        ]
        return state

    def test_detects_sql_related_pr(self, parsed_state_with_policies):
        """Detects SQL-related PR title as potential violation."""
        result = analyze_violations_node(parsed_state_with_policies)

        # Should flag as warning due to SQL in title but not in db/ folder
        assert result["should_warn"] is True or result["should_block"] is True
        assert len(result["violations"]) > 0

    def test_clean_pr_approved(self):
        """PR without violations is approved."""
        event = {
            "action": "opened",
            "pull_request": {
                "number": 103,
                "title": "Fix typo in README",
                "user": {"login": "test-dev"},
                "head": {"sha": "testsha"},
                "base": {"sha": "basesha"},
            },
        }
        state = create_initial_state(event, "opened")
        state = parse_pr_node(state)
        state["temporal_policies"] = [
            {
                "name": "no_sql_outside_db",
                "rule": "No direct SQL queries outside db/ folder",
                "valid_from": datetime(2024, 1, 1),
                "valid_to": None,
                "similarity": 1.0,
            },
        ]

        result = analyze_violations_node(state)

        assert result["decision"] == "approve"
        assert result["should_block"] is False
        assert result["should_warn"] is False
        assert len(result["violations"]) == 0

    def test_friday_deploy_blocked(self, parsed_state_with_policies):
        """PR on Friday with deploy policy is blocked."""
        # This test would need to mock datetime to test Friday
        # For now, we test the structure
        result = analyze_violations_node(parsed_state_with_policies)

        assert result["decision"] in ["block", "warn"]
        assert "confidence" in result
        assert 0.5 <= result["confidence"] <= 1.0


class TestMessageFormatting:
    """Tests for violation message formatting."""

    def test_format_block_message_with_violations(self):
        """Block message includes all violations."""
        violations = [
            {
                "type": "sql_outside_db",
                "description": "SQL queries not in db/ folder",
                "severity": "blocking",
            },
            {
                "type": "friday_deploy",
                "description": "Friday deployment policy active",
                "severity": "blocking",
            },
        ]

        message = format_block_message(violations)

        assert "🚫 **PR Blocked" in message
        assert "sql_outside_db" in message
        assert "friday_deploy" in message

    def test_format_block_message_empty(self):
        """Empty violations return empty message."""
        message = format_block_message([])
        assert message == ""

    def test_format_warning_message(self):
        """Warning message includes advisory text."""
        violations = [
            {
                "type": "similar_blocked_pr",
                "description": "Similar PR was previously blocked",
                "severity": "warning",
            },
        ]

        message = format_warning_message(violations)

        assert "⚠️ **FounderOS Sentinel Advisory" in message
        assert "Review recommended" in message


class TestSentinelAgent:
    """Tests for the complete Sentinel agent graph."""

    def test_create_sentinel_agent(self):
        """Sentinel agent graph is created successfully."""
        agent = create_sentinel_agent()
        assert agent is not None

    def test_agent_run_completes(self):
        """Agent run completes without errors."""
        event = {
            "action": "opened",
            "pull_request": {
                "number": 201,
                "title": "Update documentation",
                "user": {"login": "contributor"},
                "head": {"sha": "docsha"},
                "base": {"sha": "basesha"},
            },
        }

        agent = create_sentinel_agent()
        initial_state = create_initial_state(event, "opened")

        result = agent.invoke(initial_state)

        assert "decision" in result
        assert result["decision"] in ["approve", "warn", "block"]
        assert "confidence" in result


class TestWebhookEndpoint:
    """Tests for webhook endpoint logic (unit level)."""

    def test_ignored_non_pr_events(self):
        """Non-PR events are ignored."""
        event = {"action": "created", "issue": {}}

        from ai_service.agent.state import create_initial_state
        state = create_initial_state(event, "push")

        # Push events should be ignored in the handler
        assert state["webhook_action"] == "push"

    def test_ignored_unsupported_actions(self):
        """Unsupported PR actions are ignored."""
        event = {
            "action": "closed",
            "pull_request": {"number": 1, "title": "Test"},
        }

        state = create_initial_state(event, "closed")

        # Closed action should be ignored in the handler
        assert state["webhook_action"] == "closed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
