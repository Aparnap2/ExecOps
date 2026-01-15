"""Team Pulse Vertical Agent.

Monitors GitHub activity patterns to detect team health issues.
Triggers: Significant commit drops, PR review bottlenecks, author burnout signals.

SOPs:
- calendar_invite: Schedule 1:1 with team lead
- 1on1_reminder: Remind about upcoming 1:1s
- sentiment_check: Check team morale via survey
"""

import logging
from typing import TypedDict, Any

logger = logging.getLogger(__name__)


# =============================================================================
# State Definition
# =============================================================================

class TeamPulseState(TypedDict):
    """State for team pulse vertical agent."""

    # Required fields
    event_id: str
    event_type: str  # github.activity
    vertical: str
    urgency: str  # low, high, critical

    # Analysis results
    status: str
    analysis: dict[str, Any] | None
    draft_action: dict[str, Any] | None
    confidence: float

    # Event context
    event_context: dict[str, Any] | None

    # Approval workflow
    approval_required: bool
    approval_decision: str | None
    approver_id: str | None
    rejection_reason: str | None

    # Error handling
    error: str | None


# =============================================================================
# Activity Analysis Node
# =============================================================================

def check_activity_node(state: TeamPulseState) -> TeamPulseState:
    """Analyze GitHub activity to detect team health issues.

    Decision logic:
    - commit_drop > 50% + PTO > 50% team → calendar_invite (burnout risk)
    - commit_drop > 30% + no PTO → sentiment_check
    - commit_drop 10-30% → 1on1_reminder
    - commit_drop < 10% → no action (normal variance)
    """
    context = state.get("event_context", {})
    urgency = state.get("urgency", "low")

    # Extract activity metrics
    repo = context.get("repo", "unknown")
    current_commits = context.get("current_commits", 0)
    previous_commits = context.get("previous_commits", 0)
    time_window_hours = context.get("time_window_hours", 24)
    authors = context.get("authors", [])
    pto_today = context.get("pto_today", [])

    # Calculate drop percentage
    if previous_commits > 0:
        drop_percentage = ((previous_commits - current_commits) / previous_commits) * 100
    else:
        drop_percentage = 0.0

    # Calculate team availability
    team_size = len(set(authors + pto_today))
    pto_percentage = (len(pto_today) / team_size * 100) if team_size > 0 else 0

    # Determine action based on drop percentage and PTO
    if drop_percentage >= 50 and pto_percentage >= 50:
        # High drop + high PTO = burnout risk
        action_type = "calendar_invite"
        determined_urgency = "high"
        reasoning = (
            f"Team activity dropped {drop_percentage:.0f}% in {repo}. "
            f"{len(pto_today)}/{team_size} team members on PTO. "
            f"Schedule 1:1 to check on team health."
        )
    elif drop_percentage >= 50:
        # Significant drop without PTO explanation
        action_type = "sentiment_check"
        determined_urgency = "medium"
        reasoning = (
            f"Team activity dropped {drop_percentage:.0f}% in {repo}. "
            f"No significant PTO. Check team sentiment."
        )
    elif drop_percentage >= 30:
        # Mild drop - worth noting but no action needed
        action_type = "1on1_reminder"
        determined_urgency = "low"
        reasoning = (
            f"Team activity down {drop_percentage:.0f}% in {repo}. "
            f"Normal variance, but worth discussing in upcoming 1:1s."
        )
    else:
        # Normal variance - no action
        action_type = "no_action"
        determined_urgency = "low"
        reasoning = (
            f"Activity change ({drop_percentage:.0f}%) within normal variance"
        )

    analysis = {
        "repo": repo,
        "current_commits": current_commits,
        "previous_commits": previous_commits,
        "drop_percentage": drop_percentage,
        "team_size": team_size,
        "pto_today": pto_today,
        "pto_percentage": pto_percentage,
        "requires_action": action_type != "no_action",
        "action_type": action_type,
        "reasoning": reasoning,
        "urgency": determined_urgency if urgency == "low" else urgency,
        "founder_email": "founder@company.com",  # Would come from config
    }

    logger.info(
        f"Team pulse analysis: drop={drop_percentage:.0f}%, "
        f"action={action_type}, urgency={determined_urgency}"
    )

    # Build updated state dict to avoid duplicate keyword arguments
    updated = dict(state)
    updated["analysis"] = analysis
    updated["status"] = "analyzed"
    updated["confidence"] = 0.90 if drop_percentage >= 50 else 0.82

    return TeamPulseState(**updated)


# =============================================================================
# Draft Action Node
# =============================================================================

