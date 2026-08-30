from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Sequence

import httpx

from .config import Settings


DASHSCOPE_MULTIMODAL_EMBEDDING_MODELS = {
    "qwen3-vl-embedding",
    "qwen2.5-vl-embedding",
}
DASHSCOPE_MULTIMODAL_EMBEDDING_PATH = (
    "services/embeddings/multimodal-embedding/multimodal-embedding"
)


class OnlineServiceError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "online_service_error",
        status_code: int = 502,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details


@dataclass(frozen=True, slots=True)
class ModelStatus:
    model: str
    base_url: str
    configured: bool


class _OpenAICompatibleClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
        max_retries: int,
        service_name: str,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.max_retries = max_retries
        self.service_name = service_name
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 15.0))
        )

    def close(self) -> None:
        self._client.close()

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.base_url or not self.api_key:
            raise OnlineServiceError(
                f"{self.service_name} 未配置完整，请检查 Base URL 和 API Key。",
                code="configuration_error",
                status_code=503,
            )

        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.post(url, headers=headers, json=payload)
            except (httpx.InvalidURL, httpx.UnsupportedProtocol) as exc:
                raise OnlineServiceError(
                    f"{self.service_name} Base URL 无效，请检查配置。",
                    code="configuration_error",
                    status_code=503,
                ) from exc
            except httpx.TransportError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise OnlineServiceError(
                    f"{self.service_name} 请求超时或网络连接失败：{exc}",
                    code="network_error",
                    status_code=502,
                ) from exc

            if response.status_code < 400:
                try:
                    body = response.json()
                except ValueError as exc:
                    raise OnlineServiceError(
                        f"{self.service_name} 返回了无法解析的 JSON。",
                        code="invalid_provider_response",
                    ) from exc
                if not isinstance(body, dict):
                    raise OnlineServiceError(
                        f"{self.service_name} 返回结构不正确。",
                        code="invalid_provider_response",
                    )
                return body

            retryable = response.status_code in {408, 429, 500, 502, 503, 504}
            if retryable and attempt < self.max_retries:
                time.sleep(0.5 * (2**attempt))
                continue

            provider_message = _provider_error_message(response)
            if response.status_code in {401, 403}:
                raise OnlineServiceError(
                    f"{self.service_name} 认证失败，请检查 API Key。",
                    code="provider_auth_error",
                    status_code=502,
                )
            if response.status_code in {400, 404, 405, 422}:
                raise OnlineServiceError(
                    f"{self.service_name} 请求被拒绝，请检查 Base URL、模型名和参数。{provider_message}",
                    code="provider_request_error",
                    status_code=502,
                )
            raise OnlineServiceError(
                f"{self.service_name} 暂时不可用（HTTP {response.status_code}）。{provider_message}",
                code="provider_unavailable",
                status_code=502,
            )

        raise OnlineServiceError(
            f"{self.service_name} 请求失败：{last_error}", code="network_error"
        )

    def _post_stream_content(self, path: str, payload: dict[str, Any]) -> str:
        if not self.base_url or not self.api_key:
            raise OnlineServiceError(
                f"{self.service_name} 未配置完整，请检查 Base URL 和 API Key。",
                code="configuration_error",
                status_code=503,
            )

        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with self._client.stream(
                    "POST", url, headers=headers, json=payload
                ) as response:
                    if response.status_code >= 400:
                        response.read()
                        retryable = response.status_code in {
                            408,
                            429,
                            500,
                            502,
                            503,
                            504,
                        }
                        if retryable and attempt < self.max_retries:
                            time.sleep(0.5 * (2**attempt))
                            continue
                        raise _provider_response_error(
                            response, service_name=self.service_name
                        )

                    chunks: list[str] = []
                    for line in response.iter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line.removeprefix("data:").strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            event = json.loads(data)
                            choices = event.get("choices")
                            delta = choices[0].get("delta") if choices else None
                            content = (
                                delta.get("content")
                                if isinstance(delta, dict)
                                else None
                            )
                        except (
                            json.JSONDecodeError,
                            AttributeError,
                            IndexError,
                            TypeError,
                        ) as exc:
                            raise OnlineServiceError(
                                f"{self.service_name} 返回了无法解析的流式数据。",
                                code="invalid_provider_response",
                            ) from exc
                        if isinstance(content, str):
                            chunks.append(content)

                    content = "".join(chunks).strip()
                    if not content:
                        raise OnlineServiceError(
                            f"{self.service_name} 返回了空内容。",
                            code="invalid_provider_response",
                        )
                    return content
            except (httpx.InvalidURL, httpx.UnsupportedProtocol) as exc:
                raise OnlineServiceError(
                    f"{self.service_name} Base URL 无效，请检查配置。",
                    code="configuration_error",
                    status_code=503,
                ) from exc
            except httpx.TransportError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise OnlineServiceError(
                    f"{self.service_name} 请求超时或网络连接失败：{exc}",
                    code="network_error",
                    status_code=502,
                ) from exc

        raise OnlineServiceError(
            f"{self.service_name} 请求失败：{last_error}", code="network_error"
        )


