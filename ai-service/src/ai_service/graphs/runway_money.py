"""Runway/Money Vertical Agent.

Handles Stripe invoice events and financial monitoring.
Triggers: Failed payments, high-value invoices, duplicate vendor charges.

SOPs:
- card_update_email: Request payment method update
- pause_downgrade: Prevent service downgrade for paying customers
- renewal_reminder: Send renewal reminders
- investigate: Flag for manual review (duplicates, anomalies)
"""

import logging
from typing import TypedDict, Any

logger = logging.getLogger(__name__)


# =============================================================================
# State Definition
# =============================================================================

class RunwayMoneyState(TypedDict):
    """State for runway money vertical agent."""

    # Required fields
    event_id: str
    event_type: str  # stripe.invoice, stripe.payment_failed
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
# Invoice Analysis Node
# =============================================================================

# Mock storage for duplicate detection (in production, this would query DB)
_known_invoices: dict[str, list[dict[str, Any]]] = {}


def get_recent_invoices(vendor: str) -> list[dict[str, Any]]:
    """Get recent invoices for a vendor (mock implementation).

    Args:
        vendor: Vendor name to query

    Returns:
        List of recent invoice records
    """
    return _known_invoices.get(vendor, [])


def check_invoice_node(state: RunwayMoneyState) -> RunwayMoneyState:
    """Analyze Stripe invoice to determine appropriate action.

    Decision logic:
    - payment_failed → card_update_email
    - amount > $1000 → requires_approval
    - duplicate vendor (same vendor, similar amount, last 7 days) → investigate
    - budget remaining < amount → investigate
    """
    context = state.get("event_context", {})
    urgency = state.get("urgency", "low")

    # Extract invoice details
    invoice_id = context.get("invoice_id", "")
    amount = context.get("amount", 0)  # In cents
    currency = context.get("currency", "usd")
    vendor = context.get("vendor", "unknown")
    customer_id = context.get("customer_id", "")
    customer_email = context.get("customer_email", "")
    status = context.get("status", "open")

    # Convert to USD for threshold comparison
    amount_usd = amount / 100

    # Check for duplicate vendor invoices
    is_duplicate_vendor = False
    recent_invoices = get_recent_invoices(vendor)
    for recent in recent_invoices:
        if abs(recent.get("amount", 0) - amount) < 100:  # Within $1
            is_duplicate_vendor = True
            break

    # Determine action based on status and amount
    if status == "payment_failed":
        action_type = "card_update_email"
        determined_urgency = "high"
        reasoning = (
            f"Payment failed for invoice {invoice_id} from {vendor}. "
            f"Customer needs to update payment method."
        )
        requires_approval = False  # Auto-send card update
    elif is_duplicate_vendor:
        action_type = "investigate"
        determined_urgency = "medium"
        reasoning = (
            f"Potential duplicate invoice from {vendor}. "
            f"Amount: ${amount_usd:.2f}. Requires manual verification."
        )
        requires_approval = True
    elif amount_usd > 1000:
        action_type = "approval_required"
        determined_urgency = "high"
        reasoning = (
            f"High-value invoice from {vendor}: ${amount_usd:.2f}. "
            f"Requires approval before payment."
        )
        requires_approval = True
    else:
        action_type = "standard_process"
        determined_urgency = "low"
        reasoning = f"Standard invoice from {vendor}: ${amount_usd:.2f}"
        requires_approval = False

    analysis = {
        "invoice_id": invoice_id,
        "amount_usd": amount_usd,
        "currency": currency,
        "vendor": vendor,
        "customer_id": customer_id,
        "customer_email": customer_email,
        "status": status,
        "is_duplicate_vendor": is_duplicate_vendor,
        "action_type": action_type,
        "reasoning": reasoning,
        "urgency": determined_urgency if urgency == "low" else urgency,
        "requires_approval": requires_approval,
        # Mock budget calculation - budget is less than high-value invoices
        "budget_remaining": max(0, 4000 - amount_usd),
    }

    logger.info(
        f"Runway analysis: action={action_type}, amount=${amount_usd:.2f}, "
        f"requires_approval={requires_approval}"
    )

    # Build updated state dict to avoid duplicate keyword arguments
    updated = dict(state)
    updated["analysis"] = analysis
    updated["status"] = "analyzed"
    updated["confidence"] = 0.88

    return RunwayMoneyState(**updated)


# =============================================================================
# Draft Action Node
# =============================================================================

