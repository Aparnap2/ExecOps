"""ExecOps Action Schema - Pydantic models for Action Proposals.

These schemas define the structure for:
- ActionProposal: The core ExecOps output
- ActionPayload: The executable action details
- Event Context: Input from various sources (Sentry, Stripe, GitHub)
"""

from datetime import datetime
from typing import Literal, Any
from pydantic import BaseModel, Field


# =============================================================================
# Action Types & Payloads
# =============================================================================

class ActionPayload(BaseModel):
    """Executable action payload.

    Different action types have different required fields.
    """

    # Email action
    to: str | None = None
    subject: str | None = None
    body: str | None = None
    template_vars: dict[str, Any] | None = None

    # API/Command action
    method: str | None = None  # POST, GET, etc.
    url: str | None = None
    headers: dict[str, str] | None = None
    body_json: dict[str, Any] | None = None
    command: str | None = None  # Shell command to execute

    # Slack DM action
    slack_user_id: str | None = None
    slack_channel: str | None = None
    slack_blocks: list[dict] | None = None

    # Generic webhook
    webhook_url: str | None = None

    class Config:
        extra = "allow"  # Allow additional fields for flexibility


# =============================================================================
# Action Proposal Core Model
# =============================================================================

class ActionProposalCreate(BaseModel):
    """Schema for creating an ActionProposal."""

    event_id: str | None = None
    vertical: str = Field(..., description="release | customer_fire | runway | team_pulse")
    urgency: str = Field(default="low", description="low | high | critical")
    action_type: str = Field(..., description="email | api_call | slack_dm | webhook | command")
    payload: dict[str, Any]
    reasoning: str
    context_summary: str
    source_event: dict[str, Any] | None = None


class ActionProposalResponse(BaseModel):
    """Schema for ActionProposal API response."""

    id: str
    status: str
    urgency: str
    vertical: str
    action_type: str
    payload: dict[str, Any]
    reasoning: str
    context_summary: str
    created_at: datetime
    approved_at: datetime | None
    executed_at: datetime | None


class ActionProposalUpdate(BaseModel):
    """Schema for updating an ActionProposal."""

    status: str | None = None  # approved | rejected
    approver_id: str | None = None
    rejection_reason: str | None = None


# =============================================================================
# Event Context Schemas (Input to Agents)
# =============================================================================

class SentryEventContext(BaseModel):
    """Context from Sentry error monitoring."""

    error_id: str
    error_type: str
    message: str
    project: str
    culprit: str  # File/function that caused the error
    error_count: int = 1
    users_affected: int = 0
    first_seen: datetime
    last_seen: datetime
    tags: dict[str, str] = Field(default_factory=dict)
    fingerprint: str | None = None


class GitHubPRContext(BaseModel):
    """Context from GitHub pull request."""

    pr_number: int
    title: str
    author: str
    repo: str
    action: str  # opened, synchronize, closed
    diff_url: str | None = None
    head_sha: str
    base_sha: str
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0


class StripeInvoiceContext(BaseModel):
    """Context from Stripe invoice events."""

    invoice_id: str
    customer_id: str
    customer_email: str | None = None
    amount: int  # In cents
    currency: str
    status: str  # paid, open, void, uncollectible
    vendor: str | None = None
    description: str | None = None
    due_date: datetime | None = None
    attempt_count: int = 0


class IntercomTicketContext(BaseModel):
    """Context from Intercom support tickets."""

    ticket_id: str
    customer_name: str
    customer_email: str
    customer_tier: str  # free, starter, pro, enterprise
    priority: str  # low, medium, high, urgent
    subject: str
    body: str
    tags: list[str] = Field(default_factory=list)
    open_conversations: int = 1
    satisfaction_score: float | None = None


class GitHubActivityContext(BaseModel):
    """Context from GitHub activity (for team pulse)."""

    repo: str
    author: str
    activity_type: str  # commit, pr, review, comment
    commit_count: int = 0
    pr_count: int = 0
    review_count: int = 0
    time_window_hours: int = 24
    compared_to_previous: float = 0.0  # % change


# =============================================================================
# Agent Output Schemas
# =============================================================================

class AgentAnalysisResult(BaseModel):
    """Output from agent analysis nodes."""

    vertical: str
    context: dict[str, Any]
    decision: str  # draft_action | ignore | escalate
    confidence: float
    analysis_summary: str

    # For draft_action decision
    action_type: str | None = None
    action_payload: dict[str, Any] | None = None
    reasoning: str | None = None
    urgency: str | None = None


class DraftAction(BaseModel):
    """Drafted action proposal from agent."""

    vertical: str
    action_type: str
    payload: dict[str, Any]
    reasoning: str
    urgency: str
    context_summary: str
    execution_conditions: dict[str, Any] | None = None  # e.g., {"require_approval": True}


# =============================================================================
# Vertical Definitions
# =============================================================================

EXEC_OPS_VERTICALS = {
    "release": {
        "trigger_sources": ["sentry", "github_deploy"],
        "sops": ["rollback", "postmortem", "alert_dev"],
        "default_urgency": "high",
    },
    "customer_fire": {
        "trigger_sources": ["intercom", "zendesk"],
        "sops": ["apology_email", "senior_assign", "refund"],
        "default_urgency": "critical",
    },
    "runway": {
        "trigger_sources": ["stripe", "hubspot"],
        "sops": ["card_update_email", "pause_downgrade", "renewal_reminder"],
        "default_urgency": "high",
    },
    "team_pulse": {
        "trigger_sources": ["github", "slack"],
        "sops": ["calendar_invite", "1on1_reminder", "sentiment_check"],
        "default_urgency": "low",
    },
}


def get_vertical_config(vertical: str) -> dict:
    """Get configuration for a vertical."""
    return EXEC_OPS_VERTICALS.get(vertical, {})
