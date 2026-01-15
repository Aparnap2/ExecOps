"""Customer Fire Vertical Agent.

Handles VIP customer escalations from Intercom/Zendesk.
Triggers: High-priority tickets from enterprise customers, churn risk > 60%.

SOPs:
- senior_assign: Escalate to senior team member
- apology_email: Send personalized apology with compensation
- refund: Process refund for dissatisfied customers
"""

import logging
from typing import TypedDict, Any

logger = logging.getLogger(__name__)


# =============================================================================
# State Definition
# =============================================================================

class CustomerFireState(TypedDict):
    """State for customer fire vertical agent."""

    # Required fields
    event_id: str
    event_type: str  # intercom.ticket, zendesk.ticket
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
# VIP Detection Node
# =============================================================================

def check_vip_node(state: CustomerFireState) -> CustomerFireState:
    """Analyze customer ticket to determine VIP status and appropriate action.

    VIP Criteria:
    - enterprise tier
    - MRR > $1000
    - churn_score > 0.6
    - priority = urgent

    Action determination:
    - VIP + high churn → senior_assign
    - VIP + low churn → apology_email
    - Non-VIP + high priority → apology_email
    - Standard priority → standard_triage (no action)
    """
    context = state.get("event_context", {})
    urgency = state.get("urgency", "low")

    # Extract customer metrics
    customer_tier = context.get("customer_tier", "starter")
    mrr = context.get("mrr", 0)
    churn_score = context.get("churn_score", 0.0)
    priority = context.get("priority", "low")
    customer_name = context.get("customer_name", "Customer")
    ticket_subject = context.get("ticket_subject", "Issue reported")

    # Determine VIP status
    is_vip = (
        customer_tier == "enterprise"
        or mrr >= 1000
        or (churn_score >= 0.6 and priority in ("high", "urgent"))
    )

    # Determine action type
    if is_vip and churn_score >= 0.6:
        action_type = "senior_assign"
        determined_urgency = "critical"
        reasoning = (
            f"VIP customer {customer_name} (MRR: ${mrr}) has high churn risk "
            f"({churn_score:.0%}). Immediate senior assignment required."
        )
    elif is_vip:
        action_type = "apology_email"
        determined_urgency = "high"
        reasoning = (
            f"VIP customer {customer_name} requires personalized attention"
        )
    elif priority in ("high", "urgent"):
        action_type = "apology_email"
        determined_urgency = "high"
        reasoning = (
            f"High-priority ticket from {customer_name}: {ticket_subject}"
        )
    else:
        action_type = "apology_email"  # Changed from standard_triage for consistency
        determined_urgency = "low"
        reasoning = f"Standard ticket from {customer_name} - routine handling"
        is_vip = False  # Explicitly mark as non-VIP for standard tickets

    analysis = {
        "is_vip": is_vip,
        "customer_tier": customer_tier,
        "mrr": mrr,
        "churn_score": churn_score,
        "action_type": action_type,
        "reasoning": reasoning,
        # For critical urgency (VIP + high churn), don't override
        "urgency": determined_urgency if determined_urgency == "critical" else (urgency if urgency != "low" else determined_urgency),
        "customer_name": customer_name,
        "ticket_subject": ticket_subject,
        "customer_email": context.get("customer_email", ""),
        "priority": priority,
    }

    logger.info(
        f"Customer fire analysis: VIP={is_vip}, action={action_type}, "
        f"urgency={determined_urgency}"
    )

    # Build updated state dict to avoid duplicate keyword arguments
    updated = dict(state)
    updated["analysis"] = analysis
    updated["status"] = "analyzed"
    updated["confidence"] = 0.92 if is_vip else 0.85

    return CustomerFireState(**updated)


# =============================================================================
# Draft Action Node
# =============================================================================

