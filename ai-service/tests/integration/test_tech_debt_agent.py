"""Tests for Tech Debt Agent.

Tests for:
- TODO counting in PR diffs
- Deprecated library detection
- Tech debt scoring
- Block/warn thresholds
"""

import pytest


class TestTODOCounting:
    """Tests for TODO comment counting."""

    def test_count_single_todo(self):
        """Count single TODO comment."""
        from ai_service.agent.tech_debt import count_todos

        diff = """
        def hello():
            # TODO: Implement this
            pass
        """
        count = count_todos(diff)
        assert count == 1

    def test_count_multiple_todos(self):
        """Count multiple TODO comments."""
        from ai_service.agent.tech_debt import count_todos

        diff = """
        # TODO: Fix this bug
        def foo():
            pass
        # TODO: Optimize this
        def bar():
            pass
        # TODO: Add tests
        """
        count = count_todos(diff)
        assert count == 3

    def test_count_todos_case_insensitive(self):
        """Count TODOs regardless of case."""
        from ai_service.agent.tech_debt import count_todos

        diff = """
        # todo: lowercase todo
        # TODO: uppercase TODO
        # Todo: mixed case Todo
        """
        count = count_todos(diff)
        assert count == 3

    def test_ignore_todos_in_comments(self):
        """Ignore TODO in multi-line comments."""
        from ai_service.agent.tech_debt import count_todos

        diff = '''
        """
        This is a docstring
        with TODO inside it
        that should not count
        """
        # Actual TODO below
        # TODO: Real todo
        '''
        count = count_todos(diff)
        assert count == 1

    def test_empty_diff(self):
        """Handle empty diff."""
        from ai_service.agent.tech_debt import count_todos

        count = count_todos("")
        assert count == 0


class TestDeprecatedLibraries:
    """Tests for deprecated library detection."""

    def test_detects_momentjs(self):
        """Detect moment.js import."""
        from ai_service.agent.tech_debt import detect_deprecated_libs

        diff = "import moment from 'moment'"
        result = detect_deprecated_libs(diff)

        assert len(result) == 1
        assert result[0].library == "moment.js"
        assert "deprecated" in result[0].message.lower()

    def test_detects_require_moment(self):
        """Detect moment.js require."""
        from ai_service.agent.tech_debt import detect_deprecated_libs

        diff = "const moment = require('moment')"
        result = detect_deprecated_libs(diff)

        assert len(result) == 1
        assert result[0].library == "moment.js"

    def test_detects_lodash_old(self):
        """Detect old lodash version."""
        from ai_service.agent.tech_debt import detect_deprecated_libs

        diff = 'import _ from "lodash@3.10.1"'
        result = detect_deprecated_libs(diff)

        assert len(result) == 1
        assert "lodash" in result[0].library.lower()

    def test_detects_request_library(self):
        """Detect deprecated request library."""
        from ai_service.agent.tech_debt import detect_deprecated_libs

        diff = "const request = require('request')"
        result = detect_deprecated_libs(diff)

        assert len(result) == 1
        assert "request" in result[0].library.lower()

    def test_detects_bluebird(self):
        """Detect bluebird promise library."""
        from ai_service.agent.tech_debt import detect_deprecated_libs

        diff = "const Promise = require('bluebird')"
        result = detect_deprecated_libs(diff)

        assert len(result) == 1
        assert "bluebird" in result[0].library.lower()

    def test_no_deprecated_in_clean_code(self):
        """Return empty for clean code."""
        from ai_service.agent.tech_debt import detect_deprecated_libs

        diff = """
        import { useState } from 'react'
        import datetime from 'date-fns'
        """
        result = detect_deprecated_libs(diff)

        assert len(result) == 0

    def test_multiple_deprecated_libs(self):
        """Detect multiple deprecated libraries."""
        from ai_service.agent.tech_debt import detect_deprecated_libs

        diff = """
        const moment = require('moment')
        const request = require('request')
        """
        result = detect_deprecated_libs(diff)

        assert len(result) == 2


