from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from starlette.concurrency import run_in_threadpool

from backend.dependencies import get_knowledge_base
from backend.errors import AppError
from backend.schemas import KnowledgeUploadResponse
from travel_assistant.rag import (
    SUPPORTED_EXTENSIONS,
    KnowledgeDocument,
)

router = APIRouter(tags=["knowledge"])


@router.post("/knowledge/documents", response_model=KnowledgeUploadResponse)
async def upload_documents(
    files: list[UploadFile] = File(...),
    destination: str = Form(...),
    topic: str = Form("综合"),
    updated_at: date | None = Form(None),
) -> KnowledgeUploadResponse:
    destination = destination.strip()
    if not destination:
        raise AppError("资料目的地不能为空", code="destination_required")
    if not files:
        raise AppError("请至少上传一个文件", code="file_required")

    with tempfile.TemporaryDirectory(prefix="travel-kb-") as temp_dir:
        root = Path(temp_dir)
        documents: list[KnowledgeDocument] = []
        for index, upload in enumerate(files):
            safe_name = Path(upload.filename or "").name
            suffix = Path(safe_name).suffix.lower()
            if not safe_name or suffix not in SUPPORTED_EXTENSIONS:
                raise AppError(
                    f"不支持的文件：{safe_name or '未命名文件'}。仅支持 TXT、MD、PDF。",
                    code="unsupported_file_type",
                )
            file_dir = root / str(index)
            file_dir.mkdir()
            path = file_dir / safe_name
            path.write_bytes(await upload.read())
            documents.append(
                KnowledgeDocument(path, destination, topic.strip() or "综合", updated_at)
            )
        report = await run_in_threadpool(get_knowledge_base().ingest, documents)
    return KnowledgeUploadResponse(
        files=report.files,
        chunks=report.chunks,
        message=f"入库完成：{report.files} 个文件，{report.chunks} 个片段。",
    )

