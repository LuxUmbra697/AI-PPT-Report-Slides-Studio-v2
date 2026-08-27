import logging
import re

import httpx

from app.domain.content import ImageSource
from app.images.base import ImageAsset, ImageRequest

logger = logging.getLogger(__name__)

API_BASE = "https://api.unsplash.com"

# Unsplash 对含部分中文标点的 query 会直接 410 Content removed（实测全角冒号必现）
_PUNCT_RE = re.compile(r"[：:；;，,。.!！？?\u2014\u2013\-_/\\|（）()【】\[\]「」\"'“”‘’…·、]+")
_SPACE_RE = re.compile(r"\s+")
_MAX_QUERY_CHARS = 48


class UnsplashImageProvider:
    """Unsplash 图库检索。

    Unsplash 的接入条款要求：使用图片时标注作者，并在实际取用时回调
    download_location。这两件事都不能省，否则属于违规使用。
    """

    source: ImageSource = "stock"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        access_key: str,
        timeout_seconds: float = 30,
    ) -> None:
        self._client = client
        self._access_key = access_key
        self._timeout = timeout_seconds

    def available(self) -> bool:
        return bool(self._access_key.strip())

    async def fetch(self, request: ImageRequest) -> ImageAsset | None:
        if not self.available():
            return None

        headers = {"Authorization": f"Client-ID {self._access_key}"}
        orientation = _orientation(request.aspect_ratio)
        queries = _search_queries(request.query)
        try:
            photo = None
            for index, query in enumerate(queries):
                search = await self._client.get(
                    f"{API_BASE}/search/photos",
                    headers=headers,
                    params={
                        "query": query,
                        "per_page": 1,
                        "orientation": orientation,
                        "content_filter": "high",
                    },
                    timeout=self._timeout,
                )
                if search.status_code == 410:
                    logger.warning(
                        "Unsplash 拒绝 query（Content removed），尝试下一候选：%s",
                        query[:40],
                    )
                    continue
                search.raise_for_status()
                results = search.json().get("results") or []
                if not results:
                    # 清洗后无结果时再试更短候选
                    if index < len(queries) - 1:
                        continue
                    return None
                photo = results[0]
                break

            if photo is None:
                return None

            image = await self._client.get(
                photo["urls"]["regular"],
                timeout=self._timeout,
            )
            image.raise_for_status()
            await self._track_download(photo, headers)
        except (httpx.HTTPError, ValueError, KeyError) as error:
            logger.warning("图库检索失败，降级到占位图：%s", error)
            return None

        return ImageAsset(
            data=image.content,
            content_type=image.headers.get("content-type", "image/jpeg"),
            source="stock",
            credit=_credit(photo),
        )

    async def _track_download(self, photo: dict, headers: dict[str, str]) -> None:
        location = (photo.get("links") or {}).get("download_location")
        if not location:
            return
        try:
            await self._client.get(location, headers=headers, timeout=self._timeout)
        except httpx.HTTPError as error:
            # 下载回调失败不影响已取到的配图结果，仅记录
            logger.warning("Unsplash 下载回调失败：%s", error)


def sanitize_unsplash_query(query: str) -> str:
    """去掉易触发 Unsplash 410 的标点，压空白并截断。"""
    cleaned = _PUNCT_RE.sub(" ", query)
    cleaned = _SPACE_RE.sub(" ", cleaned).strip()
    if len(cleaned) > _MAX_QUERY_CHARS:
        cleaned = cleaned[:_MAX_QUERY_CHARS].rstrip()
    return cleaned


def _search_queries(raw: str) -> list[str]:
    """主 query + 短关键词兜底，去重保序。"""
    primary = sanitize_unsplash_query(raw)
    if not primary:
        return []
    # 取前 2～3 个词/字块作短查询，避免长叙述被内容策略误伤
    tokens = [part for part in primary.split(" ") if part]
    short = " ".join(tokens[:3]) if tokens else primary
    if len(short) > 16:
        short = short[:16].rstrip()
    out: list[str] = []
    for item in (primary, short):
        if item and item not in out:
            out.append(item)
    return out


def _orientation(aspect_ratio: float) -> str:
    if aspect_ratio >= 1.2:
        return "landscape"
    if aspect_ratio <= 0.85:
        return "portrait"
    return "squarish"


def _credit(photo: dict) -> str:
    name = ((photo.get("user") or {}).get("name")) or "Unsplash"
    return f"Photo by {name} on Unsplash"
