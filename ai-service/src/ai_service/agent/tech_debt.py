"""Tech Debt Agent for detecting and managing technical debt in PRs.

This module provides:
- TODO comment counting
- Deprecated library detection
- Tech debt scoring
- Block/warn decision logic
"""

import logging
import re
from dataclasses import dataclass
from typing import TypedDict

logger = logging.getLogger(__name__)

# Configuration constants
TODO_THRESHOLD_WARN = 25
TODO_THRESHOLD_BLOCK = 50
DEPRECATED_LIB_BLOCK = True
MAX_DEBT_SCORE = 100

# Deprecated libraries to detect
DEPRECATED_LIBRARIES = [
    {
        "name": "moment.js",
        "patterns": [r"import\s+.*\s+from\s+['\"]moment['\"]",
                     r"require\s*\(\s*['\"]moment['\"]",
                     r"from\s+['\"]moment['\"]"],
        "recommendation": "Use 'date-fns' or 'dayjs' instead",
    },
    {
        "name": "lodash < 4",
        "patterns": [r"lodash@3\.", r"lodash@[0-3]\."],
        "recommendation": "Upgrade to lodash 4+",
    },
    {
        "name": "request",
        "patterns": [r"require\s*\(\s*['\"]request['\"]",
                     r"import\s+.*\s+from\s+['\"]request['\"]"],
        "recommendation": "Use native fetch or 'axios' instead",
    },
    {
        "name": "bluebird",
        "patterns": [r"require\s*\(\s*['\"]bluebird['\"]",
                     r"import\s+.*\s+from\s+['\"]bluebird['\"]"],
        "recommendation": "Use native Promise or 'rsvp' instead",
    },
    {
        "name": "node-sass",
        "patterns": [r"require\s*\(\s*['\"]node-sass['\"]",
                     r"import\s+.*\s+from\s+['\"]node-sass['\"]"],
        "recommendation": "Use 'sass' (Dart Sass) instead",
    },
    {
        "name": "grunt",
        "patterns": [r"require\s*\(\s*['\"]grunt['\"]"],
        "recommendation": "Consider migrating to npm scripts or 'gulp'",
    },
]


@dataclass
class DeprecatedLib:
    """Deprecated library detection result."""

    library: str
    line: str
    recommendation: str
    message: str


@dataclass
class TechDebtReport:
    """Tech debt analysis report for a PR."""

    todo_count: int
    deprecated_libs: list[dict]
    debt_score: float
    decision: str  # "approve", "warn", "block"
    exceeds_threshold: bool
    recommendations: list[str]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "todo_count": self.todo_count,
            "deprecated_libs": self.deprecated_libs,
            "debt_score": self.debt_score,
            "decision": self.decision,
            "exceeds_threshold": self.exceeds_threshold,
            "recommendations": self.recommendations,
        }


# Weight constants for debt scoring
TODO_WEIGHT = 1.5
DEPRECATED_LIB_WEIGHT = 35.0


def count_todos(diff: str) -> int:
    """Count TODO comments in a diff.

    Args:
        diff: The PR diff text

    Returns:
        Number of TODO comments found
    """
    if not diff:
        return 0

    # Pattern for TODO comments (case insensitive)
    # Must have: comment marker (#, //, /*, <!--) followed by TODO with : or space
    # Matches: # TODO:, # TODO, // TODO:, // TODO, /* TODO:, etc.
    patterns = [
        r"#\s*TODO\s*[:\-]?",          # Python/Ruby shell comments
        r"//\s*TODO\s*[:\-]?",         # C++/JavaScript/Java comments
        r"/\*\s*TODO\s*[:\-]?",        # C multi-line comments
        r"<!--\s*TODO\s*[:\-]?",       # HTML comments
    ]
    pattern = "|".join(patterns)

    count = 0
    in_docstring = False
    docstring_char = None

    for line in diff.split("\n"):
        stripped = line.strip()

        # Handle docstrings (both single-line and multi-line)
        if '"""' in stripped or "'''" in stripped:
            # Count occurrences of each delimiter
            triple_double = stripped.count('"""')
            triple_single = stripped.count("'''")

            if triple_double >= 2 or triple_single >= 2:
                # Opening and closing on same line - no change in state
                pass
            elif triple_double == 1 or triple_single == 1:
                if not in_docstring:
                    # Entering docstring
                    in_docstring = True
                    docstring_char = '"""' if triple_double else "'''"
                else:
                    # Exiting docstring (same delimiter)
                    if (docstring_char == '"""' and triple_double) or \
                       (docstring_char == "'''" and triple_single):
                        in_docstring = False
                        docstring_char = None
            continue

        if in_docstring:
            continue

        # Skip multi-line comments (opening - already inside)
        if stripped.startswith("/*") or stripped.startswith("--"):
            continue
        if stripped.startswith("<!--"):
            continue

        if re.search(pattern, line, re.IGNORECASE):
            count += 1

    return count