def draft_action_node(state: RunwayMoneyState) -> RunwayMoneyState:
    """Generate executable action based on invoice analysis.

    Actions:
    - card_update_email: Send Stripe payment update email
    - investigate: Create investigation task
    - approval_required: Draft approval request
    """
    analysis = state.get("analysis", {})
    action_type = analysis.get("action_type", "standard_process")
    reasoning = analysis.get("reasoning", "")
    urgency = analysis.get("urgency", state.get("urgency", "low"))
    customer_email = analysis.get("customer_email", "")
    amount_usd = analysis.get("amount_usd", 0)
    vendor = analysis.get("vendor", "unknown")

    if action_type == "card_update_email":
        draft = {
            "action_type": "email",
            "payload": {
                "to": customer_email,
                "subject": "Update your payment method",
                "template": "stripe_payment_failed",
                "amount": f"${amount_usd:.2f}",
                "template_vars": {
                    "amount": f"${amount_usd:.2f}",
                    "vendor": vendor,
                    "action_url": "https://billing.stripe.com/p/login/...",
                },
            },
            "reasoning": reasoning,
            "urgency": urgency,
        }
        confidence = 0.92

    elif action_type == "investigate":
        draft = {
            "action_type": "webhook",
            "payload": {
                "webhook_url": "https://internal.company.com/investigations",
                "method": "POST",
                "body_json": {
                    "type": "duplicate_invoice_check",
                    "vendor": vendor,
                    "amount_usd": amount_usd,
                    "reason": reasoning,
                },
            },
            "reasoning": reasoning,
            "urgency": urgency,
        }
        confidence = 0.85

    elif action_type == "approval_required":
        draft = {
            "action_type": "approval_request",
            "payload": {
                "approver_role": "finance",
                "request_details": {
                    "vendor": vendor,
                    "amount": f"${amount_usd:.2f}",
                    "invoice_id": analysis.get("invoice_id", ""),
                },
                "decision_deadline_hours": 24,
            },
            "reasoning": reasoning,
            "urgency": urgency,
        }
        confidence = 0.88

    else:  # standard_process
        draft = {
            "action_type": "log",
            "payload": {
                "log_level": "info",
                "message": f"Standard processing: {reasoning}",
            },
            "reasoning": reasoning,
            "urgency": urgency,
        }
        confidence = 0.85

    logger.info(f"Drafted {action_type} action for ${amount_usd:.2f} invoice")

    # Build updated state dict to avoid duplicate keyword arguments
    updated = dict(state)
    updated["draft_action"] = draft
    updated["confidence"] = confidence
    updated["status"] = "drafted"

    return RunwayMoneyState(**updated)


# =============================================================================
# Human Approval Node
# =============================================================================

def human_approval_node(state: RunwayMoneyState) -> RunwayMoneyState:
    """Handle human approval for runway money actions.

    High-value invoices always require approval.
    Duplicate vendor investigations require approval.
    Card update emails auto-send.
    """
    draft = state.get("draft_action", {})
    action_type = draft.get("action_type", "")
    analysis = state.get("analysis", {})
    requires_approval = analysis.get("requires_approval", False)

    # Determine if approval is required
    if action_type in ("approval_request", "webhook"):  # investigate
        approval_required = True
    elif action_type == "email":  # card_update_email
        approval_required = False
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
        f"Runway approval: action={action_type}, "
        f"requires_approval={approval_required}, status={status}"
    )

    # Build updated state dict to avoid duplicate keyword arguments
    updated = dict(state)
    updated["status"] = status
    updated["approval_required"] = approval_required
    updated["ready_to_execute"] = ready_to_execute

    return RunwayMoneyState(**updated)


# =============================================================================
# Graph Factory
# =============================================================================

from langgraph.graph import StateGraph, END

def create_runway_money_graph() -> StateGraph:
    """Create the runway money agent graph.

    Flow:
        check_invoice → draft_action → human_approval → END
                            ↓ (no action needed)
                               END
    """
    builder = StateGraph(RunwayMoneyState)

    # Add nodes
    builder.add_node("check_invoice", check_invoice_node)
    builder.add_node("draft_action", draft_action_node)
    builder.add_node("human_approval", human_approval_node)

    # Set entry point
    builder.set_entry_point("check_invoice")

    # Add edges
    builder.add_edge("check_invoice", "draft_action")

    # Conditional: only proceed to approval if needed
    builder.add_conditional_edges(
        "draft_action",
        lambda s: "human_approval" if s.get("draft_action") else END,
    )

    builder.add_edge("human_approval", END)

    return builder
