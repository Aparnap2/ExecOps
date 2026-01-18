"""Sentinel LangGraph Nodes.

Reusable node functions for the Sentinel PR review workflow.
Integrates with existing GitHubClient, SlackClient, GraphService, SOPLoader,
and LLMService (Ollama/Qwen) for intelligent compliance analysis.
"""

import logging
import re
from typing import Any

from langgraph.types import Command

from .state import SentinelState
from ai_service.memory.graph import GraphService
from ai_service.sop.loader import SOPLoader
from ai_service.llm.service import get_llm_service, analyze_pr_compliance
from ai_service.integrations.github import GitHubClient
from ai_service.integrations.slack import SlackClient, PRSummary, Decision

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration (loaded from environment)
# =============================================================================

def _get_github_client(use_mock: bool = False):
    """Get GitHubClient from environment variables.

    Args:
        use_mock: If True, return mock client for testing
    """
    import os

    if use_mock:
        from ai_service.integrations.mock_clients import MockGitHubClient
        return MockGitHubClient(
            owner=os.getenv("GITHUB_REPO_OWNER", "test-owner"),
            repo=os.getenv("GITHUB_REPO_NAME", "test-repo"),
        )

    return GitHubClient(
        token=os.getenv("GITHUB_TOKEN", ""),
        owner=os.getenv("GITHUB_REPO_OWNER", ""),
        repo=os.getenv("GITHUB_REPO_NAME", ""),
    )


def _get_slack_client(use_mock: bool = False):
    """Get SlackClient from environment variables.

    Args:
        use_mock: If True, return mock client for testing
    """
    import os

    if use_mock:
        from ai_service.integrations.mock_clients import MockSlackClient
        return MockSlackClient(webhook_url=os.getenv("SLACK_WEBHOOK_URL", "http://mock.slack"))

    return SlackClient(webhook_url=os.getenv("SLACK_WEBHOOK_URL", ""))


# =============================================================================
# Node: Extract Linear Context
# =============================================================================

async def extract_linear_context(state: SentinelState) -> SentinelState:
    """Extract Linear Issue ID from PR body and query Neo4j for context.

    This node:
    1. Searches PR body for LIN-XXX pattern
    2. Queries Neo4j for issue state, labels, and comments
    3. Returns updated state with linear_issue_id and issue_context

    Args:
        state: Current SentinelState with pr_body

    Returns:
        Updated state with linear context populated
    """
    pr_body = state.get("pr_body", "") or ""
    pr_id = state.get("pr_id", "") or "unknown"

    logger.info(f"Extracting Linear context for PR {state.get('pr_number', 'unknown')}")

    # Extract LIN-XXX pattern from PR body
    match = re.search(r"LIN-(\d+)", pr_body)
    linear_issue_id: str | None = f"LIN-{match.group(1)}" if match else None

    issue_context: dict[str, Any] | None = None
    issue_state: str | None = None
    issue_labels: list[str] = []

    # Query Neo4j for issue context if found
    if linear_issue_id:
        graph = GraphService()
        try:
            issue_context = await graph.get_issue_context(linear_issue_id)
            if issue_context:
                issue_data = issue_context.get("issue", {})
                issue_state = issue_data.get("state") if issue_data else None
                issue_labels = issue_context.get("labels", [])
                logger.info(
                    f"Found Linear issue {linear_issue_id}: state={issue_state}, "
                    f"labels={issue_labels}"
                )
            else:
                logger.warning(f"Linear issue {linear_issue_id} not found in Neo4j")
        except Exception as e:
            logger.error(f"Failed to query Neo4j for {linear_issue_id}: {e}")
        finally:
            await graph.close()

        # Link PR to issue in graph
        try:
            graph = GraphService()
            await graph.link_pr_to_issue(pr_id, linear_issue_id)
            await graph.close()
        except Exception as e:
            logger.warning(f"Failed to link PR to issue: {e}")

    if not linear_issue_id:
        logger.info("No Linear issue linked in PR body")

    return {
        **state,
        "linear_issue_id": linear_issue_id,
        "linear_issue_state": issue_state,
        "linear_issue_labels": issue_labels,
        "issue_context": issue_context,
    }


# =============================================================================
# Node: Check Compliance (LLM-Powered)
# =============================================================================

