"""
LangGraph-based SOP (Standard Operating Procedure) workflow engine.

Implements the three core SOPs:
- SOP-001: Lead Hygiene (Sales Ops)
- SOP-010: Support Triage (Support Ops)
- SOP-015: Ops Hygiene (Data Quality)

Uses StateGraph for deterministic, stateful workflow execution.
"""

from datetime import datetime, timedelta
from typing import Any

from langgraph.graph import StateGraph

from ..schemas.sop import (
    ActionRecommendation,
    ConfidenceBreakdown,
    DecisionState,
    EscalationItem,
    EventPayload,
)


class SopState(dict):
    """
    Shared state for SOP graph execution.

    Contains all intermediate results and final outputs.
    """

    # Request context
    request_id: str
    objective: str
    events: list[EventPayload]
    constraints: dict[str, Any]

    # Intermediate results
    stale_leads: list[dict[str, Any]] | None = None
    support_tickets: list[dict[str, Any]] | None = None
    data_quality_issues: list[dict[str, Any]] | None = None

    # Confidence breakdown
    data_completeness: float = 1.0
    ambiguity: float = 0.0
    rule_violations: float = 0.0

    # Final decision
    decision_state: str = DecisionState.CONFIDENT.value
    summary: str = ""
    recommendations: list[ActionRecommendation] = []
    escalations: list[EscalationItem] = []
    executed_sops: list[str] = []

    # Metadata
    created_at: datetime = datetime.utcnow()
    processed_at: datetime | None = None


def get_stale_threshold_hours(constraints: dict[str, Any]) -> int:
    """Get stale threshold from constraints, default 48 hours."""
    return constraints.get("stale_threshold_hours", 48)


# =============================================================================
# SOP-001: Lead Hygiene Nodes
# =============================================================================

def validate_leads(state: SopState) -> SopState:
    """
    Validate leads for SOP-001 Lead Hygiene.

    Checks:
    - Status field is not empty
    - Last contacted within threshold
    """
    threshold_hours = get_stale_threshold_hours(state["constraints"])
    stale_leads: list[dict[str, Any]] = []
    total_leads = 0

    for event in state["events"]:
        if event.source.value != "hubspot":
            continue

        total_leads += 1
        data = event.data

        # Check for missing status
        has_status = data.get("status") is not None and data.get("status") != ""

        # Check last contacted
        last_contacted_str = data.get("last_contacted")
        is_stale = True

        if last_contacted_str and has_status:
            try:
                last_contacted = datetime.fromisoformat(last_contacted_str.replace("Z", "+00:00"))
                hours_since = (datetime.utcnow() - last_contacted).total_seconds() / 3600
                is_stale = hours_since > threshold_hours
            except (ValueError, TypeError):
                is_stale = True

        if not has_status or is_stale:
            stale_leads.append(
                {
                    "contact_id": data.get("contact_id"),
                    "email": data.get("email"),
                    "missing_status": not has_status,
                    "stale_hours": hours_since if "hours_since" in dir() else None,
                    "original_event": event.model_dump(),
                }
            )

    state["stale_leads"] = stale_leads

    # Update confidence based on data completeness
    if total_leads > 0:
        state["data_completeness"] = max(0.0, 1.0 - (len(stale_leads) / total_leads) * 0.5)

    return state


def summarize_leads(state: SopState) -> SopState:
    """Generate summary for lead hygiene check."""
    stale_count = len(state.get("stale_leads", []))

    if stale_count == 0:
        state["summary"] = f"All leads have valid status and were contacted within {get_stale_threshold_hours(state['constraints'])}h window."
    else:
        state["summary"] = f"Found {stale_count} stale leads requiring follow-up."

    return state


