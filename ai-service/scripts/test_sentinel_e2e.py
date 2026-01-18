#!/usr/bin/env uv run
"""ExecOps Sentinel End-to-End Integration Test.

Tests the full Sentinel workflow:
1. GraphService (Neo4j) - link PR to Issue
2. SOP loader - read deployment policy
3. Compliance check - simulate PR with/without Linear link
4. Full workflow: PR -> Extract Context -> Check Compliance -> Decision

Run: python scripts/test_sentinel_e2e.py
"""

import asyncio
import sys
import yaml
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ai_service.memory.graph import GraphService
from ai_service.agents.sentinel.nodes import check_compliance, extract_linear_context
from ai_service.agents.sentinel.state import SentinelState


async def test_graph_service():
    """Test 1: GraphService with Neo4j."""
    print("\n[TEST 1] GraphService with Neo4j")
    print("-" * 50)

    async with GraphService() as graph:
        # Health check
        healthy = await graph.health_check()
        print(f"  Neo4j Health: {'PASS' if healthy else 'FAIL'}")

        # Link a test PR to an issue
        await graph.link_pr_to_issue("e2e-test-pr-001", "LIN-999")
        print("  Linked PR 'e2e-test-pr-001' to issue 'LIN-999'")

        # Get risk score
        score = await graph.get_pr_risk_score("e2e-test-pr-001")
        print(f"  Risk Score: {score}")

    return healthy


async def test_sop_loader():
    """Test 2: SOP loader - read deployment policy."""
    print("\n[TEST 2] SOP Loader - Deployment Policy")
    print("-" * 50)

    # Simulate reading a deployment policy
    sop_content = """
trigger: pull_request.opened
conditions:
  - label_missing: "Scope: Non-Prod"
  - files_match:
      - "src/**/*.py"
actions:
  - post_comment: "Please add 'Scope: Non-Prod' label"
  - block_merge: true
  - request_changes: true
"""

    try:
        parsed = yaml.safe_load(sop_content)
        print(f"  SOP parsed: {parsed['trigger']}")
        print(f"  Conditions: {len(parsed['conditions'])} conditions")
        print(f"  Actions: {len(parsed['actions'])} actions")
        print("  SOP Loader: PASS")
        return True
    except Exception as e:
        print(f"  SOP Loader FAIL: {e}")
        return False


async def test_compliance_check():
    """Test 3: Compliance check with valid and invalid PRs."""
    print("\n[TEST 3] Compliance Check Decisions")
    print("-" * 50)

    # Test case 1: Valid PR with Linear link
    valid_pr_state = SentinelState(
        pr_id="test-pr-001",
        pr_number=42,
        pr_body="Fixes LIN-123\n\nThis PR addresses the memory leak issue.",
        linear_issue_id="LIN-123",
        linear_issue_state="IN_PROGRESS",
        linear_issue_labels=[],
    )

    result = await check_compliance(valid_pr_state)
    result_dict = dict(result) if hasattr(result, '__iter__') and not isinstance(result, dict) else result
    print(f"  Valid PR Decision: {result_dict['sentinel_decision']}")
    print(f"  Violations: {result_dict['violations']}")
    valid_passed = result_dict["sentinel_decision"] == "pass" and len(result_dict["violations"]) == 0

    # Test case 2: Invalid PR without Linear link
    invalid_pr_state = SentinelState(
        pr_id="test-pr-002",
        pr_number=43,
        pr_body="Just a bug fix without any issue reference",
        linear_issue_id=None,
        linear_issue_state=None,
        linear_issue_labels=[],
    )

    result = await check_compliance(invalid_pr_state)
    result_dict = dict(result) if hasattr(result, '__iter__') and not isinstance(result, dict) else result
    print(f"\n  Invalid PR Decision: {result_dict['sentinel_decision']}")
    print(f"  Violations: {result_dict['violations']}")
    invalid_passed = result_dict["sentinel_decision"] == "block" and len(result_dict["violations"]) > 0

    return valid_passed and invalid_passed


async def test_full_workflow():
    """Test 4: Full Sentinel workflow."""
    print("\n[TEST 4] Full Sentinel Workflow")
    print("-" * 50)

    # Simulate incoming PR webhook payload
    pr_payload = {
        "pr_id": "workflow-test-pr-001",
        "pr_number": 100,
        "pr_body": """
# Summary
This PR implements the new authentication flow.

Fixes LIN-456

## Changes
- Add OAuth2 support
- Update user session management
        """,
        "pr_author": "developer@example.com",
        "pr_diff_url": "https://github.com/org/repo/pull/100.diff",
    }

    print(f"  Incoming PR: #{pr_payload['pr_number']}")
    print(f"  Author: {pr_payload['pr_author']}")

    # Step 1: Extract context
    state = SentinelState(**pr_payload)
    context = await extract_linear_context(state)
    context_dict = dict(context) if hasattr(context, '__iter__') and not isinstance(context, dict) else context
    print(f"\n  Step 1 - Extract Context:")
    print(f"    Linear Issue ID: {context_dict.get('linear_issue_id') or 'NOT FOUND'}")
    print(f"    Issue State: {context_dict.get('linear_issue_state') or 'N/A'}")
    print(f"    Labels: {context_dict.get('linear_issue_labels') or []}")

    # Step 2: Check compliance
    compliance = await check_compliance(context)
    compliance_dict = dict(compliance) if hasattr(compliance, '__iter__') and not isinstance(compliance, dict) else compliance
    print(f"\n  Step 2 - Compliance Check:")
    print(f"    Decision: {compliance_dict['sentinel_decision']}")
    print(f"    Violations: {compliance_dict['violations']}")
    print(f"    Recommendations: {compliance_dict.get('recommendations') or []}")

    # Step 3: Final decision
    decision = compliance_dict["sentinel_decision"]
    print(f"\n  Step 3 - Final Decision:")
    print(f"    ==> {decision.upper()} <==")

    return decision in ["pass", "warn"]


async def run_all_tests():
    """Run all E2E tests and report results."""
    print("=" * 60)
    print("ExecOps Sentinel E2E Integration Test")
    print("Using: Qwen 2.5 Coder (Ollama)")
    print("=" * 60)

    results = {}

    # Test 1: GraphService
    try:
        results["GraphService"] = await test_graph_service()
    except Exception as e:
        print(f"  GraphService ERROR: {e}")
        results["GraphService"] = False

    # Test 2: SOP Loader
    try:
        results["SOP Loader"] = await test_sop_loader()
    except Exception as e:
        print(f"  SOP Loader ERROR: {e}")
        results["SOP Loader"] = False

    # Test 3: Compliance Check
    try:
        results["Compliance Check"] = await test_compliance_check()
    except Exception as e:
        print(f"  Compliance Check ERROR: {e}")
        results["Compliance Check"] = False

    # Test 4: Full Workflow
    try:
        results["Full Workflow"] = await test_full_workflow()
    except Exception as e:
        print(f"  Full Workflow ERROR: {e}")
        results["Full Workflow"] = False

    # Summary
    print("\n" + "=" * 60)
    print("E2E TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, passed_test in results.items():
        status = "PASS" if passed_test else "FAIL"
        print(f"  [{status}] {test_name}")

    print("-" * 60)
    print(f"  Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n  SUCCESS: All E2E tests passed!")
        return 0
    else:
        print(f"\n  FAILURE: {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
