"""LLM integration for ExecOps using Ollama (Qwen 2.5 Coder).

This module provides LLM capabilities using local Ollama models.
For Sentinel, we use Qwen 2.5 Coder 3B which supports tool calling.
"""

import logging
from typing import Any

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# Default Ollama settings
OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5-coder:3b"


class LLMService:
    """LLM service using Ollama for local inference.

    Supports tool calling for function invocation in Sentinel.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = OLLAMA_BASE_URL,
        temperature: float = 0.0,
    ) -> None:
        """Initialize LLM service.

        Args:
            model: Ollama model name (default: qwen2.5-coder:3b)
            base_url: Ollama server URL
            temperature: Model temperature (0.0 for deterministic outputs)
        """
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self._client: ChatOllama | None = None

    @property
    def client(self) -> ChatOllama:
        """Get or create Ollama client."""
        if self._client is None:
            self._client = ChatOllama(
                model=self.model,
                base_url=self.base_url,
                temperature=self.temperature,
            )
            logger.info(f"LLM client initialized with {self.model}")
        return self._client

    async def invoke(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """Invoke LLM with messages.

        Args:
            messages: List of message dicts with 'role' and 'content'

        Returns:
            LLM response dict with 'content' and optional 'tool_calls'
        """
        # Convert to LangChain messages
        lc_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))

        response = self.client.invoke(lc_messages)
        return self._to_dict(response)

    def _to_dict(self, response) -> dict[str, Any]:
        """Convert LangChain response to dict."""
        result = {"content": response.content if hasattr(response, 'content') else str(response)}

        # Handle tool calls if present
        if hasattr(response, 'tool_calls') and response.tool_calls:
            result["tool_calls"] = [
                {
                    "name": tc["name"],
                    "args": tc["args"],
                    "id": tc.get("id", ""),
                }
                for tc in response.tool_calls
            ]

        return result

    async def check_health(self) -> bool:
        """Check if Ollama is accessible.

        Returns:
            True if LLM is available
        """
        try:
            response = await self.invoke([
                {"role": "user", "content": "Respond with 'ok' if you can see this."}
            ])
            return "ok" in response.get("content", "").lower()
        except Exception as e:
            logger.error(f"LLM health check failed: {e}")
            return False


# Global LLM service instance
_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """Get or create global LLM service instance."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


# =============================================================================
# Sentinel-Specific LLM Prompts
# =============================================================================

SENTINEL_SYSTEM_PROMPT = """You are Sentinel, an AI agent that enforces deployment compliance.

Your role:
1. Analyze PRs for compliance with deployment policies
2. Check if Linear Issues are properly linked
3. Identify policy violations
4. Decide whether to BLOCK, WARN, or PASS a PR

You have access to:
- Graph context (PR -> Issue relationships)
- SOP policies (deployment rules)
- GitHub API (for commenting/approving)

When analyzing a PR, consider:
- Is a Linear Issue linked in the PR body?
- Is the Issue in a valid state (IN_PROGRESS, REVIEW)?
- Does the Issue have critical labels (Needs Spec)?
- What violations exist?

Respond with a compliance decision and reasoning."""


SENTINEL_ANALYSIS_PROMPT = """Analyze this PR for compliance:

PR Details:
- Number: {pr_number}
- Title: {pr_title}
- Body: {pr_body}
- Author: {pr_author}

Issue Context:
- Linked Issue: {issue_id}
- Issue State: {issue_state}
- Issue Labels: {issue_labels}

Policy Violations:
{violations}

Risk Score: {risk_score}

Based on the deployment policy, provide:
1. DECISION: block, warn, or pass
2. REASON: Brief explanation of your decision
3. ACTIONS: What should be done (if any)

Respond in JSON format:
{{
  "decision": "block|warn|pass",
  "reason": "...",
  "actions": ["action1", "action2"]
}}"""


async def analyze_pr_compliance(
    pr_info: dict[str, Any],
    issue_context: dict[str, Any] | None,
    violations: list[str],
    risk_score: float,
    llm: LLMService | None = None,
) -> dict[str, Any]:
    """Use LLM to analyze PR compliance.

    Args:
        pr_info: PR information (number, title, body, author)
        issue_context: Context from Neo4j graph
        violations: List of detected violations
        risk_score: Calculated risk score
        llm: LLM service instance

    Returns:
        LLM analysis result with decision, reason, actions
    """
    if llm is None:
        llm = get_llm_service()

    # Format issue context
    issue_id = issue_context.get("issue", {}).get("id") if issue_context else None
    issue_state = issue_context.get("issue", {}).get("state") if issue_context else "None"
    issue_labels = issue_context.get("labels", []) if issue_context else []
    violations_text = "\n".join(f"- {v}" for v in violations) if violations else "None"

    # Build prompt
    prompt = SENTINEL_ANALYSIS_PROMPT.format(
        pr_number=pr_info.get("number", ""),
        pr_title=pr_info.get("title", ""),
        pr_body=pr_info.get("body", "")[:500],  # Truncate long bodies
        pr_author=pr_info.get("author", ""),
        issue_id=issue_id or "None",
        issue_state=issue_state,
        issue_labels=", ".join(issue_labels) if issue_labels else "None",
        violations=violations_text,
        risk_score=risk_score,
    )

    try:
        response = await llm.invoke([
            {"role": "system", "content": SENTINEL_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ])

        # Try to parse JSON from response
        content = response.get("content", "{}")

        # Simple JSON parsing (in production, use structured output)
        import json
        try:
            # Try to extract JSON from response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            result = json.loads(content)
            return {
                "decision": result.get("decision", "pass"),
                "reason": result.get("reason", "Analysis complete"),
                "actions": result.get("actions", []),
            }
        except json.JSONDecodeError:
            # Fallback: parse decision from text
            content_lower = content.lower()
            if "block" in content_lower and "pass" not in content_lower.split("block")[0]:
                decision = "block"
            elif "warn" in content_lower:
                decision = "warn"
            else:
                decision = "pass"

            return {
                "decision": decision,
                "reason": content[:200],
                "actions": [],
            }

    except Exception as e:
        logger.error(f"LLM compliance analysis failed: {e}")
        # Fallback to rule-based decision
        return {
            "decision": "block" if violations else "pass",
            "reason": f"Rule-based fallback: {len(violations)} violations found",
            "actions": [],
        }


# Test function
async def _test_llm():
    """Quick test of LLM service."""
    print("Testing LLM service...")

    llm = get_llm_service()
    healthy = await llm.check_health()
    print(f"LLM health: {'✓' if healthy else '✗'}")

    if healthy:
        result = await analyze_pr_compliance(
            pr_info={"number": 123, "title": "Test PR", "body": "Fixes LIN-456", "author": "dev"},
            issue_context={"issue": {"id": "LIN-456", "state": "IN_PROGRESS"}, "labels": []},
            violations=[],
            risk_score=0.0,
        )
        print(f"Analysis result: {result}")

    print("LLM test complete.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(_test_llm())
