from typing import Any

import pytest

from app.llm.html_report import (
    DeepSeekHtmlDocumentGenerator,
    HtmlReportGenerationInput,
    HtmlReportImageAsset,
    HtmlReportOutlineItem,
)


class FakeChat:
    def __init__(self) -> None:
        self.called = False
        self.system = ""
        self.user = ""

    async def complete(self, schema: Any, *, system: str, user: str, purpose: str) -> Any:
        self.called = True
        self.system = system
        self.user = user
        return schema.model_validate(
            {
                "html": "<!doctype html><html><head><title>报告</title></head>"
                "<body><main><h1>HTML 报告</h1><p>正文完全由模型设计。</p></main>"
                "<script>document.body.dataset.ready = 'true'</script></body></html>",
            }
        )


@pytest.mark.asyncio
async def test_html_report_generator_writes_complete_document_without_template() -> None:
    chat = FakeChat()
    generator = DeepSeekHtmlDocumentGenerator(chat=chat)
    document = await generator.generate(
        HtmlReportGenerationInput(
            title="HTML 报告",
            tone="professional",
            outline=[
                HtmlReportOutlineItem(
                    title="结论", objective="说明链路", key_points=["独立", "直接"]
                )
            ],
            image_assets=[
                HtmlReportImageAsset(
                    url="/api/v1/media/media/user/project/hero.png",
                    alt="报告主视觉",
                    source="generated",
                )
            ],
        )
    )

    assert chat.called
    assert "不要使用、模拟或套用任何本系统的页面模板" in chat.system
    assert "https://cdn.tailwindcss.com" in chat.system
    assert "ECharts GL" in chat.system
    assert "Three.js" in chat.system
    assert "JsBarcode" in chat.system
    assert "SheetJS" in chat.system
    assert "实际使用其中至少 1 张" in chat.system
    assert "不得杜撰、热链或请求任何其他图片 URL" in chat.system
    assert "/api/v1/media/media/user/project/hero.png" in chat.user
    assert document.startswith("<!doctype html>")
    assert 'data-luxumbra-ai-document="true"' in document
