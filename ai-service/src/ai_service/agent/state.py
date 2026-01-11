"""LangGraph state for GitHub Sentinel agent.

This module defines the AgentState TypedDict that flows through the
Sentinel agent's decision graph.
"""

from typing import TypedDict, Literal
from datetime import datetime


class PRInfo(TypedDict):
    """Parsed PR information from webhook payload."""

    number: int
    title: str
    author: str
    action: str
    diff_url: str | None
    head_sha: str
    base_sha: str


class PolicyMatch(TypedDict):
    """A policy retrieved from temporal memory."""

    name: str
    rule: str
    valid_from: datetime
    valid_to: datetime | None
    similarity: float


class ContextMatch(TypedDict):
    """A context retrieved from semantic memory."""

    content: str
    speaker: str
    timestamp: datetime
    similarity: float


class Violation(TypedDict):
    """A policy violation found in the PR."""

    type: str
    description: str
    severity: Literal["blocking", "warning", "info"]
    line_numbers: list[int] | None


class AgentState(TypedDict):
    """State that flows through the Sentinel agent graph.

    This represents the complete context and decision state as the agent
    processes a GitHub webhook event.
    """

    # === Input ===
    webhook_event: dict  # Raw webhook payload
    webhook_action: str  # e.g., "opened", "synchronize"
    pr_info: PRInfo | None  # Parsed PR info

    # === Memory Query Results ===
    temporal_policies: list[PolicyMatch]  # From Neo4j/Graphiti
    similar_contexts: list[ContextMatch]  # From pgvector

    # === Analysis Results ===
    violations: list[Violation]
    should_block: bool
    should_warn: bool
    blocking_message: str | None
    warning_message: str | None

    # === Decision ===
    decision: Literal["block", "warn", "approve"]
    confidence: float
    reason: str

    # === Output ===
    action_taken: str | None  # What action was taken
    trace_id: str | None  # LangFuse trace ID
    timestamp: datetime  # When processing occurred


def create_initial_state(
    webhook_event: dict,
    webhook_action: str,
) -> AgentState:
    """Create initial state from a webhook event.

    Args:
        webhook_event: The raw webhook payload
        webhook_action: The action type (opened, synchronize, etc.)

    Returns:
        Initial AgentState with defaults
    """
    return AgentState(
        webhook_event=webhook_event,
        webhook_action=webhook_action,
        pr_info=None,
        temporal_policies=[],
        similar_contexts=[],
        violations=[],
        should_block=False,
        should_warn=False,
        blocking_message=None,
        warning_message=None,
        decision="approve",
        confidence=1.0,
        reason="",
        action_taken=None,
        trace_id=None,
        timestamp=datetime.utcnow(),
    )
