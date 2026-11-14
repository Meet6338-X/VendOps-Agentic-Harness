import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from vendops.api.deps import get_qdrant_client, get_rag_store
from vendops.api.routes import router
from vendops.rag.ingest import ingest_all

logger = logging.getLogger(__name__)


def _seed_sync() -> None:
    """Synchronous seeding of Qdrant collections."""
    try:
        client = get_qdrant_client()
        store = get_rag_store(client=client)
        store.ensure_collections()
        if store.count("sop_policies") == 0:
            counts = ingest_all(store)
            logger.info("Initialized RAG collections on startup: %s", counts)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning("Could not auto-seed RAG collections: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: non-blocking startup with background RAG warmup."""
    # Warmup and seed in background task so server binds and serves health immediately
    asyncio.create_task(asyncio.to_thread(_seed_sync))
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    application = FastAPI(
        title="VendOps Dispute Resolution & RAG Service",
        version="0.1.0",
        description="Autonomous Vendor Dispute Resolution API with Qdrant Multilingual RAG and SSE streaming",
        lifespan=lifespan,
    )
    application.include_router(router)
    return application


app = create_app()
