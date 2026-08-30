from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.dependencies import get_settings, get_task_manager
from backend.errors import install_exception_handlers
from backend.routes import guides, health, knowledge


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    if get_task_manager.cache_info().currsize:
        get_task_manager().shutdown()


app = FastAPI(
    title="旅行智能助手 API",
    version="2.0.0",
    description="使用在线模型 API 与 ChromaDB RAG 生成个性化旅行攻略。",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(knowledge.router, prefix="/api/v1")
app.include_router(guides.router, prefix="/api/v1")
install_exception_handlers(app)