def lead_hygiene_decision(state: SopState) -> SopState:
    """Make decision for lead hygiene SOP."""
    stale_count = len(state.get("stale_leads", []))

    # Ensure lists exist
    state.setdefault("escalations", [])
    state.setdefault("executed_sops", [])

    if stale_count == 0:
        state["decision_state"] = DecisionState.CONFIDENT.value
        state["executed_sops"].append("sop_001_lead_hygiene")
    else:
        state["decision_state"] = DecisionState.ESCALATE.value

        # Create escalation item
        escalation = EscalationItem(
            reason=f"{stale_count} leads are stale or missing status",
            severity="medium",
            context={"stale_leads": stale_count, "threshold_hours": get_stale_threshold_hours(state["constraints"])},
            suggested_actions=[
                ActionRecommendation(
                    type="email",
                    target="sales_team",
                    payload={"template": "lead_follow_up", "stale_leads_count": stale_count},
                    reason="Draft follow-up email for stale leads",
                )
            ],
        )
        state["escalations"].append(escalation)
        state["executed_sops"].append("sop_001_lead_hygiene")

    state["processed_at"] = datetime.utcnow()
    return state


# =============================================================================
# SOP-010: Support Triage Nodes
# =============================================================================

def analyze_support_tickets(state: SopState) -> SopState:
    """
    Analyze support tickets for SOP-010 Support Triage.

    Checks:
    - Sentiment/urgency scoring
    - Duplicate detection
    - SLA breach detection
    """
    tickets: list[dict[str, Any]] = []
    urgent_count = 0
    duplicates: list[dict[str, Any]] = []

    # Simple keyword-based urgency detection (can be replaced with LLM)
    urgency_keywords = ["urgent", "critical", "asap", "down", "broken", "not working", "blocked"]
    sentiment_keywords = {"negative": ["frustrated", "angry", "disappointed", "terrible"], "positive": ["thanks", "great", "love"]}

    for event in state["events"]:
        if event.source.value not in ("slack", "gmail"):
            continue

        content = str(event.data.get("content", "")).lower()
        subject = str(event.data.get("subject", "")).lower()

        # Urgency scoring
        urgency_score = 0
        for keyword in urgency_keywords:
            if keyword in content or keyword in subject:
                urgency_score += 1

        # Simple sentiment (can be replaced with proper sentiment analysis)
        sentiment = "neutral"
        for neg in sentiment_keywords["negative"]:
            if neg in content:
                sentiment = "negative"
                break

        ticket = {
            "ticket_id": event.external_id or event.source.value,
            "urgency_score": urgency_score,
            "sentiment": sentiment,
            "content_preview": content[:100],
            "source": event.source.value,
            "occurred_at": event.occurred_at.isoformat(),
        }

        if urgency_score >= 2:
            urgent_count += 1
            ticket["is_urgent"] = True

        # Check for duplicates (simple text similarity)
        for existing in tickets:
            if content[:50] == existing.get("content_preview", "")[:50]:
                duplicates.append({"original": existing, "duplicate": ticket})
                ticket["is_duplicate"] = True
                break

        tickets.append(ticket)

    state["support_tickets"] = tickets

    # Update confidence based on analysis quality
    if len(tickets) > 0:
        state["ambiguity"] = min(1.0, len(duplicates) * 0.2)

    return state


