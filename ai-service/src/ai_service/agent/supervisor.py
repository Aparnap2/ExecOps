"""Supervisor and Unified Guardrails Graph.

This module provides:
- Event routing to appropriate agents
- Unified state management across agents
- Final decision aggregation
- Slack notification formatting
"""

import logging
from typing import TypedDict, Literal, Any

from langgraph.graph import StateGraph
from langgraph.constants import START, END

from .state import AgentState

logger = logging.getLogger(__name__)


# === Unified Guardrails State ===

class GuardrailsState(TypedDict):
    """Unified state for the guardrails supervisor.

    This extends AgentState with multi-agent support.
    """

    # === Input ===
    event_type: str  # "pull_request", "stripe_invoice", "tech_debt_alert"
    webhook_event: dict
    webhook_action: str

    # === Agent Results ===
    agent_name: str | None  # Current agent processing
    sub_agent_results: dict[str, dict]  # Results from each agent

    # === Shared Analysis ===
    pr_info: dict | None
    invoice_context: dict | None
    diff_files: list[dict]

    # === Decision ===
    final_decision: str | None  # "approve", "warn", "block"
    requires_human_approval: bool
    human_approval_id: str | None

    # === Output ===
    slack_message: str | None
    trace_id: str | None


# === Event Routing ===

def route_event_to_agent(state: dict) -> str:
    """Route webhook event to the appropriate agent.

    Args:
        state: Current state with event_type

    Returns:
        Agent name to route to: "sre_agent", "cfo_agent", "tech_debt_agent", or "unknown"
    """
    event_type = state.get("event_type", "")

    routing_map = {
        "pull_request": "sre_agent",
        "github_pull_request": "sre_agent",
        "stripe_invoice": "cfo_agent",
        "stripe": "cfo_agent",
        "tech_debt_alert": "tech_debt_agent",
        "tech_debt": "tech_debt_agent",
    }

    agent = routing_map.get(event_type, "unknown")

    logger.info(f"Routing event type '{event_type}' to agent '{agent}'")
    return agent


def create_unified_state(
    event_type: str,
    webhook_event: dict,
    webhook_action: str,
) -> GuardrailsState:
    """Create initial unified state from webhook event.

    Args:
        event_type: Type of event
        webhook_event: Raw webhook payload
        webhook_action: Action type (opened, synchronize, etc.)

    Returns:
        Initial GuardrailsState
    """
    return GuardrailsState(
        event_type=event_type,
        webhook_event=webhook_event,
        webhook_action=webhook_action,
        agent_name=None,
        sub_agent_results={},
        pr_info=None,
        invoice_context=None,
        diff_files=[],
        final_decision=None,
        requires_human_approval=False,
        human_approval_id=None,
        slack_message=None,
        trace_id=None,
    )


def add_sub_agent_result(
    state: GuardrailsState,
    agent_name: str,
    result: dict,
) -> GuardrailsState:
    """Add sub-agent result to unified state.

    Args:
        state: Current state
        agent_name: Name of the agent
        result: Agent's result dict

    Returns:
        Updated state
    """
    new_results = dict(state["sub_agent_results"])
    new_results[agent_name] = result

    return {
        **state,
        "sub_agent_results": new_results,
    }


def aggregate_decisions(state: GuardrailsState) -> GuardrailsState:
    """Aggregate decisions from all agents.

    Args:
        state: Current state with sub_agent_results

    Returns:
        Updated state with aggregated decision
    """
    results = state.get("sub_agent_results", {})

    if not results:
        return {
            **state,
            "aggregated_decision": None,
            "agent_count": 0,
            "all_approved": True,
        }

    decisions = [r.get("decision", "unknown") for r in results.values()]
    agent_count = len(decisions)

    # Decision hierarchy: block > warn > approve
    if "block" in decisions:
        aggregated = "block"
    elif "warn" in decisions:
        aggregated = "warn"
    else:
        aggregated = "approve"

    all_approved = all(d == "approve" for d in decisions)

    return {
        **state,
        "aggregated_decision": aggregated,
        "agent_count": agent_count,
        "all_approved": all_approved,
    }


# === Agent Integration ===

