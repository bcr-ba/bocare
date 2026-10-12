from fastapi import APIRouter, Depends

from app.api.routes_chat import get_orchestrator
from app.pipeline.orchestrator import Orchestrator
from app.schemas.api import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(orchestrator: Orchestrator = Depends(get_orchestrator)) -> HealthResponse:
    return HealthResponse(llm_configured=orchestrator.llm_configured)
