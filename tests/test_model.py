from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from travel_assistant.config import Settings
from travel_assistant.model import OnlineChatModel, OnlineEmbeddingClient


def _settings(model: str, *, batch_size: int = 32):
    return SimpleNamespace(
        embedding_base_url="https://dashscope.aliyuncs.com/api/v1",
        embedding_api_key="test-key",
        embedding_timeout_seconds=120,
        embedding_batch_size=batch_size,
        embedding_model=model,
        embedding_dimension=1024,
        llm_max_retries=0,
    )


def _chat_settings():
    return SimpleNamespace(
        llm_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        llm_api_key="test-key",
        llm_timeout_seconds=120,
        llm_max_retries=0,
        llm_model="qwen3.8-27b",
        llm_max_tokens=4096,
        llm_enable_thinking=False,
        llm_configured=True,
    )


class OnlineChatModelTests(unittest.TestCase):
    def test_chat_generation_streams_json_without_thinking(self):
        observed_payload = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal observed_payload
            observed_payload = json.loads(request.content)
            if observed_payload.get("stream"):
                content = (
                    'data: {"choices":[{"delta":{"reasoning_content":"忽略"}}]}\n\n'
                    'data: {"choices":[{"delta":{"content":"{\\"summary\\":"}}]}\n\n'
                    'data: {"choices":[{"delta":{"content":"\\"ok\\"}"}}]}\n\n'
                    "data: [DONE]\n\n"
                )
                return httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    content=content.encode(),
                )
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"summary":"ok"}'}}]},
            )

        model = OnlineChatModel(_chat_settings())
        model._client.close()
        model._client = httpx.Client(transport=httpx.MockTransport(handler))
        try:
            result = model.generate("system", "user")
        finally:
            model.close()

        self.assertEqual(result, '{"summary":"ok"}')
        self.assertIsNotNone(observed_payload)
        self.assertIs(observed_payload.get("stream"), True)
        self.assertIs(observed_payload.get("enable_thinking"), False)
        self.assertEqual(
            observed_payload.get("response_format"), {"type": "json_object"}
        )


class SettingsTests(unittest.TestCase):
    def test_thinking_can_be_disabled_from_environment(self):
        with patch.dict(os.environ, {"LLM_ENABLE_THINKING": "false"}, clear=True):
            settings = Settings.from_env()

        self.assertIs(getattr(settings, "llm_enable_thinking", None), False)


class OnlineEmbeddingClientTests(unittest.TestCase):
    def test_qwen3_vl_uses_native_multimodal_api_and_limits_batch_to_twenty(self):
        client = OnlineEmbeddingClient(_settings("qwen3-vl-embedding"))
        calls = []

        def fake_post(path, payload):
            calls.append((path, payload))
            contents = payload["input"]["contents"]
            return {
                "output": {
                    "embeddings": [
                        {
                            "index": index,
                            "embedding": [float(index)] * 1024,
                            "type": "vl",
                        }
                        for index in reversed(range(len(contents)))
                    ]
                },
                "request_id": "test-request",
                "usage": {
                    "input_tokens": len(contents),
                    "image_tokens": 0,
                    "total_tokens": len(contents),
                },
            }

        client._post = fake_post
        vectors = client.embed([f"文本 {index}" for index in range(21)])

        self.assertEqual([len(call[1]["input"]["contents"]) for call in calls], [20, 1])
        self.assertTrue(
            all(
                call[0]
                == "services/embeddings/multimodal-embedding/multimodal-embedding"
                for call in calls
            )
        )
        self.assertEqual(
            calls[0][1],
            {
                "model": "qwen3-vl-embedding",
                "input": {
                    "contents": [{"text": f"文本 {index}"} for index in range(20)]
                },
                "parameters": {"dimension": 1024},
            },
        )
        self.assertEqual(len(vectors), 21)
        self.assertEqual(vectors[0][0], 0.0)
        self.assertEqual(vectors[19][0], 19.0)

    def test_qwen25_vl_sends_one_text_per_request(self):
        client = OnlineEmbeddingClient(_settings("qwen2.5-vl-embedding"))
        calls = []

        def fake_post(path, payload):
            calls.append((path, payload))
            return {
                "output": {
                    "embeddings": [
                        {
                            "index": 0,
                            "embedding": [float(len(calls))] * 1024,
                            "type": "fusion",
                        }
                    ]
                },
                "request_id": f"test-request-{len(calls)}",
                "usage": {"input_tokens": 1, "image_tokens": 0},
            }

        client._post = fake_post
        vectors = client.embed(["第一段", "第二段"])

        self.assertEqual(len(calls), 2)
        self.assertEqual(
            [call[1]["input"]["contents"] for call in calls],
            [[{"text": "第一段"}], [{"text": "第二段"}]],
        )
        self.assertTrue(
            all(call[1]["parameters"] == {"dimension": 1024} for call in calls)
        )
        self.assertEqual([vector[0] for vector in vectors], [1.0, 2.0])

    def test_openai_compatible_embedding_models_keep_existing_protocol(self):
        client = OnlineEmbeddingClient(_settings("local-bge-m3", batch_size=2))
        calls = []

        def fake_post(path, payload):
            calls.append((path, payload))
            return {
                "object": "list",
                "data": [
                    {
                        "object": "embedding",
                        "index": index,
                        "embedding": [float(index)] * 1024,
                    }
                    for index in range(len(payload["input"]))
                ],
                "model": "local-bge-m3",
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            }

        client._post = fake_post
        vectors = client.embed(["a", "b", "c"])

        self.assertEqual(
            calls,
            [
                ("embeddings", {"model": "local-bge-m3", "input": ["a", "b"]}),
                ("embeddings", {"model": "local-bge-m3", "input": ["c"]}),
            ],
        )
        self.assertEqual(len(vectors), 3)


if __name__ == "__main__":
    unittest.main()
