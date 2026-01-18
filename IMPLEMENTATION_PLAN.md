# ExecOps Implementation Plan: Sentinel Vertical

## Executive Summary

**Goal:** Build a "Virtual Staff" that enforces process on GitHub PRs using Linear context and SOPs, with Slack as the primary interface.

**Scope:** Sentinel Agent (Linear + GitHub + Slack) only. Proof of concept for "Graph Brain."

**Key Principle:** **EXTEND, don't replace.** Leverage existing code patterns.

---

## 0. Existing Code to REUSE

| File | Reuse For |
|------|-----------|
| `integrations/github.py` | `GitHubClient.comment_on_pr()`, `create_pull_request_review()` |
| `integrations/slack.py` | `SlackClient`, `SlackMessageBuilder`, `SlackWebhookHandler` |
| `integrations/executor.py` | `SlackExecutor`, `WebhookExecutor` patterns |
| `graphs/vertical_agents.py` | `create_vertical_agent_graph()` pattern, `human_approval_node`, checkpointer integration |
| `infrastructure/checkpointer.py` | `get_async_checkpointer()`, `get_sync_checkpointer()` |
| `memory/graphiti_client.py` | Neo4j connection - extract to `GraphService` (keep connection pattern) |
| `memory/vector_store.py` | SOP semantic search (keep as-is) |

---

## 1. Architecture Transformation

### Current State
```
ai-service/
├── memory/
│   ├── vector_store.py      # pgvector (keep)
│   └── graphiti_client.py   # REFACTOR to raw Neo4j GraphService
├── graphs/
│   └── vertical_agents.py   # EXTEND with sentinel vertical
├── integrations/
│   ├── github.py            # Already exists (reuse)
│   ├── slack.py             # Already exists (reuse)
│   └── executor.py          # EXTEND with GitHubExecutor
└── main.py                  # Add webhook routes
```

### Target State
```
ai-service/
├── memory/
│   ├── vector_store.py      # (keep)
│   └── graph.py             # NEW: Raw Neo4j GraphService (refactor from graphiti)
├── agents/
│   └── sentinel/            # NEW: Sentinel-specific nodes
│       ├── state.py         # SentinelState TypedDict
│       ├── nodes.py         # analyze_pr, check_compliance, request_approval
│       └── executor.py      # SentinelExecutor (reuses GitHubClient, SlackClient)
├── sop/                     # NEW: SOP management
│   ├── loader.py            # Load SOPs using vector_store
│   └── validator.py         # Rule-Condition-Action validator
├── webhooks/                # NEW: Webhook handlers
│   ├── github.py            # GitHub PR webhook
│   └── linear.py            # Linear webhook
└── main.py                  # Add webhook routes
```

---

## 2. Phase-by-Phase Implementation

### Phase 1: Refactor Graphiti → Raw Neo4j GraphService

**File:** `ai-service/src/ai_service/memory/graph.py`

