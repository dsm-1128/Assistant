from __future__ import annotations

import json
from typing import Sequence

from .schemas import Evidence, TravelGuide, TravelRequest

SYSTEM_PROMPT = """你是一名严谨、实用的中文旅行规划师。
你必须遵守用户的日期、预算、人数、兴趣、节奏、饮食和必去地点等约束。
检索资料是目的地事实的唯一可信来源；规划估算必须明确是估算，不得声称为实时票价、库存、营业时间或班次。
只能引用提示中真实存在的 [E1]、[E2] 等证据编号。没有证据时可以提供通用规划，但必须将 insufficient_evidence 设为 true。
只输出一个合法 JSON 对象，不要使用 Markdown 代码围栏，不要附加解释。JSON 必须符合给出的 Schema。"""


def _format_evidence(evidence: Sequence[Evidence]) -> str:
    if not evidence:
        return "没有检索到该目的地的本地知识资料。请仅给出通用规划，不要编造具体事实。"
    blocks = []
    for item in evidence:
        blocks.append(
            f"[{item.id}] 来源={item.source}；主题={item.topic}；"
            f"更新时间={item.updated_at}\n{item.content}"
        )
    return "\n\n".join(blocks)


def build_generation_prompt(
    request: TravelRequest, evidence: Sequence[Evidence]
) -> tuple[str, str]:
    request_json = json.dumps(request.model_dump(mode="json"), ensure_ascii=False, indent=2)
    schema_json = json.dumps(TravelGuide.model_json_schema(), ensure_ascii=False)
    user_prompt = f"""请根据旅行需求和检索证据生成攻略。

旅行天数：{request.days} 天
旅行需求：
{request_json}

检索证据：
{_format_evidence(evidence)}

输出 JSON Schema：
{schema_json}

额外要求：days 必须覆盖 {request.start_date.isoformat()} 到 {request.end_date.isoformat()}；
budget_total 应等于 budget_items 的 amount 合计；citations 只允许出现真实证据编号。"""
    return SYSTEM_PROMPT, user_prompt


def build_repair_prompt(raw_output: str, error: str) -> tuple[str, str]:
    schema_json = json.dumps(TravelGuide.model_json_schema(), ensure_ascii=False)
    system = "你是 JSON 格式修复器。只返回一个修复后的合法 JSON 对象，不要解释。"
    user = f"""以下旅行攻略输出未通过校验。
错误：{error}

原始输出：
{raw_output}

目标 JSON Schema：
{schema_json}

请保留原有信息并修复格式和字段，只输出 JSON。"""
    return system, user
