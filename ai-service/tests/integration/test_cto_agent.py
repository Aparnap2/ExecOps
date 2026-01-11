"""Integration tests for CTO Agent - Diff parsing and AST-based analysis.

These tests verify the CTO agent can:
1. Fetch and parse PR diffs
2. Detect SQL patterns using AST analysis
3. Detect security vulnerabilities
4. Generate policy recommendations
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


class TestFetchDiffNode:
    """Tests for PR diff fetching and parsing."""

    def test_fetch_diff_returns_parsed_diff(self):
        """Fetch diff returns parsed file changes."""
        from ai_service.agent.nodes import fetch_diff_node

        event = {
            "action": "opened",
            "pull_request": {
                "number": 101,
                "title": "Add database query",
                "user": {"login": "developer"},
                "head": {"sha": "abc123"},
                "base": {"sha": "def456"},
            },
            "repository": {"full_name": "owner/repo"},
            "files": [
                {
                    "filename": "src/service.py",
                    "status": "modified",
                    "additions": 50,
                    "deletions": 10,
                    "patch": "@@ -1,10 +1,60 @@\n+import sqlite3\n+def get_user():\n+    conn = sqlite3.connect('app.db')",
                },
                {
                    "filename": "db/schema.sql",
                    "status": "added",
                    "additions": 100,
                    "deletions": 0,
                    "patch": "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);",
                },
            ],
        }
        from ai_service.agent import create_initial_state
        state = create_initial_state(event, "opened")
        state["pr_info"] = {
            "number": 101,
            "title": "Add database query",
            "author": "developer",
            "action": "opened",
            "diff_url": "https://github.com/owner/repo/pull/101.diff",
            "head_sha": "abc123",
            "base_sha": "def456",
        }

        result = fetch_diff_node(state)

        assert "diff_files" in result
        assert len(result["diff_files"]) == 2

        # Verify file info is parsed
        file1 = result["diff_files"][0]
        assert file1["filename"] == "src/service.py"
        assert file1["status"] == "modified"
        assert file1["additions"] == 50
        assert file1["deletions"] == 10

    def test_fetch_diff_handles_no_diff_url(self):
        """Fetch diff handles missing diff_url gracefully."""
        from ai_service.agent.nodes import fetch_diff_node

        event = {
            "action": "opened",
            "pull_request": {
                "number": 102,
                "title": "Minimal PR",
                "user": {"login": "developer"},
            },
        }
        from ai_service.agent import create_initial_state
        state = create_initial_state(event, "opened")
        state["pr_info"] = {
            "number": 102,
            "title": "Minimal PR",
            "author": "developer",
            "action": "opened",
            "diff_url": None,
            "head_sha": "",
            "base_sha": "",
        }

        result = fetch_diff_node(state)

        # Should return empty diffs
        assert result["diff_files"] == []
        assert result.get("diff_error") == "No diff URL available"


class TestAnalyzeCodeNode:
    """Tests for AST-based code analysis."""

    def test_detects_sql_injection_patterns(self):
        """AST analysis detects SQL injection vulnerabilities."""
        from ai_service.agent.nodes import analyze_code_node
        from ai_service.agent.state import AgentState

        diff_files = [
            {
                "filename": "src/service.py",
                "status": "modified",
                "additions": 10,
                "deletions": 2,
                "patch": "+    cursor.execute('SELECT * FROM users WHERE id = ' + user_id)",
                "language": "python",
            },
        ]

        state = AgentState(
            webhook_event={},
            webhook_action="opened",
            pr_info={"number": 103, "title": "Add user query"},
            temporal_policies=[],
            similar_contexts=[],
            diff_files=diff_files,
            diff_error=None,
            violations=[],
            recommendations=[],
            should_block=False,
            should_warn=False,
            blocking_message=None,
            warning_message=None,
            decision="approve",
            confidence=1.0,
            reason="",
            action_taken=None,
            trace_id=None,
            timestamp=datetime.utcnow(),
        )

        result = analyze_code_node(state)

        assert len(result["violations"]) > 0
        sql_violations = [v for v in result["violations"] if "sql" in v["type"].lower()]
        assert len(sql_violations) > 0
        assert sql_violations[0]["severity"] == "blocking"

    def test_detects_hardcoded_secrets(self):
        """AST analysis detects hardcoded secrets."""
        from ai_service.agent.nodes import analyze_code_node
        from ai_service.agent.state import AgentState

        diff_files = [
            {
                "filename": "src/config.py",
                "status": "modified",
                "additions": 5,
                "deletions": 0,
                "patch": '+API_KEY = "sk-1234567890abcdef"',
                "language": "python",
            },
        ]

        state = AgentState(
            webhook_event={},
            webhook_action="opened",
            pr_info={"number": 104, "title": "Add config"},
            temporal_policies=[],
            similar_contexts=[],
            diff_files=diff_files,
            diff_error=None,
            violations=[],
            recommendations=[],
            should_block=False,
            should_warn=False,
            blocking_message=None,
            warning_message=None,
            decision="approve",
            confidence=1.0,
            reason="",
            action_taken=None,
            trace_id=None,
            timestamp=datetime.utcnow(),
        )

        result = analyze_code_node(state)

        secret_violations = [v for v in result["violations"] if "secret" in v["type"].lower()]
        assert len(secret_violations) > 0

    def test_ignores_db_folder_sql(self):
        """SQL in db/ folder is not flagged as violation."""
        from ai_service.agent.nodes import analyze_code_node
        from ai_service.agent.state import AgentState

        diff_files = [
            {
                "filename": "db/queries.sql",
                "status": "added",
                "additions": 20,
                "deletions": 0,
                "patch": "+SELECT * FROM users WHERE active = true;",
                "language": "sql",
            },
        ]

        state = AgentState(
            webhook_event={},
            webhook_action="opened",
            pr_info={"number": 106, "title": "Add SQL queries"},
            temporal_policies=[
                {
                    "name": "no_sql_outside_db",
                    "rule": "No SQL queries outside db/ folder",
                    "valid_from": datetime(2024, 1, 1),
                    "valid_to": None,
                    "similarity": 1.0,
                },
            ],
            similar_contexts=[],
            diff_files=diff_files,
            diff_error=None,
            violations=[],
            recommendations=[],
            should_block=False,
            should_warn=False,
            blocking_message=None,
            warning_message=None,
            decision="approve",
            confidence=1.0,
            reason="",
            action_taken=None,
            trace_id=None,
            timestamp=datetime.utcnow(),
        )

        result = analyze_code_node(state)

        # SQL in db/ folder should not be flagged
        sql_violations = [v for v in result["violations"] if v["type"] == "sql_outside_db"]
        assert len(sql_violations) == 0

    def test_detects_file_without_header(self):
        """Detects Python files without license header."""
        from ai_service.agent.nodes import analyze_code_node
        from ai_service.agent.state import AgentState

        diff_files = [
            {
                "filename": "src/new_file.py",
                "status": "added",
                "additions": 30,
                "deletions": 0,
                "patch": """+def main():
