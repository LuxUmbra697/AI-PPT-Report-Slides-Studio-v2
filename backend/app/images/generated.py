import base64
import logging

import httpx

from app.domain.content import ImageSource
from app.images.base import ImageAsset, ImageRequest

logger = logging.getLogger(__name__)

# OpenAI 兼容接口只接受固定尺寸，按宽高比就近选一个，
# 剩下的偏差交给渲染时的裁切处理。
SIZES: tuple[tuple[float, str], ...] = (
    (1.0, "1024x1024"),
    (1.5, "1536x1024"),
    (0.667, "1024x1536"),
)


class GeneratedImageProvider:
    """OpenAI 兼容的 /images/generations 适配器。"""

    source: ImageSource = "generated"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds

    def available(self) -> bool:
        return bool(self._api_key.strip())

    async def fetch(self, request: ImageRequest) -> ImageAsset | None:
        if not self.available():
            return None

        try:
            response = await self._client.post(
                f"{self._base_url}/images/generations",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "prompt": request.prompt,
                    "size": _closest_size(request.aspect_ratio),
                    "n": 1,
                },
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
            data = await self._read_first(payload)
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as error:
            # 配图失败只降级不报错：一张图不该让整页生成失败
            logger.warning("AI 生图失败，降级到下一级图源：%s", error)
            return None

        if data is None:
            return None
        return ImageAsset(data=data, content_type="image/png", source="generated")

    async def _read_first(self, payload: dict) -> bytes | None:
        item = payload["data"][0]
        # 不同供应商分别返回 base64 或临时链接，两种都要支持
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        url = item.get("url")
        if not url:
            return None
        response = await self._client.get(url, timeout=self._timeout)
        response.raise_for_status()
        return response.content


def _closest_size(aspect_ratio: float) -> str:
    return min(SIZES, key=lambda item: abs(item[0] - aspect_ratio))[1]
