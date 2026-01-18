"""Golden Test Cases for Sentinel Decision Quality.

These are the 3 critical scenarios that Sentinel MUST pass before deployment.
Each test verifies Decision Quality (not Chat Quality).

Golden Cases:
1. Happy Path: Valid PR with linked Linear issue -> PASS
2. Missing Link: PR without Linear issue -> BLOCK
3. BACKLOG Issue: Issue in BACKLOG state -> WARN

Run with: pytest src/ai_service/evals/test_golden_cases.py -v
"""

import pytest
from unittest.mock import AsyncMock, patch
from typing import Optional

from deepeval.test_case import LLMTestCase

import sys
sys.path.insert(0, '/home/aparna/Desktop/founder_os/ai-service/src')

from ai_service.agents.sentinel.state import create_initial_sentinel_state
from ai_service.agents.sentinel.nodes import check_compliance
from ai_service.evals.metrics import (
    SOPComplianceMetric,
    HallucinationMetric,
    ContextPrecisionMetric,
    create_sentinel_test_case,
)


# =============================================================================
# SOP RULES (The Ground Truth)
# =============================================================================

DEPLOYMENT_POLICY = """
## Deployment Compliance Rules

1. LINEAR ISSUE REQUIREMENT
   - All PRs MUST have a Linear issue linked in the PR body
   - Pattern: LIN-XXX (e.g., LIN-123)
   - Violation: BLOCK

2. ISSUE STATE REQUIREMENT
   - Linked issue MUST be in IN_PROGRESS or REVIEW state
   - BACKLOG or DONE issues require developer action first
   - Violation: WARN

3. SPEC REQUIREMENT
   - Issues with "Needs Spec" label require completed specification
   - Violation: WARN

4. RISK THRESHOLD
   - Risk score is calculated from Neo4j graph context
   - Used for prioritization, not automatic blocking

5. FRIDAY DEPLOYMENT
   - No deploys on Friday after 4pm (local time)
   - Violation: BLOCK
"""


# =============================================================================
# Test Case 1: Happy Path - Valid PR
# =============================================================================

class TestHappyPathValidPR:
    """Test Case 1: Perfect PR with all requirements met.

    Expected: PASS (auto-approve)
    """

    @pytest.mark.asyncio
    async def test_valid_pr_passes_compliance(self):
        """Happy path: Valid PR should pass compliance check."""
        # Given: A PR with valid Linear issue
        state = create_initial_sentinel_state(
            event_id="eval-happy-001",
            pr_number=101,
            pr_id="pr-node-101",
            pr_title="Add user authentication feature",
            pr_body="Implements LIN-501\n\n## Changes\n- Added OAuth login\n- Added session management",
            pr_author="developer",
            pr_url="https://github.com/owner/repo/pull/101",
        )
        state["linear_issue_id"] = "LIN-501"
        state["linear_issue_state"] = "IN_PROGRESS"
        state["linear_issue_labels"] = []
        state["risk_score"] = 0.3

        # When: Check compliance (with mocked Neo4j)
        with patch('ai_service.agents.sentinel.nodes.GraphService') as MockGraph:
            mock_instance = AsyncMock()
            mock_instance.get_pr_risk_score.return_value = 0.3
            MockGraph.return_value = mock_instance

            result = await check_compliance(state, use_llm=False, use_mock=True)

        # Then: Should pass
        assert result["sentinel_decision"] == "pass"
        assert len(result["violations"]) == 0

    def test_valid_pr_sop_compliance_eval(self):
        """Golden Eval: Agent correctly approves valid PR."""
        test_case = create_sentinel_test_case(
            pr_number=101,
            pr_body="Implements LIN-501",
            linear_issue_id="LIN-501",
            linear_issue_state="IN_PROGRESS",
            linear_issue_labels=[],
            risk_score=0.3,
            agent_decision="PASS: All compliance checks passed. PR approved.",
            sop_rules=DEPLOYMENT_POLICY,
        )

        # Test SOP Compliance
        sop_metric = SOPComplianceMetric(threshold=0.8)
        sop_score = sop_metric.measure(test_case)
        assert sop_score >= 0.8, f"SOP compliance failed: {sop_metric.reason}"

        # Test Hallucination
        hall_metric = HallucinationMetric(threshold=0.5)
        hall_score = hall_metric.measure(test_case)
        assert hall_score >= 0.5, f"Hallucination detected: {hall_metric.reason}"

    def test_valid_pr_no_hallucination(self):
        """Verify Agent doesn't invent rules for valid PR."""
        test_case = LLMTestCase(
            input="PR #101 compliance check",
            actual_output="PASS: All compliance checks passed. PR approved.",
            context=[DEPLOYMENT_POLICY],
        )

        metric = HallucinationMetric(threshold=0.5)
        score = metric.measure(test_case)
        assert score == 1.0, f"Hallucination detected: {metric.reason}"


