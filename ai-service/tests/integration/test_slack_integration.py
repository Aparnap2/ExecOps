"""Integration tests for Slack integration.

These tests verify the Slack integration can:
1. Format PR review messages
2. Handle webhook events
3. Parse interactive callbacks
4. Send notifications
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


class TestSlackMessageBuilder:
    """Tests for Slack message formatting."""

    def test_builds_approve_message(self):
        """Formats an approved PR message."""
        from ai_service.integrations.slack import (
            SlackMessageBuilder,
            PRSummary,
            Decision,
        )

        pr = PRSummary(
            number=123,
            title="Add new feature",
            author="developer",
            decision=Decision.APPROVE,
            confidence=0.95,
            url="https://github.com/owner/repo/pull/123",
        )

        builder = SlackMessageBuilder(pr)
        blocks = builder.build()

        assert len(blocks) > 0
        # Check for header
        header = blocks[0]
        assert header["type"] == "header"
        assert "APPROVE" in header["text"]["text"]

    def test_builds_block_message(self):
        """Formats a blocked PR message with violations."""
        from ai_service.integrations.slack import (
            SlackMessageBuilder,
            PRSummary,
            Decision,
        )

        pr = PRSummary(
            number=456,
            title="Add SQL injection",
            author="junior_dev",
            decision=Decision.BLOCK,
            confidence=0.98,
            violations=["SQL injection vulnerability in user query"],
            recommendations=["Use parameterized queries instead"],
            url="https://github.com/owner/repo/pull/456",
        )

        builder = SlackMessageBuilder(pr)
        blocks = builder.build()

        # Find violations section
        violations_found = False
        for block in blocks:
            if block["type"] == "section":
                text = block["text"]["text"]
                if "SQL injection" in text:
                    violations_found = True
                    break

        assert violations_found

    def test_builds_warn_message(self):
        """Formats a warning PR message."""
        from ai_service.integrations.slack import (
            SlackMessageBuilder,
            PRSummary,
            Decision,
        )

        pr = PRSummary(
            number=789,
            title="Update dependencies",
            author="maintainer",
            decision=Decision.WARN,
            confidence=0.75,
            recommendations=["Consider updating major versions in separate PR"],
            url="https://github.com/owner/repo/pull/789",
        )

        builder = SlackMessageBuilder(pr)
        blocks = builder.build()

        # Check for warning emoji in header
        header = blocks[0]
        assert ":warning:" in header["text"]["text"]

    def test_builds_budget_impact_section(self):
        """Includes budget impact in message."""
        from ai_service.integrations.slack import (
            SlackMessageBuilder,
            PRSummary,
            Decision,
        )

        pr = PRSummary(
            number=101,
            title="Add expensive service",
            author="architect",
            decision=Decision.WARN,
            confidence=0.85,
            budget_impact={
                "estimated_monthly_cost": 450.0,
                "monthly_budget": 500.0,
                "exceeds_budget": False,
            },
            url="https://github.com/owner/repo/pull/101",
        )

        builder = SlackMessageBuilder(pr)
        blocks = builder.build()

        # Find budget section
        budget_found = False
        for block in blocks:
            if block["type"] == "section":
                text = block["text"]["text"]
                if "Budget Impact" in text and "$450" in text:
                    budget_found = True
                    break

        assert budget_found

    def test_includes_action_buttons(self):
        """Message includes interactive action buttons."""
        from ai_service.integrations.slack import (
            SlackMessageBuilder,
            PRSummary,
            Decision,
        )

        pr = PRSummary(
            number=202,
            title="Fix bug",
            author="developer",
            decision=Decision.APPROVE,
            confidence=0.95,
            url="https://github.com/owner/repo/pull/202",
        )

        builder = SlackMessageBuilder(pr)
        blocks = builder.build()

        # Find actions block
        actions_block = None
        for block in blocks:
            if block["type"] == "actions":
                actions_block = block
                break

        assert actions_block is not None
        assert len(actions_block["elements"]) == 3

        # Check button types
        button_texts = [e["text"]["text"] for e in actions_block["elements"]]
        assert "Approve" in button_texts
        assert "Request Changes" in button_texts
        assert "View in GitHub" in button_texts

    def test_empty_violations_no_section(self):
        """No violations section when none exist."""
        from ai_service.integrations.slack import (
            SlackMessageBuilder,
            PRSummary,
            Decision,
        )

        pr = PRSummary(
            number=303,
            title="Clean fix",
            author="developer",
            decision=Decision.APPROVE,
            confidence=1.0,
            violations=[],
            recommendations=[],
            url="https://github.com/owner/repo/pull/303",
        )

        builder = SlackMessageBuilder(pr)
        blocks = builder.build()

        # Check no violations section
        for block in blocks:
            if block["type"] == "section":
                text = block["text"]["text"]
                assert "Violations" not in text


class TestSlackWebhookHandler:
    """Tests for Slack webhook handling."""

    def test_verifies_url_challenge(self):
        """Responds to URL verification challenge."""
        from ai_service.integrations.slack import SlackWebhookHandler

        handler = SlackWebhookHandler(signing_secret="test-secret")

        response = handler.verify_url("test-challenge-token")

        assert response["challenge"] == "test-challenge-token"

    def test_parses_interactive_callback(self):
        """Parses interactive message callback."""
        from ai_service.integrations.slack import SlackWebhookHandler

        handler = SlackWebhookHandler(signing_secret="test-secret")

        payload = {
            "actions": [{"action_id": "sentinel_approve", "value": "123"}],
            "user": {"id": "U12345"},
            "channel": {"id": "C67890"},
            "message": {"ts": "1234567890.123456"},
        }

        result = handler.parse_interaction_callback(payload)

        assert result is not None
        assert result["action_id"] == "sentinel_approve"
        assert result["pr_number"] == 123
        assert result["user_id"] == "U12345"
        assert result["is_valid"] is True

    def test_rejects_invalid_callback(self):
        """Rejects callbacks without sentinel action_id."""
        from ai_service.integrations.slack import SlackWebhookHandler

        handler = SlackWebhookHandler(signing_secret="test-secret")

        payload = {
            "actions": [{"action_id": "other_action", "value": "123"}],
            "user": {"id": "U12345"},
        }

        result = handler.parse_interaction_callback(payload)

        assert result is None or result.get("is_valid") is False

    def test_get_action_from_callback(self):
        """Extracts action from valid callback."""
        from ai_service.integrations.slack import SlackWebhookHandler

        handler = SlackWebhookHandler(signing_secret="test-secret")

        callback = {
            "action_id": "sentinel_approve",
            "pr_number": 123,
            "is_valid": True,
        }

        action = handler.get_action_from_callback(callback)

        assert action == "approve"

    def test_get_request_changes_action(self):
        """Extracts request_changes action."""
        from ai_service.integrations.slack import SlackWebhookHandler

        handler = SlackWebhookHandler(signing_secret="test-secret")

        callback = {
            "action_id": "sentinel_request_changes",
            "pr_number": 456,
            "is_valid": True,
        }

        action = handler.get_action_from_callback(callback)

        assert action == "request_changes"

    def test_returns_none_for_invalid_callback(self):
        """Returns None for invalid callback data."""
        from ai_service.integrations.slack import SlackWebhookHandler

        handler = SlackWebhookHandler(signing_secret="test-secret")

        callback = {"is_valid": False}

        action = handler.get_action_from_callback(callback)

        assert action is None


class TestSlackClient:
    """Tests for Slack HTTP client."""

    @pytest.mark.asyncio
    async def test_sends_notification(self):
        """Sends PR notification to Slack."""
        from ai_service.integrations.slack import SlackClient, PRSummary, Decision

        with patch("httpx.Client") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_client.post_async.return_value = mock_response
            mock_client_class.return_value = mock_client

            client = SlackClient(webhook_url="https://hooks.slack.com/test")
            pr = PRSummary(
                number=999,
                title="Test PR",
                author="tester",
                decision=Decision.APPROVE,
                confidence=1.0,
            )

            result = await client.notify_pr_review(pr)

            assert result is True
            mock_client.post_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_send_error(self):
        """Handles HTTP errors gracefully."""
        from ai_service.integrations.slack import SlackClient, PRSummary, Decision
        import httpx

        with patch("httpx.Client") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock(
                side_effect=httpx.HTTPError("Network error")
            )
            mock_client.post_async.return_value = mock_response
            mock_client_class.return_value = mock_client

            client = SlackClient(webhook_url="https://hooks.slack.com/test")
            pr = PRSummary(
                number=888,
                title="Test PR",
                author="tester",
                decision=Decision.APPROVE,
                confidence=1.0,
            )

            result = await client.notify_pr_review(pr)

            assert result is False


class TestPRSummary:
    """Tests for PRSummary dataclass."""

    def test_default_values(self):
        """PRSummary sets defaults correctly."""
        from ai_service.integrations.slack import PRSummary, Decision

        pr = PRSummary(
            number=100,
            title="Test",
            author="dev",
            decision=Decision.APPROVE,
            confidence=0.9,
        )

        assert pr.violations == []
        assert pr.recommendations == []
        assert pr.budget_impact is None
        assert pr.url is None
        assert pr.timestamp is not None

    def test_with_all_fields(self):
        """PRSummary with all optional fields."""
        from ai_service.integrations.slack import PRSummary, Decision
        from datetime import timezone

        ts = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        pr = PRSummary(
            number=555,
            title="Full PR",
            author="developer",
            decision=Decision.BLOCK,
            confidence=0.99,
            violations=["Critical bug"],
            recommendations=["Fix the bug"],
            budget_impact={"cost": 100},
            url="https://github.com/repo/pull/555",
            timestamp=ts,
        )

        assert pr.violations == ["Critical bug"]
        assert pr.recommendations == ["Fix the bug"]
        assert pr.budget_impact == {"cost": 100}
        assert pr.url == "https://github.com/repo/pull/555"
        assert pr.timestamp == ts


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_format_block_message(self):
        """format_block_message returns blocks."""
        from ai_service.integrations.slack import (
            format_block_message,
            PRSummary,
            Decision,
        )

        pr = PRSummary(
            number=777,
            title="Test",
            author="dev",
            decision=Decision.APPROVE,
            confidence=1.0,
        )

        blocks = format_block_message(pr)

        assert isinstance(blocks, list)
        assert len(blocks) > 0

    def test_create_slack_client(self):
        """create_slack_client returns configured client."""
        from ai_service.integrations.slack import create_slack_client

        client = create_slack_client(webhook_url="https://hooks.slack.com/test")

        assert client.webhook_url == "https://hooks.slack.com/test"
        assert client.timeout == 10.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
