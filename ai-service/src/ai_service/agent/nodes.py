"""LangGraph nodes for GitHub Sentinel agent.

This module contains the node functions that process GitHub webhook events
through the Sentinel agent's decision graph.
"""

import logging
import re
from datetime import datetime
from typing import TypedDict, Literal, Any

from langgraph.graph import StateGraph

from .state import AgentState, PolicyMatch, Violation, DiffFile

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
    graph.add_node("fetch_diff", fetch_diff_node)
    graph.add_node("query_temporal", query_temporal_memory_node)
    graph.add_node("query_semantic", query_semantic_memory_node)
    graph.add_node("analyze_code", analyze_code_node)
    graph.add_node("analyze", analyze_violations_node)
    graph.add_node("recommendations", generate_recommendations_node)

    # Set entry point
    graph.set_entry_point("parse_pr")

    # Define edges
    graph.add_edge("parse_pr", "fetch_diff")
    graph.add_edge("fetch_diff", "query_temporal")
    graph.add_edge("query_temporal", "query_semantic")
    graph.add_edge("query_semantic", "analyze_code")
    graph.add_edge("analyze_code", "analyze")
    graph.add_edge("analyze", "recommendations")

    return graph.compile()


def fetch_diff_node(state: AgentState) -> AgentState:
    """Fetch and parse the PR diff using GitHub API.

    Args:
        state: Current agent state with PR info

    Returns:
        Updated state with parsed diff files
    """
    pr_info = state.get("pr_info", {})
    diff_url = pr_info.get("diff_url")

    if not diff_url:
        logger.warning("No diff URL available for PR #%d", pr_info.get("number"))
        return {
            **state,
            "diff_files": [],
            "diff_error": "No diff URL available",
        }

    # Parse repo info from webhook event
    event = state.get("webhook_event", {})
    repo = event.get("repository", {})
    repo_full_name = repo.get("full_name", "")

    # Mock GitHub client for now - in production would use PyGitHub
    # For testing, we'll parse the mock diff if present in event
    diff_files: list[DiffFile] = []

    # Check if we have mock diff data in the event
    if "files" in event:
        for file_data in event["files"]:
            diff_files.append(DiffFile(
                filename=file_data.get("filename", ""),
                status=file_data.get("status", "modified"),
                additions=file_data.get("additions", 0),
                deletions=file_data.get("deletions", 0),
                patch=file_data.get("patch"),
                language=_detect_language(file_data.get("filename", "")),
            ))
    else:
        # Generate mock diff files for testing
        # In production, this would fetch from GitHub API
        logger.info("Would fetch diff from: %s", diff_url)
        diff_files = _generate_mock_diff_files(pr_info)

    logger.info("Parsed %d files from diff", len(diff_files))
    return {
        **state,
        "diff_files": diff_files,
        "diff_error": None,
    }


def _detect_language(filename: str) -> str | None:
    """Detect programming language from filename."""
    extension_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".sql": "sql",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
    }

    for ext, lang in extension_map.items():
        if filename.endswith(ext):
            return lang
    return None


def _generate_mock_diff_files(pr_info: dict) -> list[DiffFile]:
    """Generate mock diff files for testing."""
    title = pr_info.get("title", "").lower()

    diff_files = []

    if "database" in title or "sql" in title:
        diff_files.append(DiffFile(
            filename="src/service.py",
            status="modified",
            additions=20,
            deletions=5,
            patch="""@@ -1,5 +1,10 @@
+import sqlite3
+
 def get_user(user_id):
+    conn = sqlite3.connect('app.db')
+    cursor = conn.cursor()
+    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
+    return cursor.fetchone()
-    return {"id": user_id, "name": "test"}
""",
            language="python",
        ))

    return diff_files