def detect_deprecated_libs(diff: str) -> list[DeprecatedLib]:
    """Detect deprecated library usage in diff.

    Args:
        diff: The PR diff text

    Returns:
        List of deprecated libraries found (deduped by line)
    """
    if not diff:
        return []

    # Use dict to deduplicate by line content
    seen_lines: dict[str, DeprecatedLib] = {}

    for lib in DEPRECATED_LIBRARIES:
        for pattern in lib["patterns"]:
            matches = re.finditer(pattern, diff, re.IGNORECASE)
            for match in matches:
                # Get the line containing the match
                line_start = diff.rfind("\n", 0, match.start()) + 1
                line_end = diff.find("\n", match.start())
                if line_end == -1:
                    line_end = len(diff)
                line = diff[line_start:line_end].strip()

                # Only add if we haven't seen this line before
                if line not in seen_lines:
                    seen_lines[line] = DeprecatedLib(
                        library=lib["name"],
                        line=line,
                        recommendation=lib["recommendation"],
                        message=f"Deprecated library '{lib['name']}' detected. {lib['recommendation']}",
                    )

    return list(seen_lines.values())


def calculate_debt_score(todo_count: int, deprecated_libs: list) -> float:
    """Calculate tech debt score.

    Args:
        todo_count: Number of TODO comments
        deprecated_libs: List of deprecated libraries found

    Returns:
        Debt score (0-100+)
    """
    # Handle both list and int inputs for backwards compatibility
    if isinstance(deprecated_libs, int):
        lib_count = deprecated_libs
    else:
        lib_count = len(deprecated_libs)

    # Base score from TODOs
    score = todo_count * TODO_WEIGHT

    # Add heavy weight for deprecated libraries
    score += lib_count * DEPRECATED_LIB_WEIGHT

    # Cap at MAX_DEBT_SCORE * 2 for threshold purposes
    return min(score, MAX_DEBT_SCORE * 2)


def should_block(todo_count: int, deprecated_libs: list, debt_score: float) -> bool:
    """Determine if PR should be blocked.

    Args:
        todo_count: Number of TODO comments
        deprecated_libs: List of deprecated libraries
        debt_score: Calculated debt score

    Returns:
        True if PR should be blocked
    """
    # Block if too many TODOs
    if todo_count >= TODO_THRESHOLD_BLOCK:
        return True

    # Block if any deprecated library (depending on config)
    if DEPRECATED_LIB_BLOCK and len(deprecated_libs) > 0:
        return True

    # Block if extremely high debt score
    if debt_score >= MAX_DEBT_SCORE:
        return True

    return False


def should_warn(todo_count: int, deprecated_libs: list, debt_score: float) -> bool:
    """Determine if PR should trigger a warning.

    Args:
        todo_count: Number of TODO comments
        deprecated_libs: List of deprecated libraries
        debt_score: Calculated debt score

    Returns:
        True if PR should get a warning
    """
    # Warn if high TODO count but not blocking
    if TODO_THRESHOLD_WARN <= todo_count < TODO_THRESHOLD_BLOCK:
        return True

    # Warn if debt score is elevated
    if 50 <= debt_score < MAX_DEBT_SCORE:
        return True

    return False