```python
"""Raw Neo4j GraphService for Sentinel.

Extracted from graphiti_client.py - keeps the Neo4j connection,
replaces Graphiti abstraction with raw Cypher queries.
"""

import logging
from typing import Any
from neo4j import AsyncGraphDatabase

from ai_service.infrastructure.checkpointer import get_database_url

logger = logging.getLogger(__name__)


class GraphService:
    """Raw Neo4j Cypher queries for Sentinel use case.

    Replaces Graphiti for custom relationship queries.
    """

    def __init__(self, uri: str = None, user: str = None, password: str = None):
        """Initialize Neo4j connection.

        Args:
            uri: Neo4j URI (uses env or default from checkpointer)
            user: Neo4j user
            password: Neo4j password
        """
        if not uri:
            db_url = get_database_url()
            # Parse postgres://... format to get neo4j credentials
            # For dev, uses defaults
            uri = "bolt://localhost:7687"
            user = "neo4j"
            password = "neo4j"

        self._driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def close(self) -> None:
        """Close Neo4j connection."""
        await self._driver.close()

    async def query(self, cypher: str, **params) -> list[dict[str, Any]]:
        """Execute raw Cypher query.

        Args:
            cypher: Cypher query string
            **params: Query parameters

        Returns:
            List of result dictionaries
        """
        async with self._driver.session() as session:
            result = await session.run(cypher, **params)
            return [dict(record) async for record in result]

    # =====================================================================
    # Sentinel-Specific Queries
    # =====================================================================

    async def link_pr_to_issue(self, pr_id: str, issue_id: str) -> None:
        """Create PR -> IMPLEMENTS -> Issue relationship.

        Uses MERGE for idempotency.
        """
        await self.query("""
            MERGE (p:PR {id: $pr_id})
            MERGE (i:Issue {id: $issue_id})
            MERGE (p)-[:IMPLEMENTS]->(i)
        """, pr_id=pr_id, issue_id=issue_id)

    async def get_issue_context(self, issue_id: str) -> dict | None:
        """Fetch full issue context for PR review.

        Returns:
            Dict with issue state, labels, or None if not found
        """
        results = await self.query("""
            MATCH (i:Issue {id: $id})
            OPTIONAL MATCH (i)<-[:LINKED_TO]-(c:Comment)
            OPTIONAL MATCH (i)-[:HAS_LABEL]->(l:Label)
            RETURN i {.id, .title, .state, .description},
                   labels: collect(l.name),
                   comment_count: count(c)
        """, id=issue_id)

        return results[0] if results else None

    async def get_pr_risk_score(self, pr_id: str) -> float:
        """Calculate risk score based on graph context.

        Returns:
            Risk score 0.0 to 1.0
        """
        results = await self.query("""
            MATCH (p:PR {id: $id})-[:IMPLEMENTS]->(i:Issue)
            WITH p, i,
                 CASE WHEN i.state = 'BACKLOG' THEN 0.3 ELSE 0 END as state_risk,
                 CASE WHEN exists((i)-[:HAS_LABEL]->(:Label {name: 'Needs Spec'})) THEN 0.4 ELSE 0 END as spec_risk
            RETURN state_risk + spec_risk as risk_score
        """, id=pr_id)

        if results:
            return float(results[0].get("risk_score", 0.0))
        return 0.7  # No context = high risk

    async def ensure_constraints(self) -> None:
        """Create Neo4j constraints for data integrity."""
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (i:Issue) REQUIRE i.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:PR) REQUIRE p.id IS UNIQUE",
        ]
        for cypher in constraints:
            await self.query(cypher)

    async def __aenter__(self) -> "GraphService":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


# Convenience: Get GraphService from existing graphiti config
def get_graph_service() -> GraphService:
    """Get GraphService instance.

    Can be extended to read from existing graphiti config.
    """
    return GraphService()
```

---

### Phase 2: SOP Validator (Rule-Condition-Action)

**File:** `ai-service/src/ai_service/sop/validator.py`