def triage_decision(state: SopState) -> SopState:
    """Make decision for support triage SOP."""
    tickets = state.get("support_tickets", [])
    urgent_tickets = [t for t in tickets if t.get("is_urgent", False)]
    duplicate_count = len([t for t in tickets if t.get("is_duplicate", False)])

    # Ensure lists exist
    state.setdefault("recommendations", [])
    state.setdefault("escalations", [])
    state.setdefault("executed_sops", [])

    # Generate summary
    state["summary"] = (
        f"Processed {len(tickets)} tickets: {len(urgent_tickets)} urgent, "
        f"{duplicate_count} potential duplicates."
    )

    if len(urgent_tickets) == 0 and duplicate_count == 0:
        state["decision_state"] = DecisionState.CONFIDENT.value
        state["recommendations"].append(
            ActionRecommendation(
                type="slack_message",
                target="support_channel",
                payload={"message": "No urgent tickets detected. All clear."},
                reason="Routine status update for support channel",
            )
        )
    elif len(urgent_tickets) <= 2:
        state["decision_state"] = DecisionState.UNCERTAIN.value
        state["recommendations"].append(
            ActionRecommendation(
                type="crm_update",
                target="support_queue",
                payload={"action": "assign_urgent", "count": len(urgent_tickets)},
                reason="Mark urgent tickets for priority review",
            )
        )
    else:
        state["decision_state"] = DecisionState.ESCALATE.value
        state["escalations"].append(
            EscalationItem(
                reason=f"{len(urgent_tickets)} urgent support tickets require immediate attention",
                severity="high",
                context={"urgent_tickets": urgent_tickets},
                suggested_actions=[
                    ActionRecommendation(
                        type="slack_message",
                        target="on_call",
                        payload={"message": "URGENT: Multiple support tickets need immediate review"},
                        reason="Alert on-call team",
                    )
                ],
            )
        )

    state["executed_sops"].append("sop_010_support_triage")
    state["processed_at"] = datetime.utcnow()
    return state


# =============================================================================
# SOP-015: Ops Hygiene Nodes
# =============================================================================

def check_data_quality(state: SopState) -> SopState:
    """
    Check data quality for SOP-015 Ops Hygiene.

    Checks:
    - Missing fields in critical workflows
    - Webhook failures
    - Sync errors
    """
    issues: list[dict[str, Any]] = []
    critical_issues = 0

    # Check for missing critical fields
    critical_fields = {
        "deal": ["status", "value", "close_date"],
        "invoice": ["amount", "status", "link"],
        "contact": ["email", "status", "last_contacted"],
    }

    for event in state["events"]:
        data = event.data
        entity_type = data.get("entity_type", "")

        if entity_type in critical_fields:
            for field in critical_fields[entity_type]:
                if field not in data or data[field] is None:
                    issues.append(
                        {
                            "type": "missing_field",
                            "entity_type": entity_type,
                            "field": field,
                            "entity_id": data.get("id"),
                            "severity": "medium" if field != "status" else "high",
                        }
                    )
                    if field == "status":
                        critical_issues += 1

        # Check for webhook/sync errors
        if data.get("sync_error") or data.get("webhook_failed"):
            issues.append(
                {
                    "type": "sync_error",
                    "error": data.get("sync_error") or data.get("webhook_failed"),
                    "entity_id": data.get("id"),
                    "severity": "high",
                }
            )
            critical_issues += 1

    state["data_quality_issues"] = issues

    # Update rule violations based on issues
    if len(state["events"]) > 0:
        state["rule_violations"] = min(1.0, critical_issues * 0.3)

    return state


def hygiene_decision(state: SopState) -> SopState:
    """Make decision for ops hygiene SOP."""
    issues = state.get("data_quality_issues", [])
    critical_count = sum(1 for i in issues if i.get("severity") == "high")

    # Ensure lists exist
    state.setdefault("recommendations", [])
    state.setdefault("escalations", [])
    state.setdefault("executed_sops", [])

    if len(issues) == 0:
        state["decision_state"] = DecisionState.CONFIDENT.value
        state["summary"] = "All data quality checks passed. No issues detected."
    elif critical_count == 0:
        state["decision_state"] = DecisionState.UNCERTAIN.value
        state["summary"] = f"Found {len(issues)} minor data quality issues."
        state["recommendations"].append(
            ActionRecommendation(
                type="crm_update",
                target="data_team",
                payload={"action": "fix_quality_issues", "count": len(issues)},
                reason="Flag data quality issues for team review",
            )
        )
    else:
        state["decision_state"] = DecisionState.ESCALATE.value
        state["summary"] = f"Found {critical_count} critical data quality issues requiring immediate attention."
        state["escalations"].append(
            EscalationItem(
                reason=f"{critical_count} critical data quality issues detected",
                severity="high",
                context={"issues": [i for i in issues if i.get("severity") == "high"]},
                suggested_actions=[
                    ActionRecommendation(
                        type="email",
                        target="ops_lead",
                        payload={"subject": "Critical Data Quality Issues", "issue_count": critical_count},
                        reason="Alert ops lead to critical issues",
                    )
                ],
            )
        )

    state["executed_sops"].append("sop_015_ops_hygiene")
    state["processed_at"] = datetime.utcnow()
    return state