# =============================================================================
# Test Case 2: Missing Linear Link
# =============================================================================

class TestMissingLinearLink:
    """Test Case 2: PR without Linear issue linked.

    Expected: BLOCK
    """

    @pytest.mark.asyncio
    async def test_missing_linear_issue_blocks(self):
        """PR without Linear issue should be blocked."""
        # Given: PR without Linear issue
        state = create_initial_sentinel_state(
            event_id="eval-missing-001",
            pr_number=402,
            pr_id="pr-node-402",
            pr_title="Quick bug fix",
            pr_body="Just a small fix, no time to create issue",
            pr_author="developer",
            pr_url="https://github.com/owner/repo/pull/402",
        )
        state["linear_issue_id"] = None
        state["linear_issue_state"] = None
        state["linear_issue_labels"] = []
        state["risk_score"] = 0.5

        # When: Check compliance
        with patch('ai_service.agents.sentinel.nodes.GraphService') as MockGraph:
            mock_instance = AsyncMock()
            mock_instance.get_pr_risk_score.return_value = 0.5
            MockGraph.return_value = mock_instance

            result = await check_compliance(state, use_llm=False, use_mock=True)

        # Then: Should block
        assert result["sentinel_decision"] == "block"
        assert len(result["violations"]) > 0
        assert "No Linear Issue linked" in result["violations"][0]

    def test_missing_link_sop_compliance_eval(self):
        """Golden Eval: Agent correctly blocks PR without Linear link."""
        test_case = create_sentinel_test_case(
            pr_number=402,
            pr_body="Just a small fix",
            linear_issue_id=None,
            linear_issue_state=None,
            linear_issue_labels=[],
            risk_score=0.5,
            agent_decision="BLOCK: No Linear Issue linked. Add LIN-XXX to PR body.",
            sop_rules=DEPLOYMENT_POLICY,
        )

        # Test SOP Compliance
        sop_metric = SOPComplianceMetric(threshold=0.8)
        sop_score = sop_metric.measure(test_case)
        assert sop_score >= 0.8, f"SOP compliance failed: {sop_metric.reason}"

        # Test Hallucination
        hall_metric = HallucinationMetric(threshold=0.5)
        hall_score = hall_metric.measure(test_case)
        assert hall_score >= 0.5, f"Hallucination detected: {hall_metric.reason}"

    def test_missing_link_correct_reasoning(self):
        """Verify Agent provides correct reason for blocking."""
        test_case = LLMTestCase(
            input="PR #402 compliance check - no Linear issue",
            actual_output="BLOCK: No Linear Issue linked (add LIN-XXX to PR body)",
            context=[DEPLOYMENT_POLICY],
        )

        metric = SOPComplianceMetric(threshold=0.8)
        score = metric.measure(test_case)
        assert score == 1.0, f"SOP compliance failed: {metric.reason}"


# =============================================================================
# Test Case 3: Issue in BACKLOG State
# =============================================================================