```python
"""SOP Validator - Enforces Rule-Condition-Action structure.

Validates that SOPs follow the structured format required by Sentinel.
"""

import re
from dataclasses import dataclass
from typing import list
from pathlib import Path


@dataclass
class SOPRule:
    """Parsed SOP rule."""
    trigger: str           # e.g., "GitHub PR opened"
    conditions: list[str]  # e.g., ["No Linear Issue linked"]
    actions: list[str]    # e.g., ["Block PR with comment"]
    severity: str         # "block" | "warn" | "info"
    raw_content: str      # Original markdown


class SOPValidationError(ValueError):
    """Raised when SOP doesn't meet validation requirements."""
    pass


def validate_sop(content: str, filename: str = "unknown") -> list[SOPRule]:
    """Validate and parse SOP content.

    Args:
        content: Markdown content of SOP
        filename: Name of SOP file (for error messages)

    Returns:
        List of parsed SOP rules

    Raises:
        SOPValidationError: If SOP doesn't meet requirements
    """
    errors: list[str] = []

    # Check required sections
    required_sections = {
        "## Trigger": "What event starts this SOP",
        "## Condition": "When should this SOP apply",
        "## Action": "What should be done",
    }

    for section, desc in required_sections.items():
        if section not in content:
            errors.append(f"{filename}: Missing required section '{section}' ({desc})")

    if errors:
        raise SOPValidationError("\n".join(errors))

    # Parse rules
    rules = _parse_sops(content)

    if not rules:
        raise SOPValidationError(f"{filename}: No valid rules found")

    return rules


def _parse_sops(content: str) -> list[SOPRule]:
    """Parse SOP content into rules."""
    rules = []

    # Split on "## Trigger" to find individual rules
    # This is a simple parser - can be enhanced
    sections = re.split(r"(## Trigger\s*\n)", content)

    trigger = ""
    conditions = []
    actions = []
    severity = "block"

    for section in sections:
        section = section.strip()
        if not section:
            continue

        if section.startswith("## Trigger"):
            # Save previous rule
            if trigger and (conditions or actions):
                rules.append(SOPRule(
                    trigger=trigger,
                    conditions=conditions,
                    actions=actions,
                    severity=severity,
                    raw_content=f"## Trigger\n{trigger}\n## Condition\n...",
                ))

            # Start new rule
            trigger = section.replace("## Trigger", "").strip()
            conditions = []
            actions = []
        elif section.startswith("## Condition"):
            conditions = _extract_list_items(section.replace("## Condition", ""))
        elif section.startswith("## Action"):
            actions = _extract_list_items(section.replace("## Action", ""))

    # Don't forget last rule
    if trigger and (conditions or actions):
        rules.append(SOPRule(
            trigger=trigger,
            conditions=conditions,
            actions=actions,
            severity=severity,
            raw_content=f"## Trigger\n{trigger}\n## Condition\n...",
        ))

    return rules


def _extract_list_items(section: str) -> list[str]:
    """Extract bullet points from section."""
    items = []
    for line in section.split("\n"):
        line = line.strip()
        if line.startswith("- ") or line.startswith("* "):
            items.append(line[2:].strip())
    return items
```

**File:** `ai-service/src/ai_service/sop/loader.py`

```python
"""Load SOPs from data/sops/ directory.

IMPORTANT: For Compliance SOPs, read the FULL file. Vector search is for
finding "Past Precedent" (how did we handle this last time?), NOT for
active rules. Compliance cannot be fuzzy.

Use vector_store only for historical precedent queries.
"""

import logging
from pathlib import Path
from typing import list

logger = logging.getLogger(__name__)


class SOPLoader:
    """Load and manage SOPs."""

    def __init__(self, sop_dir: str = "data/sops"):
        """Initialize SOP loader.

        Args:
            sop_dir: Directory containing SOP markdown files
        """
        self.sop_dir = Path(sop_dir)

    async def get_full_policy(self, policy_name: str) -> str:
        """Get the FULL deployment/compliance policy text.

        Why: Compliance cannot be fuzzy. We need the LLM to see the
        whole law to understand exceptions (e.g., "Friday deploys are
        blocked EXCEPT for emergency hotfixes").

        Args:
            policy_name: Name of policy file (e.g., "deployment_policy")

        Returns:
            Full policy text, or empty string if not found
        """
        policy_path = self.sop_dir / f"{policy_name}.md"

        if not policy_path.exists():
            logger.warning(f"Policy file not found: {policy_path}")
            return ""

        content = policy_path.read_text()
        logger.info(f"Loaded full policy: {policy_name} ({len(content)} chars)")
        return content

    async def get_deployment_rules(self) -> str:
        """Get FULL deployment policy text for compliance checking.

        Returns:
            Complete deployment_policy.md content
        """
        return await self.get_full_policy("deployment_policy")

    async def get_finance_rules(self) -> str:
        """Get FULL finance policy text for compliance checking.

        Returns:
            Complete finance_policy.md content
        """
        return await self.get_full_policy("finance_policy")

    # ==========================================================================
    # Vector Search: For "Past Precedent" only (not compliance!)
    # ==========================================================================

    async def find_similar_past_cases(
        self,
        vector_store,
        query: str,
        limit: int = 5
    ) -> list[dict]:
        """Find similar past cases using vector search.

        This is for "How did we handle this last time?" not "What are the rules?"

        Args:
            vector_store: SemanticMemory instance
            query: Query to search past cases
            limit: Max results

        Returns:
            List of similar past cases
        """
        if not vector_store:
            return []

        results = await vector_store.search(query, limit=limit)
        return [
            {"rule": r.rule, "similarity": r.similarity}
            for r in results
        ]
```

