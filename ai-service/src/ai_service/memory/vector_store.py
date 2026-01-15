"""Semantic memory layer using PostgreSQL + pgvector.

This module provides the SemanticMemory class for storing and searching
text content using vector embeddings stored in pgvector.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector

logger = logging.getLogger(__name__)


@dataclass
class ContextMatch:
    """Result of a semantic search."""

    content: str
    speaker: str
    timestamp: datetime
    metadata: dict[str, Any]
    similarity: float


class SemanticMemory:
    """PostgreSQL + pgvector for semantic search of past context.

    This class stores text content (messages, decisions, policies) and
    enables similarity search using embeddings.
    """

    def __init__(
        self,
        connection_string: str,
        embedding_model: str = "text-embedding-3-small",
        *,
        collection_name: str = "founder_context",
    ) -> None:
        """Initialize the semantic memory store.

        Args:
            connection_string: PostgreSQL connection URL
            embedding_model: OpenAI embedding model name
            collection_name: Name of the vector collection
        """
        self._embeddings = OpenAIEmbeddings(model=embedding_model)
        self._collection_name = collection_name
        self._connection_string = connection_string

        self._vector_store = PGVector(
            embeddings=self._embeddings,
            connection=connection_string,
            collection_name=collection_name,
            pre_delete_collection=False,  # Preserve existing data
        )

        logger.info(
            f"SemanticMemory initialized with collection '{collection_name}'"
        )

    async def ingest_message(
        self,
        content: str,
        speaker: str,
        timestamp: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[str]:
        """Ingest a message for semantic search.

        Args:
            content: The message text to store
            speaker: Who said/wrote this
            timestamp: When it was said (default: now)
            metadata: Additional context metadata

        Returns:
            List of document IDs
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        doc = Document(
            page_content=content,
            metadata={
                "speaker": speaker,
                "timestamp": timestamp.isoformat(),
                "type": "message",
                **(metadata or {}),
            },
        )

        ids = await self._vector_store.add_documents([doc])
        logger.info(f"Ingested message from '{speaker}' with ID: {ids[0]}")
        return ids

    async def ingest_context(
        self,
        content: str,
        context_type: str,
        timestamp: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[str]:
        """Ingest a context entry with type categorization.

        Args:
            content: The text content
            context_type: Type (decision, policy, event, etc.)
            timestamp: When this occurred
            metadata: Additional metadata

        Returns:
            List of document IDs
        """
        if timestamp is None:
            timestamp = datetime.utcnow()

        doc = Document(
            page_content=content,
            metadata={
                "timestamp": timestamp.isoformat(),
                "type": context_type,
                **(metadata or {}),
            },
        )

        ids = await self._vector_store.add_documents([doc])
        logger.info(
            f"Ingested {context_type} context with ID: {ids[0]}"
        )
        return ids

    async def search_similar(
        self,
        query: str,
        k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[ContextMatch]:
        """Search for similar past context.

        Args:
            query: Search query
            k: Number of results
            filter_metadata: Optional metadata filters

        Returns:
            List of matching contexts sorted by similarity
        """
        logger.debug(f"Searching for similar context: '{query}'")

        search_kwargs = {"k": k}
        if filter_metadata:
            search_kwargs["filter"] = filter_metadata

        docs = await self._vector_store.similarity_search(query, **search_kwargs)

        matches: list[ContextMatch] = []
        for doc in docs:
            match = ContextMatch(
                content=doc.page_content,
                speaker=doc.metadata.get("speaker", "unknown"),
                timestamp=datetime.fromisoformat(
                    doc.metadata.get("timestamp", datetime.utcnow().isoformat())
                ),
                metadata=doc.metadata,
                similarity=0.5,  # PGVector doesn't return scores by default
            )
            matches.append(match)

        logger.debug(f"Found {len(matches)} similar contexts")
        return matches

    async def search_by_type(
        self,
        query: str,
        context_type: str,
        k: int = 5,
    ) -> list[ContextMatch]:
        """Search for similar context of a specific type.

        Args:
            query: Search query
            context_type: Filter by type (decision, policy, event, etc.)
            k: Number of results

        Returns:
            List of matching contexts
        """
        return await self.search_similar(
            query,
            k=k,
            filter_metadata={"type": context_type},
        )

    async def search_decisions(
        self,
        query: str,
        k: int = 3,
    ) -> list[ContextMatch]:
        """Search for similar past decisions.

        Args:
            query: Search query
            k: Number of results

        Returns:
            List of matching past decisions
        """
        return await self.search_by_type(query, "decision", k=k)

    async def search_policies(
        self,
        query: str,
        k: int = 3,
    ) -> list[ContextMatch]:
        """Search for similar past policies.

        Args:
            query: Search query
            k: Number of results

        Returns:
            List of matching policies
        """
        return await self.search_by_type(query, "policy", k=k)

    def get_vector_store(self) -> PGVector:
        """Get the underlying PGVector store for advanced usage."""
        return self._vector_store

    async def delete_collection(self) -> None:
        """Delete the vector collection (use with caution)."""
        await self._vector_store.delete_collection()
        logger.info(f"Collection '{self._collection_name}' deleted")