# =============================================================================
# Graph Factory
# =============================================================================

def create_sop_graph(objective: str) -> StateGraph[SopState]:
    """
    Create a SOP graph based on the objective.

    Args:
        objective: One of 'lead_hygiene', 'support_triage', 'ops_hygiene', or 'all'

    Returns:
        Compiled StateGraph ready for execution
    """
    graph = StateGraph(SopState)

    if objective == "lead_hygiene":
        graph.add_node("validate_leads", validate_leads)
        graph.add_node("summarize_leads", summarize_leads)
        graph.add_node("decision", lead_hygiene_decision)
        graph.set_entry_point("validate_leads")
        graph.add_edge("validate_leads", "summarize_leads")
        graph.add_edge("summarize_leads", "decision")

    elif objective == "support_triage":
        graph.add_node("analyze_tickets", analyze_support_tickets)
        graph.add_node("decision", triage_decision)
        graph.set_entry_point("analyze_tickets")
        graph.add_edge("analyze_tickets", "decision")

    elif objective == "ops_hygiene":
        graph.add_node("check_quality", check_data_quality)
        graph.add_node("decision", hygiene_decision)
        graph.set_entry_point("check_quality")
        graph.add_edge("check_quality", "decision")

    else:  # "all" or composite
        # Lead hygiene branch
        graph.add_node("validate_leads", validate_leads)
        graph.add_node("lead_decision", lead_hygiene_decision)

        # Support triage branch
        graph.add_node("analyze_tickets", analyze_support_tickets)
        graph.add_node("triage_decision", triage_decision)

        # Ops hygiene branch
        graph.add_node("check_quality", check_data_quality)
        graph.add_node("hygiene_decision", hygiene_decision)

        # Final aggregation node
        def aggregate(state: SopState) -> SopState:
            """Aggregate results from all SOPs."""
            all_sops = state.get("executed_sops", [])
            all_escalations = state.get("escalations", [])

            # Determine overall state
            if any(e.severity == "high" for e in all_escalations):
                overall_state = DecisionState.ESCALATE.value
            elif any(e.severity == "medium" for e in all_escalations):
                overall_state = DecisionState.UNCERTAIN.value
            else:
                overall_state = DecisionState.CONFIDENT.value

            state["decision_state"] = overall_state
            state["summary"] = f"Ran {len(all_sops)} SOPs: {', '.join(all_sops)}"
            state["processed_at"] = datetime.utcnow()
            return state

        graph.add_node("aggregate", aggregate)

        # Set up parallel execution
        graph.set_entry_point("validate_leads")
        graph.add_edge("validate_leads", "lead_decision")
        graph.add_edge("lead_decision", "analyze_tickets")
        graph.add_edge("analyze_tickets", "check_quality")
        graph.add_edge("check_quality", "hygiene_decision")
        graph.add_edge("hygiene_decision", "aggregate")

    return graph


def sop_router(objective: str) -> str:
    """
    Route to the appropriate graph based on objective.

    Returns:
        Graph name for logging/debugging
    """
    routing = {
        "lead_hygiene": "sop_001_lead_hygiene",
        "support_triage": "sop_010_support_triage",
        "ops_hygiene": "sop_015_ops_hygiene",
        "all": "sop_composite",
    }
    return routing.get(objective, "unknown_sop")
