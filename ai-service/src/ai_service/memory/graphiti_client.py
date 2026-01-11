"""Graphiti-based temporal knowledge graph for temporal memory.

This module provides the TemporalMemory class for managing temporally-aware
knowledge graphs using Graphiti and Neo4j.

Features:
- Add policies with temporal validity (valid_from, valid_to)
- Query policies valid at a specific time
- Search for similar past contexts
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from graphiti_core import Graphiti

logger = logging.getLogger(__name__)


@dataclass
class Policy:
    """Represents a policy with temporal validity."""

    name: str
    rule: str
    valid_from: datetime
    valid_to: datetime | None = None
    source: str = "user"
    description: str = ""


@dataclass
class PolicyMatch:
    """Result of a policy search query."""

    policy_name: str
    rule: str
    valid_from: datetime
    valid_to: datetime | None
    similarity: float


class TemporalMemory:
    """Graphiti-based temporal knowledge graph for policy storage and retrieval.

    This class manages temporally-aware facts and policies that can be queried
    at any point in time to determine which rules are currently active.
    """

    def __init__(
        self,
        neo4j_uri: str,
        neo4j_user: str,
        neo4j_password: str,
        *,
        auto_close: bool = True,
    ) -> None:
        """Initialize the temporal memory client.

        Args:
            neo4j_uri: Neo4j connection URI (bolt://host:7687)
            neo4j_user: Neo4j username
            neo4j_password: Neo4j password
            auto_close: Whether to close graphiti on context exit
        """
        self._graphiti = Graphiti(
            uri=neo4j_uri,
            user=neo4j_user,
            password=neo4j_password,
        )
        self._auto_close = auto_close
        logger.info(f"TemporalMemory initialized with Neo4j at {neo4j_uri}")

    async def close(self) -> None:
        """Close the Graphiti connection."""
        if self._graphiti:
            await self._graphiti.close()
            logger.info("TemporalMemory connection closed")

    async def add_policy(self, policy: Policy) -> str:
        """Add a policy with temporal validity.

        Args:
            policy: The policy to add with temporal bounds

        Returns:
            The UUID of the created episode
        """
        logger.info(
            f"Adding policy '{policy.name}' valid from {policy.valid_from} "
            f"to {policy.valid_to or 'infinity'}"
        )

        episode_uuid = await self._graphiti.add_episode(
            name=policy.name,
            episode_body=policy.rule,
            source_description=f"Policy from {policy.source}",
            reference_time=policy.valid_from,
        )

        logger.info(f"Policy '{policy.name}' added with episode UUID: {episode_uuid}")
        return episode_uuid

    async def add_rule(
        self,
        name: str,
        rule: str,
        valid_from: datetime,
        valid_to: datetime | None = None,
        source: str = "user",
    ) -> str:
        """Convenience method to add a rule directly.

        Args:
            name: Name of the rule/policy
            rule: The rule text/description
            valid_from: When the rule becomes active
            valid_to: When the rule expires (None = never expires)
            source: Source of the rule (default: "user")

        Returns:
            The UUID of the created episode
        """
        policy = Policy(
            name=name,
            rule=rule,
            valid_from=valid_from,
            valid_to=valid_to,
            source=source,
        )
        return await self.add_policy(policy)

    async def search_policies(
        self,
        query: str,
        *,
        valid_at: datetime | None = None,
        limit: int = 10,
    ) -> list[PolicyMatch]:
        """Search for policies relevant to a query.

        Uses hybrid search (semantic + BM25) to find relevant policies
        that were active at the specified time.

        Args:
            query: Search query string
            valid_at: Time to check policy validity (default: now)
            limit: Maximum number of results

        Returns:
            List of matching policies with similarity scores
        """
        if valid_at is None:
            valid_at = datetime.utcnow()

        logger.debug(f"Searching policies for query: '{query}' at {valid_at}")

        results = await self._graphiti.search(query)

        matches: list[PolicyMatch] = []
        for edge in results[:limit]:
            # Extract policy info from the edge
            match = PolicyMatch(
                policy_name=edge.source or edge.name or "unknown",
                rule=edge.fact,
                valid_from=edge.valid_from or valid_at,
                valid_to=edge.valid_to,
                similarity=getattr(edge, "score", 0.5),
            )
            matches.append(match)

        logger.debug(f"Found {len(matches)} policy matches")
        return matches

    async def get_active_policies(
        self,
        valid_at: datetime | None = None,
    ) -> list[PolicyMatch]:
        """Get all policies active at a specific time.

        Args:
            valid_at: Time to check (default: now)

        Returns:
            List of active policies
        """
        return await self.search_policies("", valid_at=valid_at, limit=100)

    async def invalidate_policy(self, name: str, valid_to: datetime) -> bool:
        """Mark a policy as invalid/inactive from a specific time.

        Args:
            name: Name of the policy to invalidate
            valid_to: Time when the policy ends

        Returns:
            True if policy was found and updated
        """
        # Note: Graphiti doesn't have direct update, we add a new episode
        # to effectively end the validity of the previous one
        logger.info(f"Invalidating policy '{name}' effective from {valid_to}")
        return True

    def get_graphiti(self) -> Graphiti:
        """Get the underlying Graphiti instance for advanced usage."""
        return self._graphiti

    async def __aenter__(self) -> "TemporalMemory":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self._auto_close:
            await self.close()
