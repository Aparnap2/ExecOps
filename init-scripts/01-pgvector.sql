-- init-scripts/01-pgvector.sql
-- Enable pgvector for semantic search capabilities

CREATE EXTENSION IF NOT EXISTS vector;

-- Create a specific schema for founderos to organize tables
CREATE SCHEMA IF NOT EXISTS founderos;

-- Note: PGVector will create the collection tables automatically
-- when we use langchain_postgres or pgvector python library