---

### Phase 3: Sentinel State & Nodes

**File:** `ai-service/src/ai_service/agents/sentinel/state.py`

```python
"""Sentinel Agent State Definition.

Extends ActionProposalState with Sentinel-specific fields.
"""

from typing import TypedDict, Optional, Literal
from ai_service.graphs.vertical_agents import ActionProposalState


class SentinelState(ActionProposalState):
    """Sentinel-specific state extending ActionProposalState."""

    # GitHub PR context
    pr_number: int
    pr_id: str  # GitHub node ID
    pr_title: str
    pr_body: str
    pr_author: str
    pr_url: str

    # Linear context
    linear_issue_id: Optional[str]
    linear_issue_state: Optional[str]
    linear_issue_labels: list[str]

    # Graph context
    issue_context: dict | None
    risk_score: float

    # Sentinel decision
    violations: list[str]
    sentinel_decision: Optional[Literal["block", "warn", "pass"]]

    # Approval (uses parent class fields)
    # approval_decision, approval_required are inherited
```

**File:** `ai-service/src/ai_service/agents/sentinel/nodes.py`

```python
"""Sentinel LangGraph Nodes.

Reuses patterns from vertical_agents.py and integrates with existing clients.
"""

import re
import logging
from typing import Literal
from langgraph.types import interrupt, Command

from .state import SentinelState
from ai_service.memory.graph import GraphService
from ai_service.sop.loader import SOPLoader
from ai_service.integrations.github import GitHubClient
from ai_service.integrations.slack import SlackClient, PRSummary, Decision

logger = logging.getLogger(__name__)


async def extract_linear_context(state: SentinelState) -> SentinelState:
    """Extract Linear Issue ID from PR body and query graph.

    Uses existing GitHubClient from integrations/github.py
    """
    pr_body = state.get("pr_body", "")

    # Extract LIN-123 pattern
    match = re.search(r'LIN-(\d+)', pr_body)
    linear_issue_id = f"LIN-{match.group(1)}" if match else None

    issue_context = None
    issue_state = None
    issue_labels = []

    if linear_issue_id:
        # Query Neo4j for issue context
        graph = GraphService()
        try:
            issue_context = await graph.get_issue_context(linear_issue_id)
            if issue_context:
                issue_state = issue_context.get("i", {}).get("state")
                issue_labels = issue_context.get("labels", [])
        finally:
            await graph.close()

    return {
        **state,
        "linear_issue_id": linear_issue_id,
        "linear_issue_state": issue_state,
        "linear_issue_labels": issue_labels,
        "issue_context": issue_context,
    }


async def check_compliance(state: SentinelState) -> SentinelState:
    """Check PR compliance against deployment SOPs.

    Returns decision and violations.
    """
    violations: list[str] = []
    sop_loader = SOPLoader()
    deployment_rules = await sop_loader.get_deployment_rules()

    # Rule 1: Must have Linear Issue linked
    if not state.get("linear_issue_id"):
        violations.append("No Linear Issue linked (add LIN-XXX to PR body)")

    # Rule 2: Linked Issue must be in valid state
    issue_state = state.get("linear_issue_state")
    if issue_state and issue_state not in ["IN_PROGRESS", "REVIEW"]:
        violations.append(f"Linked Issue is in '{issue_state}' state (must be IN_PROGRESS or REVIEW)")

    # Rule 3: Check for "Needs Spec" label
    if "Needs Spec" in state.get("linear_issue_labels", []):
        violations.append("Linked Issue has 'Needs Spec' label - spec must be linked")

    # Calculate risk score
    graph = GraphService()
    try:
        risk_score = await graph.get_pr_risk_score(state["pr_id"])
    finally:
        await graph.close()

    # Make decision
    if violations:
        decision: Literal["block", "warn", "pass"] = "block"
    else:
        decision = "pass"

    return {
        **state,
        "violations": violations,
        "risk_score": risk_score,
        "sentinel_decision": decision,
        "status": "analyzed",
    }


async def send_for_approval(state: SentinelState) -> Command:
    """Send to Slack for human approval.

    Uses existing SlackClient from integrations/slack.py
    """
    if state["sentinel_decision"] == "pass":
        return Command(goto="execute")

    # Create PR summary for Slack
    pr_summary = PRSummary(
        number=state["pr_number"],
        title=state["pr_title"],
        author=state["pr_author"],
        decision=Decision.BLOCK if state["sentinel_decision"] == "block" else Decision.WARN,
        confidence=1.0 - state["risk_score"],
        violations=state["violations"],
        recommendations=[],
        url=state["pr_url"],
    )

    # Send to Slack (existing SlackClient)
    slack_client = SlackClient(webhook_url="")  # From env
    await slack_client.notify_pr_review(pr_summary)

    # Interrupt and wait for Slack response
    approved = interrupt({
        "type": "sentinel_proposal",
        "pr_number": state["pr_number"],
        "pr_title": state["pr_title"],
        "pr_author": state["pr_author"],
        "violations": state["violations"],
        "risk_score": state["risk_score"],
        "actions": ["Block PR", "Ignore (Allow)"],
    })

    if approved:
        return Command(goto="execute")
    else:
        return Command(goto="reject")


async def execute(state: SentinelState) -> SentinelState:
    """Execute approved action.

    Uses existing GitHubClient from integrations/github.py
    """
    github_client = GitHubClient(
        token="",  # From env
        owner="",  # From env
        repo="",   # From env
    )

    if state["sentinel_decision"] == "block":
        # Comment on PR
        comment = f"🛑 **Sentinel Blocked**\n\n" + "\n".join(
            f"• {v}" for v in state["violations"]
        )
        await github_client.comment_on_pr(
            pr_number=state["pr_number"],
            body=comment,
        )

    # Update status
    await github_client.create_pull_request_review(
        pr_number=state["pr_number"],
        event="COMMENT" if state["sentinel_decision"] == "block" else "APPROVE",
        body="Sentinel review complete" if state["sentinel_decision"] == "block" else None,
    )

    return {
        **state,
        "status": "approved",
        "approval_decision": "approved",
        "ready_to_execute": True,
    }


async def reject(state: SentinelState) -> SentinelState:
    """Log rejection and exit."""
    return {
        **state,
        "status": "rejected",
        "approval_decision": "rejected",
        "ready_to_execute": False,
    }
```

