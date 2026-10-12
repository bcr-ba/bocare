import json
from typing import Any, Iterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.logging_context import get_request_id
from app.pipeline.orchestrator import Orchestrator
from app.schemas.api import ChatRequest, ChatResponse, SourceOut

router = APIRouter(tags=["chat"])


def get_orchestrator(request: Request) -> Orchestrator:
    return request.app.state.orchestrator


# Plain `def`: the pipeline makes blocking HTTP calls, so FastAPI runs it in a worker thread.
@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, orchestrator: Orchestrator = Depends(get_orchestrator)) -> ChatResponse:
    result = orchestrator.handle(body.message, session_id=body.session_id, language=body.language,
                                 request_id=get_request_id())
    return ChatResponse.from_result(result)


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _events(orchestrator: Orchestrator, body: ChatRequest, request_id: str) -> Iterator[str]:
    for event, payload in orchestrator.stream(body.message, session_id=body.session_id, language=body.language,
                                              request_id=request_id):
        if event in ("triage", "done"):
            yield _sse(event, ChatResponse.from_result(payload).model_dump())
        elif event == "sources":
            yield _sse(event, [SourceOut(title=s.name, url=s.url).model_dump() for s in payload])
        else:
            yield _sse(event, {"stage": payload})


@router.post("/chat/stream", responses={200: {"content": {"text/event-stream": {}}}})
def chat_stream(body: ChatRequest, orchestrator: Orchestrator = Depends(get_orchestrator)) -> StreamingResponse:
    """Server-sent events. `triage` arrives first (urgency, recommendation, safety messages,
    follow-up questions), then `sources` and `status` updates, and finally `done` with the same
    body as POST /chat. The generated answer is only sent in `done`, after verification."""
    # The request ID is read now: the stream itself is produced after the middleware has returned.
    return StreamingResponse(_events(orchestrator, body, get_request_id()), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
