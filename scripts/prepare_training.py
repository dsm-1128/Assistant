from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ALLOWED_ROLES = {"system", "user", "assistant"}


def normalize_record(record: dict[str, object]) -> dict[str, list[dict[str, str]]]:
    messages = record.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages 必须是非空数组")
    normalized: list[dict[str, str]] = []
    roles: set[str] = set()
    for index, message in enumerate(messages, start=1):
        if not isinstance(message, dict):
            raise ValueError(f"第 {index} 条消息必须是对象")
        role = message.get("role")
        content = message.get("content")
        if role not in ALLOWED_ROLES:
            raise ValueError(f"第 {index} 条消息的 role 不合法：{role!r}")
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"第 {index} 条消息的 content 不能为空")
        roles.add(role)
        normalized.append({"role": role, "content": content.strip()})
    if not {"user", "assistant"}.issubset(roles):
        raise ValueError("每条样本至少需要一条 user 和一条 assistant 消息")
    return {"messages": normalized}


def main() -> int:
    parser = argparse.ArgumentParser(description="校验并规范化 ms-swift 对话训练数据")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        records = []
        with args.input.open("r", encoding="utf-8") as source:
            for line_number, line in enumerate(source, start=1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                    if not isinstance(raw, dict):
                        raise ValueError("每行必须是 JSON 对象")
                    records.append(normalize_record(raw))
                except (json.JSONDecodeError, ValueError) as exc:
                    raise ValueError(f"第 {line_number} 行无效：{exc}") from exc
        if not records:
            raise ValueError("输入文件没有有效记录")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="\n") as target:
            for record in records:
                target.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"已输出 {len(records)} 条样本到 {args.output}")
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
