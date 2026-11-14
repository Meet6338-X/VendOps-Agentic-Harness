import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from vendops.api.deps import get_qdrant_client, get_rag_store
from vendops.api.routes import router
from vendops.rag.ingest import ingest_all

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: initialize Qdrant store collections and ingest policies."""
    try:
        client = get_qdrant_client()
        store = get_rag_store(client=client)
        store.ensure_collections()
        # Seed SOP policies if collection is empty
        if store.count("sop_policies") == 0:
            counts = ingest_all(store)
            logger.info("Initialized RAG collections on startup: %s", counts)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning("Could not auto-seed RAG collections on startup: %s", exc)

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
