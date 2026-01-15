"""Test script to verify real database connections."""

import asyncio
import sys
sys.path.insert(0, '/home/aparna/Desktop/founder_os/ai-service/src')

from ai_service.memory.graphiti_client import TemporalMemory, Policy
from ai_service.memory.vector_store import SemanticMemory
from datetime import datetime, timezone


async def test_temporal_memory():
    """Test TemporalMemory with real Neo4j."""
    print("Testing TemporalMemory with Neo4j...")

    async with TemporalMemory(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="founderos_secret",
    ) as memory:
        # Add a test policy
        policy = Policy(
            name="test_policy",
            rule="Test rule for verification",
            valid_from=datetime(2024, 1, 1, tzinfo=timezone.utc),
            valid_to=None,
            source="test",
        )

        episode_uuid = await memory.add_policy(policy)
        print(f"  Added policy: {episode_uuid}")

        # Search for policies
        results = await memory.search_policies("test rule")
        print(f"  Found {len(results)} matching policies")

        if results:
            print(f"  First result: {results[0].policy_name}")

    print("  TemporalMemory test PASSED!")
    return True


async def test_semantic_memory():
    """Test SemanticMemory with real PostgreSQL + pgvector."""
    print("Testing SemanticMemory with PostgreSQL + pgvector...")

    memory = SemanticMemory(
        connection_string="postgresql://founderos:founderos_secret@localhost:5432/founderos",
    )

    # Ingest a test message
    now = datetime.now(timezone.utc)
    ids = await memory.ingest_message(
        content="This is a test message for verification",
        speaker="test_user",
        timestamp=now,
        metadata={"test": True},
    )
    print(f"  Ingested message: {ids}")

    # Search for similar content
    results = await memory.search_similar("test message", k=5)
    print(f"  Found {len(results)} similar contexts")

    if results:
        print(f"  First result: {results[0].content[:50]}...")

    memory._vector_store.delete_collection()
    print("  SemanticMemory test PASSED!")
    return True


async def main():
    """Run all connection tests."""
    print("=" * 60)
    print("FounderOS Memory Layer Connection Tests")
    print("=" * 60)

    all_passed = True

    try:
        await test_temporal_memory()
    except Exception as e:
        print(f"  TemporalMemory test FAILED: {e}")
        all_passed = False

    print()

    try:
        await test_semantic_memory()
    except Exception as e:
        print(f"  SemanticMemory test FAILED: {e}")
        all_passed = False

    print()
    print("=" * 60)
    if all_passed:
        print("All tests PASSED!")
    else:
        print("Some tests FAILED!")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
