"""SOP Validator - Enforces Rule-Condition-Action structure.

Validates that SOPs follow the structured format required by Sentinel.
Machine-readable rules are essential for automated compliance checking.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SOPRule:
    """Parsed SOP rule with trigger, conditions, and actions.

    Attributes:
        trigger: The event that starts this SOP (e.g., "GitHub PR opened")
        conditions: List of conditions that must be met (e.g., ["No Linear Issue linked"])
        actions: List of actions to take (e.g., ["Block PR with comment"])
        severity: Severity level - "block", "warn", or "info"
        policy_name: Name of the policy file this rule came from
        raw_content: Original markdown content for reference
    """
    trigger: str
    conditions: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    severity: str = "block"
    policy_name: Optional[str] = None
    raw_content: str = ""


class SOPValidationError(ValueError):
    """Raised when SOP doesn't meet validation requirements.

    This error provides detailed feedback about which sections or
    rules are missing or malformed.
    """

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        """Initialize validation error.

        Args:
            message: Summary error message
            errors: List of specific validation errors
        """
        super().__init__(message)
        self.errors = errors or [message]


def validate_sop(content: str, filename: str = "unknown") -> list[SOPRule]:
    """Validate and parse SOP content into structured rules.

    Args:
        content: Markdown content of SOP
        filename: Name of SOP file (for error messages and rule metadata)

    Returns:
        List of parsed SOP rules

    Raises:
        SOPValidationError: If SOP doesn't meet structural requirements
    """
    errors: list[str] = []

    # Check required sections - these are mandatory for machine-readable SOPs
    required_sections = {
        "## Trigger": "What event starts this SOP",
        "## Condition": "When should this SOP apply",
        "## Action": "What should be done",
    }

    for section, description in required_sections.items():
        if section not in content:
            errors.append(f"{filename}: Missing required section '{section}' ({description})")

    if errors:
        raise SOPValidationError(
            message=f"SOP validation failed for {filename}",
            errors=errors,
        )

    # Parse rules from content
    rules = _parse_sops(content, filename)

    if not rules:
        raise SOPValidationError(
            message=f"{filename}: No valid rules found after parsing",
            errors=[f"{filename}: Could not extract any Rule-Condition-Action structures"],
        )

    logger.info(f"Validated {len(rules)} rules from {filename}")
    return rules


def _parse_sops(content: str, policy_name: str) -> list[SOPRule]:
    """Parse SOP content into rules.

    Args:
        content: Full SOP markdown content
        policy_name: Name of the policy file for metadata

    Returns:
        List of parsed SOPRule objects
    """
    rules: list[SOPRule] = []

    # Find all "## Trigger" positions and extract complete rule blocks
    # A rule block starts at ## Trigger and ends at the next ## Trigger or EOF
    trigger_positions: list[tuple[int, int, str]] = []

    for match in re.finditer(r"^## Trigger", content, re.MULTILINE | re.IGNORECASE):
        start = match.start()
        # Find the next ## Trigger or end of file
        next_match = re.search(r"^## Trigger", content[match.end():], re.MULTILINE | re.IGNORECASE)
        if next_match:
            end = match.end() + next_match.start()
        else:
            end = len(content)
        trigger_positions.append((start, end, match.group(0)))

    for start, end, trigger_name in trigger_positions:
        rule_content = content[start:end].strip()
        rule = _parse_single_rule(rule_content, policy_name)
        if rule:
            rules.append(rule)

    return rules


def _parse_single_rule(content: str, policy_name: str) -> SOPRule | None:
    """Parse a single rule block into SOPRule.

    Args:
        content: The rule block starting from ## Trigger
        policy_name: Name of the policy file

    Returns:
        Parsed SOPRule or None if invalid
    """
    # Extract trigger (everything after ## Trigger until ## Condition or ## Action)
    trigger_match = re.search(r"## Trigger\s*(.*?)(?=## (?:Condition|Action)|$)", content, re.DOTALL | re.IGNORECASE)
    trigger = trigger_match.group(1).strip() if trigger_match else ""

    if not trigger:
        return None

    # Extract conditions - lookahead for ## Action or end of content
    conditions_match = re.search(r"## Condition\s*(.*?)(?=## Action|\n\n|\Z)", content, re.DOTALL | re.IGNORECASE)
    conditions = _extract_list_items(conditions_match.group(1)) if conditions_match else []

    # Extract actions - lookahead for ## Trigger, header, or end of content
    actions_match = re.search(r"## Action\s*(.*?)(?=## (?:Trigger)|\n\n#|\Z)", content, re.DOTALL | re.IGNORECASE)
    actions = _extract_list_items(actions_match.group(1)) if actions_match else []

    # If no actions found with lookahead, try greedy match to end
    if not actions:
        trailing_match = re.search(r"## Action\s*(.*)$", content, re.DOTALL | re.IGNORECASE)
        if trailing_match:
            actions = _extract_list_items(trailing_match.group(1))

    # Determine severity from actions or conditions
    severity = _extract_severity(conditions, actions)

    return SOPRule(
        trigger=trigger,
        conditions=conditions,
        actions=actions,
        severity=severity,
        policy_name=policy_name,
        raw_content=content.strip(),
    )


def _extract_list_items(section: str) -> list[str]:
    """Extract bullet points from a section.

    Args:
        section: Markdown section content

    Returns:
        List of extracted items (without bullet markers)
    """
    items: list[str] = []
    for line in section.split("\n"):
        line = line.strip()
        # Match common bullet markers: - *, 1. (ordered), or just text lines
        if line.startswith("- ") or line.startswith("* "):
            items.append(line[2:].strip())
        elif re.match(r"^\d+[\.\)]\s+", line):
            # Remove numbered list prefix
            items.append(re.sub(r"^\d+[\.\)]\s+", "", line).strip())
        elif line and not line.startswith("##"):
            # Non-empty non-header lines are also included
            items.append(line)

    return items


def _extract_severity(conditions: list[str], actions: list[str]) -> str:
    """Determine severity level from conditions and actions.

    Args:
        conditions: List of condition strings
        actions: List of action strings

    Returns:
        Severity level: "block", "warn", or "info"
    """
    text = " ".join(conditions + actions).lower()

    if "block" in text or "reject" in text or "prevent" in text:
        return "block"
    elif "warn" in text or "alert" in text or "notify" in text:
        return "warn"
    else:
        return "info"


def validate_rule_structure(rule: SOPRule) -> list[str]:
    """Validate a single parsed rule for completeness.

    Args:
        rule: Parsed SOPRule to validate

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[str] = []

    if not rule.trigger:
        errors.append("Rule missing trigger section")

    if not rule.conditions:
        errors.append("Rule missing condition items")

    if not rule.actions:
        errors.append("Rule missing action items")

    if rule.severity not in ("block", "warn", "info"):
        errors.append(f"Invalid severity level: {rule.severity}")

    return errors
