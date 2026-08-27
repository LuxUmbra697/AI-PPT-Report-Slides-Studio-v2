import logging

import httpx

from app.domain.content import ImageSource
from app.images.base import ImageAsset, ImageRequest

logger = logging.getLogger(__name__)

GENERATION_PATH = "/services/aigc/multimodal-generation/generation"

# 百炼 size 格式为「宽*高」；按槽位宽高比就近选，减少后续裁切损失
SIZES: tuple[tuple[float, str], ...] = (
    (1.0, "1328*1328"),
    (1.5, "1664*928"),
    (0.667, "928*1664"),
)


class BailianImageProvider:
    """阿里云百炼 DashScope multimodal-generation 文生图适配器。

    qwen-image-3.0 等模型不支持 OpenAI compatible-mode，必须走原生接口。
    """

    source: ImageSource = "generated"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str,
        model: str,
        base_url: str = "https://dashscope.aliyuncs.com/api/v1",
        workspace_id: str = "",
        timeout_seconds: float = 60,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._base_url = _resolve_base_url(base_url, workspace_id)

    def available(self) -> bool:
        return bool(self._api_key.strip())

    async def fetch(self, request: ImageRequest) -> ImageAsset | None:
        if not self.available():
            return None

        try:
            response = await self._client.post(
                f"{self._base_url}{GENERATION_PATH}",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "input": {
                        "messages": [
                            {
                                "role": "user",
                                "content": [{"text": request.prompt}],
                            }
                        ]
                    },
                    "parameters": {
                        "size": _closest_size(request.aspect_ratio),
                        "n": 1,
                        "watermark": False,
                        "prompt_extend": True,
                    },
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code"):
                logger.warning(
                    "百炼生图业务失败，降级到下一级图源：%s %s",
                    payload.get("code"),
                    payload.get("message"),
                )
                return None
            url = _extract_image_url(payload)
            if not url:
                return None
            image = await self._client.get(url, timeout=self._timeout)
            image.raise_for_status()
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
            logger.warning("百炼生图失败，降级到下一级图源：%s", error)
            return None

        return ImageAsset(data=image.content, content_type="image/png", source="generated")


def _resolve_base_url(base_url: str, workspace_id: str) -> str:
    workspace = workspace_id.strip()
    if workspace:
        return f"https://{workspace}.cn-beijing.maas.aliyuncs.com/api/v1"
    return base_url.rstrip("/")


def _closest_size(aspect_ratio: float) -> str:
    return min(SIZES, key=lambda item: abs(item[0] - aspect_ratio))[1]


def _extract_image_url(payload: dict) -> str | None:
    choices = payload.get("output", {}).get("choices") or []
    if not choices:
        return None
    content = choices[0].get("message", {}).get("content") or []
    for item in content:
        if isinstance(item, dict) and item.get("image"):
            return str(item["image"])
    return None
