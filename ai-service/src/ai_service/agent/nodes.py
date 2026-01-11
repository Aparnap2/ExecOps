"""LangGraph nodes for GitHub Sentinel agent.

This module contains the node functions that process GitHub webhook events
through the Sentinel agent's decision graph.
"""

import logging
import re
from datetime import datetime
from typing import TypedDict, Literal, Any

from langgraph.graph import StateGraph

from .state import AgentState, PolicyMatch, Violation

logger = logging.getLogger(__name__)


def parse_pr_node(state: AgentState) -> AgentState:
    """Parse the PR information from the webhook payload.

    Args:
        state: Current agent state

    Returns:
        Updated state with parsed PR info
    """
    event = state["webhook_event"]
    action = state["webhook_action"]

    logger.info(f"Parsing PR for action: {action}")

    # Handle different webhook event structures
    if "pull_request" in event:
        pr = event["pull_request"]
        pr_info = {
            "number": pr.get("number", 0),
            "title": pr.get("title", ""),
            "author": pr.get("user", {}).get("login", "unknown"),
            "action": action,
            "diff_url": pr.get("diff_url"),
            "head_sha": pr.get("head", {}).get("sha", ""),
            "base_sha": pr.get("base", {}).get("sha", ""),
        }
    elif "repository" in event and "pull_request" in event.get("sender", {}):
        # Alternative structure from some webhook formats
        pr = event.get("pull_request", {})
        pr_info = {
            "number": pr.get("number", 0),
            "title": pr.get("title", ""),
            "author": event.get("sender", {}).get("login", "unknown"),
            "action": action,
            "diff_url": pr.get("diff_url"),
            "head_sha": pr.get("head", {}).get("sha", ""),
            "base_sha": pr.get("base", {}).get("sha", ""),
        }
    else:
        # Fallback for incomplete payloads
        pr_info = {
            "number": 0,
            "title": "",
            "author": "unknown",
            "action": action,
            "diff_url": None,
            "head_sha": "",
            "base_sha": "",
        }
        logger.warning("Could not parse PR info from webhook payload")

    logger.info(f"Parsed PR #{pr_info['number']}: {pr_info['title']}")
    return {**state, "pr_info": pr_info}


def query_temporal_memory_node(state: AgentState) -> AgentState:
    """Query temporal memory (Neo4j/Graphiti) for active policies.

    Args:
        state: Current agent state

    Returns:
        Updated state with temporal policies
    """
    from ..memory.graphiti_client import TemporalMemory

    # Get PR content for policy search
    pr_info = state.get("pr_info", {})
    query = f"{pr_info.get('title', '')} {pr_info.get('action', '')}"

    # Create mock temporal memory for now
    # In production, this would connect to Graphiti
    policies: list[PolicyMatch] = []

    # Built-in policies based on common patterns
    built_in_policies = [
        PolicyMatch(
            name="no_sql_outside_db",
            rule="No direct SQL queries allowed outside db/ folder",
            valid_from=datetime(2024, 1, 1),
            valid_to=None,
            similarity=1.0,
        ),
        PolicyMatch(
            name="no_deploy_friday",
            rule="No deployments on Fridays",
            valid_from=datetime(2024, 1, 1),
            valid_to=None,
            similarity=0.8,
        ),
    ]

    policies.extend(built_in_policies)

    logger.info(f"Retrieved {len(policies)} temporal policies")
    return {**state, "temporal_policies": policies}


def query_semantic_memory_node(state: AgentState) -> AgentState:
    """Query semantic memory (pgvector) for similar past decisions.

    Args:
        state: Current agent state

    Returns:
        Updated state with similar contexts
    """
    from ..memory.vector_store import SemanticMemory

    pr_info = state.get("pr_info", {})
    query = pr_info.get("title", "")

    # Mock semantic search results for now
    # In production, this would search pgvector
    similar_contexts = []

    logger.info(f"Searched semantic memory for: '{query}'")
    return {**state, "similar_contexts": similar_contexts}