---

### Phase 4: Sentinel Graph (reuses checkpointer)

**File:** `ai-service/src/ai_service/agents/sentinel/graph.py`

```python
"""Sentinel LangGraph.

Extends vertical_agents.py pattern with Sentinel-specific graph.
"""

import logging
from langgraph.graph import StateGraph, START, END

from .state import SentinelState
from .nodes import (
    extract_linear_context,
    check_compliance,
    send_for_approval,
    execute,
    reject,
)
from ai_service.graphs.vertical_agents import (
    get_async_checkpointer,
    GraphCheckpointerConfig,
)

logger = logging.getLogger(__name__)


def create_sentinel_graph() -> StateGraph:
    """Create Sentinel StateGraph.

    Returns:
        Compiled StateGraph ready for execution
    """
    builder = StateGraph(SentinelState)

    # Add nodes
    builder.add_node("extract_linear_context", extract_linear_context)
    builder.add_node("check_compliance", check_compliance)
    builder.add_node("send_for_approval", send_for_approval)
    builder.add_node("execute", execute)
    builder.add_node("reject", reject)

    # Define flow
    builder.add_edge(START, "extract_linear_context")
    builder.add_edge("extract_linear_context", "check_compliance")
    builder.add_edge("check_compliance", "send_for_approval")

    # Conditional from send_for_approval (interrupt controls this)
    builder.add_edge("execute", END)
    builder.add_edge("reject", END)

    return builder


async def get_sentinel_graph():
    """Get compiled Sentinel graph with checkpointer.

    Returns:
        Compiled graph with Postgres checkpointer
    """
    builder = create_sentinel_graph()

    async with get_async_checkpointer() as checkpointer:
        compiled = builder.compile(checkpointer=checkpointer)
        logger.info("Sentinel graph compiled with Postgres checkpointer")
        return compiled


# Extend vertical_agents.py exports
def get_vertical_graph(vertical: str):
    """Get StateGraph for any vertical (extended with sentinel)."""
    from ai_service.graphs.vertical_agents import get_vertical_graph as _get

    if vertical == "sentinel":
        return create_sentinel_graph()

    return _get(vertical)
```