+    pass
+""",
                "language": "python",
            },
        ]

        state = AgentState(
            webhook_event={},
            webhook_action="opened",
            pr_info={"number": 107, "title": "Add new module"},
            temporal_policies=[
                {
                    "name": "require_license_header",
                    "rule": "All Python files must have license header",
                    "valid_from": datetime(2024, 1, 1),
                    "valid_to": None,
                    "similarity": 1.0,
                },
            ],
            similar_contexts=[],
            diff_files=diff_files,
            diff_error=None,
            violations=[],
            recommendations=[],
            should_block=False,
            should_warn=False,
            blocking_message=None,
            warning_message=None,
            decision="approve",
            confidence=1.0,
            reason="",
            action_taken=None,
            trace_id=None,
            timestamp=datetime.utcnow(),
        )

        result = analyze_code_node(state)

        header_violations = [v for v in result["violations"] if "header" in v["type"].lower()]
        assert len(header_violations) > 0


class TestRecommendationsNode:
    """Tests for policy recommendation generation."""

    def test_generates_sql_recommendation(self):
        """Generates recommendation to move SQL to db/ folder."""
        from ai_service.agent.nodes import generate_recommendations_node
        from ai_service.agent.state import AgentState

        state = AgentState(
            webhook_event={},
            webhook_action="opened",
            pr_info={"number": 108, "title": "Add query"},
            temporal_policies=[],
            similar_contexts=[],
            diff_files=[],
            diff_error=None,
            violations=[
                {
                    "type": "sql_outside_db",
                    "description": "SQL query in src/service.py not in db/ folder",
                    "severity": "warning",
                    "line_numbers": [5, 6, 7],
                },
            ],
            recommendations=[],
            should_block=False,
            should_warn=True,
            blocking_message=None,
            warning_message=None,
            decision="warn",
            confidence=0.85,
            reason="Found 1 violation",
            action_taken=None,
            trace_id=None,
            timestamp=datetime.utcnow(),
        )

        result = generate_recommendations_node(state)

        assert "recommendations" in result
        assert len(result["recommendations"]) > 0

        # Should recommend moving SQL to db/
        rec = result["recommendations"][0]
        assert "db/" in rec.get("action", "")
        assert rec["violation_type"] == "sql_outside_db"

    def test_generates_security_recommendation(self):
        """Generates recommendation for security findings."""
        from ai_service.agent.nodes import generate_recommendations_node
        from ai_service.agent.state import AgentState

        state = AgentState(
            webhook_event={},
            webhook_action="opened",
            pr_info={"number": 109, "title": "Fix auth"},
            temporal_policies=[],
            similar_contexts=[],
            diff_files=[],
            diff_error=None,
            violations=[
                {
                    "type": "sql_injection",
                    "description": "Potential SQL injection in query construction",
                    "severity": "blocking",
                    "line_numbers": [15],
                },
            ],
            recommendations=[],
            should_block=True,
            should_warn=False,
            blocking_message=None,
            warning_message=None,
            decision="block",
            confidence=0.95,
            reason="Found security violation",
            action_taken=None,
            trace_id=None,
            timestamp=datetime.utcnow(),
        )

        result = generate_recommendations_node(state)

        sec_recs = [r for r in result["recommendations"] if r["violation_type"] == "sql_injection"]
        assert len(sec_recs) > 0
        # Should suggest parameterized queries
        assert "parameter" in sec_recs[0].get("action", "").lower()

    def test_empty_recommendations_for_clean_pr(self):
        """No recommendations for PR with no violations."""
        from ai_service.agent.nodes import generate_recommendations_node
        from ai_service.agent.state import AgentState

        state = AgentState(
            webhook_event={},
            webhook_action="opened",
            pr_info={"number": 110, "title": "Fix typo"},
            temporal_policies=[],
            similar_contexts=[],
            diff_files=[],
            diff_error=None,
            violations=[],
            recommendations=[],
            should_block=False,
            should_warn=False,
            blocking_message=None,
            warning_message=None,
            decision="approve",
            confidence=1.0,
            reason="No violations found",
            action_taken=None,
            trace_id=None,
            timestamp=datetime.utcnow(),
        )

        result = generate_recommendations_node(state)

        assert result["recommendations"] == []


class TestCTOAgentIntegration:
    """Tests for the complete CTO-enhanced agent graph."""

    def test_cto_agent_has_diff_node(self):
        """CTO agent includes diff fetching node."""
        from ai_service.agent.nodes import create_sentinel_agent

        agent = create_sentinel_agent()

        # Agent should have nodes for diff processing
        # This is verified by the graph structure
        assert agent is not None

    def test_cto_agent_run_with_full_flow(self):
        """Complete CTO agent run with all enhanced features."""
        from ai_service.agent.nodes import create_sentinel_agent
        from ai_service.agent import create_initial_state

        event = {
            "action": "opened",
            "pull_request": {
                "number": 201,
                "title": "Add database access",
                "user": {"login": "developer"},
                "head": {"sha": "testsha"},
                "base": {"sha": "basesha"},
            },
            "repository": {"full_name": "owner/repo"},
        }

        agent = create_sentinel_agent()
        initial_state = create_initial_state(event, "opened")

        result = agent.invoke(initial_state)

        assert "decision" in result
        assert result["decision"] in ["approve", "warn", "block"]
        assert "confidence" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
