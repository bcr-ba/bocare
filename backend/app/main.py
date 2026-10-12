import logging
import threading
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from app.api.routes_chat import router as chat_router
from app.api.routes_health import router as health_router
from app.core import config_loader
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.logging_context import request_id_middleware
from app.core.settings import ROOT_DIR, Settings, get_settings
from app.llm.client import LLMClient, OllamaClient, OpenRouterClient
from app.pipeline.orchestrator import Orchestrator
from app.pipeline.responder import Responder
from app.pipeline.safety import InputValidator, RateLimiter
from app.pipeline.verifier import Verifier
from app.retrieval.base import Retriever
from app.retrieval.dense import DenseRetriever
from app.retrieval.embeddings import build_embedder
from app.retrieval.medlineplus import MedlinePlusRetriever
from app.retrieval.vector_index import VectorIndex, VectorIndexError

logger = logging.getLogger(__name__)


def build_llm(settings: Settings) -> LLMClient:
    # The clients read their remaining parameters from the same settings.
    if settings.llm_provider == "ollama":
        return OllamaClient(model=settings.ollama_model, fallback_model=settings.ollama_fallback_model)
    return OpenRouterClient()


def build_retriever(settings: Settings) -> Retriever:
    if settings.retriever == "dense":
        try:
            index = VectorIndex.load(ROOT_DIR / settings.index_dir, settings.embedding_model)
            return DenseRetriever(index, build_embedder(settings), settings)
        except VectorIndexError as exc:
            # The app still works with keyword search; build the index to get semantic search.
            logger.warning("%s Falling back to the MedlinePlus keyword retriever.", exc)
    return MedlinePlusRetriever(settings)


def build_orchestrator(settings: Settings) -> Orchestrator:
    llm = build_llm(settings)
    verifier = Verifier(judge=llm if settings.judge_enabled else None, judge_min_level=settings.judge_min_level)
    responder = Responder(build_retriever(settings), llm, verifier, max_attempts=settings.llm_max_attempts)
    validator = InputValidator(RateLimiter(settings.rate_limit_per_minute))
    return Orchestrator(responder, validator)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the local models in the background at startup; the API is usable meanwhile.
    responder = app.state.orchestrator.responder
    for component in (responder.llm, responder.retriever):
        warm_up = getattr(component, "warm_up", None)
        if warm_up:
            threading.Thread(target=warm_up, name=f"warm-up-{type(component).__name__}", daemon=True).start()
    yield


def create_app(orchestrator: Optional[Orchestrator] = None) -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    config_loader.validate_all()  # a broken YAML file stops the server here, with the file named

    app = FastAPI(title="BoCare API", version="0.1.0", lifespan=lifespan)
    app.state.orchestrator = orchestrator or build_orchestrator(settings)
    app.middleware("http")(request_id_middleware)
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(chat_router)
    return app


app = create_app()
