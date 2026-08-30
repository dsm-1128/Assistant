from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
import logging
from threading import Lock
from typing import Literal
from uuid import uuid4

from travel_assistant.planner import TravelPlanner
from travel_assistant.schemas import Evidence, TravelGuide, TravelRequest

from .errors import error_detail
from .schemas import ErrorDetail, QueueStatus, TaskResponse

TaskStatus = Literal["queued", "running", "completed", "failed"]
logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class _TaskRecord:
    task_id: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    guide: TravelGuide | None = None
    evidence: list[Evidence] = field(default_factory=list)
    error: ErrorDetail | None = None

    def response(self) -> TaskResponse:
        return TaskResponse(
            task_id=self.task_id,
            status=self.status,
            created_at=self.created_at,
            updated_at=self.updated_at,
            guide=self.guide,
            evidence=list(self.evidence),
            error=self.error,
        )


class GuideTaskManager:
    def __init__(self, planner: TravelPlanner):
        self.planner = planner
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="travel-guide"
        )
        self._records: dict[str, _TaskRecord] = {}
        self._lock = Lock()

    def submit(self, request: TravelRequest) -> TaskResponse:
        task_id = uuid4().hex
        timestamp = _now()
        record = _TaskRecord(task_id, "queued", timestamp, timestamp)
        with self._lock:
            self._records[task_id] = record
            response = record.response()
        self._executor.submit(self._run, task_id, request.model_copy(deep=True))
        return response

    def _run(self, task_id: str, request: TravelRequest) -> None:
        with self._lock:
            record = self._records[task_id]
            record.status = "running"
            record.updated_at = _now()
        try:
            result = self.planner.create_guide_result(request)
        except Exception as exc:
            logger.exception("攻略任务 %s 执行失败", task_id)
            with self._lock:
                record = self._records[task_id]
                record.status = "failed"
                record.error = error_detail(exc)
                record.updated_at = _now()
            return
        with self._lock:
            record = self._records[task_id]
            record.status = "completed"
            record.guide = result.guide
            record.evidence = result.evidence
            record.updated_at = _now()

    def get(self, task_id: str) -> TaskResponse | None:
        with self._lock:
            record = self._records.get(task_id)
            return record.response() if record is not None else None

    def status(self) -> QueueStatus:
        with self._lock:
            statuses = [record.status for record in self._records.values()]
        return QueueStatus(
            queued=statuses.count("queued"), running=statuses.count("running")
        )

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=False)
