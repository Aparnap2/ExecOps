"""Release Hygiene Vertical Agent.

Handles Sentry error events and GitHub deploy events to maintain release quality.
Triggers: High error rates, failed deploys, rollback needs.

SOPs:
- rollback: Error rate > 2% after deploy
- postmortem: Failed deploy requiring analysis
- alert_dev: Notify engineering team
"""

import logging
from typing import TypedDict, Any

logger = logging.getLogger(__name__)


# =============================================================================
# State Definition
# =============================================================================

class ReleaseHygieneState(TypedDict):
    """State for release hygiene vertical agent."""

    # Required fields
    event_id: str
    event_type: str  # sentry.error, github.deploy
    vertical: str
    urgency: str  # low, high, critical

    # Analysis results
    status: str  # pending, pending_approval, approved, rejected, executed
    analysis: dict[str, Any] | None
    draft_action: dict[str, Any] | None
    confidence: float

    # Event context from external sources
    event_context: dict[str, Any] | None

    # Approval workflow
    approval_required: bool
    approval_decision: str | None  # approved, rejected
    approver_id: str | None
    rejection_reason: str | None

    # Error handling
    error: str | None


# =============================================================================
# Context Gathering Node
# =============================================================================

def gather_context_node(state: ReleaseHygieneState) -> ReleaseHygieneState:
    """Analyze Sentry/GitHub event context to determine if action is needed.

    Decision logic:
    - error_rate > 2% → requires_action: True, action_type: rollback
    - error_rate 1-2% → requires_action: True, action_type: alert_dev
    - error_rate < 1% → requires_action: False, action_type: monitor
    """
    context = state.get("event_context", {})
    urgency = state.get("urgency", "low")

    # Extract key metrics
    error_rate = context.get("error_rate", 0.0)
    users_affected = context.get("users_affected", 0)
    recent_deploys = context.get("recent_deploys", 0)
    project = context.get("project", "unknown")

    # Determine if action is required based on error rate thresholds
    if error_rate >= 0.02:  # 2% threshold
        requires_action = True
        action_type = "rollback"
        reasoning = (
            f"Error rate {error_rate:.1%} exceeds 2% threshold "
            f"in {project} affecting {users_affected} users"
        )
        determined_urgency = "critical" if error_rate >= 0.05 else "high"
    elif error_rate >= 0.01:  # 1% warning threshold
        requires_action = True
        action_type = "alert_dev"
        reasoning = (
            f"Elevated error rate {error_rate:.1%} detected in {project}"
        )
        determined_urgency = "medium"
    else:
        requires_action = False
        action_type = "monitor"
        reasoning = f"Error rate {error_rate:.1%} is within acceptable bounds"
        determined_urgency = "low"

    # Factor in recent deploys (deploys often introduce errors)
    if recent_deploys > 0 and requires_action:
        reasoning += f" ({recent_deploys} recent deploy(s) detected)"

    analysis = {
        "error_rate": error_rate,
        "users_affected": users_affected,
        "project": project,
        "requires_action": requires_action,
        "action_type": action_type,
        "reasoning": reasoning,
        "urgency": determined_urgency if urgency == "low" else urgency,
    }

    logger.info(
        f"Release hygiene analysis: action={requires_action}, "
        f"type={action_type}, urgency={determined_urgency}"
    )

    # Build updated state dict to avoid duplicate keyword arguments
    updated = dict(state)
    updated["analysis"] = analysis
    updated["status"] = "analyzed"
    updated["confidence"] = 0.95 if requires_action else 0.85

    return ReleaseHygieneState(**updated)


# =============================================================================
# Draft Action Node
# =============================================================================

