"""Postgres Checkpointer Infrastructure for ExecOps.

This module provides LangGraph persistence using PostgreSQL.
Uses langgraph-checkpoint-postgres for durable state management.

Usage:
    from ai_service.infrastructure.checkpointer import get_checkpointer

    graph = create_release_hygiene_graph()
    checkpointer = get_checkpointer()

    # Invoke with checkpointing
    result = graph.invoke(
        state,
        config=RunnableConfig(
            configurable={"thread_id": event_id},
            checkpointers=[checkpointer]
        )
    )
"""

import logging
from typing import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager

logger = logging.getLogger(__name__)

# Global checkpointer instances (lazy initialization)
_async_checkpointer = None
_sync_checkpointer = None


def get_database_url() -> str:
    """Get database URL from environment."""
    import os
    return os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")


def _get_postgres_classes():
    """Lazy import of postgres checkpointer classes."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.checkpoint.postgres import PostgresSaver
    return PostgresSaver, AsyncPostgresSaver


@contextmanager
def get_sync_checkpointer() -> Generator:
    """Get synchronous Postgres checkpointer.

    Usage:
        with get_sync_checkpointer() as checkpointer:
            graph.compile(checkpointer=checkpointer)
    """
    global _sync_checkpointer

    if _sync_checkpointer is None:
        PostgresSaver, _ = _get_postgres_classes()
        db_uri = get_database_url()
        _sync_checkpointer = PostgresSaver.from_conn_string(db_uri)
        # Create tables on first use
        _sync_checkpointer.setup()
        logger.info("Initialized sync Postgres checkpointer")

    yield _sync_checkpointer


@asynccontextmanager
async def get_async_checkpointer() -> AsyncGenerator:
    """Get asynchronous Postgres checkpointer.

    Usage:
        async with get_async_checkpointer() as checkpointer:
            await graph.ainvoke(state, config=config)
    """
    global _async_checkpointer

    if _async_checkpointer is None:
        _, AsyncPostgresSaver = _get_postgres_classes()
        db_uri = get_database_url()
        _async_checkpointer = AsyncPostgresSaver.from_conn_string(db_uri)
        # Create tables on first use
        await _async_checkpointer.setup()
        logger.info("Initialized async Postgres checkpointer")

    yield _async_checkpointer


class CheckpointerManager:
    """Manages checkpointer lifecycle for FastAPI dependency injection."""

    def __init__(self, db_url: str | None = None):
        self.db_url = db_url or get_database_url()
        self._instance = None

    async def get_checkpointer(self):
        """Get or create checkpointer instance."""
        if self._instance is None:
            _, AsyncPostgresSaver = _get_postgres_classes()
            self._instance = AsyncPostgresSaver.from_conn_string(self.db_url)
            await self._instance.setup()
            logger.info("CheckpointerManager initialized")
        return self._instance

    async def close(self) -> None:
        """Close checkpointer connection."""
        if self._instance:
            await self._instance.aclose()
            self._instance = None


# Convenience function for FastAPI dependency
def get_checkpointer_manager() -> CheckpointerManager:
    """Get checkpointer manager for FastAPI dependency injection.

    Usage in FastAPI:
        from fastapi import Depends

        async def process_event(
            checkpointer: CheckpointerManager = Depends(get_checkpointer_manager)
        ):
            cp = await checkpointer.get_checkpointer()
            ...
    """
    return CheckpointerManager()


# Checkpointer configuration for graphs
class GraphCheckpointerConfig:
    """Pre-configured checkpointer settings for different deployment modes."""

    DEVELOPMENT = {
        "checkpointer": "memory",  # Use in-memory for dev
        "urable": False,
    }

    PRODUCTION = {
        "checkpointer": "postgres",
        "urable": True,
    }

    @staticmethod
    def get_thread_id(event_id: str, vertical: str) -> str:
        """Generate thread_id for checkpointing.

        Format: {vertical}-{event_id}
        Example: release-123e4567-e89b
        """
        return f"{vertical}-{event_id}"

    @staticmethod
    def get_configurable(thread_id: str, checkpoint_ns: str = "") -> dict:
        """Get configurable dict for graph invocation."""
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
            }
        }


async def setup_postgres_tables() -> None:
    """One-time setup to create Postgres tables for LangGraph checkpointing.

    Call this during application startup or migration.
    """
    logger.info("Setting up Postgres checkpointer tables...")
    async with get_async_checkpointer() as cp:
        # Tables are created by .setup()
        logger.info("Postgres checkpointer tables ready")


def migrate_from_memory_to_postgres(
    memory_checkpointer,
    postgres_checkpointer,
    thread_ids: list[str]
) -> None:
    """Migrate checkpoints from memory to Postgres.

    Useful for development -> production migration.

    Args:
        memory_checkpointer: Existing memory checkpointer
        postgres_checkpointer: Target Postgres checkpointer
        thread_ids: List of thread IDs to migrate
    """
    import json

    for thread_id in thread_ids:
        config = {"configurable": {"thread_id": thread_id}}
        checkpoint = memory_checkpointer.get(config)

        if checkpoint:
            # Convert to dict format for Postgres
            checkpoint_dict = {
                "v": checkpoint.get("v", 1),
                "ts": checkpoint.get("ts", ""),
                "id": checkpoint.get("id", ""),
                "channel_values": checkpoint.get("channel_values", {}),
                "channel_versions": checkpoint.get("channel_versions", {}),
                "versions_seen": checkpoint.get("versions_seen", {}),
            }
            postgres_checkpointer.put(config, checkpoint_dict, {}, {})

    logger.info(f"Migrated {len(thread_ids)} checkpoints to Postgres")