async def check_compliance(
    state: SentinelState,
    use_llm: bool = True,
    use_mock: bool = False,
) -> SentinelState:
    """Check PR compliance against deployment SOPs.

    Uses LLM (Qwen 2.5 Coder via Ollama) for intelligent analysis when available,
    falling back to rule-based checks if LLM is unavailable.

    Validates:
    1. Linear issue is linked in PR body
    2. Linked issue is in valid state (IN_PROGRESS or REVIEW)
    3. Issue does not have "Needs Spec" label
    4. Calculates risk score based on graph context

    Args:
        state: Current SentinelState with linear context
        use_llm: If True, use LLM for compliance analysis
        use_mock: If True, use mock clients for testing

    Returns:
        Updated state with violations, risk_score, and sentinel_decision
    """
    import os

    logger.info(f"Checking compliance for PR #{state.get('pr_number', 'unknown')}")

    # First, run rule-based checks to get violations and risk score
    violations: list[str] = []
    pr_id = state.get("pr_id", "")

    # Rule 1: Must have Linear Issue linked
    if not state.get("linear_issue_id"):
        violations.append("No Linear Issue linked (add LIN-XXX to PR body)")

    # Rule 2: Linked Issue must be in valid state
    issue_state = state.get("linear_issue_state")
    valid_states = ["IN_PROGRESS", "REVIEW"]
    if issue_state and issue_state not in valid_states:
        violations.append(
            f"Linked Issue is in '{issue_state}' state "
            f"(must be IN_PROGRESS or REVIEW)"
        )

    # Rule 3: Check for "Needs Spec" label
    issue_labels = state.get("linear_issue_labels", [])
    if "Needs Spec" in issue_labels:
        violations.append(
            "Linked Issue has 'Needs Spec' label - spec must be finalized first"
        )

    # Calculate risk score from Neo4j
    risk_score: float = 0.5  # Default moderate risk
    if pr_id:
        graph = GraphService()
        try:
            risk_score = await graph.get_pr_risk_score(pr_id)
            logger.info(f"Risk score for PR: {risk_score}")
        except Exception as e:
            logger.error(f"Failed to calculate risk score: {e}")
        finally:
            await graph.close()

    # Use LLM for intelligent compliance analysis
    llm_decision = None
    llm_reason = None

    if use_llm and os.getenv("USE_LLM_COMPLIANCE", "true").lower() == "true":
        try:
            llm = get_llm_service()
            llm_healthy = await llm.check_health()

            if llm_healthy:
                logger.info("Using LLM for compliance analysis...")

                # Prepare PR info for LLM
                pr_info = {
                    "number": state.get("pr_number", 0),
                    "title": state.get("pr_title", ""),
                    "body": state.get("pr_body", "")[:500],
                    "author": state.get("pr_author", ""),
                }

                # Get full deployment policy for LLM context
                sop_loader = SOPLoader()
                deployment_policy = await sop_loader.get_deployment_rules()

                # Analyze with LLM
                llm_result = await analyze_pr_compliance(
                    pr_info=pr_info,
                    issue_context=state.get("issue_context"),
                    violations=violations,
                    risk_score=risk_score,
                    llm=llm,
                )

                llm_decision = llm_result.get("decision", "pass")
                llm_reason = llm_result.get("reason", "")
                logger.info(f"LLM compliance decision: {llm_decision} - {llm_reason}")
            else:
                logger.warning("LLM health check failed, using rule-based compliance")
        except Exception as e:
            logger.error(f"LLM compliance analysis failed: {e}, using rule-based")

    # Use LLM decision if available, otherwise rule-based
    if llm_decision:
        sentinel_decision = llm_decision
        if llm_reason:
            # Add LLM reasoning to state for transparency
            violations = violations + [f"LLM Analysis: {llm_reason}"]
    else:
        # Rule-based decision
        if violations:
            has_blocking_violation = not state.get("linear_issue_id")
            sentinel_decision = "block" if has_blocking_violation else "warn"
        else:
            sentinel_decision = "pass"

    logger.info(
        f"Compliance check complete: decision={sentinel_decision}, "
        f"violations={len(violations)}, risk={risk_score:.2f}"
    )

    return {
        **state,
        "violations": violations,
        "risk_score": risk_score,
        "sentinel_decision": sentinel_decision,
        "status": "analyzed",
        "llm_analysis": {
            "used": llm_decision is not None,
            "decision": llm_decision,
            "reason": llm_reason,
        } if llm_decision else None,
    }


# =============================================================================
# Node: Send for Approval
# =============================================================================