class AgentState(TypedDict):
    """Extended agent state for tech debt analysis."""

    pr_info: dict
    diff_files: list[dict]
    tech_debt_report: dict | None
    decision: str
    confidence: float
    reason: str


def tech_debt_analysis_node(state: AgentState) -> AgentState:
    """Analyze PR for tech debt.

    Args:
        state: Current agent state

    Returns:
        Updated state with tech debt analysis
    """
    diff_files = state.get("diff_files", [])
    pr_info = state.get("pr_info", {})

    total_todos = 0
    all_deprecated_libs = []
    all_recommendations = []

    for diff_file in diff_files:
        filename = diff_file.get("filename", "")
        patch = diff_file.get("patch", "")

        # Count TODOs
        todos = count_todos(patch)
        total_todos += todos

        # Detect deprecated libraries
        deprecated = detect_deprecated_libs(patch)
        for lib in deprecated:
            all_deprecated_libs.append({
                "library": lib.library,
                "file": filename,
                "line": lib.line,
                "message": lib.message,
                "recommendation": lib.recommendation,
            })
            if lib.recommendation not in all_recommendations:
                all_recommendations.append(lib.recommendation)

    # Calculate debt score
    debt_score = calculate_debt_score(total_todos, all_deprecated_libs)

    # Determine decision
    if should_block(total_todos, all_deprecated_libs, debt_score):
        decision = "block"
    elif should_warn(total_todos, all_deprecated_libs, debt_score):
        decision = "warn"
    else:
        decision = "approve"

    # Generate recommendations
    if total_todos > 0:
        all_recommendations.append(f"Consider resolving {total_todos} TODO(s) in this PR")

    # Build report
    report = TechDebtReport(
        todo_count=total_todos,
        deprecated_libs=all_deprecated_libs,
        debt_score=debt_score,
        decision=decision,
        exceeds_threshold=total_todos >= TODO_THRESHOLD_BLOCK,
        recommendations=all_recommendations,
    )

    logger.info(
        f"Tech Debt Analysis: PR #{pr_info.get('number')}: "
        f"{total_todos} TODOs, {len(all_deprecated_libs)} deprecated libs, "
        f"decision: {decision}"
    )

    return {
        **state,
        "tech_debt_report": report.to_dict(),
        "decision": decision,
        "confidence": 0.95 if decision == "approve" else 0.85,
        "reason": f"Tech debt analysis: {total_todos} TODOs, {len(all_deprecated_libs)} deprecated libraries",
    }


def create_tech_debt_agent():
    """Create the Tech Debt Agent StateGraph.

    Returns:
        Compiled StateGraph for tech debt analysis
    """
    from langgraph.graph import StateGraph
    from langgraph.constants import START, END

    graph = StateGraph(AgentState)

    # Add the main analysis node
    graph.add_node("analyze_tech_debt", tech_debt_analysis_node)

    # Set entry point
    graph.set_entry_point("analyze_tech_debt")
    graph.add_edge("analyze_tech_debt", END)

    return graph.compile()


# Convenience function for testing
def analyze_pr_tech_debt(pr_diff: str) -> TechDebtReport:
    """Analyze a single PR diff for tech debt.

    Args:
        pr_diff: The PR diff text

    Returns:
        TechDebtReport with analysis results
    """
    todos = count_todos(pr_diff)
    deprecated = detect_deprecated_libs(pr_diff)
    score = calculate_debt_score(todos, deprecated)

    if should_block(todos, deprecated, score):
        decision = "block"
    elif should_warn(todos, deprecated, score):
        decision = "warn"
    else:
        decision = "approve"

    return TechDebtReport(
        todo_count=todos,
        deprecated_libs=[d.to_dict() if hasattr(d, "to_dict") else {
            "library": d.library,
            "line": d.line,
            "recommendation": d.recommendation,
            "message": d.message,
        } for d in deprecated],
        debt_score=score,
        decision=decision,
        exceeds_threshold=todos >= TODO_THRESHOLD_BLOCK,
        recommendations=[d.recommendation for d in deprecated] if deprecated else [],
    )