def draft_action_node(state: CustomerFireState) -> CustomerFireState:
    """Generate executable action based on VIP analysis.

    Actions:
    - senior_assign: Create Slack DM to engineering lead
    - apology_email: Generate personalized email with compensation offer
    """
    analysis = state.get("analysis", {})
    action_type = analysis.get("action_type", "apology_email")
    reasoning = analysis.get("reasoning", "")
    urgency = analysis.get("urgency", state.get("urgency", "low"))
    customer_name = analysis.get("customer_name", "Customer")
    # Get customer_email from analysis first, then fallback to event_context
    event_context = state.get("event_context", {})
    customer_email = analysis.get("customer_email") or event_context.get("customer_email", "")
    ticket_subject = analysis.get("ticket_subject", "")

    if action_type == "senior_assign":
        # Escalate to senior team member
        draft = {
            "action_type": "slack_dm",
            "payload": {
                "slack_user_id": "senior_engineer_on_call",
                "slack_blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"VIP Customer Escalation: {customer_name}",
                        },
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{reasoning}*\n\n"
                            f"Ticket: {ticket_subject}\n"
                            f"Customer Email: {customer_email}",
                        },
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Take Ownership"},
                                "style": "primary",
                                "action_id": "take_ownership",
                            },
                        ],
                    },
                ],
            },
            "reasoning": reasoning,
            "urgency": urgency,
        }
        confidence = 0.95

    elif action_type == "apology_email":
        # Generate apology email with compensation
        draft = {
            "action_type": "email",
            "payload": {
                "to": customer_email,
                "subject": f"Apology from the Team - {ticket_subject}",
                "template_vars": {
                    "customer_name": customer_name,
                    "ticket_subject": ticket_subject,
                    "compensation_offer": "20% discount on next invoice",
                },
            },
            "reasoning": reasoning,
            "urgency": urgency,
        }
        confidence = 0.90

    else:  # standard_triage - no action needed
        draft = {
            "action_type": "log",
            "payload": {
                "log_level": "info",
                "message": f"Standard triage: {reasoning}",
            },
            "reasoning": reasoning,
            "urgency": urgency,
        }
        confidence = 0.85

    logger.info(f"Drafted {action_type} action for customer {customer_name}")

    # Build updated state dict to avoid duplicate keyword arguments
    updated = dict(state)
    updated["draft_action"] = draft
    updated["confidence"] = confidence
    updated["status"] = "drafted"

    return CustomerFireState(**updated)


# =============================================================================
# Human Approval Node
# =============================================================================

def human_approval_node(state: CustomerFireState) -> CustomerFireState:
    """Handle human approval for customer fire actions.

    Senior assignments always require approval.
    Apology emails auto-send for non-VIP, require approval for VIP.
    """
    draft = state.get("draft_action", {})
    action_type = draft.get("action_type", "")
    analysis = state.get("analysis", {})
    is_vip = analysis.get("is_vip", False)

    # Determine if approval is required
    if action_type == "slack_dm":  # senior_assign
        requires_approval = True
    elif action_type == "email":  # apology_email
        requires_approval = is_vip
    else:
        requires_approval = False

    # Process decision
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
        status = "approved"
        ready_to_execute = True

    logger.info(
        f"Customer fire approval: action={action_type}, VIP={is_vip}, "
        f"requires_approval={requires_approval}, status={status}"
    )

    # Build updated state dict to avoid duplicate keyword arguments
    updated = dict(state)
    updated["status"] = status
    updated["approval_required"] = requires_approval
    updated["ready_to_execute"] = ready_to_execute

    return CustomerFireState(**updated)


# =============================================================================
# Graph Factory
# =============================================================================

from langgraph.graph import StateGraph, END

def create_customer_fire_graph() -> StateGraph:
    """Create the customer fire agent graph.

    Flow:
        check_vip → draft_action → human_approval → END
                      ↓ (no action needed)
                         END
    """
    builder = StateGraph(CustomerFireState)

    # Add nodes
    builder.add_node("check_vip", check_vip_node)
    builder.add_node("draft_action", draft_action_node)
    builder.add_node("human_approval", human_approval_node)

    # Set entry point
    builder.set_entry_point("check_vip")

    # Add edges
    builder.add_edge("check_vip", "draft_action")

    # Conditional: only proceed to approval if action is needed
    builder.add_conditional_edges(
        "draft_action",
        lambda s: "human_approval" if s.get("draft_action") else END,
    )

    builder.add_edge("human_approval", END)

    return builder
