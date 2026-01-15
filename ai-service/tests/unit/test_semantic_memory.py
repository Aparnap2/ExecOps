"""Unit tests for semantic memory (PostgreSQL + pgvector).

These tests verify the semantic memory layer can:
1. Initialize connection to PostgreSQL with pgvector
2. Ingest messages with embeddings
3. Search for similar content using vector similarity
4. Filter searches by metadata (type, timestamp, etc.)
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


class TestSemanticMemoryInitialization:
    """Tests for SemanticMemory initialization."""

    def test_initializes_with_connection_string(self):
        """SemanticMemory initializes with PostgreSQL connection string."""
        from ai_service.memory.vector_store import SemanticMemory

        mock_vector_store = MagicMock()

        with patch('ai_service.memory.vector_store.PGVector', return_value=mock_vector_store):
            memory = SemanticMemory(
                connection_string="postgresql://user:pass@localhost:5432/db",
            )

            assert memory._connection_string == "postgresql://user:pass@localhost:5432/db"
            assert memory._collection_name == "founder_context"

    def test_initializes_with_custom_collection(self):
        """SemanticMemory uses custom collection name when provided."""
        from ai_service.memory.vector_store import SemanticMemory

        mock_vector_store = MagicMock()

        with patch('ai_service.memory.vector_store.PGVector', return_value=mock_vector_store):
            memory = SemanticMemory(
                connection_string="postgresql://user:pass@localhost:5432/db",
                collection_name="custom_collection",
            )

            assert memory._collection_name == "custom_collection"

    def test_initializes_with_custom_embedding_model(self):
        """SemanticMemory uses custom embedding model when provided."""
        from ai_service.memory.vector_store import SemanticMemory

        mock_vector_store = MagicMock()

        with patch('ai_service.memory.vector_store.PGVector', return_value=mock_vector_store):
            with patch('ai_service.memory.vector_store.OpenAIEmbeddings') as mock_embeddings:
                memory = SemanticMemory(
                    connection_string="postgresql://user:pass@localhost:5432/db",
                    embedding_model="text-embedding-3-large",
                )

                mock_embeddings.assert_called_once_with(model="text-embedding-3-large")


class TestMessageIngestion:
    """Tests for message/document ingestion."""

    @pytest.mark.asyncio
    async def test_ingest_message_stores_content(self):
        """Ingesting a message stores it in pgvector."""
        from ai_service.memory.vector_store import SemanticMemory
        from langchain_core.documents import Document

        # Create mock vector store with properly configured async methods
        mock_vs = MagicMock()
        mock_vs.add_documents = AsyncMock(return_value=["doc-id-123"])
        mock_vs.similarity_search = AsyncMock(return_value=[])
        mock_vs.delete_collection = AsyncMock(return_value=None)

        with patch('ai_service.memory.vector_store.PGVector', return_value=mock_vs):
            memory = SemanticMemory(
                connection_string="postgresql://user:pass@localhost:5432/db",
            )

            # Configure the instance's vector store
            memory._vector_store = mock_vs

            now = datetime.now(timezone.utc)
            ids = await memory.ingest_message(
                content="Customer reported billing issue",
                speaker="support_agent",
                timestamp=now,
                metadata={"ticket_id": "TICKET-123"},
            )

            mock_vs.add_documents.assert_called_once()
            call_args = mock_vs.add_documents.call_args[0][0]

            # Verify the document content
            assert len(call_args) == 1
            assert call_args[0].page_content == "Customer reported billing issue"
            assert call_args[0].metadata["speaker"] == "support_agent"
            assert call_args[0].metadata["ticket_id"] == "TICKET-123"

    @pytest.mark.asyncio
    async def test_ingest_context_with_type(self):
        """Ingesting context with type categorizes it correctly."""
        from ai_service.memory.vector_store import SemanticMemory

        mock_vs = MagicMock()
        mock_vs.add_documents = AsyncMock(return_value=["doc-id-456"])
        mock_vs.similarity_search = AsyncMock(return_value=[])
        mock_vs.delete_collection = AsyncMock(return_value=None)

        with patch('ai_service.memory.vector_store.PGVector', return_value=mock_vs):
            memory = SemanticMemory(
                connection_string="postgresql://user:pass@localhost:5432/db",
            )
            memory._vector_store = mock_vs

            await memory.ingest_context(
                content="Decision: Approved vendor contract for AWS",
                context_type="decision",
            )

            mock_vs.add_documents.assert_called_once()
            call_args = mock_vs.add_documents.call_args[0][0]

            assert call_args[0].metadata["type"] == "decision"


class TestSemanticSearch:
    """Tests for similarity search functionality."""

    @pytest.mark.asyncio
    async def test_search_similar_returns_results(self):
        """Search for similar content returns matching documents."""
        from ai_service.memory.vector_store import SemanticMemory, ContextMatch
        from langchain_core.documents import Document

        # Create mock search results
        mock_doc = Document(
            page_content="Similar past decision about SQL policy",
            metadata={
                "speaker": "cto",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "decision",
            },
        )

        mock_vs = MagicMock()
        mock_vs.add_documents = AsyncMock(return_value=["doc-id-123"])
        mock_vs.similarity_search = AsyncMock(return_value=[mock_doc])
        mock_vs.delete_collection = AsyncMock(return_value=None)

        with patch('ai_service.memory.vector_store.PGVector', return_value=mock_vs):
            memory = SemanticMemory(
                connection_string="postgresql://user:pass@localhost:5432/db",
            )
            memory._vector_store = mock_vs

            results = await memory.search_similar("SQL database policy", k=5)

            assert len(results) == 1
            assert isinstance(results[0], ContextMatch)
            assert "SQL" in results[0].content

    @pytest.mark.asyncio
    async def test_search_by_type_filters_correctly(self):
        """Search by type filters results to specified type."""
        from ai_service.memory.vector_store import SemanticMemory

        mock_vs = MagicMock()
        mock_vs.add_documents = AsyncMock(return_value=["doc-id-123"])
        mock_vs.similarity_search = AsyncMock(return_value=[])
        mock_vs.delete_collection = AsyncMock(return_value=None)

        with patch('ai_service.memory.vector_store.PGVector', return_value=mock_vs):
            memory = SemanticMemory(
                connection_string="postgresql://user:pass@localhost:5432/db",
            )
            memory._vector_store = mock_vs

            # Search for only "policy" type
            await memory.search_by_type(
                query="database access rules",
                context_type="policy",
                k=3,
            )

            mock_vs.similarity_search.assert_called_once()
            call_kwargs = mock_vs.similarity_search.call_args[1]

            # Verify filter was applied
            assert "filter" in call_kwargs
            assert call_kwargs["filter"]["type"] == "policy"

    @pytest.mark.asyncio
    async def test_search_decisions_convenience(self):
        """search_decisions is a convenience wrapper for type-specific search."""
        from ai_service.memory.vector_store import SemanticMemory

        mock_vs = MagicMock()
        mock_vs.add_documents = AsyncMock(return_value=["doc-id-123"])
        mock_vs.similarity_search = AsyncMock(return_value=[])
        mock_vs.delete_collection = AsyncMock(return_value=None)

        with patch('ai_service.memory.vector_store.PGVector', return_value=mock_vs):
            memory = SemanticMemory(
                connection_string="postgresql://user:pass@localhost:5432/db",
            )
            memory._vector_store = mock_vs

            await memory.search_decisions(
                query="previous approval for vendor",
                k=3,
            )

            mock_vs.similarity_search.assert_called_once()
            call_kwargs = mock_vs.similarity_search.call_args[1]

            assert call_kwargs["filter"]["type"] == "decision"

    @pytest.mark.asyncio
    async def test_search_policies_convenience(self):
        """search_policies is a convenience wrapper for type-specific search."""
        from ai_service.memory.vector_store import SemanticMemory

        mock_vs = MagicMock()
        mock_vs.add_documents = AsyncMock(return_value=["doc-id-123"])
        mock_vs.similarity_search = AsyncMock(return_value=[])
        mock_vs.delete_collection = AsyncMock(return_value=None)

        with patch('ai_service.memory.vector_store.PGVector', return_value=mock_vs):
            memory = SemanticMemory(
                connection_string="postgresql://user:pass@localhost:5432/db",
            )
            memory._vector_store = mock_vs

            await memory.search_policies(
                query="deployment rules",
                k=3,
            )

            mock_vs.similarity_search.assert_called_once()
            call_kwargs = mock_vs.similarity_search.call_args[1]

            assert call_kwargs["filter"]["type"] == "policy"


class TestContextMatchDataclass:
    """Tests for ContextMatch dataclass."""

    def test_context_match_creation(self):
        """ContextMatch can be created with all fields."""
        from ai_service.memory.vector_store import ContextMatch

        now = datetime.now(timezone.utc)
        match = ContextMatch(
            content="Past decision content",
            speaker="cto",
            timestamp=now,
            metadata={"type": "decision"},
            similarity=0.88,
        )

        assert match.content == "Past decision content"
        assert match.speaker == "cto"
        assert match.timestamp == now
        assert match.metadata["type"] == "decision"
        assert match.similarity == 0.88


class TestCollectionManagement:
    """Tests for collection lifecycle management."""

    @pytest.mark.asyncio
    async def test_delete_collection(self):
        """delete_collection removes all documents from collection."""
        from ai_service.memory.vector_store import SemanticMemory

        mock_vs = MagicMock()
        mock_vs.add_documents = AsyncMock(return_value=["doc-id-123"])
        mock_vs.similarity_search = AsyncMock(return_value=[])
        mock_vs.delete_collection = AsyncMock(return_value=None)

        with patch('ai_service.memory.vector_store.PGVector', return_value=mock_vs):
            memory = SemanticMemory(
                connection_string="postgresql://user:pass@localhost:5432/db",
            )
            memory._vector_store = mock_vs

            await memory.delete_collection()

            mock_vs.delete_collection.assert_called_once()

    def test_get_vector_store(self):
        """get_vector_store returns the underlying PGVector store."""
        from ai_service.memory.vector_store import SemanticMemory

        mock_vs = MagicMock()

        with patch('ai_service.memory.vector_store.PGVector', return_value=mock_vs):
            memory = SemanticMemory(
                connection_string="postgresql://user:pass@localhost:5432/db",
            )

            assert memory.get_vector_store() is mock_vs


class TestSearchWithFilters:
    """Tests for complex search scenarios with filters."""

    @pytest.mark.asyncio
    async def test_search_with_multiple_filters(self):
        """Search can filter by multiple metadata criteria."""
        from ai_service.memory.vector_store import SemanticMemory

        mock_vs = MagicMock()
        mock_vs.add_documents = AsyncMock(return_value=["doc-id-123"])
        mock_vs.similarity_search = AsyncMock(return_value=[])
        mock_vs.delete_collection = AsyncMock(return_value=None)

        with patch('ai_service.memory.vector_store.PGVector', return_value=mock_vs):
            memory = SemanticMemory(
                connection_string="postgresql://user:pass@localhost:5432/db",
            )
            memory._vector_store = mock_vs

            await memory.search_similar(
                query="budget approval",
                k=10,
                filter_metadata={
                    "type": "decision",
                    "speaker": "cfo",
                },
            )

            mock_vs.similarity_search.assert_called_once()
            call_kwargs = mock_vs.similarity_search.call_args[1]

            assert call_kwargs["filter"]["type"] == "decision"
            assert call_kwargs["filter"]["speaker"] == "cfo"

    @pytest.mark.asyncio
    async def test_search_with_no_filter_returns_all_types(self):
        """Search without filter returns all content types."""
        from ai_service.memory.vector_store import SemanticMemory

        mock_vs = MagicMock()
        mock_vs.add_documents = AsyncMock(return_value=["doc-id-123"])
        mock_vs.similarity_search = AsyncMock(return_value=[])
        mock_vs.delete_collection = AsyncMock(return_value=None)

        with patch('ai_service.memory.vector_store.PGVector', return_value=mock_vs):
            memory = SemanticMemory(
                connection_string="postgresql://user:pass@localhost:5432/db",
            )
            memory._vector_store = mock_vs

            await memory.search_similar(
                query="general query",
                k=5,
            )

            mock_vs.similarity_search.assert_called_once()
            call_kwargs = mock_vs.similarity_search.call_args[1]

            # No filter should be applied
            assert "filter" not in call_kwargs or call_kwargs.get("filter") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
