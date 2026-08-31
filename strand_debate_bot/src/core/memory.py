"""Chroma-backed cross-debate memory store.

Implements `strands.memory.types.MemoryStore` directly -- `search`/`add` are
called from graph node code (see `src/agents/moderator.py`), not through
`strands.memory.MemoryManager`'s agent-attached tool/injection machinery,
which assumes one `Agent` deciding for itself when to recall/store facts
about "the user" (see design.md, Decision 1). Uses Chroma's bundled default
embedding function rather than a separate embeddings dependency.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import chromadb

from strands.memory.types import MemoryEntry, Metadata, SearchOptions

DEFAULT_MAX_SEARCH_RESULTS = 2
DEFAULT_COLLECTION_NAME = "debates"


class ChromaMemoryStore:
    """A `MemoryStore` backed by a local, persistent Chroma collection."""

    def __init__(
        self,
        persist_directory: str,
        *,
        name: str = DEFAULT_COLLECTION_NAME,
        max_search_results: int = DEFAULT_MAX_SEARCH_RESULTS,
    ) -> None:
        self.name = name
        self.description: str | None = None
        self.max_search_results = max_search_results
        self.writable = True
        self.extraction = None

        self._client = chromadb.PersistentClient(path=persist_directory)
        self._collection = self._client.get_or_create_collection(name=name)

    async def search(self, query: str, options: SearchOptions | None = None) -> list[MemoryEntry]:
        """Return past entries most similar to `query`, most similar first."""
        limit = (options or {}).get("max_search_results") or self.max_search_results

        results = await asyncio.to_thread(
            self._collection.query, query_texts=[query], n_results=limit
        )

        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]

        return [
            MemoryEntry(content=document, metadata=dict(metadata) if metadata else None)
            for document, metadata in zip(documents, metadatas)
        ]

    async def add(self, content: str, metadata: Metadata | None = None) -> str:
        """Add `content` as a new entry; returns its generated id."""
        entry_id = str(uuid.uuid4())
        await asyncio.to_thread(
            self._collection.add,
            documents=[content],
            metadatas=[metadata] if metadata else None,
            ids=[entry_id],
        )
        return entry_id


class S3VectorMemoryStore:
    """A `MemoryStore` backed by an Amazon S3 Vectors index (deploy-to-agentcore
    design.md, Decision 5) -- the AWS deployment target's replacement for
    `ChromaMemoryStore` above. Same `search`/`add` shape, called from the exact
    same node-code sites (`src/agents/moderator.py`) -- nothing about *when*
    or *how* memory is used changes, only where it's stored.

    S3 Vectors has no separate "document body" field the way Chroma does, so
    `content` is stored as one more key inside the vector's own metadata and
    read back out the same way on `search`.
    """

    def __init__(
        self,
        bucket: str,
        *,
        index_name: str = DEFAULT_COLLECTION_NAME,
        embedding_model_id: str = "amazon.titan-embed-text-v2:0",
        region_name: str | None = None,
        max_search_results: int = DEFAULT_MAX_SEARCH_RESULTS,
    ) -> None:
        import boto3

        self.name = index_name
        self.description: str | None = None
        self.max_search_results = max_search_results
        self.writable = True
        self.extraction = None

        self._bucket = bucket
        self._index_name = index_name
        self._embedding_model_id = embedding_model_id
        self._vectors_client = boto3.client("s3vectors", region_name=region_name)
        self._bedrock_client = boto3.client("bedrock-runtime", region_name=region_name)

    async def _embed(self, text: str) -> list[float]:
        response = await asyncio.to_thread(
            self._bedrock_client.invoke_model,
            modelId=self._embedding_model_id,
            body=json.dumps({"inputText": text}),
        )
        payload = json.loads(response["body"].read())
        return payload["embedding"]

    async def search(self, query: str, options: SearchOptions | None = None) -> list[MemoryEntry]:
        """Return past entries most similar to `query`, most similar first."""
        limit = (options or {}).get("max_search_results") or self.max_search_results
        query_vector = await self._embed(query)

        response = await asyncio.to_thread(
            self._vectors_client.query_vectors,
            vectorBucketName=self._bucket,
            indexName=self._index_name,
            topK=limit,
            queryVector={"float32": query_vector},
            returnMetadata=True,
            returnDistance=True,
        )

        entries = []
        for vector in response.get("vectors", []):
            metadata = dict(vector.get("metadata") or {})
            content = metadata.pop("content", "")
            entries.append(MemoryEntry(content=content, metadata=metadata or None))
        return entries

    async def add(self, content: str, metadata: Metadata | None = None) -> str:
        """Add `content` as a new entry; returns its generated id."""
        entry_id = str(uuid.uuid4())
        embedding = await self._embed(content)
        vector_metadata = {"content": content, **(metadata or {})}

        await asyncio.to_thread(
            self._vectors_client.put_vectors,
            vectorBucketName=self._bucket,
            indexName=self._index_name,
            vectors=[{"key": entry_id, "data": {"float32": embedding}, "metadata": vector_metadata}],
        )
        return entry_id
