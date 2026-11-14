import logging
import os
import uuid
from collections.abc import Sequence
from typing import Any

from fastembed import TextEmbedding
from pydantic import Field
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from vendops.contracts.schemas import StrictBaseModel

# Ensure unauthenticated huggingface requests are not blocked by invalid local token
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
DEFAULT_VECTOR_SIZE = 384
DEFAULT_COLLECTIONS: list[str] = ["sop_policies", "historical_disputes"]


class SearchResult(StrictBaseModel):
    """Result item returned by vector store search."""

    id: str
    score: float
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Document(StrictBaseModel):
    """Document representation for indexing into vector store."""

    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    id: str | None = None


class QdrantStore:
    """Multilingual vector store backed by Qdrant and FastEmbed."""

    def __init__(
        self,
        client: QdrantClient | None = None,
        url: str | None = None,
        embedder: Any | None = None,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        vector_size: int = DEFAULT_VECTOR_SIZE,
    ) -> None:
        self.vector_size = vector_size
        self.model_name = model_name

        if client is not None:
            self.client = client
        else:
            target_url = url or os.environ.get("QDRANT_URL", ":memory:")
            if target_url == ":memory:":
                self.client = QdrantClient(":memory:")
            else:
                self.client = QdrantClient(url=target_url)

        if embedder is not None:
            self.embedder = embedder
        else:
            self.embedder = TextEmbedding(model_name=self.model_name)

    def ensure_collections(
        self, collection_names: Sequence[str] | None = None
    ) -> None:
        """Create required collections if they do not exist."""
        targets = list(collection_names) if collection_names else DEFAULT_COLLECTIONS
        for name in targets:
            if not self.client.collection_exists(name):
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(
                        size=self.vector_size, distance=Distance.COSINE
                    ),
                )
                logger.info("Created collection %s (dim=%d)", name, self.vector_size)

    def add_documents(
        self,
        documents: Sequence[dict[str, Any] | Document],
        collection_name: str = "sop_policies",
    ) -> list[str]:
        """Embed and upsert documents into the specified collection."""
        if not documents:
            return []

        self.ensure_collections([collection_name])

        texts: list[str] = []
        doc_ids: list[str] = []
        payloads: list[dict[str, Any]] = []

        for doc in documents:
            if isinstance(doc, Document):
                text = doc.text
                meta = dict(doc.metadata)
                assigned_id = doc.id
            else:
                text = str(doc.get("text", doc.get("content", "")))
                meta = {
                    k: v
                    for k, v in doc.items()
                    if k not in ("text", "content", "id")
                }
                assigned_id = doc.get("id")

            if not assigned_id:
                point_id = str(uuid.uuid4())
            else:
                try:
                    point_id = str(uuid.UUID(str(assigned_id)))
                except ValueError:
                    point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(assigned_id)))

            texts.append(text)
            doc_ids.append(point_id)
            meta["text"] = text
            if assigned_id:
                meta["original_id"] = str(assigned_id)
            payloads.append(meta)

        embeddings_gen = self.embedder.embed(texts)
        points: list[PointStruct] = []
        for point_id, vector, payload in zip(doc_ids, embeddings_gen, payloads):
            vec_list = (
                vector.tolist() if hasattr(vector, "tolist") else list(vector)
            )
            points.append(
                PointStruct(id=point_id, vector=vec_list, payload=payload)
            )

        self.client.upsert(collection_name=collection_name, points=points)
        return doc_ids

    def search(
        self,
        query: str,
        collection_name: str = "sop_policies",
        limit: int = 5,
        score_threshold: float = 0.0,
    ) -> list[SearchResult]:
        """Search the specified collection using cosine similarity."""
        if not self.client.collection_exists(collection_name):
            return []

        query_vectors = list(self.embedder.embed([query]))
        if not query_vectors:
            return []
        qv = query_vectors[0]
        query_vector = qv.tolist() if hasattr(qv, "tolist") else list(qv)

        res = self.client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit,
            score_threshold=score_threshold if score_threshold > 0.0 else None,
        )

        results: list[SearchResult] = []
        for pt in res.points:
            pt_payload = pt.payload or {}
            pt_text = str(pt_payload.get("text", ""))
            pt_metadata = {k: v for k, v in pt_payload.items() if k != "text"}
            results.append(
                SearchResult(
                    id=str(pt.id),
                    score=float(pt.score),
                    text=pt_text,
                    metadata=pt_metadata,
                )
            )
        return results

    def count(self, collection_name: str) -> int:
        """Return total points in collection."""
        if not self.client.collection_exists(collection_name):
            return 0
        info = self.client.count(collection_name=collection_name)
        return int(info.count)