def analyze_violations_node(state: AgentState) -> AgentState:
    """Analyze PR against policies to find violations.

    Args:
        state: Current agent state

    Returns:
        Updated state with violations and decision
    """
    pr_info = state.get("pr_info", {})
    temporal_policies = state.get("temporal_policies", [])
    similar_contexts = state.get("similar_contexts", [])

    violations: list[Violation] = []
    should_block = False
    should_warn = False

    # Get diff content from event (mock - in production would fetch)
    pr_title = pr_info.get("title", "").lower()
    pr_action = pr_info.get("action", "")

    # Check 1: SQL outside db/ folder (simulated)
    sql_patterns = [
        r"SELECT\s+.*\s+FROM",
        r"INSERT\s+INTO",
        r"UPDATE\s+.*\s+SET",
        r"DELETE\s+FROM",
    ]

    # Check for SQL-related PR titles
    if any(keyword in pr_title for keyword in ["sql", "query"]):
        if "db/" not in pr_title:
            violations.append(
                Violation(
                    type="sql_outside_db",
                    description="PR mentions SQL but may not be in db/ folder",
                    severity="warning",
                    line_numbers=None,
                )
            )
            should_warn = True

    # Check 2: Friday deployment policy
    if any(p["name"] == "no_deploy_friday" for p in temporal_policies):
        if datetime.utcnow().weekday() == 4:  # Friday = 4
            violations.append(
                Violation(
                    type="friday_deploy",
                    description="Policy: No Friday Deploys",
                    severity="blocking",
                    line_numbers=None,
                )
            )
            should_block = True

    # Check 3: Based on similar past decisions
    for context in similar_contexts:
        if "blocked" in context.get("content", "").lower():
            violations.append(
                Violation(
                    type="similar_blocked_pr",
                    description="Similar PR was previously blocked",
                    severity="warning",
                    line_numbers=None,
                )
            )
            should_warn = True

    # Determine decision
    if should_block:
        decision: Literal["block", "warn", "approve"] = "block"
    elif should_warn:
        decision = "warn"
    else:
        decision = "approve"

    # Calculate confidence
    confidence = 1.0
    if violations:
        confidence = 1.0 - (len(violations) * 0.1)
    confidence = max(0.5, min(1.0, confidence))

    # Generate messages
    blocking_message = None
    warning_message = None

    if violations:
        reason = f"Found {len(violations)} violation(s)"
    else:
        reason = "No policy violations found"

    return {
        **state,
        "violations": violations,
        "should_block": should_block,
        "should_warn": should_warn,
        "blocking_message": blocking_message,
        "warning_message": warning_message,
        "decision": decision,
        "confidence": confidence,
        "reason": reason,
    }


def format_block_message(violations: list[Violation]) -> str:
    """Format a blocking message with all violations.

    Args:
        violations: List of policy violations

    Returns:
        Formatted markdown message
    """
    if not violations:
        return ""

    lines = [
        "🚫 **PR Blocked by FounderOS Sentinel**",
        "",
        "**Violations Found:**",
    ]

    for v in violations:
        severity_emoji = "🔴" if v["severity"] == "blocking" else "🟡"
        lines.append(f"{severity_emoji} **{v['type']}**: {v['description']}")

    lines.extend(
        [
            "",
            "---",
            "_This action was automatically generated based on active policies._",
            "_Temporal memory check: " + datetime.utcnow().isoformat() + "_",
        ]
    )

    return "\n".join(lines)


def format_warning_message(violations: list[Violation]) -> str:
    """Format a warning message with all violations.

    Args:
        violations: List of policy violations

    Returns:
        Formatted markdown message
    """
    if not violations:
        return ""

    lines = [
        "⚠️ **FounderOS Sentinel Advisory**",
        "",
        "**Notes:**",
    ]

    for v in violations:
        lines.append(f"- **{v['type']}**: {v['description']}")

    lines.extend(
        [
            "",
            "_Review recommended but not required._",
        ]
    )

    return "\n".join(lines)


def create_sentinel_agent() -> StateGraph:
    """Create the GitHub Sentinel LangGraph agent.

    Returns:
        Compiled StateGraph for PR analysis
    """
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("parse_pr", parse_pr_node)
    graph.add_node("query_temporal", query_temporal_memory_node)
    graph.add_node("query_semantic", query_semantic_memory_node)
    graph.add_node("analyze", analyze_violations_node)

    # Set entry point
    graph.set_entry_point("parse_pr")

    # Define edges
    graph.add_edge("parse_pr", "query_temporal")
    graph.add_edge("query_temporal", "query_semantic")
    graph.add_edge("query_semantic", "analyze")

    return graph.compile()