def analyze_code_node(state: AgentState) -> AgentState:
    """Analyze code changes using AST and pattern matching.

    Args:
        state: Current agent state with diff files

    Returns:
        Updated state with detected violations
    """
    diff_files = state.get("diff_files", [])
    temporal_policies = state.get("temporal_policies", [])
    violations: list[Violation] = []

    for diff_file in diff_files:
        filename = diff_file.get("filename", "")
        patch = diff_file.get("patch", "") or ""
        language = diff_file.get("language")

        # Check for SQL outside db/ folder
        if _contains_sql(patch) and not filename.startswith("db/"):
            # Check if there's a policy for this
            has_sql_policy = any(
                p.get("name") == "no_sql_outside_db" for p in temporal_policies
            )
            if has_sql_policy:
                violations.append(Violation(
                    type="sql_outside_db",
                    description=f"SQL query in {filename} not in db/ folder",
                    severity="warning",
                    line_numbers=_find_line_numbers(patch, ["SELECT", "INSERT", "UPDATE", "DELETE"]),
                ))

        # Check for SQL injection patterns
        if _contains_sql_injection(patch):
            violations.append(Violation(
                type="sql_injection",
                description=f"Potential SQL injection in {filename}",
                severity="blocking",
                line_numbers=_find_line_numbers(patch, ["execute(", "execute("]),
            ))

        # Check for hardcoded secrets
        if _contains_hardcoded_secrets(patch):
            violations.append(Violation(
                type="hardcoded_secret",
                description=f"Potential hardcoded secret in {filename}",
                severity="blocking",
                line_numbers=_find_line_numbers(patch, ["api_key", "secret", "password"]),
            ))

        # Check for missing license header in Python files
        if language == "python" and diff_file.get("status") == "added":
            if not _has_license_header(patch):
                violations.append(Violation(
                    type="missing_license_header",
                    description=f"Python file {filename} missing license header",
                    severity="warning",
                    line_numbers=None,
                ))

        # Check for async/await issues
        if _contains_unawaited_async(patch):
            violations.append(Violation(
                type="unawaited_async",
                description=f"Potential unawaited async call in {filename}",
                severity="warning",
                line_numbers=_find_line_numbers(patch, ["await"]),
            ))

    logger.info("Found %d violations in %d files", len(violations), len(diff_files))
    return {
        **state,
        "violations": violations,
    }


def _contains_sql(patch: str) -> bool:
    """Check if patch contains SQL statements."""
    sql_patterns = [
        r"SELECT\s+",
        r"INSERT\s+INTO",
        r"UPDATE\s+.*\s+SET",
        r"DELETE\s+FROM",
        r"CREATE\s+TABLE",
        r"DROP\s+TABLE",
        r"ALTER\s+TABLE",
    ]
    return any(re.search(pattern, patch, re.IGNORECASE) for pattern in sql_patterns)


def _contains_sql_injection(patch: str) -> bool:
    """Check for SQL injection vulnerabilities."""
    # String concatenation in SQL (e.g., "'SELECT * FROM ' + user_id")
    if re.search(r"execute\s*\(\s*['\"][^'\"]*['\"]\s*[\+\?]", patch, re.IGNORECASE):
        return True
    # f-string SQL injection
    if re.search(rf"f['\"].*{{\s*.*\s*}}.*['\"]", patch):
        return True
    return False


def _contains_hardcoded_secrets(patch: str) -> bool:
    """Check for hardcoded secret patterns."""
    secret_patterns = [
        r'api[_-]?key\s*=\s*["\'][^"\']+["\']',
        r'secret\s*=\s*["\'][^"\']{8,}["\']',
        r'password\s*=\s*["\'][^"\']+["\']',
        r'private[_-]?key\s*=\s*["\']-----BEGIN',
    ]
    return any(re.search(pattern, patch, re.IGNORECASE) for pattern in secret_patterns)


def _has_license_header(patch: str) -> bool:
    """Check if Python code has license header."""
    license_patterns = [
        r"# Copyright",
        r"# License",
        r"# SPDX-License-Identifier",
        r'"""Copyright',
        r'"""License',
    ]
    return any(re.search(pattern, patch, re.IGNORECASE) for pattern in license_patterns)