def run_sre_agent(state: dict) -> dict:
    """Run SRE (GitHub Sentinel) agent.

    Args:
        state: Current guardrails state

    Returns:
        Updated state with SRE analysis
    """
    from .nodes import (
        parse_pr_node,
        fetch_diff_node,
        query_temporal_memory_node,
        query_semantic_memory_node,
        analyze_code_node,
        analyze_violations_node,
        generate_recommendations_node,
    )

    # Create AgentState from guardrails state
    agent_state = AgentState(
        webhook_event=state["webhook_event"],
        webhook_action=state["webhook_action"],
        pr_info=None,
        temporal_policies=[],
        similar_contexts=[],
        diff_files=[],
        diff_error=None,
        violations=[],
        recommendations=[],
        should_block=False,
        should_warn=False,
        blocking_message=None,
        warning_message=None,
        decision="approve",
        confidence=1.0,
        reason="",
        action_taken=None,
        trace_id=None,
        timestamp=None,
    )

    # Run through SRE agent nodes
    agent_state = parse_pr_node(agent_state)
    agent_state = fetch_diff_node(agent_state)
    agent_state = query_temporal_memory_node(agent_state)
    agent_state = query_semantic_memory_node(agent_state)
    agent_state = analyze_code_node(agent_state)
    agent_state = analyze_violations_node(agent_state)
    agent_state = generate_recommendations_node(agent_state)

    # Return result
    return {
        **state,
        "pr_info": agent_state.get("pr_info"),
        "diff_files": agent_state.get("diff_files"),
        "sre_report": {
            "violations": agent_state.get("violations", []),
            "recommendations": agent_state.get("recommendations", []),
            "decision": agent_state.get("decision"),
            "confidence": agent_state.get("confidence"),
            "reason": agent_state.get("reason"),
        },
        "decision": agent_state.get("decision"),
        "confidence": agent_state.get("confidence"),
        "reason": agent_state.get("reason"),
    }


def run_cfo_agent(state: dict) -> dict:
    """Run CFO agent for budget/stripe analysis.

    Args:
        state: Current guardrails state

    Returns:
        Updated state with CFO analysis
    """
    from .nodes import analyze_budget_node
    from ..integrations.stripe import cfo_analyze_invoice_node

    # Get invoice context if present
    invoice_context = state.get("invoice_context")

    if invoice_context:
        # Analyze Stripe invoice
        cfo_state = {
            "invoice_context": invoice_context,
            "monthly_budget": 500.0,
            "known_vendors": [],
            "duplicate_vendors": [],
        }
        result = cfo_analyze_invoice_node(cfo_state)

        return {
            **state,
            "cfo_report": {
                "budget_impact": result.get("budget_impact"),
                "decision": result.get("decision"),
                "reason": result.get("reason"),
            },
            "decision": result.get("decision", state.get("decision")),
            "confidence": result.get("confidence", 0.9),
            "reason": result.get("reason", state.get("reason", "")),
        }

    # Fallback: budget analysis for PR changes
    agent_state = dict(state)
    agent_state["monthly_budget"] = 500.0
    agent_state["pr_changes"] = state.get("pr_changes", {})

    result = analyze_budget_node(AgentState(**agent_state))

    return {
        **state,
        "cfo_report": {
            "budget_impact": result.get("budget_impact"),
            "decision": result.get("decision"),
            "reason": result.get("reason"),
        },
        "decision": result.get("decision", state.get("decision")),
        "confidence": result.get("confidence", 0.9),
        "reason": result.get("reason", state.get("reason", "")),
    }


def run_tech_debt_agent(state: dict) -> dict:
    """Run Tech Debt agent for code quality analysis.

    Args:
        state: Current guardrails state

    Returns:
        Updated state with tech debt analysis
    """
    from .tech_debt import tech_debt_analysis_node

    # Create tech debt analysis state
    td_state = {
        "pr_info": state.get("pr_info", {}),
        "diff_files": state.get("diff_files", []),
    }

    result = tech_debt_analysis_node(td_state)

    return {
        **state,
        "tech_debt_report": result.get("tech_debt_report"),
        "decision": result.get("decision", state.get("decision")),
        "confidence": result.get("confidence", 0.9),
        "reason": result.get("reason", state.get("reason", "")),
    }


# === Approval Logic ===

def should_request_approval(
    decision: str,
    violations: list[dict],
    confidence: float = 0.9,
) -> bool:
    """Determine if human approval should be requested.

    Args:
        decision: Agent's decision
        violations: List of violations found
        confidence: Agent confidence level

    Returns:
        True if human approval should be requested
    """
    # Block always requires approval
    if decision == "block":
        return True

    # Warn requires approval unless high confidence
    if decision == "warn":
        # Check for high severity violations
        has_high_severity = any(
            v.get("severity") == "blocking" for v in violations
        )
        if has_high_severity:
            return True
        # Low confidence warn requires approval
        if confidence < 0.85:
            return True
        return True  # Default: require approval for warns

    # Approve with high confidence skips approval
    if decision == "approve" and confidence >= 0.90:
        return False

    return False


# === Final Decision ===

def finalize_decision(agent_results: dict[str, dict]) -> dict:
    """Aggregate all agent results into final decision.

    Args:
        agent_results: Dict mapping agent name to their results

    Returns:
        Dict with final_decision, requires_human_approval, and summary
    """
    if not agent_results:
        return {
            "final_decision": "approve",
            "requires_human_approval": False,
            "summary": "No agents processed this event",
        }

    decisions = [r.get("decision", "unknown") for r in agent_results.values()]

    # Decision hierarchy: block > warn > approve
    if "block" in decisions:
        final = "block"
    elif "warn" in decisions:
        final = "warn"
    else:
        final = "approve"

    # Determine if human approval is needed
    requires_approval = final in ("block", "warn")

    # Generate summary
    agent_summary = ", ".join(
        f"{name}({r.get('decision', 'unknown')})"
        for name, r in agent_results.items()
    )

    return {
        "final_decision": final,
        "requires_human_approval": requires_approval,
        "summary": agent_summary,
        "agent_results": agent_results,
    }


