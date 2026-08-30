from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from travel_assistant.config import Settings
from travel_assistant.model import OnlineEmbeddingClient
from travel_assistant.rag import (
    SUPPORTED_EXTENSIONS,
    KnowledgeDocument,
    TravelKnowledgeBase,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="将旅行资料导入本地 ChromaDB")
    parser.add_argument("--path", type=Path, required=True, help="资料文件或目录")
    parser.add_argument("--destination", required=True, help="资料对应目的地")
    parser.add_argument("--topic", default="综合", help="资料主题")
    parser.add_argument("--updated-at", type=date.fromisoformat, help="更新时间 YYYY-MM-DD")
    args = parser.parse_args()

    if args.path.is_file():
        paths = [args.path] if args.path.suffix.lower() in SUPPORTED_EXTENSIONS else []
    elif args.path.is_dir():
        paths = sorted(
            path
            for path in args.path.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )
    else:
        print(f"路径不存在：{args.path}", file=sys.stderr)
        return 2
    if not paths:
        print("没有找到支持的 TXT、MD 或 PDF 文件", file=sys.stderr)
        return 2

    documents = [
        KnowledgeDocument(path, args.destination, args.topic, args.updated_at)
        for path in paths
    ]
    settings = Settings.from_env()
    report = TravelKnowledgeBase(
        settings, OnlineEmbeddingClient(settings)
    ).ingest(documents)
    print(f"入库完成：{report.files} 个文件，{report.chunks} 个片段")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
