from __future__ import annotations

from functools import lru_cache

from travel_assistant.config import Settings
from travel_assistant.model import OnlineChatModel, OnlineEmbeddingClient
from travel_assistant.planner import TravelPlanner
from travel_assistant.rag import TravelKnowledgeBase

from .tasks import GuideTaskManager


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()


@lru_cache
def get_chat_model() -> OnlineChatModel:
    return OnlineChatModel(get_settings())


@lru_cache
def get_embedding_client() -> OnlineEmbeddingClient:
    return OnlineEmbeddingClient(get_settings())


@lru_cache
def get_knowledge_base() -> TravelKnowledgeBase:
    return TravelKnowledgeBase(get_settings(), get_embedding_client())


@lru_cache
def get_planner() -> TravelPlanner:
    return TravelPlanner(get_knowledge_base(), get_chat_model())


@lru_cache
def get_task_manager() -> GuideTaskManager:
    return GuideTaskManager(get_planner())

