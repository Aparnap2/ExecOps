"""Sentinel Agent State Definition.

Extends ActionProposalState with Sentinel-specific fields for GitHub PR review.
"""

import logging
from typing import TypedDict, Any
from ai_service.graphs.vertical_agents import ActionProposalState

logger = logging.getLogger(__name__)


class SentinelState(ActionProposalState):
    """Sentinel-specific state extending ActionProposalState.

    Used for GitHub PR review with Linear context and SOP compliance checking.
    All fields are optional (total=False) to allow partial state updates.
    """

    # GitHub PR context
    pr_number: int | None
    pr_id: str | None  # GitHub node ID (e.g., "MDExOlB1bGxSb3R0MjE2MTMxMzA0")
    pr_title: str | None
    pr_body: str | None
    pr_author: str | None
    pr_url: str | None

    # Linear issue context (extracted from PR body and Neo4j)
    linear_issue_id: str | None
    linear_issue_state: str | None  # e.g., "IN_PROGRESS", "BACKLOG", "DONE"
    linear_issue_labels: list[str]

    # Graph context (from Neo4j queries)
    issue_context: dict[str, Any] | None

    # Sentinel analysis results
    risk_score: float  # 0.0 (safe) to 1.0 (high risk)
    violations: list[str]
    sentinel_decision: str | None  # "block", "warn", "pass"

    # Approval workflow
    approval_required: bool
    approval_decision: str | None  # "approved", "rejected" from interrupt resume
    approver_id: str | None
    rejection_reason: str | None

    # Execution tracking
    ready_to_execute: bool
    executed_at: str | None


def create_initial_sentinel_state(
    event_id: str,
    pr_number: int,
    pr_id: str,
    pr_title: str,
    pr_body: str,
    pr_author: str,
    pr_url: str,
    urgency: str = "medium",
) -> SentinelState:
    """Factory function to create initial SentinelState.

    Args:
        event_id: Unique event identifier
        pr_number: GitHub PR number
        pr_id: GitHub PR node ID
        pr_title: PR title
        pr_body: PR description body
        pr_author: PR author username
        pr_url: GitHub PR URL
        urgency: Urgency level (low, medium, high, critical)

    Returns:
        Initial SentinelState dict with all required fields set
    """
    return SentinelState(
        # Required identification from parent
        event_id=event_id,
        event_type="github.pr",
        vertical="sentinel",
        urgency=urgency,
        status="pending",

        # GitHub PR context
        pr_number=pr_number,
        pr_id=pr_id,
        pr_title=pr_title,
        pr_body=pr_body,
        pr_author=pr_author,
        pr_url=pr_url,

        # Linear context (to be populated by extract_linear_context)
        linear_issue_id=None,
        linear_issue_state=None,
        linear_issue_labels=[],

        # Graph context (to be populated by nodes)
        issue_context=None,

        # Analysis results
        risk_score=0.5,  # Default moderate risk
        violations=[],
        sentinel_decision=None,

        # Action proposal (inherited from ActionProposalState)
        analysis=None,
        draft_action=None,
        confidence=0.0,
        event_context=None,

        # Approval workflow
        approval_required=True,
        approval_decision=None,
        approver_id=None,
        rejection_reason=None,

        # Execution tracking
        ready_to_execute=False,
        executed_at=None,

        # Error handling
        error=None,
    )


__all__ = ["SentinelState", "create_initial_sentinel_state"]