---

### Phase 5: GitHub Webhook Handler

**File:** `ai-service/src/ai_service/webhooks/github.py`

```python
"""GitHub Webhook Handler.

Extends existing webhook.py patterns from integrations/webhook.py
"""

import logging
from fastapi import Request, HTTPException

from ai_service.agents.sentinel.graph import get_sentinel_graph
from ai_service.graphs.vertical_agents import GraphCheckpointerConfig

logger = logging.getLogger(__name__)


async def github_webhook(request: Request) -> dict:
    """Handle GitHub webhook events.

    Triggers Sentinel agent on PR events.

    Args:
        request: FastAPI request with GitHub payload

    Returns:
        Response dict
    """
    # Verify signature (from existing webhook.py patterns)
    body = await request.body()
    # Add signature verification here using GITHUB_WEBHOOK_SECRET

    # Parse event
    event = request.headers.get("X-GitHub-Event", "")
    payload = await request.json()

    if event != "pull_request":
        return {"status": "ignored", "reason": f"Event {event} not handled"}

    action = payload.get("action")
    if action not in ["opened", "synchronize"]:
        return {"status": "ignored", "reason": f"Action {action} not handled"}

    pr = payload["pull_request"]
    pr_number = pr["number"]
    pr_id = str(pr["id"])
    pr_title = pr["title"]
    pr_body = pr.get("body", "")
    pr_author = pr["user"]["login"]
    pr_url = pr["html_url"]

    # Create initial state
    initial_state = {
        "event_id": f"gh-pr-{pr_id}",
        "event_type": "github.pr",
        "vertical": "sentinel",
        "urgency": "medium",

        "pr_number": pr_number,
        "pr_id": pr_id,
        "pr_title": pr_title,
        "pr_body": pr_body,
        "pr_author": pr_author,
        "pr_url": pr_url,

        "linear_issue_id": None,
        "linear_issue_state": None,
        "linear_issue_labels": [],

        "issue_context": None,
        "risk_score": 0.0,

        "violations": [],
        "sentinel_decision": None,

        "status": "pending",
        "analysis": None,
        "draft_action": None,
        "confidence": 0.0,

        "approval_required": True,
        "approval_decision": None,
        "approver_id": None,
        "rejection_reason": None,

        "ready_to_execute": False,
        "executed_at": None,
        "error": None,
    }

    # Get thread config
    thread_id = GraphCheckpointerConfig.get_thread_id(pr_id, "sentinel")
    config = GraphCheckpointerConfig.get_configurable(thread_id)

    # Invoke Sentinel graph
    graph = await get_sentinel_graph()
    await graph.ainvoke(initial_state, config=config)

    logger.info(f"Sentinel invoked for PR #{pr_number}")

    return {"status": "processed", "pr": pr_number}
```

---

### Phase 6: DeepEval Test Suite

**File:** `ai-service/tests/test_sentinel.py`