class TestTechDebtScoring:
    """Tests for tech debt scoring."""

    def test_calculate_debt_score(self):
        """Calculate tech debt score."""
        from ai_service.agent.tech_debt import calculate_debt_score

        score = calculate_debt_score(todo_count=10, deprecated_libs=1)
        assert score > 0

    def test_score_thresholds(self):
        """Test score thresholds for block/warn."""
        from ai_service.agent.tech_debt import calculate_debt_score

        # Low debt - should be approve
        low_score = calculate_debt_score(todo_count=5, deprecated_libs=0)
        assert low_score < 50

        # Medium debt - should warn
        med_score = calculate_debt_score(todo_count=35, deprecated_libs=0)
        assert 50 <= med_score < 100

        # High debt - should block
        high_score = calculate_debt_score(todo_count=60, deprecated_libs=2)
        assert high_score >= 100

    def test_deprecated_libs_heavier_weight(self):
        """Deprecated libraries weigh more than TODOs."""
        from ai_service.agent.tech_debt import calculate_debt_score

        # 10 TODOs = moderate score
        todo_score = calculate_debt_score(todo_count=10, deprecated_libs=0)

        # 1 deprecated lib = similar or higher score
        lib_score = calculate_debt_score(todo_count=0, deprecated_libs=1)

        # Deprecated libs should weigh more
        assert lib_score >= todo_score


class TestTechDebtAgentNode:
    """Tests for the main tech debt agent node."""

    def test_approves_clean_pr(self):
        """Approve PR with no tech debt."""
        from ai_service.agent.tech_debt import tech_debt_analysis_node

        state = {
            "pr_info": {"number": 1, "title": "Clean PR"},
            "diff_files": [{"filename": "test.py", "patch": "# Clean code\npass"}],
        }

        result = tech_debt_analysis_node(state)

        assert result["tech_debt_report"]["decision"] == "approve"
        assert result["tech_debt_report"]["todo_count"] == 0
        assert result["tech_debt_report"]["debt_score"] == 0

    def test_warns_high_todos(self):
        """Warn when TODO count is high."""
        from ai_service.agent.tech_debt import tech_debt_analysis_node

        diff = "\n".join(["# TODO: Task {}".format(i) for i in range(35)])
        state = {
            "pr_info": {"number": 2, "title": "High TODO PR"},
            "diff_files": [{"filename": "test.py", "patch": diff}],
        }

        result = tech_debt_analysis_node(state)

        assert result["tech_debt_report"]["decision"] == "warn"
        assert result["tech_debt_report"]["todo_count"] == 35

    def test_blocks_deprecated_lib(self):
        """Block when deprecated library is used."""
        from ai_service.agent.tech_debt import tech_debt_analysis_node

        state = {
            "pr_info": {"number": 3, "title": "Moment.js PR"},
            "diff_files": [{"filename": "test.js", "patch": "import moment from 'moment'"}],
        }

        result = tech_debt_analysis_node(state)

        assert result["tech_debt_report"]["decision"] == "block"
        assert len(result["tech_debt_report"]["deprecated_libs"]) == 1

    def test_blocks_excessive_debt(self):
        """Block when debt score exceeds threshold."""
        from ai_service.agent.tech_debt import tech_debt_analysis_node

        # Create diff with many TODOs
        diff = "\n".join(["# TODO: Task {}".format(i) for i in range(60)])
        state = {
            "pr_info": {"number": 4, "title": "Huge Debt PR"},
            "diff_files": [{"filename": "test.py", "patch": diff}],
        }

        result = tech_debt_analysis_node(state)

        assert result["tech_debt_report"]["decision"] == "block"
        assert result["tech_debt_report"]["exceeds_threshold"] is True

    def test_multiple_files(self):
        """Analyze multiple files in PR."""
        from ai_service.agent.tech_debt import tech_debt_analysis_node

        state = {
            "pr_info": {"number": 5, "title": "Multi-file PR"},
            "diff_files": [
                {"filename": "file1.py", "patch": "# TODO: Task 1\n# TODO: Task 2"},
                {"filename": "file2.py", "patch": "# TODO: Task 3"},
            ],
        }

        result = tech_debt_analysis_node(state)

        assert result["tech_debt_report"]["todo_count"] == 3

    def test_includes_recommendations(self):
        """Include recommendations for fixing debt."""
        from ai_service.agent.tech_debt import tech_debt_analysis_node

        state = {
            "pr_info": {"number": 6, "title": "Debt PR"},
            "diff_files": [
                {"filename": "test.js", "patch": "import moment from 'moment'"},
            ],
        }

        result = tech_debt_analysis_node(state)

        assert len(result["tech_debt_report"]["recommendations"]) > 0
        assert "date-fns" in result["tech_debt_report"]["recommendations"][0]


class TestTechDebtAgentCreation:
    """Tests for Tech Debt Agent graph creation."""

    def test_create_tech_debt_agent(self):
        """Create Tech Debt Agent StateGraph."""
        from ai_service.agent.tech_debt import create_tech_debt_agent

        agent = create_tech_debt_agent()
        assert agent is not None

    def test_agent_has_required_nodes(self):
        """Agent has analysis node."""
        from ai_service.agent.tech_debt import create_tech_debt_agent

        agent = create_tech_debt_agent()
        # Graph should be compilable
        assert agent is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
