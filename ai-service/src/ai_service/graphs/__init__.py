"""ExecOps Vertical Agent Graphs.

LangGraph StateGraph implementations for the 4 vertical agents:

1. Release Hygiene (release_hygiene.py)
   - Triggered by: Sentry errors, GitHub deploys
   - Actions: rollback, postmortem, alert_dev

2. Customer Fire (customer_fire.py)
   - Triggered by: Intercom/Zendesk VIP tickets
   - Actions: senior_assign, apology_email, refund

3. Runway/Money (runway_money.py)
   - Triggered by: Stripe invoices, payment failures
   - Actions: card_update_email, investigate, approval_request

4. Team Pulse (team_pulse.py)
   - Triggered by: GitHub activity changes
   - Actions: calendar_invite, sentiment_check, 1on1_reminder

Usage:
    from ai_service.graphs import (
        route_to_vertical,
        create_vertical_agent_graph,
    )

    # Route event to vertical
    vertical = route_to_vertical("sentry.error")

    # Get compiled graph
    graph = create_vertical_agent_graph(vertical)

    # Invoke with state
    result = graph.invoke(initial_state)
"""

from ai_service.graphs.vertical_agents import (
    ActionProposalState,
    route_to_vertical,
    get_vertical_graph,
    create_vertical_agent_graph,
    human_approval_node,
)

from ai_service.graphs.release_hygiene import (
    ReleaseHygieneState,
    create_release_hygiene_graph,
)

from ai_service.graphs.customer_fire import (
    CustomerFireState,
    create_customer_fire_graph,
)

from ai_service.graphs.runway_money import (
    RunwayMoneyState,
    create_runway_money_graph,
)

from ai_service.graphs.team_pulse import (
    TeamPulseState,
    create_team_pulse_graph,
)

__all__ = [
    # Common exports
    "ActionProposalState",
    "route_to_vertical",
    "get_vertical_graph",
    "create_vertical_agent_graph",
    "human_approval_node",
    # Vertical-specific
    "ReleaseHygieneState",
    "create_release_hygiene_graph",
    "CustomerFireState",
    "create_customer_fire_graph",
    "RunwayMoneyState",
    "create_runway_money_graph",
    "TeamPulseState",
    "create_team_pulse_graph",
]
