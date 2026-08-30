from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _project_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数，当前值为 {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} 必须大于 0")
    return value


def _non_negative_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是整数，当前值为 {raw!r}") from exc
    if value < 0:
        raise ValueError(f"{name} 必须大于等于 0")
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} 必须是数字，当前值为 {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} 必须大于 0")
    return value


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} 必须是布尔值，当前值为 {raw!r}")


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_timeout_seconds: float
    llm_max_retries: int
    llm_max_tokens: int
    llm_enable_thinking: bool
    embedding_base_url: str
    embedding_api_key: str
    embedding_model: str
    embedding_dimension: int
    embedding_timeout_seconds: float
    embedding_batch_size: int
    chroma_path: Path
    collection_name: str
    retrieval_top_k: int
    chunk_size: int
    chunk_overlap: int
    cors_origins: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(PROJECT_ROOT / ".env", override=False)

        llm_base_url = os.getenv("LLM_BASE_URL", "").strip().rstrip("/")
        llm_api_key = os.getenv("LLM_API_KEY", "").strip()
        embedding_base_url = (
            os.getenv("EMBEDDING_BASE_URL", "").strip().rstrip("/") or llm_base_url
        )
        embedding_api_key = os.getenv("EMBEDDING_API_KEY", "").strip() or llm_api_key

        chunk_size = _positive_int("CHUNK_SIZE", 800)
        chunk_overlap = _non_negative_int("CHUNK_OVERLAP", 120)
        if chunk_overlap >= chunk_size:
            raise ValueError("CHUNK_OVERLAP 必须小于 CHUNK_SIZE")

        return cls(
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            llm_model=os.getenv("LLM_MODEL", "").strip(),
            llm_timeout_seconds=_positive_float("LLM_TIMEOUT_SECONDS", 180),
            llm_max_retries=_non_negative_int("LLM_MAX_RETRIES", 1),
            llm_max_tokens=_positive_int("LLM_MAX_TOKENS", 4096),
            llm_enable_thinking=_boolean("LLM_ENABLE_THINKING", False),
            embedding_base_url=embedding_base_url,
            embedding_api_key=embedding_api_key,
            embedding_model=os.getenv("EMBEDDING_MODEL", "").strip(),
            embedding_dimension=_positive_int("EMBEDDING_DIMENSION", 1024),
            embedding_timeout_seconds=_positive_float(
                "EMBEDDING_TIMEOUT_SECONDS", 120
            ),
            embedding_batch_size=_positive_int("EMBEDDING_BATCH_SIZE", 32),
            chroma_path=_project_path(os.getenv("CHROMA_PATH", "./data/chroma")),
            collection_name=os.getenv(
                "CHROMA_COLLECTION", "travel_knowledge_online"
            ).strip(),
            retrieval_top_k=_positive_int("RETRIEVAL_TOP_K", 6),
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            cors_origins=_csv(
                "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ),
        )

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)

    @property
    def embedding_configured(self) -> bool:
        return bool(
            self.embedding_base_url
            and self.embedding_api_key
            and self.embedding_model
            and self.embedding_dimension
        )
