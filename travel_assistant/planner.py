from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta

from pydantic import ValidationError

from .model import OnlineChatModel
from .prompts import build_generation_prompt, build_repair_prompt
from .rag import TravelKnowledgeBase
from .schemas import Evidence, TravelGuide, TravelRequest


class GuideGenerationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PlannerResult:
    guide: TravelGuide
    evidence: list[Evidence]


def _extract_json(text: str) -> str:
    stripped = text.strip()
    try:
        json.loads(stripped)
        return stripped
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    if start < 0:
        raise ValueError("模型输出中没有 JSON 对象")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(stripped)):
        char = stripped[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = stripped[start : index + 1]
                json.loads(candidate)
                return candidate
    raise ValueError("模型输出中的 JSON 对象不完整")


def _validate_guide(
    raw: str, evidence: list[Evidence], request: TravelRequest
) -> TravelGuide:
    guide = TravelGuide.model_validate_json(_extract_json(raw))
    expected_dates = [
        request.start_date + timedelta(days=offset) for offset in range(request.days)
    ]
    actual_dates = [day.date for day in guide.days]
    if actual_dates != expected_dates:
        raise ValueError(
            f"行程日期必须连续覆盖 {request.start_date} 至 {request.end_date}"
        )
    allowed = {item.id for item in evidence}
    guide.citations = [item for item in guide.citations if item in allowed]
    for day in guide.days:
        for activity in day.activities:
            activity.citations = [
                item for item in activity.citations if item in allowed
            ]
    guide.insufficient_evidence = not evidence
    return guide


class TravelPlanner:
    def __init__(self, knowledge_base: TravelKnowledgeBase, model: OnlineChatModel):
        self.knowledge_base = knowledge_base
        self.model = model
        self.last_evidence: list[Evidence] = []

    def create_guide(self, request: TravelRequest) -> TravelGuide:
        """兼容原有调用：返回攻略，并在 ``last_evidence`` 暴露本次证据。"""
        return self.create_guide_result(request).guide

    def create_guide_result(self, request: TravelRequest) -> PlannerResult:
        """为异步任务返回攻略与证据的同一份结果快照。"""
        query_parts = [request.destination, *request.interests, *request.must_visit]
        if request.additional_requirements.strip():
            query_parts.append(request.additional_requirements.strip())
        query = " ".join(part for part in query_parts if part).strip()
        evidence = self.knowledge_base.search(query, request.destination)
        self.last_evidence = evidence
        system_prompt, user_prompt = build_generation_prompt(request, evidence)
        raw = self.model.generate(system_prompt, user_prompt)
        try:
            guide = _validate_guide(raw, evidence, request)
        except (ValueError, ValidationError) as first_error:
            repair_system, repair_user = build_repair_prompt(raw, str(first_error))
            repaired = self.model.generate(repair_system, repair_user)
            try:
                guide = _validate_guide(repaired, evidence, request)
            except (ValueError, ValidationError) as second_error:
                raise GuideGenerationError(
                    f"模型两次输出均无法解析。首次：{first_error}；修复后：{second_error}"
                ) from second_error
        return PlannerResult(guide=guide, evidence=evidence)
