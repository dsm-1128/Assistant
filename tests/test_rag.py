from __future__ import annotations

import sys
import types
import unittest
from dataclasses import dataclass as standard_dataclass
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_rag_module():
    """在未安装项目依赖的环境中加载 RAG 模块。"""

    package = types.ModuleType("travel_assistant")
    package.__path__ = [str(PROJECT_ROOT / "travel_assistant")]
    sys.modules["travel_assistant"] = package

    chromadb = types.ModuleType("chromadb")
    chromadb.PersistentClient = object
    chromadb_errors = types.ModuleType("chromadb.errors")

    class NotFoundError(Exception):
        pass

    chromadb_errors.NotFoundError = NotFoundError
    sys.modules["chromadb"] = chromadb
    sys.modules["chromadb.errors"] = chromadb_errors

    pypdf = types.ModuleType("pypdf")
    pypdf.PdfReader = object
    sys.modules["pypdf"] = pypdf

    config = types.ModuleType("travel_assistant.config")
    config.Settings = object
    sys.modules["travel_assistant.config"] = config

    model = types.ModuleType("travel_assistant.model")
    model.OnlineEmbeddingClient = object
    sys.modules["travel_assistant.model"] = model

    schemas = types.ModuleType("travel_assistant.schemas")
    schemas.Evidence = object
    sys.modules["travel_assistant.schemas"] = schemas

    module_name = "travel_assistant.rag"
    sys.modules.pop(module_name, None)
    spec = spec_from_file_location(module_name, PROJECT_ROOT / "travel_assistant" / "rag.py")
    assert spec and spec.loader
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    # 当前工作区只有 Python 3.7；生产代码需要 3.10+ 的 dataclass(slots=True)。
    # 兼容包装仅让测试能够加载被测分支，不改变业务行为。
    import dataclasses

    original_dataclass = dataclasses.dataclass

    def compatible_dataclass(*args, **kwargs):
        kwargs.pop("slots", None)
        return standard_dataclass(*args, **kwargs)

    dataclasses.dataclass = compatible_dataclass
    try:
        spec.loader.exec_module(module)
    finally:
        dataclasses.dataclass = original_dataclass
    return module


rag = _load_rag_module()


class _Chroma159Collection:
    """只实现本回归所需的 Chroma 1.5.9 Collection 行为。"""

    def __init__(self, *, metadata, configuration, count=0):
        self.metadata = metadata
        self.configuration = configuration
        self._count = count
        self.modify_calls = []

    def count(self):
        return self._count

    def modify(self, *, metadata):
        # Chroma 1.5.9 的 Collection._validate_modify_request 行为。
        if "hnsw:space" in metadata:
            raise ValueError(
                "Changing the distance function of a collection once it is created "
                "is not supported currently."
            )
        self.modify_calls.append(dict(metadata))
        self.metadata = dict(metadata)


class _Client:
    def __init__(self, collection):
        self.collection = collection
        self.created_metadata = None

    def get_or_create_collection(self, *, name, embedding_function, metadata):
        self.created_metadata = dict(metadata)
        return self.collection


def _knowledge_base():
    knowledge_base = object.__new__(rag.TravelKnowledgeBase)
    knowledge_base.settings = SimpleNamespace(
        embedding_model="text-embedding-v2",
        embedding_dimension=1024,
        collection_name="travel_knowledge",
    )
    knowledge_base._collection = None
    return knowledge_base


class TravelKnowledgeBaseCompatibilityTests(unittest.TestCase):
    def test_empty_cosine_collection_updates_only_mutable_metadata(self):
        """若重新把 hnsw:space 传给 modify，Chroma 1.5.9 会拒绝写入。"""

        knowledge_base = _knowledge_base()
        collection = _Chroma159Collection(
            metadata={
                "hnsw:space": "cosine",
                "description": "已有知识库",
                "embedding_model": "old-model",
                "embedding_dimension": 768,
            },
            configuration={"hnsw": {"space": "cosine"}},
        )

        knowledge_base._ensure_collection_compatible(collection)

        self.assertEqual(
            collection.modify_calls,
            [
                {
                    "description": "已有知识库",
                    "embedding_model": "text-embedding-v2",
                    "embedding_dimension": 1024,
                }
            ],
        )

    def test_empty_collection_with_non_cosine_configuration_fails_without_modify(self):
        """若真实距离不是 cosine，不能尝试通过 metadata 修改距离。"""

        knowledge_base = _knowledge_base()
        collection = _Chroma159Collection(
            metadata={"hnsw:space": "cosine"},
            configuration={"hnsw": {"space": "l2"}},
        )

        with self.assertRaisesRegex(rag.EmbeddingModelError, "距离"):
            knowledge_base._ensure_collection_compatible(collection)

        self.assertEqual(collection.modify_calls, [])

    def test_new_collection_is_created_with_cosine_metadata(self):
        """新建 collection 仍需在创建时指定 cosine 距离。"""

        knowledge_base = _knowledge_base()
        collection = _Chroma159Collection(
            metadata={
                "hnsw:space": "cosine",
                "embedding_model": "text-embedding-v2",
                "embedding_dimension": 1024,
            },
            configuration={"hnsw": {"space": "cosine"}},
        )
        client = _Client(collection)
        knowledge_base._client = client

        knowledge_base._get_collection()

        self.assertEqual(
            client.created_metadata,
            {
                "hnsw:space": "cosine",
                "embedding_model": "text-embedding-v2",
                "embedding_dimension": 1024,
            },
        )

    def test_non_empty_collection_keeps_embedding_compatibility_protection(self):
        """非空 collection 的模型或维度不兼容时必须继续拒绝使用。"""

        knowledge_base = _knowledge_base()
        collection = _Chroma159Collection(
            metadata={
                "hnsw:space": "cosine",
                "embedding_model": "old-model",
                "embedding_dimension": 768,
            },
            configuration={"hnsw": {"space": "cosine"}},
            count=1,
        )

        with self.assertRaisesRegex(rag.EmbeddingModelError, "不能混用"):
            knowledge_base._ensure_collection_compatible(collection)


if __name__ == "__main__":
    unittest.main()