def _contains_unawaited_async(patch: str) -> bool:
    """Check for unawaited async calls."""
    # Check if there's async code but no await keyword nearby
    if "async def" in patch and "await" not in patch:
        return True
    # Check for database calls without await
    if re.search(r"\bdatabase\b.*\.\w+\s*\(", patch, re.IGNORECASE):
        if "await" not in patch:
            return True
    return False


def _find_line_numbers(patch: str, keywords: list[str]) -> list[int] | None:
    """Find line numbers containing keywords in patch."""
    lines = patch.split("\n")
    found_lines = []

    for i, line in enumerate(lines, 1):
        for keyword in keywords:
            if keyword in line:
                found_lines.append(i)
                break

    return found_lines if found_lines else None


def generate_recommendations_node(state: AgentState) -> AgentState:
    """Generate recommendations for fixing violations.

    Args:
        state: Current agent state with violations

    Returns:
        Updated state with recommendations
    """
    violations = state.get("violations", [])
    recommendations: list[dict] = []

    for violation in violations:
        violation_type = violation.get("type", "")
        rec = _get_recommendation(violation)
        if rec:
            recommendations.append(rec)

    logger.info("Generated %d recommendations", len(recommendations))
    return {
        **state,
        "recommendations": recommendations,
    }


def _get_recommendation(violation: Violation) -> dict | None:
    """Get recommendation for a specific violation."""
    violation_type = violation.get("type", "")

    recommendations = {
        "sql_outside_db": {
            "violation_type": "sql_outside_db",
            "description": violation["description"],
            "action": "Move SQL queries to db/ folder or create a repository pattern",
            "priority": "medium",
        },
        "sql_injection": {
            "violation_type": "sql_injection",
            "description": violation["description"],
            "action": "Use parameterized queries: cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))",
            "priority": "high",
        },
        "hardcoded_secret": {
            "violation_type": "hardcoded_secret",
            "description": violation["description"],
            "action": "Move secrets to environment variables or a secrets manager",
            "priority": "high",
        },
        "missing_license_header": {
            "violation_type": "missing_license_header",
            "description": violation["description"],
            "action": "Add a license header to the file (see LICENSE file for template)",
            "priority": "low",
        },
        "unawaited_async": {
            "violation_type": "unawaited_async",
            "description": violation["description"],
            "action": "Add 'await' keyword before async function calls or use background tasks",
            "priority": "medium",
        },
    }

    return recommendations.get(violation_type)


# === CFO Agent Functions ===

# AWS pricing constants (simplified)
AWS_PRICING = {
    "lambda": {
        "per_invoke": 0.0000002,  # $0.20 per 1M requests
        "per_gb_second": 0.0000166667,  # $0.20 per 1M GB-seconds
    },
    "ec2": {
        "t3_micro": 0.0104,  # $0.0104 per hour
        "t3_small": 0.0208,
        "t3_medium": 0.0416,
        "t3_large": 0.0832,
    },
    "s3": {
        "storage_per_gb": 0.023,  # $0.023 per GB-month
        "per_1000_requests": 0.0004,  # $0.40 per 1M requests
    },
    "dynamodb": {
        "per_read_unit": 0.00013,  # $0.13 per million read units
        "per_write_unit": 0.00065,  # $0.65 per million write units
    },
    "rds": {
        "t3_micro": 0.017,  # $0.017 per hour
        "t3_small": 0.034,
        "t3_medium": 0.068,
    },
    "elasticache": {
        "t3_micro": 0.014,  # $0.014 per hour
    },
    "redshift": {
        "dc2_large": 0.25,  # $0.25 per hour
    },
}


