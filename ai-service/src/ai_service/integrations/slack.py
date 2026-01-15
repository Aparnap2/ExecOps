"""Slack integration for GitHub Sentinel.

This module provides:
- Slack webhook handler for events
- Message formatting for Slack blocks
- Interactive message actions (approve, block, warn)
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Decision(str, Enum):
    """PR review decision."""

    APPROVE = "approve"
    WARN = "warn"
    BLOCK = "block"


class SlackBlockType(str, Enum):
    """Slack block types."""

    SECTION = "section"
    DIVIDER = "divider"
    ACTIONS = "actions"
    CONTEXT = "context"
    HEADER = "header"


@dataclass
class PRSummary:
    """Summary of a PR for Slack notification."""

    number: int
    title: str
    author: str
    decision: Decision
    confidence: float
    violations: list[str] = None
    recommendations: list[str] = None
    budget_impact: dict = None
    url: str = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.violations is None:
            self.violations = []
        if self.recommendations is None:
            self.recommendations = []
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class SlackMessageBuilder:
    """Build Slack message blocks for PR notifications."""

    # Emojis for decisions
    DECISION_EMOJIS = {
        Decision.APPROVE: ":white_check_mark:",
        Decision.WARN: ":warning:",
        Decision.BLOCK: ":no_entry:",
    }

    # Colors for attachments (Slack legacy format)
    DECISION_COLORS = {
        Decision.APPROVE: "#36a64f",  # Green
        Decision.WARN: "#ffcc00",  # Yellow
        Decision.BLOCK: "#dc3545",  # Red
    }

    def __init__(self, pr_summary: PRSummary):
        """Initialize with PR summary.

        Args:
            pr_summary: The PR summary to format
        """
        self.pr = pr_summary
        self.blocks: list[dict[str, Any]] = []

    def _add_header(self) -> None:
        """Add header block with decision."""
        emoji = self.DECISION_EMOJIS.get(self.pr.decision, ":question:")
        text = f"{emoji} *PR Review: {self.pr.decision.upper()}*"
        self.blocks.append(
            {
                "type": SlackBlockType.HEADER.value,
                "text": {"type": "plain_text", "text": text},
            }
        )

    def _add_pr_section(self) -> None:
        """Add PR info section."""
        pr_text = (
            f"*<{self.pr.url}|PR #{self.pr.number}>* - {self.pr.title}\n"
            f"Author: {self.pr.author} | Confidence: {self.pr.confidence:.0%}"
        )
        self.blocks.append(
            {
                "type": SlackBlockType.SECTION.value,
                "text": {"type": "mrkdwn", "text": pr_text},
            }
        )

    def _add_violations_section(self) -> None:
        """Add violations section if any exist."""
        if not self.pr.violations:
            return

        violations_text = "*Violations Found:*\n" + "\n".join(
            f"• {v}" for v in self.pr.violations
        )
        self.blocks.append(
            {
                "type": SlackBlockType.SECTION.value,
                "text": {"type": "mrkdwn", "text": violations_text},
            }
        )

    def _add_recommendations_section(self) -> None:
        """Add recommendations section if any exist."""
        if not self.pr.recommendations:
            return

        recs_text = "*Recommendations:*\n" + "\n".join(
            f"• {r}" for r in self.pr.recommendations
        )
        self.blocks.append(
            {
                "type": SlackBlockType.SECTION.value,
                "text": {"type": "mrkdwn", "text": recs_text},
            }
        )

    def _add_budget_section(self) -> None:
        """Add budget impact section if applicable."""
        if not self.pr.budget_impact:
            return

        budget = self.pr.budget_impact
        est_cost = budget.get("estimated_monthly_cost", 0)
        budget_limit = budget.get("monthly_budget", 0)
        exceeds = budget.get("exceeds_budget", False)

        status = ":no_entry: Exceeds budget" if exceeds else ":white_check_mark: Within budget"
        budget_text = (
            f"*Budget Impact*\n"
            f"Estimated Cost: ${est_cost:.2f}/month\n"
            f"Budget Limit: ${budget_limit:.2f}/month\n"
            f"Status: {status}"
        )
        self.blocks.append(
            {
                "type": SlackBlockType.SECTION.value,
                "text": {"type": "mrkdwn", "text": budget_text},
            }
        )

    def _add_actions(self) -> None:
        """Add action buttons for interactive response."""
        action_values = {
            Decision.APPROVE: "approve",
            Decision.WARN: "warn",
            Decision.BLOCK: "block",
        }

        # Add buttons for all possible actions
        self.blocks.append(
            {
                "type": SlackBlockType.ACTIONS.value,
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "style": "primary",
                        "action_id": "sentinel_approve",
                        "value": str(self.pr.number),
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Request Changes"},
                        "style": "danger",
                        "action_id": "sentinel_request_changes",
                        "value": str(self.pr.number),
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View in GitHub"},
                        "url": self.pr.url,
                        "action_id": "sentinel_view",
                    },
                ],
            }
        )

    def _add_context(self) -> None:
        """Add timestamp context."""
        self.blocks.append(
            {
                "type": SlackBlockType.CONTEXT.value,
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Reviewed at {self.pr.timestamp.strftime('%Y-%m-%d %H:%M UTC')}",
                    }
                ],
            }
        )

    def _add_divider(self) -> None:
        """Add divider between sections."""
        self.blocks.append({"type": SlackBlockType.DIVIDER.value})

    def build(self) -> list[dict[str, Any]]:
        """Build the complete Slack message.

        Returns:
            List of Slack block elements
        """
        self._add_header()
        self._add_divider()
        self._add_pr_section()

        if self.pr.violations:
            self._add_divider()
            self._add_violations_section()

        if self.pr.recommendations:
            self._add_divider()
            self._add_recommendations_section()

        if self.pr.budget_impact:
            self._add_divider()
            self._add_budget_section()

        self._add_divider()
        self._add_actions()
        self._add_context()

        return self.blocks


class SlackClient:
    """HTTP client for sending Slack messages."""

    def __init__(self, webhook_url: str, timeout: float = 10.0) -> None:
        """Initialize Slack client.

        Args:
            webhook_url: Slack incoming webhook URL
            timeout: Request timeout in seconds
        """
        self.webhook_url = webhook_url
        self.timeout = timeout
        self._client: httpx.Client | None = None

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    async def send_message(
        self,
        blocks: list[dict[str, Any]],
        text: str,
        channel: str | None = None,
    ) -> bool:
        """Send a message to Slack.

        Args:
            blocks: Slack block elements
            text: Fallback text for notifications
            channel: Optional channel override

        Returns:
            True if message sent successfully
        """
        payload: dict[str, Any] = {
            "blocks": blocks,
            "text": text,
        }

        if channel:
            payload["channel"] = channel

        try:
            client = self._get_client()
            response = await client.post_async(
                self.webhook_url, json=payload
            )
            response.raise_for_status()
            logger.info("Slack message sent successfully")
            return True
        except httpx.HTTPError as e:
            logger.error(f"Failed to send Slack message: {e}")
            return False

    async def notify_pr_review(self, pr_summary: PRSummary) -> bool:
        """Send PR review notification to Slack.

        Args:
            pr_summary: The PR review summary

        Returns:
            True if notification sent successfully
        """
        builder = SlackMessageBuilder(pr_summary)
        blocks = builder.build()

        fallback_text = (
            f"PR #{pr_summary.number}: {pr_summary.decision.upper()} - "
            f"{pr_summary.title} by {pr_summary.author}"
        )

        return await self.send_message(blocks, fallback_text)

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None


class SlackWebhookHandler(BaseModel):
    """Handle incoming Slack webhook events.

    Supports:
    - URL verification challenges
    - Interactive message callbacks
    """

    signing_secret: str = Field(..., description="Slack app signing secret")
    verification_token: str | None = Field(
        default=None, description="Legacy verification token"
    )

    def verify_url(self, challenge: str) -> dict[str, str]:
        """Respond to Slack URL verification challenge.

        Args:
            challenge: The challenge string from Slack

        Returns:
            Response with challenge value
        """
        return {"challenge": challenge}

    def parse_interaction_callback(
        self, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Parse interactive message callback payload.

        Args:
            payload: The raw callback payload

        Returns:
            Parsed interaction data or None if invalid
        """
        action_id = payload.get("actions", [{}])[0].get("action_id")
        pr_number = payload.get("actions", [{}])[0].get("value")
        user_id = payload.get("user", {}).get("id")
        channel_id = payload.get("channel", {}).get("id")
        message_ts = payload.get("message", {}).get("ts")

        if not action_id or not pr_number:
            return None

        return {
            "action_id": action_id,
            "pr_number": int(pr_number),
            "user_id": user_id,
            "channel_id": channel_id,
            "message_ts": message_ts,
            "is_valid": action_id.startswith("sentinel_"),
        }

    def get_action_from_callback(self, callback_data: dict[str, Any]) -> str | None:
        """Extract the intended action from callback data.

        Args:
            callback_data: Parsed callback data

        Returns:
            Action string or None
        """
        if not callback_data.get("is_valid"):
            return None

        action_id = callback_data.get("action_id", "")
        if action_id == "sentinel_approve":
            return "approve"
        elif action_id == "sentinel_request_changes":
            return "request_changes"
        return None


# Module-level convenience functions


def format_block_message(pr_summary: PRSummary) -> list[dict[str, Any]]:
    """Format a PR review message for Slack.

    Args:
        pr_summary: The PR review summary

    Returns:
        Slack block elements
    """
    builder = SlackMessageBuilder(pr_summary)
    return builder.build()


def format_warning_message(pr_summary: PRSummary) -> list[dict[str, Any]]:
    """Format a warning message for Slack.

    Args:
        pr_summary: The PR review summary

    Returns:
        Slack block elements
    """
    # Reuse the main builder - it handles all decision types
    return format_block_message(pr_summary)


def create_slack_client(webhook_url: str) -> SlackClient:
    """Create a Slack client with the given webhook URL.

    Args:
        webhook_url: Slack incoming webhook URL

    Returns:
        Configured Slack client
    """
    return SlackClient(webhook_url)
