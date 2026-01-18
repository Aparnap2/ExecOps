"""Vertical Agents Router and Common Components.

Routes incoming events to the appropriate vertical agent based on event_type.
Provides shared state types and human approval workflows used across all verticals.
"""

import logging
from typing import TypedDict, Any

from .release_hygiene import (
    create_release_hygiene_graph,
    ReleaseHygieneState,
)
from .customer_fire import (
    create_customer_fire_graph,
    CustomerFireState,
)
from .runway_money import (
    create_runway_money_graph,
    RunwayMoneyState,
)
from .team_pulse import (
    create_team_pulse_graph,
    TeamPulseState,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Unified State Type
# =============================================================================

class ActionProposalState(TypedDict, total=False):
    """Unified state for all vertical agents.

    All vertical agents use this common state structure with optional
    fields that may be specific to certain verticals.
    """

    # Required identification
    event_id: str
    event_type: str
    vertical: str  # release, customer_fire, runway, team_pulse
    urgency: str  # low, medium, high, critical

    # Processing state (with defaults)
    status: str  # pending, analyzed, drafted, pending_approval, approved, rejected, executed
    analysis: dict[str, Any] | None
    draft_action: dict[str, Any] | None
    confidence: float  # 0.0 to 1.0

    # Event context (vertical-specific)
    event_context: dict[str, Any] | None

    # Approval workflow
    approval_required: bool
    approval_decision: str | None  # approved, rejected
    approver_id: str | None
    rejection_reason: str | None

    # Execution tracking
    ready_to_execute: bool
    executed_at: str | None

    # Error handling
    error: str | None


# =============================================================================
# Vertical Router
# =============================================================================

# Map event types to vertical agents
_VERTICAL_MAP = {
    # Release hygiene triggers
    "sentry.error": "release_hygiene",
    "sentry.metric": "release_hygiene",
    "github.deploy": "release_hygiene",
    "github.release": "release_hygiene",

    # Customer fire triggers
    "intercom.ticket": "customer_fire",
    "intercom.conversation": "customer_fire",
    "zendesk.ticket": "customer_fire",
    "zendesk.escalation": "customer_fire",

    # Runway/money triggers
    "stripe.invoice": "runway_money",
    "stripe.payment_failed": "runway_money",
    "stripe.charge": "runway_money",
    "hubspot.deal": "runway_money",

    # Team pulse triggers
    "github.activity": "team_pulse",
    "github.commit": "team_pulse",
    "github.pr": "team_pulse",
    "slack.message": "team_pulse",
}


def route_to_vertical(event_type_or_dict: str | dict[str, Any]) -> str:
    """Route event_type to the appropriate vertical agent.

    Args:
        event_type_or_dict: Either an event_type string (e.g., "sentry.error")
            or a dict with "event_type" key for backward compatibility.

    Returns:
        Vertical agent name: "release_hygiene", "customer_fire",
        "runway_money", or "team_pulse"

    Raises:
        ValueError: If event_type is not recognized
    """
    # Handle both string and dict inputs for backward compatibility
    if isinstance(event_type_or_dict, dict):
        event_type = event_type_or_dict.get("event_type", "")
    else:
        event_type = event_type_or_dict

    vertical = _VERTICAL_MAP.get(event_type)

    if not vertical:
        logger.warning(f"Unhandled event type: {event_type}")
        raise ValueError(f"No vertical agent for event type: {event_type}")

    logger.info(f"Routing {event_type} -> {vertical}")
    return vertical


def get_vertical_graph(vertical: str):
    """Get the StateGraph for a vertical agent.

    Args:
        vertical: Vertical agent name

    Returns:
        Compiled StateGraph for the vertical

    Raises:
        ValueError: If vertical is not recognized
    """
    graphs = {
        "release_hygiene": create_release_hygiene_graph,
        "customer_fire": create_customer_fire_graph,
        "runway_money": create_runway_money_graph,
        "team_pulse": create_team_pulse_graph,
    }

    graph_factory = graphs.get(vertical)

    if not graph_factory:
        raise ValueError(f"No graph factory for vertical: {vertical}")

    return graph_factory()


# =============================================================================
# Human Approval Node (Shared)
# =============================================================================

def human_approval_node(state: ActionProposalState) -> ActionProposalState:
    """Shared human approval workflow for all verticals.

    This node handles the approval decision and updates the state
    accordingly. The actual approval requirement is determined by
    each vertical's specific logic.

    Args:
        state: Current action proposal state

    Returns:
        Updated state with approval decision applied
    """
    decision = state.get("approval_decision")
    draft = state.get("draft_action", {})
    action_type = draft.get("action_type", "") if draft else ""
    approval_required = state.get("approval_required", False)

    # Commands (rollback, etc.) always require approval
    if action_type == "command":
        approval_required = True

    if decision == "approved":
        new_status = "approved"
        ready_to_execute = True
    elif decision == "rejected":
        new_status = "rejected"
        ready_to_execute = False
    elif approval_required:
        new_status = "pending_approval"
        ready_to_execute = False
    else:
        # Auto-approve if no approval required
        new_status = "approved"
        ready_to_execute = True

    logger.info(
        f"Human approval: decision={decision}, "
        f"required={approval_required}, new_status={new_status}"
    )

    # Build updated state without duplicating fields
    updated = dict(state)
    updated["status"] = new_status
    updated["approval_required"] = approval_required
    updated["ready_to_execute"] = ready_to_execute

    return ActionProposalState(**updated)


# =============================================================================
# Graph Composition Utilities
# =============================================================================

def create_vertical_agent_graph(vertical: str, use_postgres: bool = True):
    """Create a compiled graph for the specified vertical.

    This is a convenience function that:
    1. Creates the vertical-specific StateGraph
    2. Compiles with checkpointer (Postgres in prod, memory in dev)
    3. Returns the compiled graph

    Args:
        vertical: Vertical agent name
        use_postgres: Use Postgres checkpointer (default: True in production)

    Returns:
        Compiled StateGraph ready for invocation
    """
    import os

    graph = get_vertical_graph(vertical)

    # Use appropriate checkpointer
    if use_postgres and os.getenv("USE_POSTGRES_CHECKPOINTER", "true").lower() == "true":
        try:
            from ai_service.infrastructure.checkpointer import get_sync_checkpointer

            with get_sync_checkpointer() as checkpointer:
                compiled = graph.compile(checkpointer=checkpointer)
                logger.info(f"Compiled {vertical} graph with Postgres checkpointer")
        except Exception as e:
            logger.warning(f"Failed to use Postgres checkpointer: {e}. Falling back to memory.")
            from langgraph.checkpoint.memory import MemorySaver
            memory = MemorySaver()
            compiled = graph.compile(checkpointer=memory)
    else:
        from langgraph.checkpoint.memory import MemorySaver
        memory = MemorySaver()
        compiled = graph.compile(checkpointer=memory)
        logger.info(f"Compiled {vertical} graph with memory checkpointer")

    return compiled


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "ActionProposalState",
    "route_to_vertical",
    "get_vertical_graph",
    "create_vertical_agent_graph",
    "human_approval_node",
    # State types for type checking
    "ReleaseHygieneState",
    "CustomerFireState",
    "RunwayMoneyState",
    "TeamPulseState",
]