async def send_for_approval(
    state: SentinelState,
    use_mock: bool = False,
) -> Command:
    """Send PR to Slack for human approval via interrupt.

    For "pass" decisions, auto-proceed to execute.
    For "block"/"warn" decisions, send Slack notification and interrupt
    waiting for human decision.

    Args:
        state: Current SentinelState with analysis complete

    Returns:
        Command to goto either "execute" or waiting for interrupt resume
    """
    pr_number = state.get("pr_number", 0)
    pr_title = state.get("pr_title", "Unknown")
    pr_author = state.get("pr_author", "unknown")
    violations = state.get("violations", [])
    risk_score = state.get("risk_score", 0.5)
    decision = state.get("sentinel_decision", "pass")

    logger.info(f"Sending PR #{pr_number} for approval (decision: {decision})")

    # Auto-approve if no violations
    if decision == "pass":
        logger.info(f"PR #{pr_number} passed compliance - auto-approving")
        return Command(goto="execute")

    # Send Slack notification for block/warn decisions
    slack_client = _get_slack_client(use_mock=use_mock)

    decision_enum = Decision.BLOCK if decision == "block" else Decision.WARN

    pr_summary = PRSummary(
        number=pr_number,
        title=pr_title,
        author=pr_author,
        decision=decision_enum,
        confidence=1.0 - risk_score,
        violations=violations,
        recommendations=_get_recommendations(violations),
        url=state.get("pr_url", ""),
    )

    try:
        await slack_client.notify_pr_review(pr_summary)
        logger.info(f"Slack notification sent for PR #{pr_number}")
    except Exception as e:
        logger.error(f"Failed to send Slack notification: {e}")

    # Interrupt and wait for Slack response via webhook
    interrupt_data = {
        "type": "sentinel_proposal",
        "pr_number": pr_number,
        "pr_title": pr_title,
        "pr_author": pr_author,
        "violations": violations,
        "risk_score": risk_score,
        "decision": decision,
        "actions": ["approve", "reject"],
    }

    logger.info(f"Interrupting for approval on PR #{pr_number}")
    result = interrupt(interrupt_data)

    # Check resume value for decision
    if result and result.get("action") == "approve":
        return Command(goto="execute")
    else:
        return Command(goto="reject")


def _get_recommendations(violations: list[str]) -> list[str]:
    """Generate recommendations based on violations."""
    recommendations = []

    for violation in violations:
        if "No Linear Issue" in violation:
            recommendations.append("Link a Linear issue to this PR")
        elif "BACKLOG" in violation or "state" in violation:
            recommendations.append("Move issue to IN_PROGRESS or REVIEW")
        elif "Needs Spec" in violation:
            recommendations.append("Complete the specification before merging")

    return recommendations


# =============================================================================
# Node: Execute
# =============================================================================

async def execute(
    state: SentinelState,
    use_mock: bool = False,
) -> SentinelState:
    """Execute the approved Sentinel action on GitHub.

    Actions:
    - block: Comment on PR with violation details
    - warn: Post warning comment
    - pass: Approve PR (optional)

    Args:
        state: Approved SentinelState with sentinel_decision

    Returns:
        Updated state with execution results
    """
    pr_number = state.get("pr_number", 0)
    pr_title = state.get("pr_title", "Unknown")
    decision = state.get("sentinel_decision", "pass")
    violations = state.get("violations", [])

    logger.info(f"Executing Sentinel decision '{decision}' on PR #{pr_number}")

    github_client = _get_github_client(use_mock=use_mock)

    # Generate comment body based on decision
    if decision == "block":
        comment_body = (
            f"**Sentinel Blocked**\n\n"
            f"This PR has been blocked due to compliance violations:\n\n"
            + "\n".join(f"- {v}" for v in violations)
            + "\n\n"
            f"Please address these issues before requesting review again."
        )

        await github_client.comment_on_pr(
            pr_number=pr_number,
            body=comment_body,
        )

        # Request changes via review
        await github_client.create_pull_request_review(
            pr_number=pr_number,
            event="REQUEST_CHANGES",
            body="Sentinel compliance check failed",
        )

        logger.info(f"PR #{pr_number} blocked with comment")

    elif decision == "warn":
        comment_body = (
            f"**Sentinel Warning**\n\n"
            f"The following issues were detected:\n\n"
            + "\n".join(f"- {v}" for v in violations)
            + "\n\n"
            f"Consider addressing these before merging."
        )

        await github_client.comment_on_pr(
            pr_number=pr_number,
            body=comment_body,
        )

        logger.info(f"PR #{pr_number} warned with comment")

    else:  # pass - auto approve
        try:
            await github_client.create_pull_request_review(
                pr_number=pr_number,
                event="APPROVE",
                body="Sentinel compliance check passed",
            )
            logger.info(f"PR #{pr_number} auto-approved")
        except Exception as e:
            logger.warning(f"Failed to auto-approve PR: {e}")

    from datetime import datetime, timezone

    return {
        **state,
        "status": "executed",
        "approval_decision": "approved",
        "ready_to_execute": True,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }


# =============================================================================
# Node: Reject
# =============================================================================

async def reject(state: SentinelState) -> SentinelState:
    """Log rejection when human reviewer denies the action.

    Args:
        state: SentinelState with rejection decision

    Returns:
        Updated state marked as rejected
    """
    pr_number = state.get("pr_number", 0)
    rejection_reason = state.get("rejection_reason", "No reason provided")

    logger.info(
        f"Sentinel decision rejected for PR #{pr_number}: {rejection_reason}"
    )

    return {
        **state,
        "status": "rejected",
        "approval_decision": "rejected",
        "ready_to_execute": False,
    }


__all__ = [
    "extract_linear_context",
    "check_compliance",
    "send_for_approval",
    "execute",
    "reject",
]