def draft_action_node(state: TeamPulseState) -> TeamPulseState:
    """Generate executable action based on activity analysis.

    Actions:
    - calendar_invite: Create calendar invite for 1:1
    - sentiment_check: Create survey request
    - 1on1_reminder: Create Slack reminder
    """
    analysis = state.get("analysis", {})
    action_type = analysis.get("action_type", "no_action")
    reasoning = analysis.get("reasoning", "")
    urgency = analysis.get("urgency", state.get("urgency", "low"))
    repo = analysis.get("repo", "unknown")
    founder_email = analysis.get("founder_email", "")

    if action_type == "calendar_invite":
        draft = {
            "action_type": "email",
            "payload": {
                "to": founder_email,
                "subject": f"1:1 Check-in: Team Pulse Alert for {repo}",
                "template": "calendar_invite",
                "template_vars": {
                    "reason": reasoning,
                    "repo": repo,
                    "duration_minutes": 30,
                },
            },
            "reasoning": reasoning,
            "urgency": urgency,
        }
        confidence = 0.90

    elif action_type == "sentiment_check":
        draft = {
            "action_type": "webhook",
            "payload": {
                "webhook_url": "https://internal.company.com/surveys",
                "method": "POST",
                "body_json": {
                    "survey_type": "team_sentiment",
                    "repo": repo,
                    "trigger_reason": reasoning,
                    "questions": [
                        "How is the team feeling about current workload?",
                        "Any blockers or challenges?",
                        "What can leadership do to help?",
                    ],
                },
            },
            "reasoning": reasoning,
            "urgency": urgency,
        }
        confidence = 0.85

    elif action_type == "1on1_reminder":
        draft = {
            "action_type": "slack_dm",
            "payload": {
                "slack_user_id": "founder",
                "slack_blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Team Pulse Reminder*\n\n{reasoning}\n\n"
                            f"Consider discussing {repo} in your upcoming 1:1s.",
                        },
                    },
                ],
            },
            "reasoning": reasoning,
            "urgency": urgency,
        }
        confidence = 0.82

    else:  # no_action
        draft = {
            "action_type": "log",
            "payload": {
                "log_level": "info",
                "message": f"No action needed: {reasoning}",
            },
            "reasoning": reasoning,
            "urgency": urgency,
        }
        confidence = 0.85

    logger.info(f"Drafted {action_type} action for team pulse")

    # Build updated state dict to avoid duplicate keyword arguments
    updated = dict(state)
    updated["draft_action"] = draft
    updated["confidence"] = confidence
    updated["status"] = "drafted"

    return TeamPulseState(**updated)


# =============================================================================
# Human Approval Node
# =============================================================================

def human_approval_node(state: TeamPulseState) -> TeamPulseState:
    """Handle human approval for team pulse actions.

    Team pulse actions are low urgency by default and don't require approval.
    Calendar invites for burnout risk may require founder approval.
    """
    draft = state.get("draft_action", {})
    action_type = draft.get("action_type", "")
    analysis = state.get("analysis", {})
    urgency = analysis.get("urgency", "low")

    # Team pulse actions typically don't require approval
    # Calendar invites for critical burnout risk might need confirmation
    if action_type == "email" and urgency == "high":
        approval_required = True
    else:
        approval_required = False

    # Process decision
    decision = state.get("approval_decision")
    if decision == "approved":
        status = "approved"
        ready_to_execute = True
    elif decision == "rejected":
        status = "rejected"
        ready_to_execute = False
    elif approval_required:
        status = "pending_approval"
        ready_to_execute = False
    else:
        status = "approved"
        ready_to_execute = True

    logger.info(
        f"Team pulse approval: action={action_type}, "
        f"requires_approval={approval_required}, status={status}"
    )

    # Build updated state dict to avoid duplicate keyword arguments
    updated = dict(state)
    updated["status"] = status
    updated["approval_required"] = approval_required
    updated["ready_to_execute"] = ready_to_execute

    return TeamPulseState(**updated)


# =============================================================================
# Graph Factory
# =============================================================================

from langgraph.graph import StateGraph, END

def create_team_pulse_graph() -> StateGraph:
    """Create the team pulse agent graph.

    Flow:
        check_activity → draft_action → human_approval → END
                           ↓ (no action needed)
                              END
    """
    builder = StateGraph(TeamPulseState)

    # Add nodes
    builder.add_node("check_activity", check_activity_node)
    builder.add_node("draft_action", draft_action_node)
    builder.add_node("human_approval", human_approval_node)

    # Set entry point
    builder.set_entry_point("check_activity")

    # Add edges
    builder.add_edge("check_activity", "draft_action")

    # Conditional: only proceed to approval if needed
    builder.add_conditional_edges(
        "draft_action",
        lambda s: "human_approval" if s.get("draft_action") else END,
    )

    builder.add_edge("human_approval", END)

    return builder