def analyze_budget_node(state: AgentState) -> AgentState:
    """Analyze PR for budget impact and cost implications.

    Args:
        state: Current agent state with PR changes

    Returns:
        Updated state with budget impact analysis
    """
    pr_changes = state.get("pr_changes", {})
    monthly_budget = state.get("monthly_budget", 500.0)

    new_services = pr_changes.get("new_services", [])
    modified_services = pr_changes.get("modified_services", [])
    deletion_services = pr_changes.get("deletion_services", [])

    # Estimate costs for new services
    estimated_costs = estimate_cost_node({
        service: _get_default_usage(service)
        for service in new_services
    })

    # Calculate monthly cost
    total_monthly_cost = sum(estimated_costs.values())

    # Determine if over budget
    overage_percentage = max(0, (total_monthly_cost / monthly_budget) - 1) * 100
    exceeds_budget = total_monthly_cost > monthly_budget

    budget_impact = {
        "new_services": new_services,
        "modified_services": modified_services,
        "deletion_services": deletion_services,
        "estimated_monthly_cost": total_monthly_cost,
        "monthly_budget": monthly_budget,
        "exceeds_budget": exceeds_budget,
        "overage_percentage": overage_percentage,
        "cost_breakdown": estimated_costs,
        "currency": "USD",
    }

    logger.info(
        f"Budget analysis: ${total_monthly_cost:.2f}/month, "
        f"budget: ${monthly_budget:.2f}, "
        f"over: {exceeds_budget}"
    )

    return {
        **state,
        "budget_impact": budget_impact,
    }


def _get_default_usage(service: str) -> dict:
    """Get default usage patterns for a service."""
    defaults = {
        "lambda": {"invocations": 100000, "duration_seconds": 0.5, "memory_mb": 256},
        "ec2": {"instance_hours": 720, "instance_type": "t3.micro"},
        "s3": {"storage_gb": 10, "requests": 10000},
        "dynamodb": {"read_units": 5, "write_units": 5},
        "rds": {"instance_hours": 720, "instance_type": "t3.micro"},
        "elasticache": {"instance_hours": 720, "instance_type": "t3.micro"},
        "redshift": {"instance_hours": 720, "instance_type": "dc2.large"},
    }
    return defaults.get(service, {})


def estimate_cost_node(service_usage: dict[str, dict]) -> dict[str, float]:
    """Estimate monthly cost for given service usage.

    Args:
        service_usage: Dict mapping service names to usage metrics

    Returns:
        Dict with cost per service and total
    """
    costs = {}
    total = 0.0

    for service, usage in service_usage.items():
        if service not in AWS_PRICING:
            logger.warning(f"Unknown service: {service}, skipping cost estimate")
            continue

        cost = 0.0
        pricing = AWS_PRICING[service]

        if service == "lambda":
            invocations = usage.get("invocations", 0)
            duration = usage.get("duration_seconds", 0.5)
            memory = usage.get("memory_mb", 256)

            # Request cost
            cost += invocations * pricing["per_invoke"]
            # Compute cost (GB-seconds)
            gb_seconds = invocations * duration * (memory / 1024)
            cost += gb_seconds * pricing["per_gb_second"]

        elif service == "ec2":
            instance_type = usage.get("instance_type", "t3.micro")
            hours = usage.get("instance_hours", 720)
            hourly_rate = pricing.get(instance_type, pricing["t3_micro"])
            cost = hours * hourly_rate

        elif service == "s3":
            storage = usage.get("storage_gb", 0)
            requests = usage.get("requests", 0)
            cost = (storage * pricing["storage_per_gb"]) + \
                   (requests / 1000) * pricing["per_1000_requests"]

        elif service == "dynamodb":
            read_units = usage.get("read_units", 0)
            write_units = usage.get("write_units", 0)
            cost = (read_units * 26280 * pricing["per_read_unit"]) + \
                   (write_units * 26280 * pricing["per_write_unit"])

        elif service in ("ec2", "rds", "elasticache", "redshift"):
            instance_type = usage.get("instance_type", "t3_micro")
            hours = usage.get("instance_hours", 720)
            key = instance_type if instance_type in pricing else f"{instance_type.split('.')[0]}_micro"
            hourly_rate = pricing.get(key, pricing.get(list(pricing.keys())[0], 0.02))
            cost = hours * hourly_rate

        costs[service] = round(cost, 2)
        total += cost

    costs["total_monthly"] = round(total, 2)
    return costs


