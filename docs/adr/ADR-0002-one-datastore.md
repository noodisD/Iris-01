# ADR-0002: One datastore — PostgreSQL with pgvector

## Status
Accepted — 2026-09-06

## Context
The documented architecture had three stores: PostgreSQL as the canonical one,
Neo4j as a "graph lens", and ChromaDB/FAISS as a "vector lens". ChromaDB/FAISS
had already been replaced by pgvector in January 2026, though the README still
advertised it.

Neo4j turned out to be write-only. Every `graph_db.*` call in the product was an
insert or a link; the only readers were `graph_sync_queue.py`, which had no
importers, and a CLI rebuild command. It cost a container with a 2 GB heap, a
write on every ingest, and — because the driver connected at module import — an
outage there took the entire API down.

## Decision
PostgreSQL with the pgvector extension is the only datastore. Neo4j and its
driver, configuration and compose service were removed.

## Consequences
A similarity search can carry a relational constraint in one statement and one
transaction: nearest neighbours *and* `WHERE user_id = …`. That is what enforces
the user-scoping invariant; a standalone vector store cannot express it without
duplicating ownership metadata and keeping it in sync — which is exactly what
the deleted `vector_store.py` was.

Graph queries (multi-hop relationship discovery) are no longer possible without
reintroducing a store. The graph was rebuildable from PostgreSQL, so nothing
was lost that cannot be rebuilt.
