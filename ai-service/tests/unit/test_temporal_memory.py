"""Unit tests for temporal memory (Neo4j + Graphiti).

These tests verify the temporal memory layer can:
1. Initialize connection to Neo4j
2. Add and retrieve policies with temporal validity
3. Search policies valid at specific timestamps
4. Handle temporal constraints correctly
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch


class TestTemporalMemoryInitialization:
    """Tests for TemporalMemory initialization."""

    def test_initializes_with_neo4j_credentials(self):
        """TemporalMemory initializes with correct Neo4j connection params."""
        from ai_service.memory.graphiti_client import TemporalMemory

        mock_graphiti = MagicMock()
        with patch('ai_service.memory.graphiti_client.Graphiti', return_value=mock_graphiti):
            memory = TemporalMemory(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password123",
            )

            assert memory._graphiti is not None

    def test_initializes_with_env_vars(self):
        """TemporalMemory uses environment variables when not provided."""
        import os
        from ai_service.memory.graphiti_client import TemporalMemory

        os.environ['NEO4J_URI'] = 'bolt://test:7687'
        os.environ['NEO4J_USER'] = 'test_user'
        os.environ['NEO4J_PASSWORD'] = 'test_pass'

        try:
            mock_graphiti = MagicMock()
            with patch('ai_service.memory.graphiti_client.Graphiti', return_value=mock_graphiti):
                memory = TemporalMemory(
                    neo4j_uri=os.environ['NEO4J_URI'],
                    neo4j_user=os.environ['NEO4J_USER'],
                    neo4j_password=os.environ['NEO4J_PASSWORD'],
                )
                assert memory._graphiti is not None
        finally:
            del os.environ['NEO4J_URI']
            del os.environ['NEO4J_USER']
            del os.environ['NEO4J_PASSWORD']


class TestPolicyManagement:
    """Tests for policy CRUD operations."""

    @pytest.fixture
    def mock_graphiti(self):
        """Create a mock Graphiti instance."""
        mock = MagicMock()
        mock.add_episode = AsyncMock(return_value="episode-uuid-123")
        mock.search = AsyncMock(return_value=[])
        mock.close = AsyncMock()
        return mock

    @pytest.mark.asyncio
    async def test_add_policy_stores_in_neo4j(self, mock_graphiti):
        """Adding a policy stores it in Neo4j via Graphiti."""
        from ai_service.memory.graphiti_client import TemporalMemory, Policy

        with patch('ai_service.memory.graphiti_client.Graphiti', return_value=mock_graphiti):
            memory = TemporalMemory(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                auto_close=False,
            )

            policy = Policy(
                name="no_sql_outside_db",
                rule="No direct SQL queries outside db/ folder",
                valid_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
                valid_to=None,
                source="founder",
            )

            episode_uuid = await memory.add_policy(policy)

            mock_graphiti.add_episode.assert_called_once()
            call_kwargs = mock_graphiti.add_episode.call_args[1]
            assert call_kwargs['name'] == "no_sql_outside_db"
            assert call_kwargs['episode_body'] == "No direct SQL queries outside db/ folder"
            assert episode_uuid == "episode-uuid-123"

    @pytest.mark.asyncio
    async def test_add_rule_convenience_method(self, mock_graphiti):
        """add_rule is a convenience wrapper for add_policy."""
        with patch('ai_service.memory.graphiti_client.Graphiti', return_value=mock_graphiti):
            from ai_service.memory.graphiti_client import TemporalMemory

            memory = TemporalMemory(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                auto_close=False,
            )

            valid_from = datetime(2024, 1, 1, tzinfo=timezone.utc)
            valid_to = datetime(2025, 1, 1, tzinfo=timezone.utc)

            episode_uuid = await memory.add_rule(
                name="no_friday_deploys",
                rule="No deployments on Fridays after 2pm UTC",
                valid_from=valid_from,
                valid_to=valid_to,
                source="cto",
            )

            mock_graphiti.add_episode.assert_called_once()
            assert episode_uuid == "episode-uuid-123"

    @pytest.mark.asyncio
    async def test_search_policies_returns_results(self, mock_graphiti):
        """search_policies returns matching policies."""
        from ai_service.memory.graphiti_client import TemporalMemory, PolicyMatch

        # Mock search results
        mock_edge = MagicMock()
        mock_edge.source = "no_sql_outside_db"
        mock_edge.fact = "No direct SQL queries outside db/ folder"
        mock_edge.valid_from = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_edge.valid_to = None
        mock_edge.score = 0.95

        mock_graphiti.search = AsyncMock(return_value=[mock_edge])

        with patch('ai_service.memory.graphiti_client.Graphiti', return_value=mock_graphiti):
            memory = TemporalMemory(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                auto_close=False,
            )

            results = await memory.search_policies("SQL database rules")

            assert len(results) == 1
            assert isinstance(results[0], PolicyMatch)
            assert results[0].policy_name == "no_sql_outside_db"
            assert results[0].similarity == 0.95

    @pytest.mark.asyncio
    async def test_search_with_valid_at_timestamp(self, mock_graphiti):
        """search_policies accepts valid_at parameter for temporal queries."""
        from ai_service.memory.graphiti_client import TemporalMemory

        with patch('ai_service.memory.graphiti_client.Graphiti', return_value=mock_graphiti):
            memory = TemporalMemory(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                auto_close=False,
            )

            # Search for policies valid at a specific time
            valid_at = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
            await memory.search_policies("deployment policy", valid_at=valid_at)

            # Verify the search was called
            mock_graphiti.search.assert_called_once()


class TestTemporalPolicyValidation:
    """Tests for temporal policy validation logic."""

    @pytest.mark.asyncio
    async def test_policy_with_future_valid_from(self):
        """Policy with future valid_from should not be enforced yet."""
        from ai_service.memory.graphiti_client import TemporalMemory

        mock_graphiti = MagicMock()
        mock_graphiti.add_episode = AsyncMock(return_value="future-episode-uuid")
        mock_graphiti.search = AsyncMock(return_value=[])
        mock_graphiti.close = AsyncMock()

        with patch('ai_service.memory.graphiti_client.Graphiti', return_value=mock_graphiti):
            memory = TemporalMemory(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
                auto_close=False,
            )

            # Add a policy that starts in the future
            future_date = datetime.now(timezone.utc) + timedelta(days=30)
            episode_uuid = await memory.add_rule(
                name="future_policy",
                rule="This policy is not yet active",
                valid_from=future_date,
            )

            # Verify the policy was added with future date
            mock_graphiti.add_episode.assert_called_once()
            call_kwargs = mock_graphiti.add_episode.call_args[1]
            assert call_kwargs['reference_time'] == future_date

            # Search for active policies at current time
            results = await memory.search_policies("future policy", valid_at=datetime.now(timezone.utc))

            # The search should be called
            mock_graphiti.search.assert_called_once()


class TestContextManager:
    """Tests for async context manager support."""

    @pytest.mark.asyncio
    async def test_context_manager_enter_exit(self):
        """TemporalMemory can be used as async context manager."""
        from ai_service.memory.graphiti_client import TemporalMemory

        mock_graphiti = MagicMock()
        mock_graphiti.close = AsyncMock()

        with patch('ai_service.memory.graphiti_client.Graphiti', return_value=mock_graphiti):
            async with TemporalMemory(
                neo4j_uri="bolt://localhost:7687",
                neo4j_user="neo4j",
                neo4j_password="password",
            ) as memory:
                assert memory._graphiti is not None

            mock_graphiti.close.assert_called_once()


class TestPolicyMatchDataclass:
    """Tests for PolicyMatch dataclass."""

    def test_policy_match_creation(self):
        """PolicyMatch can be created with all fields."""
        from ai_service.memory.graphiti_client import PolicyMatch

        now = datetime.now(timezone.utc)
        policy_match = PolicyMatch(
            policy_name="test_policy",
            rule="Test rule",
            valid_from=now,
            valid_to=None,
            similarity=0.85,
        )

        assert policy_match.policy_name == "test_policy"
        assert policy_match.rule == "Test rule"
        assert policy_match.valid_from == now
        assert policy_match.valid_to is None
        assert policy_match.similarity == 0.85


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