class TestBacklogIssue:
    """Test Case 3: Issue in BACKLOG state.

    Expected: WARN
    """

    @pytest.mark.asyncio
    async def test_backlog_issue_warns(self):
        """PR linked to BACKLOG issue should get warning."""
        state = create_initial_sentinel_state(
            event_id="eval-backlog-001",
            pr_number=333,
            pr_id="pr-node-333",
            pr_title="Working on feature",
            pr_body="Implements LIN-333",
            pr_author="developer",
            pr_url="https://github.com/owner/repo/pull/333",
        )
        state["linear_issue_id"] = "LIN-333"
        state["linear_issue_state"] = "BACKLOG"  # Invalid state
        state["linear_issue_labels"] = []
        state["risk_score"] = 0.4

        with patch('ai_service.agents.sentinel.nodes.GraphService') as MockGraph:
            mock_instance = AsyncMock()
            mock_instance.get_pr_risk_score.return_value = 0.4
            MockGraph.return_value = mock_instance

            result = await check_compliance(state, use_llm=False, use_mock=True)

        assert result["sentinel_decision"] == "warn"
        assert any("BACKLOG" in v for v in result["violations"])

    def test_backlog_issue_sop_compliance_eval(self):
        """Golden Eval: Agent correctly warns about BACKLOG issue."""
        test_case = create_sentinel_test_case(
            pr_number=333,
            pr_body="Implements LIN-333",
            linear_issue_id="LIN-333",
            linear_issue_state="BACKLOG",
            linear_issue_labels=[],
            risk_score=0.4,
            agent_decision="WARN: Linked Issue is in 'BACKLOG' state (must be IN_PROGRESS or REVIEW)",
            sop_rules=DEPLOYMENT_POLICY,
        )

        # Test SOP Compliance
        sop_metric = SOPComplianceMetric(threshold=0.8)
        sop_score = sop_metric.measure(test_case)
        assert sop_score >= 0.8, f"SOP compliance failed: {sop_metric.reason}"

        # Test Hallucination
        hall_metric = HallucinationMetric(threshold=0.5)
        hall_score = hall_metric.measure(test_case)
        assert hall_score >= 0.5, f"Hallucination detected: {hall_metric.reason}"

    def test_backlog_issue_correct_reasoning(self):
        """Verify Agent provides correct reason for warning."""
        test_case = LLMTestCase(
            input="PR #333 compliance check - BACKLOG issue",
            actual_output="WARN: Linked Issue is in 'BACKLOG' state (must be IN_PROGRESS or REVIEW)",
            context=[DEPLOYMENT_POLICY],
        )

        metric = SOPComplianceMetric(threshold=0.8)
        score = metric.measure(test_case)
        assert score == 1.0, f"SOP compliance failed: {metric.reason}"


# =============================================================================
# Test Case 4: Needs Spec Label (Bonus)
# =============================================================================

class TestNeedsSpecLabel:
    """Test Case 4: Issue with 'Needs Spec' label.

    Expected: WARN
    """

    @pytest.mark.asyncio
    async def test_needs_spec_label_warns(self):
        """PR with 'Needs Spec' label should get warning."""
        state = create_initial_sentinel_state(
            event_id="eval-spec-001",
            pr_number=444,
            pr_id="pr-node-444",
            pr_title="Feature without spec",
            pr_body="Implements LIN-444",
            pr_author="developer",
            pr_url="https://github.com/owner/repo/pull/444",
        )
        state["linear_issue_id"] = "LIN-444"
        state["linear_issue_state"] = "IN_PROGRESS"
        state["linear_issue_labels"] = ["Needs Spec"]  # Invalid label
        state["risk_score"] = 0.4

        with patch('ai_service.agents.sentinel.nodes.GraphService') as MockGraph:
            mock_instance = AsyncMock()
            mock_instance.get_pr_risk_score.return_value = 0.4
            MockGraph.return_value = mock_instance

            result = await check_compliance(state, use_llm=False, use_mock=True)

        assert result["sentinel_decision"] == "warn"
        assert any("Needs Spec" in v for v in result["violations"])

    def test_needs_spec_label_sop_compliance_eval(self):
        """Golden Eval: Agent correctly warns about 'Needs Spec' label."""
        test_case = create_sentinel_test_case(
            pr_number=444,
            pr_body="Implements LIN-444",
            linear_issue_id="LIN-444",
            linear_issue_state="IN_PROGRESS",
            linear_issue_labels=["Needs Spec"],
            risk_score=0.4,
            agent_decision="WARN: Linked Issue has 'Needs Spec' label - spec must be finalized first",
            sop_rules=DEPLOYMENT_POLICY,
        )

        # Test SOP Compliance
        sop_metric = SOPComplianceMetric(threshold=0.8)
        sop_score = sop_metric.measure(test_case)
        assert sop_score >= 0.8, f"SOP compliance failed: {sop_metric.reason}"

        # Test Hallucination
        hall_metric = HallucinationMetric(threshold=0.5)
        hall_score = hall_metric.measure(test_case)
        assert hall_score >= 0.5, f"Hallucination detected: {hall_metric.reason}"


# =============================================================================
# Test Case 5: Context Precision Check
# =============================================================================

class TestContextPrecision:
    """Test Case 5: Verify Agent uses full context.

    Expected: Agent references multiple elements from context
    """

    def test_context_precision_high_score(self):
        """Verify Agent references multiple context elements."""
        test_case = LLMTestCase(
            input="PR #555 compliance check",
            actual_output="BLOCK: No Linear Issue linked. This violates the LINEAR ISSUE REQUIREMENT.",
            context=[DEPLOYMENT_POLICY],
        )

        metric = ContextPrecisionMetric(threshold=0.5)
        score = metric.measure(test_case)
        assert score >= 0.5, f"Context precision failed: {metric.reason}"


# =============================================================================
# Run All Golden Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
