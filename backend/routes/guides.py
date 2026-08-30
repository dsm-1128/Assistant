from __future__ import annotations

from fastapi import APIRouter

from backend.dependencies import get_task_manager
from backend.errors import AppError
from backend.schemas import GuideSubmitResponse, TaskResponse
from travel_assistant.schemas import TravelRequest

router = APIRouter(tags=["guides"])


@router.post("/guides", response_model=GuideSubmitResponse, status_code=202)
def create_guide(request: TravelRequest) -> GuideSubmitResponse:
    task = get_task_manager().submit(request)
    return GuideSubmitResponse(task_id=task.task_id)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str) -> TaskResponse:
    task = get_task_manager().get(task_id)
    if task is None:
        raise AppError(
            "任务不存在或服务重启后已失效。",
            code="task_not_found",
            status_code=404,
        )
    return task