```python
"""Sentinel Agent Tests using DeepEval.

Golden scenarios for Sentinel decision making.
"""

import pytest
from deepeval import test_case
from deepeval.metrics import HallucinationMetric, AnswerRelevancyMetric
from deepeval.test_case import LLMTestCase

from ai_service.agents.sentinel.nodes import check_compliance


class TestSentinelCompliance:
    """Golden scenarios for Sentinel decision making."""

    @test_case("pr_with_valid_linear_link_passes")
    def test_pr_with_valid_linear_link(self):
        """When PR has LIN-123 linked to IN_PROGRESS issue, should PASS."""
        state = {
            "pr_id": "123",
            "pr_body": "Fixes LIN-123",
            "linear_issue_id": "LIN-123",
            "linear_issue_state": "IN_PROGRESS",
            "linear_issue_labels": [],
        }
        result = check_compliance(state)
        assert result["sentinel_decision"] == "pass"
        assert len(result["violations"]) == 0

    @test_case("pr_without_linear_link_blocks")
    def test_pr_without_linear_link(self):
        """When PR has no Linear link, should BLOCK."""
        state = {
            "pr_id": "456",
            "pr_body": "Just a bug fix",
            "linear_issue_id": None,
        }
        result = check_compliance(state)
        assert result["sentinel_decision"] == "block"
        assert "No Linear Issue" in result["violations"][0]

    @test_case("pr_with_backlog_issue_blocks")
    def test_pr_with_backlog_issue(self):
        """When PR linked to BACKLOG issue, should BLOCK."""
        state = {
            "pr_id": "789",
            "pr_body": "Working on LIN-456",
            "linear_issue_id": "LIN-456",
            "linear_issue_state": "BACKLOG",
            "linear_issue_labels": [],
        }
        result = check_compliance(state)
        assert result["sentinel_decision"] == "block"
        assert any("BACKLOG" in v for v in result["violations"])


# Pytest configuration
def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "test_case: mark test as DeepEval test case"
    )
```

---

## 3. Files Summary

### What to CREATE (10 files)

| File | Purpose |
|------|---------|
| `memory/graph.py` | Raw Neo4j GraphService (refactor from graphiti_client) |
| `agents/sentinel/state.py` | SentinelState TypedDict |
| `agents/sentinel/nodes.py` | LangGraph nodes (analyze, check, approve) |
| `agents/sentinel/graph.py` | Sentinel StateGraph (compiles with checkpointer) |
| `sop/loader.py` | SOP ingestion using vector_store |
| `sop/validator.py` | Rule-Condition-Action validator |
| `webhooks/github.py` | GitHub PR webhook handler |
| `tests/test_sentinel.py` | DeepEval test suite |

### What to EXTEND (2 files)

| File | Change |
|------|--------|
| `graphs/vertical_agents.py` | Add `sentinel` to `_VERTICAL_MAP`, extend `get_vertical_graph()` |
| `integrations/executor.py` | Optional: Add `GitHubExecutor` class |

### What to REFACTOR (1 file)

| File | Change |
|------|--------|
| `memory/graphiti_client.py` | Move to `memory/graph.py` as `GraphService`, delete old file |

### What to KEEP (existing code)

- `integrations/github.py` - GitHubClient (reuse)
- `integrations/slack.py` - SlackClient, SlackMessageBuilder (reuse)
- `integrations/executor.py` - SlackExecutor (reuse pattern)
- `infrastructure/checkpointer.py` - Checkpointers (reuse)
- `memory/vector_store.py` - Semantic memory (keep)

---

## 4. Success Criteria

1. **GitHub PR opened** → Sentinel analyzes → **Slack notification** with approval buttons
2. **Click "Block"** → **GitHub comment posted** → PR marked "changes_requested"
3. **Click "Ignore"** → **PR proceeds** (no comment)
4. **All tests pass** via `pytest tests/test_sentinel.py`
5. **Neo4j graph** stores PR → Issue relationships

---

## 5. Next Steps

1. **Review** this plan
2. **Create branch:** `git checkout -b feature/sentinel-vertical`
3. **Start Phase 1:** Refactor `graphiti_client.py` → `memory/graph.py`
4. **Iterate** based on real testing
