from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Sequence

import chromadb
from chromadb.errors import NotFoundError
from pypdf import PdfReader

from .config import Settings
from .model import OnlineEmbeddingClient
from .schemas import Evidence

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}


class DocumentLoadError(RuntimeError):
    pass


class EmbeddingModelError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    path: Path
    destination: str
    topic: str = "综合"
    updated_at: date | None = None


@dataclass(frozen=True, slots=True)
class IngestReport:
    files: int
    chunks: int


@dataclass(frozen=True, slots=True)
class KnowledgeBaseStatus:
    collection_name: str
    path: str
    chunks: int
    embedding_model: str
    embedding_dimension: int
    compatible: bool
    compatibility_message: str


def _read_document(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise DocumentLoadError(f"不支持的文件格式：{path.name}")
    try:
        if suffix == ".pdf":
            pages = [page.extract_text() or "" for page in PdfReader(str(path)).pages]
            text = "\n".join(pages)
        else:
            text = path.read_text(encoding="utf-8")
    except Exception as exc:
        raise DocumentLoadError(f"读取 {path.name} 失败：{exc}") from exc
    text = text.strip()
    if not text:
        raise DocumentLoadError(f"{path.name} 没有可提取的文本")
    return text


def _split_text(text: str, size: int, overlap: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunk = text[start : start + size].strip()
        if chunk:
            chunks.append(chunk)
        if start + size >= len(text):
            break
        start += size - overlap
    return chunks


class TravelKnowledgeBase:
    def __init__(
        self,
        settings: Settings,
        embeddings: OnlineEmbeddingClient | None = None,
    ):
        self.settings = settings
        self.embeddings = embeddings or OnlineEmbeddingClient(settings)
        settings.chroma_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(settings.chroma_path))
        self._collection = None

    def _expected_metadata(self) -> dict[str, str | int]:
        return {
            "hnsw:space": "cosine",
            "embedding_model": self.settings.embedding_model,
            "embedding_dimension": self.settings.embedding_dimension,
        }

    def _get_collection(self):
        if self._collection is None:
            self._collection = self._client.get_or_create_collection(
                name=self.settings.collection_name,
                embedding_function=None,
                metadata=self._expected_metadata(),
            )
        self._ensure_collection_compatible(self._collection)
        return self._collection

    @staticmethod
    def _collection_hnsw_space(collection: Any) -> str | None:
        configuration = getattr(collection, "configuration", None)
        if not isinstance(configuration, Mapping):
            return None
        hnsw = configuration.get("hnsw")
        if not isinstance(hnsw, Mapping):
            return None
        space = hnsw.get("space")
        return str(space) if space is not None else None

    def _ensure_collection_compatible(self, collection: Any) -> None:
        actual_space = self._collection_hnsw_space(collection)
        if actual_space != "cosine":
            raise EmbeddingModelError(
                "当前 Chroma Collection 的向量距离不是 cosine。"
                f"Collection={actual_space or '未记录'}，当前要求=cosine。"
                "距离函数在创建 Collection 时确定，不能通过 metadata 修改；"
                "请更换 CHROMA_COLLECTION，或备份后清空旧 Collection 并按 cosine 重新入库。"
            )

        if collection.count() == 0:
            current = dict(collection.metadata or {})
            expected = {
                "embedding_model": self.settings.embedding_model,
                "embedding_dimension": self.settings.embedding_dimension,
            }
            if any(current.get(key) != value for key, value in expected.items()):
                mutable_metadata = {
                    key: value for key, value in current.items() if key != "hnsw:space"
                }
                collection.modify(metadata={**mutable_metadata, **expected})
            return

        metadata = collection.metadata or {}
        actual_model = str(metadata.get("embedding_model", ""))
        try:
            actual_dimension = int(metadata.get("embedding_dimension", 0))
        except (TypeError, ValueError):
            actual_dimension = 0
        if (
            actual_model != self.settings.embedding_model
            or actual_dimension != self.settings.embedding_dimension
        ):
            raise EmbeddingModelError(
                "当前 Chroma Collection 的 Embedding 配置与运行配置不一致。"
                f"Collection={actual_model or '未记录'}/{actual_dimension or '未记录'}，"
                f"当前={self.settings.embedding_model}/{self.settings.embedding_dimension}。"
                "请更换 CHROMA_COLLECTION，或备份后清空旧 Collection 并重新入库；"
                "不同模型或维度的向量不能混用。"
            )

    def ingest(self, documents: Sequence[KnowledgeDocument]) -> IngestReport:
        if not documents:
            raise ValueError("至少需要一个知识文档")
        collection = self._get_collection()
        total_chunks = 0
        for document in documents:
            destination = document.destination.strip()
            if not destination:
                raise ValueError("资料目的地不能为空")
            text = _read_document(document.path)
            chunks = _split_text(
                text, self.settings.chunk_size, self.settings.chunk_overlap
            )
            if not chunks:
                continue
            vectors = self.embeddings.embed(chunks)

            ids: list[str] = []
            metadatas: list[dict[str, str | int]] = []
            for index, chunk in enumerate(chunks):
                digest_input = (
                    f"{document.path.name}|{destination}|{document.topic}|{index}|{chunk}"
                )
                ids.append(hashlib.sha256(digest_input.encode("utf-8")).hexdigest())
                metadatas.append(
                    {
                        "destination": destination,
                        "topic": document.topic.strip() or "综合",
                        "source": document.path.name,
                        "updated_at": document.updated_at.isoformat()
                        if document.updated_at
                        else "未知",
                        "chunk_index": index,
                        "embedding_model": self.settings.embedding_model,
                        "embedding_dimension": self.settings.embedding_dimension,
                    }
                )
            collection.upsert(
                ids=ids,
                documents=chunks,
                metadatas=metadatas,
                embeddings=vectors,
            )
            total_chunks += len(chunks)
        return IngestReport(files=len(documents), chunks=total_chunks)

    def search(
        self, query: str, destination: str, top_k: int | None = None
    ) -> list[Evidence]:
        collection = self._get_collection()
        if collection.count() == 0:
            return []
        query_vector = self.embeddings.embed([query])[0]
        result = collection.query(
            query_embeddings=[query_vector],
            n_results=top_k or self.settings.retrieval_top_k,
            where={"destination": destination.strip()},
            include=["documents", "metadatas", "distances"],
        )
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        evidence: list[Evidence] = []
        for index, (content, metadata, distance) in enumerate(
            zip(documents, metadatas, distances, strict=False), start=1
        ):
            evidence.append(
                Evidence(
                    id=f"E{index}",
                    content=content,
                    source=str(metadata.get("source", "未知来源")),
                    destination=str(metadata.get("destination", destination)),
                    topic=str(metadata.get("topic", "综合")),
                    updated_at=str(metadata.get("updated_at", "未知")),
                    distance=float(distance),
                )
            )
        return evidence

    def status(self) -> KnowledgeBaseStatus:
        chunks = 0
        compatible = True
        message = "Collection 尚未创建"
        try:
            collection = self._client.get_collection(
                name=self.settings.collection_name,
                embedding_function=None,
            )
            chunks = collection.count()
            self._ensure_collection_compatible(collection)
            message = "配置兼容"
        except NotFoundError:
            pass
        except EmbeddingModelError as exc:
            compatible = False
            message = str(exc)
        except Exception as exc:
            compatible = False
            message = f"读取 Collection 状态失败：{exc}"
        return KnowledgeBaseStatus(
            collection_name=self.settings.collection_name,
            path=str(self.settings.chroma_path),
            chunks=chunks,
            embedding_model=self.settings.embedding_model,
            embedding_dimension=self.settings.embedding_dimension,
            compatible=compatible,
            compatibility_message=message,
        )
