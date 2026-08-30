from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from backend.dependencies import (
    get_chat_model,
    get_knowledge_base,
    get_settings,
    get_task_manager,
)
from backend.schemas import (
    HealthResponse,
    KnowledgeStatus,
    OnlineModelStatus,
    StatusResponse,
)

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.get("/status", response_model=StatusResponse)
def status() -> StatusResponse:
    settings = get_settings()
    model = get_chat_model().status()
    knowledge = get_knowledge_base().status()
    return StatusResponse(
        llm=OnlineModelStatus(
            configured=model.configured, model=model.model, base_url=model.base_url
        ),
        embedding=OnlineModelStatus(
            configured=settings.embedding_configured,
            model=settings.embedding_model,
            base_url=settings.embedding_base_url,
        ),
        knowledge_base=KnowledgeStatus(**asdict(knowledge)),
        queue=get_task_manager().status(),
    )
