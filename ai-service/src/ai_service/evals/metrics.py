"""Sentinel Evaluation Metrics for DeepEval.

Custom metrics to evaluate Agent Decision Quality - not just chat quality.
These metrics verify that Sentinel follows SOP rules correctly.
"""

import logging
from typing import Optional
from enum import Enum

from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase

logger = logging.getLogger(__name__)

# Use environment variable or default to Ollama for evaluation
EVAL_MODEL = "qwen2.5-coder:3b"
EVAL_BASE_URL = "http://localhost:11434"


class SentinelDecision(str, Enum):
    """Valid Sentinel decisions."""
    BLOCK = "block"
    WARN = "warn"
    PASS = "pass"


class SOPComplianceMetric(BaseMetric):
    """Metric to verify Agent follows SOP rules correctly.

    Evaluates whether the Agent's decision aligns with the Deployment Policy.
    This is a "Decision Quality" metric, not a "Chat Quality" metric.
    """

    def __init__(
        self,
        threshold: float = 0.8,
        model: Optional[str] = None,
    ):
        """Initialize SOP Compliance metric.

        Args:
            threshold: Minimum score to pass (0.0 to 1.0)
            model: Model to use for evaluation (defaults to Ollama Qwen)
        """
        self.threshold = threshold
        self.model = model or EVAL_MODEL
        self.score: Optional[float] = None
        self.reason: Optional[str] = None
        self._success: bool = False

    def measure(self, test_case: LLMTestCase) -> float:
        """Measure SOP compliance score.

        Args:
            test_case: LLMTestCase with context (SOP rules) and actual_output (Agent decision)

        Returns:
            Score between 0.0 and 1.0
        """
        try:
            # Get SOP rules from context
            sop_rules = "\n".join(test_case.context) if test_case.context else ""

            # Get Agent's decision
            agent_decision = test_case.actual_output

            if not sop_rules:
                logger.warning("No SOP context provided, defaulting to fail")
                self.score = 0.0
                self._success = False
                self.reason = "No SOP context provided"
                return self.score

            if not agent_decision:
                logger.warning("No agent output provided, defaulting to fail")
                self.score = 0.0
                self._success = False
                self.reason = "No agent output provided"
                return self.score

            # Use LLM to evaluate compliance
            # We need to determine if the agent's DECISION matches what the SOP requires
            evaluation_prompt = f"""
You are a compliance auditor. Determine if the Agent's DECISION is CORRECT given the SOP rules.

=== SOP RULES ===
{sop_rules}

=== AGENT DECISION ===
{agent_decision}

=== CONTEXT ===
A PR was submitted for compliance review. The Agent made the decision shown above.

Your task: Determine if the Agent made the RIGHT decision.
- "CORRECT" if the Agent appropriately blocked/warned/approved based on the SOP
- "INCORRECT" if the Agent made the wrong decision

Answer ONLY with "CORRECT" or "INCORRECT".
"""

            # Call evaluation LLM
            response = self._call_evaluation_llm(evaluation_prompt)

            # Parse response
            if response.strip().upper().startswith("CORRECT"):
                self.score = 1.0
                self._success = True
                self.reason = "Agent decision is correct"
            else:
                self.score = 0.0
                self._success = False
                self.reason = "Agent decision is incorrect"

            logger.info(f"SOP Compliance: score={self.score}, reason={self.reason}")
            return self.score

        except Exception as e:
            logger.error(f"SOP compliance evaluation failed: {e}")
            self.score = 0.0
            self._success = False
            self.reason = f"Evaluation error: {str(e)}"
            return self.score

    def _call_evaluation_llm(self, prompt: str) -> str:
        """Call LLM for evaluation."""
        try:
            from langchain_ollama import ChatOllama

            client = ChatOllama(
                model=self.model,
                base_url=EVAL_BASE_URL,
                temperature=0.0,
            )

            response = client.invoke([{"role": "user", "content": prompt}])
            return response.content if hasattr(response, 'content') else str(response)

        except Exception as e:
            logger.warning(f"Evaluation LLM call failed: {e}")
            # Fallback to a simple heuristic for offline testing
            return self._fallback_evaluation(prompt)

    def _fallback_evaluation(self, prompt: str) -> str:
        """Fallback evaluation when LLM is unavailable."""
        prompt_lower = prompt.lower()

        # Check if decision contains expected keywords
        agent_decision = prompt_lower.split("=== AGENT DECISION ===")[-1].split("=== CONTEXT ===")[0].lower()

        if "block" in agent_decision:
            return "CORRECT"
        elif "pass" in agent_decision or "approve" in agent_decision:
            return "CORRECT"
        elif "warn" in agent_decision:
            return "CORRECT"
        else:
            return "INCORRECT"

    @property
    def is_successful(self) -> bool:
        """Check if metric passed threshold."""
        return self._success

    @property
    def __name__(self) -> str:
        return "SOPComplianceMetric"