def draft_action_node(state: ReleaseHygieneState) -> ReleaseHygieneState:
    """Generate executable action based on analysis.

    Returns action payload based on action_type:
    - rollback: git revert command
    - alert_dev: Slack DM to engineering channel
    - monitor: No immediate action, just log
    """
    analysis = state.get("analysis", {})
    action_type = analysis.get("action_type", "monitor")
    reasoning = analysis.get("reasoning", "")
    urgency = analysis.get("urgency", state.get("urgency", "low"))
    context = state.get("event_context", {})
    project = context.get("project", "unknown")

    if action_type == "rollback":
        # Generate rollback command
        draft = {
            "action_type": "command",
            "payload": {
                "command": f"git revert HEAD --no-verify",
                "working_dir": f"/deployments/{project}",
                "timeout_seconds": 60,
            },
            "reasoning": reasoning,
            "urgency": urgency,
        }
        confidence = 0.90
    elif action_type == "alert_dev":
        # Generate alert to engineering
        draft = {
            "action_type": "slack_dm",
            "payload": {
                "slack_channel": "#engineering-alerts",
                "slack_blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"Elevated Error Rate: {project}",
                        },
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{reasoning}*\n\nError rate: {context.get('error_rate', 0):.1%}",
                        },
                    },
                ],
            },
            "reasoning": reasoning,
            "urgency": urgency,
        }
        confidence = 0.88
    else:  # monitor
        draft = {
            "action_type": "log",
            "payload": {
                "log_level": "info",
                "message": f"Monitor mode: {reasoning}",
            },
            "reasoning": reasoning,
            "urgency": urgency,
        }
        confidence = 0.85

    logger.info(f"Drafted {action_type} action with confidence {confidence}")

    # Build updated state dict to avoid duplicate keyword arguments
    updated = dict(state)
    updated["draft_action"] = draft
    updated["confidence"] = confidence
    updated["status"] = "drafted"

    return ReleaseHygieneState(**updated)


# =============================================================================
# Human Approval Node
# =============================================================================

def human_approval_node(state: ReleaseHygieneState) -> ReleaseHygieneState:
    """Handle human approval workflow for release hygiene actions.

    All rollback commands require human approval by default.
    Alert_dev actions may auto-execute for urgency=medium or lower.
    """
    draft = state.get("draft_action", {})
    action_type = draft.get("action_type", "")
    urgency = draft.get("urgency", "low")

    # Rollbacks always require approval
    if action_type == "command":  # rollback is a command
        requires_approval = True
    elif action_type == "slack_dm":
        # Alerts to #engineering require approval for high/critical urgency
        requires_approval = urgency in ("high", "critical")
    else:
        requires_approval = False

    # If already decided, update status accordingly
    decision = state.get("approval_decision")
    if decision == "approved":
        status = "approved"
        ready_to_execute = True
    elif decision == "rejected":
        status = "rejected"
        ready_to_execute = False
    elif requires_approval:
        status = "pending_approval"
        ready_to_execute = False
    else:
        # Auto-approve for low-urgency alerts
        status = "approved"
        ready_to_execute = True

    logger.info(
        f"Approval check: action={action_type}, "
        f"urgency={urgency}, requires_approval={requires_approval}, "
        f"status={status}"
    )

    # Build updated state dict to avoid duplicate keyword arguments
    updated = dict(state)
    updated["status"] = status
    updated["approval_required"] = requires_approval
    updated["ready_to_execute"] = ready_to_execute

    return ReleaseHygieneState(**updated)


# =============================================================================
# Graph Factory
# =============================================================================

from langgraph.graph import StateGraph, END

def create_release_hygiene_graph() -> StateGraph:
    """Create the release hygiene agent graph.

    Flow:
        gather_context → draft_action → human_approval → END
                      ↓ (no action needed)
                         END
    """
    builder = StateGraph(ReleaseHygieneState)

    # Add nodes
    builder.add_node("gather_context", gather_context_node)
    builder.add_node("draft_action", draft_action_node)
    builder.add_node("human_approval", human_approval_node)

    # Set entry point
    builder.set_entry_point("gather_context")

    # Add edges
    builder.add_edge("gather_context", "draft_action")

    # Conditional: only proceed to approval if action is drafted
    builder.add_conditional_edges(
        "draft_action",
        lambda s: "human_approval" if s.get("draft_action") else END,
    )

    builder.add_edge("human_approval", END)

    return builder
