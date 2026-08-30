from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from travel_assistant.schemas import Evidence, TravelGuide


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "travel-assistant-backend"


class GuideSubmitResponse(BaseModel):
    task_id: str
    status: Literal["queued"] = "queued"


class TaskResponse(BaseModel):
    task_id: str
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime
    updated_at: datetime
    guide: TravelGuide | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    error: ErrorDetail | None = None


class KnowledgeUploadResponse(BaseModel):
    files: int
    chunks: int
    message: str


class OnlineModelStatus(BaseModel):
    configured: bool
    model: str
    base_url: str


class KnowledgeStatus(BaseModel):
    collection_name: str
    path: str
    chunks: int
    embedding_model: str
    embedding_dimension: int
    compatible: bool
    compatibility_message: str


class QueueStatus(BaseModel):
    queued: int
    running: int


class StatusResponse(BaseModel):
    service: Literal["ok"] = "ok"
    llm: OnlineModelStatus
    embedding: OnlineModelStatus
    knowledge_base: KnowledgeStatus
    queue: QueueStatus