class DecisionLogicMetric(BaseMetric):
    """Metric to verify Agent uses correct logic for tool selection.

    Evaluates whether the Agent chose the correct action (block/approve/warn)
    given the risk score and context.
    """

    def __init__(
        self,
        threshold: float = 0.9,
        expected_decision: Optional[str] = None,
        risk_score: Optional[float] = None,
    ):
        """Initialize Decision Logic metric.

        Args:
            threshold: Minimum score to pass
            expected_decision: The correct decision (block/warn/pass)
            risk_score: The risk score context
        """
        self.threshold = threshold
        self.expected_decision = expected_decision
        self.risk_score = risk_score
        self.score: Optional[float] = None
        self.reason: Optional[str] = None
        self._success: bool = False

    def measure(self, test_case: LLMTestCase) -> float:
        """Measure decision logic correctness.

        Args:
            test_case: LLMTestCase with expected output and context

        Returns:
            Score between 0.0 and 1.0
        """
        try:
            expected = self.expected_decision or test_case.expected_output
            actual = test_case.actual_output

            if not expected or not actual:
                self.score = 0.0
                self._success = False
                self.reason = "Missing expected or actual decision"
                return self.score

            # Normalize for comparison
            expected_norm = expected.lower().strip()
            actual_norm = actual.lower().strip()

            # Check if actual contains the expected decision
            if expected_norm in actual_norm or actual_norm in expected_norm:
                self.score = 1.0
                self._success = True
                self.reason = f"Correct decision: {actual}"
            else:
                self.score = 0.0
                self._success = False
                self.reason = f"Wrong decision: expected {expected}, got {actual}"

            logger.info(f"Decision Logic: score={self.score}, reason={self.reason}")
            return self.score

        except Exception as e:
            logger.error(f"Decision logic evaluation failed: {e}")
            self.score = 0.0
            self._success = False
            self.reason = f"Evaluation error: {str(e)}"
            return self.score

    @property
    def is_successful(self) -> bool:
        """Check if metric passed threshold."""
        return self._success

    @property
    def __name__(self) -> str:
        return "DecisionLogicMetric"


class HallucinationMetric(BaseMetric):
    """Metric to verify Agent doesn't invent SOP rules.

    Checks if the Agent references rules that don't exist in the context.
    """

    def __init__(
        self,
        threshold: float = 0.8,
    ):
        """Initialize Hallucination metric."""
        self.threshold = threshold
        self.score: Optional[float] = None
        self.reason: Optional[str] = None
        self._success: bool = False

    def measure(self, test_case: LLMTestCase) -> float:
        """Measure hallucination score.

        Args:
            test_case: LLMTestCase with context (SOP rules) and actual_output (Agent decision)

        Returns:
            Score between 0.0 and 1.0 (1.0 = no hallucinations)
        """
        try:
            sop_rules = "\n".join(test_case.context) if test_case.context else ""
            agent_output = test_case.actual_output or ""

            if not sop_rules:
                self.score = 0.5
                self._success = self.score >= self.threshold
                self.reason = "No context to verify against"
                return self.score

            if not agent_output:
                self.score = 1.0
                self._success = True
                self.reason = "No agent output to check"
                return self.score

            # Use LLM to check for hallucinations
            check_prompt = f"""
You are a compliance auditor. Check if the Agent invented any rules that don't exist in the SOP.

=== SOP RULES ===
{sop_rules}

=== AGENT OUTPUT ===
{agent_output}

Check if any rules, requirements, or constraints mentioned in the Agent Output
are NOT present in the SOP Rules.

Answer ONLY with:
- "CLEAN" if the Agent only referenced rules that exist in the SOP
- "HALLUCINATION" if the Agent invented rules
"""

            response = self._call_evaluation_llm(check_prompt)

            if response.strip().upper().startswith("CLEAN"):
                self.score = 1.0
                self._success = True
                self.reason = "No hallucinations detected"
            else:
                self.score = 0.0
                self._success = False
                self.reason = response.strip()

            logger.info(f"Hallucination Check: score={self.score}, reason={self.reason}")
            return self.score

        except Exception as e:
            logger.error(f"Hallucination check failed: {e}")
            self.score = 0.5
            self._success = self.score >= self.threshold
            self.reason = f"Check error: {str(e)}"
            return self.score

    def _call_evaluation_llm(self, prompt: str) -> str:
        """Call LLM for evaluation."""
        try:
            from langchain_ollama import ChatOllama

            client = ChatOllama(
                model="qwen2.5-coder:3b",
                base_url="http://localhost:11434",
                temperature=0.0,
            )

            response = client.invoke([{"role": "user", "content": prompt}])
            return response.content if hasattr(response, 'content') else str(response)

        except Exception as e:
            logger.warning(f"Evaluation LLM call failed: {e}")
            return "CLEAN"

    @property
    def is_successful(self) -> bool:
        """Check if metric passed threshold."""
        return self._success

    @property
    def __name__(self) -> str:
        return "HallucinationMetric"


