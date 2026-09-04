from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.worker.html_report_tasks as html_tasks
from app.images.base import ImageAsset, ImageRequest
from app.llm.html_report import HtmlReportGenerationInput, HtmlReportOutlineItem

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeImagePipeline:
    enabled = True

    def __init__(self) -> None:
        self.requests: list[ImageRequest] = []

    async def fetch(self, request: ImageRequest) -> ImageAsset:
        self.requests.append(request)
        return ImageAsset(
            data=_PNG,
            content_type="image/png",
            source="generated",
            credit="由测试图源提供",
        )


@pytest.mark.asyncio
async def test_html_report_images_are_server_stored_before_the_model_uses_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline = FakeImagePipeline()
    stored: list[tuple[bytes, str]] = []
    monkeypatch.setattr(
        html_tasks,
        "get_settings",
        lambda: SimpleNamespace(html_report_image_count=2),
    )
    monkeypatch.setattr(
        html_tasks,
        "store_image",
        lambda **kwargs: (
            stored.append((kwargs["data"], kwargs["extension"]))
            or f"media/{kwargs['user_id']}/{kwargs['project_id']}/asset.png"
        ),
    )
    payload = HtmlReportGenerationInput(
        title="星际探索",
        tone="inspiring",
        style_prompt="复古太空站，克制的蓝紫光",
        outline=[
            HtmlReportOutlineItem(title="序章", objective="建立背景", key_points=["起点"]),
            HtmlReportOutlineItem(title="远征", objective="说明探索", key_points=["航程"]),
            HtmlReportOutlineItem(title="展望", objective="总结未来", key_points=["未来"]),
        ],
    )

    assets = await html_tasks._prepare_image_assets(
        {"image_pipeline": pipeline}, payload, uuid4(), uuid4()
    )

    assert len(assets) == 2
    assert len(stored) == 2
    assert all(data == _PNG and extension == ".png" for data, extension in stored)
    assert all(asset.url.startswith("/api/v1/media/media/") for asset in assets)
    assert all(asset.credit == "由测试图源提供" for asset in assets)
    assert "不要 PPT 页面" in pipeline.requests[0].prompt