def should_handoff_to_cfo(state: AgentState) -> bool:
    """Determine if PR should be handed off to CFO for review.

    Args:
        state: Current agent state

    Returns:
        True if handoff is recommended
    """
    budget_impact = state.get("budget_impact", {})
    estimated_cost = budget_impact.get("estimated_monthly_cost", 0)
    monthly_budget = budget_impact.get("monthly_budget", 500)

    # Handoff if cost exceeds 50% of budget
    if estimated_cost > monthly_budget * 0.5:
        return True

    # Handoff if any service is high-cost
    high_cost_services = {"rds", "elasticache", "redshift", "ec2"}
    new_services = budget_impact.get("new_services", [])
    if any(s in high_cost_services for s in new_services):
        return True

    return False


def create_cfo_handoff_state(
    pr_info: dict,
    violations: list[dict],
    budget_impact: dict,
    recommendations: list[dict],
) -> dict:
    """Create state for CFO agent handoff.

    Args:
        pr_info: Parsed PR information
        violations: List of policy violations
        budget_impact: Budget impact analysis
        recommendations: List of recommendations

    Returns:
        State dict for CFO agent
    """
    return {
        "pr_info": pr_info,
        "violations": violations,
        "budget_impact": budget_impact,
        "recommendations": recommendations,
    }


def create_cfo_agent() -> StateGraph:
    """Create the CFO agent for budget analysis.

    Returns:
        StateGraph for CFO budget analysis
    """
    from langgraph.graph import StateGraph

    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("analyze_budget", analyze_budget_node)
    graph.add_node("enforce_policy", enforce_budget_policy_node)

    # Set entry point
    graph.set_entry_point("analyze_budget")
    graph.add_edge("analyze_budget", "enforce_policy")

    return graph.compile()


def enforce_budget_policy_node(state: AgentState) -> AgentState:
    """Enforce budget policies and determine final decision.

    Args:
        state: Current agent state with budget analysis

    Returns:
        Updated state with budget enforcement decision
    """
    budget_impact = state.get("budget_impact", {})
    estimated_cost = budget_impact.get("estimated_monthly_cost", 0)
    monthly_budget = budget_impact.get("monthly_budget", 500)

    policy = {
        "monthly_budget": monthly_budget,
        "warn_threshold": 0.8,
        "block_threshold": 1.0,
    }

    result = enforce_budget_policy(estimated_cost, policy)

    # Update state based on budget decision
    new_decision = result["decision"]
    should_block = new_decision == "block"
    should_warn = new_decision == "warn"

    # Add budget-specific reason
    reason = result.get("message", "")

    return {
        **state,
        "decision": new_decision,
        "should_block": should_block,
        "should_warn": should_warn,
        "reason": reason,
    }


def enforce_budget_policy(estimated_cost: float, policy: dict) -> dict:
    """Enforce budget policy and return decision.

    Args:
        estimated_cost: Estimated monthly cost
        policy: Budget policy with thresholds

    Returns:
        Dict with decision and message
    """
    budget = policy["monthly_budget"]
    warn_threshold = budget * policy["warn_threshold"]
    block_threshold = budget * policy["block_threshold"]

    if estimated_cost <= warn_threshold:
        return {
            "decision": "approve",
            "message": None,
        }
    elif estimated_cost <= block_threshold:
        return {
            "decision": "warn",
            "message": f"Warning: Estimated cost ${estimated_cost:.2f} exceeds {policy['warn_threshold']*100:.0f}% of budget (${budget:.2f})",
        }
    else:
        return {
            "decision": "block",
            "message": f"Blocked: Estimated cost ${estimated_cost:.2f} exceeds monthly budget of ${budget:.2f}",
        }