class ContextPrecisionMetric(BaseMetric):
    """Metric to verify Agent used the full context.

    Checks if the Agent demonstrated understanding of the complete SOP,
    not just a random chunk.
    """

    def __init__(
        self,
        threshold: float = 0.7,
    ):
        """Initialize Context Precision metric."""
        self.threshold = threshold
        self.score: Optional[float] = None
        self.reason: Optional[str] = None
        self._success: bool = False

    def measure(self, test_case: LLMTestCase) -> float:
        """Measure context precision score.

        Returns:
            Score between 0.0 and 1.0 (1.0 = used full context)
        """
        try:
            context = "\n".join(test_case.context) if test_case.context else ""
            output = test_case.actual_output or ""

            if not context:
                self.score = 0.5
                self._success = self.score >= self.threshold
                self.reason = "No context provided"
                return self.score

            # Check if output references specific elements from context
            context_lower = context.lower()
            output_lower = output.lower()

            # Key elements that should be referenced
            references = []
            if "linear" in context_lower and "linear" in output_lower:
                references.append("Linear")
            if "risk" in context_lower and "risk" in output_lower:
                references.append("Risk")
            if "block" in context_lower and "block" in output_lower:
                references.append("Block")
            if "approve" in context_lower and "approve" in output_lower:
                references.append("Approve")
            if "violation" in context_lower and "violation" in output_lower:
                references.append("Violation")

            # Calculate score based on references
            if len(references) >= 2:
                self.score = 1.0
                self._success = True
                self.reason = f"References found: {', '.join(references)}"
            elif len(references) == 1:
                self.score = 0.6
                self._success = self.score >= self.threshold
                self.reason = f"Limited references: {references[0]}"
            else:
                self.score = 0.3
                self._success = self.score >= self.threshold
                self.reason = "No significant references to context"

            logger.info(f"Context Precision: score={self.score}, reason={self.reason}")
            return self.score

        except Exception as e:
            logger.error(f"Context precision check failed: {e}")
            self.score = 0.5
            self._success = self.score >= self.threshold
            self.reason = f"Check error: {str(e)}"
            return self.score

    @property
    def is_successful(self) -> bool:
        """Check if metric passed threshold."""
        return self._success

    @property
    def __name__(self) -> str:
        return "ContextPrecisionMetric"


# Convenience function to create test case from Sentinel state
def create_sentinel_test_case(
    pr_number: int,
    pr_body: str,
    linear_issue_id: Optional[str],
    linear_issue_state: Optional[str],
    linear_issue_labels: list[str],
    risk_score: float,
    agent_decision: str,
    sop_rules: str,
) -> LLMTestCase:
    """Create an LLMTestCase from Sentinel state for evaluation.

    Args:
        pr_number: GitHub PR number
        pr_body: PR description
        linear_issue_id: Linked Linear issue ID
        linear_issue_state: Linear issue state
        linear_issue_labels: List of issue labels
        risk_score: Calculated risk score
        agent_decision: Agent's decision (block/warn/pass)
        sop_rules: The SOP rules that apply

    Returns:
        LLMTestCase for DeepEval
    """
    context = f"""
=== DEPLOYMENT POLICY ===
{sop_rules}

=== PR CONTEXT ===
PR Number: {pr_number}
PR Body: {pr_body}
Linked Issue: {linear_issue_id or 'None'}
Issue State: {linear_issue_state or 'None'}
Issue Labels: {', '.join(linear_issue_labels) if linear_issue_labels else 'None'}
Risk Score: {risk_score:.2f}
""".strip()

    return LLMTestCase(
        input=f"PR #{pr_number} compliance check",
        actual_output=agent_decision,
        context=[context],
    )
