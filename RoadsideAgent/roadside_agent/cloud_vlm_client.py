from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional

from .config import CloudConfig
from .prompt import build_messages
from .types import RoadsideBatchInput, RoadsideDecision


class CloudVlmClient:
    def decide(self, batch_input: RoadsideBatchInput, images: list[dict[str, Any]]) -> RoadsideDecision:
        raise NotImplementedError


class DisabledCloudVlmClient(CloudVlmClient):
    def decide(self, batch_input: RoadsideBatchInput, images: list[dict[str, Any]]) -> RoadsideDecision:
        raise RuntimeError("Roadside cloud VLM client is disabled")


class OpenAICompatibleClient(CloudVlmClient):
    def __init__(self, config: CloudConfig) -> None:
        self.base_url = (config.base_url or "https://api.openai.com/v1").rstrip("/")
        self.api_key = os.environ.get(config.api_key_env or "OPENAI_API_KEY", "")
        self.model = config.model or "gpt-4o"
        self.timeout = config.timeout_ms / 1000.0
        self.extra = dict(config.extra)

    def decide(self, batch_input: RoadsideBatchInput, images: list[dict[str, Any]]) -> RoadsideDecision:
        messages = self._to_openai_messages(batch_input=batch_input, images=images)
        payload = {
            "model": self.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        payload.update(self.extra)
        data = self._post_json(f"{self.base_url}/chat/completions", payload)
        content = data["choices"][0]["message"]["content"]
        return RoadsideDecision.from_dict(json.loads(content))

    def _to_openai_messages(
        self,
        batch_input: RoadsideBatchInput,
        images: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        base_messages = build_messages(batch_input)
        user_payload = base_messages[-1]["content"]
        content: list[dict[str, Any]] = [
            {"type": "text", "text": json.dumps(user_payload, ensure_ascii=False)}
        ]

        for item in images:
            text_anchor = (
                f'vehicle_id={item["vehicle_id"]} '
                f'camera_id={item["camera_id"]} '
                f'image_key={item["image_key"]}'
            )
            encoded = encode_image_to_data_url(item["image"])
            if not encoded:
                continue
            content.append({"type": "text", "text": text_anchor})
            content.append({"type": "image_url", "image_url": {"url": encoded}})

        return [
            {"role": "system", "content": base_messages[0]["content"]},
            {"role": "user", "content": content},
        ]

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Roadside cloud VLM request failed: {exc}") from exc


class DashScopeCompatibleClient(OpenAICompatibleClient):
    def __init__(self, config: CloudConfig) -> None:
        if config.base_url is None:
            config.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        if config.api_key_env is None:
            config.api_key_env = "DASHSCOPE_API_KEY"
        super().__init__(config)


class VolcArkCompatibleClient(OpenAICompatibleClient):
    def __init__(self, config: CloudConfig) -> None:
        if config.base_url is None:
            config.base_url = "https://ark.cn-beijing.volces.com/api/v3"
        if config.api_key_env is None:
            config.api_key_env = "ARK_API_KEY"
        super().__init__(config)


def build_cloud_vlm_client(config: CloudConfig) -> CloudVlmClient:
    provider = config.provider.lower()
    if provider in {"openai", "openai_compatible"}:
        return OpenAICompatibleClient(config)
    if provider in {"dashscope", "qwen"}:
        return DashScopeCompatibleClient(config)
    if provider in {"ark", "volc", "volcengine"}:
        return VolcArkCompatibleClient(config)
    return DisabledCloudVlmClient()


def encode_image_to_data_url(image: Any, quality: int = 70) -> Optional[str]:
    try:
        import cv2
    except ImportError:
        return None

    ok, buffer = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        return None

    encoded = base64.b64encode(buffer.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"
