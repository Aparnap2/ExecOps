"""Raw Neo4j GraphService for Sentinel.

Extracted from graphiti_client.py - keeps the Neo4j connection,
replaces Graphiti abstraction with raw Cypher queries.

Connection:
    - URI: bolt://localhost:7687
    - Auth: neo4j/founderos_secret
"""

import logging
from typing import Any
from contextlib import asynccontextmanager

from neo4j import AsyncGraphDatabase

logger = logging.getLogger(__name__)


# Default Neo4j connection settings
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "founderos_secret"


class GraphService:
    """Raw Neo4j Cypher queries for Sentinel use case.

    Replaces Graphiti for custom relationship queries.
    Provides:
    - PR -> Issue linking (IMPLEMENTS relationship)
    - Issue context retrieval (state, labels, comments)
    - Risk score calculation based on graph context
    """

    def __init__(
        self,
        uri: str = NEO4J_URI,
        user: str = NEO4J_USER,
        password: str = NEO4J_PASSWORD,
    ) -> None:
        """Initialize Neo4j connection.

        Args:
            uri: Neo4j Bolt URI
            user: Neo4j username
            password: Neo4j password
        """
        self._uri = uri
        self._user = user
        self._password = password
        self._driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        logger.info(f"GraphService initialized with {uri}")

    async def close(self) -> None:
        """Close Neo4j connection."""
        if self._driver:
            await self._driver.close()
            logger.info("GraphService connection closed")

    @asynccontextmanager
    async def session(self):
        """Context manager for Neo4j session."""
        async with self._driver.session() as session:
            yield session

    async def query(self, cypher: str, **params) -> list[dict[str, Any]]:
        """Execute raw Cypher query.

        Args:
            cypher: Cypher query string
            **params: Query parameters

        Returns:
            List of result dictionaries
        """
        async with self.session() as session:
            result = await session.run(cypher, **params)
            return [dict(record) async for record in result]

    # ==========================================================================
    # Sentinel-Specific Queries
    # ==========================================================================

    async def link_pr_to_issue(self, pr_id: str, issue_id: str) -> dict:
        """Create PR -> IMPLEMENTS -> Issue relationship.

        Uses MERGE for idempotency - safe to call multiple times.

        Args:
            pr_id: GitHub PR node ID (e.g., "12345")
            issue_id: Linear Issue ID (e.g., "LIN-123")

        Returns:
            Dict with created relationship info
        """
        result = await self.query("""
            MERGE (p:PR {id: $pr_id})
            MERGE (i:Issue {id: $issue_id})
            MERGE (p)-[r:IMPLEMENTS]->(i)
            RETURN p.id as pr_id, i.id as issue_id, type(r) as relationship
        """, pr_id=pr_id, issue_id=issue_id)

        logger.info(f"Linked PR {pr_id} -> IMPLEMENTS -> Issue {issue_id}")
        return result[0] if result else {}

    async def get_issue_context(self, issue_id: str) -> dict | None:
        """Fetch full issue context for PR review.

        Returns:
            Dict with issue state, labels, comment count, or None if not found
        """
        results = await self.query("""
            MATCH (i:Issue {id: $id})
            OPTIONAL MATCH (i)<-[:LINKED_TO]-(c:Comment)
            OPTIONAL MATCH (i)-[:HAS_LABEL]->(l:Label)
            RETURN i {
                .id,
                .title,
                .state,
                .description,
                .priority,
                .created_at
            } as issue,
                   labels: collect(DISTINCT l.name) as labels,
                   comment_count: count(DISTINCT c) as comment_count
        """, id=issue_id)

        if results:
            return results[0]
        return None

    async def get_pr_context(self, pr_id: str) -> dict | None:
        """Fetch PR and its linked issue context.

        Returns:
            Dict with PR info and linked issue, or None if PR not found
        """
        results = await self.query("""
            MATCH (p:PR {id: $id})
            OPTIONAL MATCH (p)-[:IMPLEMENTS]->(i:Issue)
            OPTIONAL MATCH (i)<-[:LINKED_TO]-(c:Comment)
            OPTIONAL MATCH (i)-[:HAS_LABEL]->(l:Label)
            RETURN p {
                .id,
                .title,
                .number,
                .author,
                .url,
                .state
            } as pr,
                   i {
                .id,
                .title,
                .state,
                .description
            } as issue,
                   collect(DISTINCT l.name) as issue_labels,
                   count(DISTINCT c) as issue_comments
        """, id=pr_id)

        return results[0] if results else None

    async def get_pr_risk_score(self, pr_id: str) -> float:
        """Calculate risk score based on graph context.

        Risk factors:
        - No linked issue: 0.5
        - Issue in BACKLOG: 0.3
        - Issue has "Needs Spec" label: 0.4
        - Issue has "VIP" label: -0.2 (lower risk)

        Returns:
            Risk score 0.0 (safe) to 1.0 (high risk)
        """
        results = await self.query("""
            MATCH (p:PR {id: $id})
            OPTIONAL MATCH (p)-[:IMPLEMENTS]->(i:Issue)
            WITH p, i,
                 CASE WHEN i IS NULL THEN 1 ELSE 0 END as no_issue,
                 CASE WHEN i.state = 'BACKLOG' THEN 0.3 ELSE 0 END as state_risk,
                 CASE WHEN exists((i)-[:HAS_LABEL]->(:Label {name: 'Needs Spec'})) THEN 0.4 ELSE 0 END as spec_risk,
                 CASE WHEN exists((i)-[:HAS_LABEL]->(:Label {name: 'VIP'})) THEN -0.2 ELSE 0 END as vip_bonus
            RETURN no_issue + state_risk + spec_risk + vip_bonus as risk_score
            LIMIT 1
        """, id=pr_id)

        if results:
            score = float(results[0].get("risk_score", 0.0))
            return max(0.0, min(1.0, score))  # Clamp between 0 and 1

        return 0.5  # Default: no context = moderate risk

    async def ensure_constraints(self) -> None:
        """Create Neo4j constraints for data integrity.

        Call this once during startup.
        """
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (i:Issue) REQUIRE i.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:PR) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (v:Vendor) REQUIRE v.id IS UNIQUE",
        ]

        for cypher in constraints:
            try:
                await self.query(cypher)
            except Exception as e:
                logger.warning(f"Constraint creation skipped: {e}")

        logger.info("Neo4j constraints ensured")

    async def health_check(self) -> bool:
        """Check Neo4j connectivity.

        Returns:
            True if connected and responsive
        """
        try:
            result = await self.query("RETURN 1 as health")
            return result[0]["health"] == 1 if result else False
        except Exception as e:
            logger.error(f"Neo4j health check failed: {e}")
            return False

    async def __aenter__(self) -> "GraphService":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


# Convenience function for getting GraphService
def get_graph_service() -> GraphService:
    """Get GraphService instance with default connection."""
    return GraphService()


# Test function (run directly to verify connection)
async def _test_connection():
    """Quick test to verify Neo4j connection."""
    print("Testing Neo4j connection...")

    graph = GraphService()

    # Health check
    healthy = await graph.health_check()
    print(f"Health check: {'✓' if healthy else '✗'}")

    if healthy:
        # Ensure constraints
        await graph.ensure_constraints()
        print("Constraints created: ✓")

        # Test link
        result = await graph.link_pr_to_issue("test-pr-123", "LIN-456")
        print(f"Test link created: {result}")

        # Test risk score
        score = await graph.get_pr_risk_score("test-pr-123")
        print(f"Risk score: {score}")

    await graph.close()
    print("Connection test complete.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(_test_connection())