def _provider_error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict):
            message = error.get("message")
            return f" 服务商信息：{message}" if message else ""
        if isinstance(error, str):
            return f" 服务商信息：{error}"
    except ValueError:
        pass
    return ""


def _provider_response_error(
    response: httpx.Response, *, service_name: str
) -> OnlineServiceError:
    provider_message = _provider_error_message(response)
    if response.status_code in {401, 403}:
        return OnlineServiceError(
            f"{service_name} 认证失败，请检查 API Key。",
            code="provider_auth_error",
            status_code=502,
        )
    if response.status_code in {400, 404, 405, 422}:
        return OnlineServiceError(
            f"{service_name} 请求被拒绝，请检查 Base URL、模型名和参数。"
            f"{provider_message}",
            code="provider_request_error",
            status_code=502,
        )
    return OnlineServiceError(
        f"{service_name} 暂时不可用（HTTP {response.status_code}）。"
        f"{provider_message}",
        code="provider_unavailable",
        status_code=502,
    )


class OnlineChatModel(_OpenAICompatibleClient):
    def __init__(self, settings: Settings):
        self.settings = settings
        super().__init__(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            service_name="在线聊天模型",
        )

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if not self.settings.llm_model:
            raise OnlineServiceError(
                "在线聊天模型未配置，请设置 LLM_MODEL。",
                code="configuration_error",
                status_code=503,
            )
        return self._post_stream_content(
            "chat/completions",
            {
                "model": self.settings.llm_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.6,
                "top_p": 0.9,
                "max_tokens": self.settings.llm_max_tokens,
                "stream": True,
                "enable_thinking": self.settings.llm_enable_thinking,
                "response_format": {"type": "json_object"},
            },
        )

    def status(self) -> ModelStatus:
        return ModelStatus(
            model=self.settings.llm_model,
            base_url=self.settings.llm_base_url,
            configured=self.settings.llm_configured,
        )


class OnlineEmbeddingClient(_OpenAICompatibleClient):
    def __init__(self, settings: Settings):
        self.settings = settings
        super().__init__(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            timeout_seconds=settings.embedding_timeout_seconds,
            max_retries=settings.llm_max_retries,
            service_name="在线 Embedding 模型",
        )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.settings.embedding_model:
            raise OnlineServiceError(
                "在线 Embedding 模型未配置，请设置 EMBEDDING_MODEL。",
                code="configuration_error",
                status_code=503,
            )

        all_embeddings: list[list[float]] = []
        batch_size = self.settings.embedding_batch_size
        if self.settings.embedding_model == "qwen3-vl-embedding":
            batch_size = min(batch_size, 20)
        elif self.settings.embedding_model == "qwen2.5-vl-embedding":
            batch_size = 1

        for start in range(0, len(texts), batch_size):
            batch = list(texts[start : start + batch_size])
            if self.settings.embedding_model in DASHSCOPE_MULTIMODAL_EMBEDDING_MODELS:
                body = self._post(
                    DASHSCOPE_MULTIMODAL_EMBEDDING_PATH,
                    {
                        "model": self.settings.embedding_model,
                        "input": {
                            "contents": [{"text": text} for text in batch]
                        },
                        "parameters": {
                            "dimension": self.settings.embedding_dimension
                        },
                    },
                )
                output = body.get("output")
                data = output.get("embeddings") if isinstance(output, dict) else None
            else:
                body = self._post(
                    "embeddings",
                    {"model": self.settings.embedding_model, "input": batch},
                )
                data = body.get("data")

            if not isinstance(data, list) or len(data) != len(batch):
                raise OnlineServiceError(
                    "在线 Embedding 模型返回的向量数量与输入不一致。",
                    code="invalid_provider_response",
                )
            try:
                ordered = sorted(data, key=lambda item: int(item["index"]))
                indexes = [int(item["index"]) for item in ordered]
                embeddings = [
                    [float(value) for value in item["embedding"]] for item in ordered
                ]
            except (KeyError, TypeError, ValueError) as exc:
                raise OnlineServiceError(
                    "在线 Embedding 模型返回的向量结构不正确。",
                    code="invalid_provider_response",
                ) from exc
            if indexes != list(range(len(batch))):
                raise OnlineServiceError(
                    "在线 Embedding 模型返回的向量索引不连续。",
                    code="invalid_provider_response",
                )
            for vector in embeddings:
                if len(vector) != self.settings.embedding_dimension:
                    raise OnlineServiceError(
                        "在线 Embedding 实际维度与 EMBEDDING_DIMENSION 不一致："
                        f"期望 {self.settings.embedding_dimension}，实际 {len(vector)}。",
                        code="embedding_dimension_mismatch",
                    )
            all_embeddings.extend(embeddings)
        return all_embeddings


class QwenTravelModel(OnlineChatModel):
    """旧类名的兼容入口；当前实现只调用在线 OpenAI-compatible API。"""