# === Slack Formatting ===

def format_guardrails_result(result: dict) -> str:
    """Format guardrails result for Slack notification.

    Args:
        result: Final result dict

    Returns:
        Formatted Slack message
    """
    decision = result.get("final_decision", "unknown")
    agent_results = result.get("agent_results", {})

    if decision == "approve":
        emoji = "✅"
        header = f"{emoji} **Pull Request Approved**"
    elif decision == "warn":
        emoji = "⚠️"
        header = f"{emoji} **Attention Required**"
    else:
        emoji = "🚫"
        header = f"{emoji} **Pull Request Blocked**"

    lines = [header, ""]

    for agent, agent_result in agent_results.items():
        agent_decision = agent_result.get("decision", "unknown")
        agent_emoji = "✅" if agent_decision == "approve" else "⚠️" if agent_decision == "warn" else "🚫"
        lines.append(f"{agent_emoji} **{agent.replace('_', ' ').title()}**: {agent_decision}")

    lines.extend([
        "",
        f"_Decision: {decision}_",
    ])

    return "\n".join(lines)


def format_approval_request(
    agent_name: str,
    trigger: str,
    amount: str | None = None,
    vendor: str | None = None,
    reason: str | None = None,
) -> str:
    """Format human approval request message.

    Args:
        agent_name: Agent requesting approval
        trigger: What triggered the request
        amount: Optional amount (for invoices)
        vendor: Optional vendor name
        reason: Reason for the decision

    Returns:
        Formatted approval request message
    """
    lines = [
        f"👤 *Human Approval Required*",
        "",
        f"**Agent:** {agent_name}",
        f"**Trigger:** {trigger}",
    ]

    if amount:
        lines.append(f"**Amount:** {amount}")

    if vendor:
        lines.append(f"**Vendor:** {vendor}")

    if reason:
        lines.extend(["", f"**Reason:** {reason}"])

    lines.extend([
        "",
        "Please review and approve or reject this request.",
    ])

    return "\n".join(lines)


# === Supervisor Node ===

def supervisor_node(state: GuardrailsState) -> GuardrailsState:
    """Main supervisor node that routes to agents.

    Args:
        state: Current guardrails state

    Returns:
        Updated state after agent processing
    """
    event_type = state.get("event_type", "")
    agent = route_event_to_agent(state)

    if agent == "unknown":
        logger.warning(f"Unknown event type: {event_type}")
        return {
            **state,
            "final_decision": "error",
            "reason": f"Unknown event type: {event_type}",
        }

    # Route to appropriate agent
    if agent == "sre_agent":
        result = run_sre_agent(state)
    elif agent == "cfo_agent":
        result = run_cfo_agent(state)
    elif agent == "tech_debt_agent":
        result = run_tech_debt_agent(state)
    else:
        result = state

    # Add agent name
    result["agent_name"] = agent

    # Aggregate decisions if we have sub-agent results
    if "sub_agent_results" in result:
        aggregated = aggregate_decisions(result)
        result.update(aggregated)

    return result


def create_guardrails_agent() -> StateGraph:
    """Create the unified guardrails StateGraph.

    Returns:
        Compiled StateGraph with all agents
    """
    graph = StateGraph(GuardrailsState)

    # Add supervisor node
    graph.add_node("supervisor", supervisor_node)

    # Add sub-agent nodes
    graph.add_node("sre_agent", run_sre_agent)
    graph.add_node("cfo_agent", run_cfo_agent)
    graph.add_node("tech_debt_agent", run_tech_debt_agent)

    # Set entry point
    graph.set_entry_point("supervisor")

    # Route to appropriate agent based on event type
    def route_to_agent(state: GuardrailsState) -> str:
        event_type = state.get("event_type", "")

        routing = {
            "pull_request": "sre_agent",
            "github_pull_request": "sre_agent",
            "stripe_invoice": "cfo_agent",
            "stripe": "cfo_agent",
            "tech_debt_alert": "tech_debt_agent",
            "tech_debt": "tech_debt_agent",
        }

        return routing.get(event_type, "supervisor")

    graph.add_conditional_edges("supervisor", route_to_agent)

    # All agents go to END
    graph.add_edge("sre_agent", END)
    graph.add_edge("cfo_agent", END)
    graph.add_edge("tech_debt_agent", END)

    return graph


# === Convenience Functions ===

def process_webhook(
    event_type: str,
    webhook_event: dict,
    webhook_action: str,
) -> dict:
    """Process a webhook event through the guardrails system.

    Args:
        event_type: Type of event
        webhook_event: Raw webhook payload
        webhook_action: Action type

    Returns:
        Processing result with decision
    """
    state = create_unified_state(event_type, webhook_event, webhook_action)

    # For simple cases, just run supervisor directly
    result = supervisor_node(state)

    return result


def get_active_agents() -> list[str]:
    """Get list of active agent names.

    Returns:
        List of agent names
    """
    return ["sre_agent", "cfo_agent", "tech_debt_agent"]
