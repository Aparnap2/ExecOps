"""Mock clients for third-party integrations (GitHub, Slack, Linear).

These mocks replicate the exact interface of real clients but return
deterministic test data. Use them for testing without external API calls.

Usage:
    from ai_service.integrations.mock_clients import MockGitHubClient, MockSlackClient, MockLinearClient

    # Use in tests
    github = MockGitHubClient()
    await github.comment_on_pr(pr_number=123, body="Test comment")

    # Swap for real clients in production
    from ai_service.integrations.github import GitHubClient
    github = GitHubClient(token=...)  # Real client
"""

import logging
from typing import Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


# =============================================================================
# Mock GitHub Client
# =============================================================================

@dataclass
class MockGitHubComment:
    """Mock GitHub PR comment."""
    id: int
    body: str
    user: str
    created_at: datetime = field(default_factory=datetime.utcnow)


class MockGitHubClient:
    """Mock GitHub API client replicating GitHubClient interface.

    Replicates the interface from ai_service.integrations.github.GitHubClient
    for testing without making actual API calls.

    Attributes:
        comments: List of posted comments
        reviews: List of created reviews
        pr_state: Current PR state (open, closed, merged)
    """

    def __init__(
        self,
        owner: str = "test-owner",
        repo: str = "test-repo",
        token: str = "mock-token",
    ) -> None:
        """Initialize mock GitHub client.

        Args:
            owner: Repository owner
            repo: Repository name
            token: Mock authentication token
        """
        self.owner = owner
        self.repo = repo
        self.token = token
        self.comments: list[MockGitHubComment] = []
        self.reviews: list[dict] = []
        self.pr_state = "open"
        self.pr_data = {}
        logger.info(f"MockGitHubClient initialized for {owner}/{repo}")

    async def comment_on_pr(
        self,
        pr_number: int,
        body: str,
        *,
        commit_id: str | None = None,
        path: str | None = None,
        line: int | None = None,
    ) -> MockGitHubComment:
        """Mock: Create a comment on a pull request.

        Replicates GitHubClient.comment_on_pr() signature.
        """
        comment = MockGitHubComment(
            id=len(self.comments) + 1,
            body=body,
            user="sentinel-bot[bot]",
        )
        self.comments.append(comment)
        logger.info(f"Mock: Commented on PR #{pr_number}: {body[:50]}...")
        return comment

    async def create_pull_request_review(
        self,
        pr_number: int,
        event: str = "COMMENT",
        body: str | None = None,
    ) -> dict[str, Any]:
        """Mock: Create a review for a pull request.

        Replicates GitHubClient.create_pull_request_review() signature.
        """
        review = {
            "id": len(self.reviews) + 1,
            "event": event,
            "body": body,
            "pr_number": pr_number,
            "created_at": datetime.utcnow().isoformat(),
        }
        self.reviews.append(review)
        logger.info(f"Mock: Created {event} review on PR #{pr_number}")
        return review

    async def get_pull_request(self, pr_number: int) -> dict[str, Any]:
        """Mock: Get a pull request by number.

        Replicates GitHubClient.get_pull_request() signature.
        """
        return {
            "number": pr_number,
            "id": 1234567 + pr_number,
            "title": f"Test PR #{pr_number}",
            "state": self.pr_state,
            "body": "",
            "user": {"login": "test-user"},
            "html_url": f"https://github.com/{self.owner}/{self.repo}/pull/{pr_number}",
        }

    async def update_pr(
        self,
        pr_number: int,
        *,
        state: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Mock: Update a pull request.

        Replicates GitHubClient.update_pr() signature.
        """
        if state:
            self.pr_state = state
        logger.info(f"Mock: Updated PR #{pr_number} state to {state}")
        return {"number": pr_number, "state": self.pr_state}

    async def get_pr_files(self, pr_number: int) -> list[dict[str, Any]]:
        """Mock: Get files changed in a PR.

        Replicates GitHubClient.get_pr_files() signature.
        """
        return [
            {"filename": "src/main.py", "status": "modified", "additions": 10, "deletions": 5},
            {"filename": "tests/test.py", "status": "added", "additions": 50, "deletions": 0},
        ]

    def reset(self) -> None:
        """Reset mock state for fresh test."""
        self.comments.clear()
        self.reviews.clear()
        self.pr_state = "open"
        logger.info("MockGitHubClient reset")


# =============================================================================
# Mock Slack Client
# =============================================================================

@dataclass
class MockSlackMessage:
    """Mock Slack message."""
    channel: str
    text: str
    blocks: list[dict]
    sent_at: datetime = field(default_factory=datetime.utcnow)


class MockSlackClient:
    """Mock Slack API client replicating SlackClient interface.

    Replicates the interface from ai_service.integrations.slack.SlackClient
    for testing without making actual API calls.

    Attributes:
        messages: List of sent messages
        blocks: List of message blocks
    """

    def __init__(self, webhook_url: str = "http://mock.slack/webhook") -> None:
        """Initialize mock Slack client.

        Args:
            webhook_url: Mock webhook URL
        """
        self.webhook_url = webhook_url
        self.messages: list[MockSlackMessage] = []
        logger.info("MockSlackClient initialized")

    async def send_message(
        self,
        blocks: list[dict[str, Any]],
        text: str,
        channel: str | None = None,
    ) -> bool:
        """Mock: Send a message to Slack.

        Replicates SlackClient.send_message() signature.
        """
        message = MockSlackMessage(
            channel=channel or "#exec-ops",
            text=text,
            blocks=blocks,
        )
        self.messages.append(message)
        logger.info(f"Mock: Sent Slack message to {message.channel}: {text[:50]}...")
        return True

    async def notify_pr_review(self, pr_summary) -> bool:
        """Mock: Send PR review notification to Slack.

        Replicates SlackClient.notify_pr_review() signature.
        """
        from ai_service.integrations.slack import SlackMessageBuilder

        builder = SlackMessageBuilder(pr_summary)
        blocks = builder.build()

        fallback_text = (
            f"PR #{pr_summary.number}: {pr_summary.decision.upper()} - "
            f"{pr_summary.title} by {pr_summary.author}"
        )

        return await self.send_message(blocks, fallback_text, channel="#exec-ops")

    def reset(self) -> None:
        """Reset mock state for fresh test."""
        self.messages.clear()
        logger.info("MockSlackClient reset")


# =============================================================================
# Mock Linear Client
# =============================================================================

@dataclass
class MockLinearIssue:
    """Mock Linear issue."""
    id: str
    title: str
    state: str
    priority: int = 0
    labels: list[str] = field(default_factory=list)
    description: str = ""


class MockLinearClient:
    """Mock Linear API client for testing.

    Replicates expected Linear API interface for Sentinel testing.

    Attributes:
        issues: Dict of issue_id -> MockLinearIssue
    """

    def __init__(self, api_key: str = "mock-api-key") -> None:
        """Initialize mock Linear client.

        Args:
            api_key: Mock API key
        """
        self.api_key = api_key
        self.issues: dict[str, MockLinearIssue] = {}
        logger.info("MockLinearClient initialized")

    async def get_issue(self, issue_id: str) -> MockLinearIssue | None:
        """Mock: Get a Linear issue by ID.

        Replicates expected LinearClient.get_issue() signature.
        """
        return self.issues.get(issue_id)

    async def create_issue(
        self,
        title: str,
        description: str = "",
        state_id: str = "backlog",
        label_ids: list[str] | None = None,
    ) -> MockLinearIssue:
        """Mock: Create a new Linear issue.

        Replicates expected LinearClient.create_issue() signature.
        """
        import uuid
        issue_id = f"{state_id.upper()}-{uuid.uuid4().hex[:4]}"

        # Generate ID like LIN-123 from state
        if state_id == "in_progress":
            issue_id = f"LIN-{len(self.issues) + 1}"

        issue = MockLinearIssue(
            id=issue_id,
            title=title,
            state=state_id.upper(),
            labels=label_ids or [],
            description=description,
        )
        self.issues[issue_id] = issue
        logger.info(f"Mock: Created Linear issue {issue_id}: {title}")
        return issue

    async def update_issue_state(self, issue_id: str, state: str) -> bool:
        """Mock: Update an issue's state.

        Replicates expected LinearClient.update_issue_state() signature.
        """
        if issue_id in self.issues:
            self.issues[issue_id].state = state.upper()
            logger.info(f"Mock: Updated issue {issue_id} state to {state}")
            return True
        return False

    def add_issue(self, issue: MockLinearIssue) -> None:
        """Add a pre-configured issue for testing."""
        self.issues[issue.id] = issue
        logger.info(f"Mock: Added issue {issue.id} for testing")

    def reset(self) -> None:
        """Reset mock state for fresh test."""
        self.issues.clear()
        logger.info("MockLinearClient reset")


# =============================================================================
# Mock Factory
# =============================================================================

class MockClientFactory:
    """Factory for creating mock clients for testing.

    Usage:
        factory = MockClientFactory()
        github = factory.create_github()
        slack = factory.create_slack()

        # Use in tests
        await github.comment_on_pr(...)

        # Reset for next test
        factory.reset_all()
    """

    def __init__(self) -> None:
        self._github: MockGitHubClient | None = None
        self._slack: MockSlackClient | None = None
        self._linear: MockLinearClient | None = None

    def create_github(
        self,
        owner: str = "test-owner",
        repo: str = "test-repo",
    ) -> MockGitHubClient:
        """Create mock GitHub client."""
        self._github = MockGitHubClient(owner=owner, repo=repo)
        return self._github

    def create_slack(self, webhook_url: str = "http://mock.slack") -> MockSlackClient:
        """Create mock Slack client."""
        self._slack = MockSlackClient(webhook_url=webhook_url)
        return self._slack

    def create_linear(self, api_key: str = "mock-key") -> MockLinearClient:
        """Create mock Linear client."""
        self._linear = MockLinearClient(api_key=api_key)
        return self._linear

    def get_github(self) -> MockGitHubClient:
        """Get existing GitHub client or create new."""
        if self._github is None:
            self._github = MockGitHubClient()
        return self._github

    def get_slack(self) -> MockSlackClient:
        """Get existing Slack client or create new."""
        if self._slack is None:
            self._slack = MockSlackClient()
        return self._slack

    def get_linear(self) -> MockLinearClient:
        """Get existing Linear client or create new."""
        if self._linear is None:
            self._linear = MockLinearClient()
        return self._linear

    def reset_all(self) -> None:
        """Reset all mock clients."""
        if self._github:
            self._github.reset()
        if self._slack:
            self._slack.reset()
        if self._linear:
            self._linear.reset()
        logger.info("All mock clients reset")


# =============================================================================
# Test Utilities
# =============================================================================

async def test_mock_clients():
    """Quick test of all mock clients."""
    print("Testing mock clients...")

    factory = MockClientFactory()

    # Test GitHub
    github = factory.create_github()
    comment = await github.comment_on_pr(pr_number=123, body="Test comment")
    print(f"GitHub comment: {comment.id} - {comment.body}")

    # Test Slack
    slack = factory.create_slack()
    sent = await slack.send_message(blocks=[], text="Test message", channel="#test")
    print(f"Slack message sent: {sent}")

    # Test Linear
    linear = factory.create_linear()
    issue = await linear.create_issue("Test Issue", state_id="in_progress")
    print(f"Linear issue: {issue.id} - {issue.title}")

    # Reset
    factory.reset_all()
    print("Mock clients test complete.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_mock_clients())
