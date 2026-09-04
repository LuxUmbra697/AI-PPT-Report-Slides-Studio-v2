"""用已确认大纲生成完整、独立的 HTML 报告文档。"""

from __future__ import annotations

import json

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, Field, ValidationError

from app.llm.base import OutlineSourceSection
from app.llm.client import StructuredChatClient
from app.llm.errors import InvalidModelOutputError
from app.services.html_document import validate_generated_document


class HtmlReportOutlineItem(BaseModel):
    title: str
    objective: str
    key_points: list[str]
    source_refs: list[str] = Field(default_factory=list)


class HtmlReportImageAsset(BaseModel):
    """由服务端取得并保存的 HTML 报告视觉资产。

    网页模型只会拿到本项目媒体地址，既不会依赖生图供应商的临时 URL，也不会把
    Unsplash 等第三方热链带进成品。``credit`` 保留给模型在适当位置做署名。
    """

    url: str
    alt: str
    source: str
    credit: str | None = None


class HtmlReportGenerationInput(BaseModel):
    title: str
    audience: str | None = None
    tone: str
    style_prompt: str | None = None
    outline: list[HtmlReportOutlineItem] = Field(min_length=1, max_length=20)
    sections: list[OutlineSourceSection] = Field(default_factory=list)
    image_assets: list[HtmlReportImageAsset] = Field(default_factory=list, max_length=3)


class HtmlDocumentDraft(BaseModel):
    """结构化调用的外壳；html 的内容由模型完整创作。"""

    html: str = Field(min_length=80, max_length=420_000)


class DeepSeekHtmlDocumentGenerator:
    def __init__(
        self,
        *,
        model: BaseChatModel | None = None,
        api_key: str = "",
        chat: StructuredChatClient | None = None,
    ) -> None:
        if chat is not None:
            self._chat = chat
        elif model is not None:
            self._chat = StructuredChatClient(model=model, api_key=api_key)
        else:
            raise TypeError("需要 model 或 chat")

    async def generate(self, payload: HtmlReportGenerationInput) -> str:
        try:
            draft = await self._chat.complete(
                HtmlDocumentDraft,
                system=(
                    "你是一位顶尖的中文创意前端设计师与信息可视化工程师。请根据已确认的"
                    "大纲、来源材料、受众、语气及风格提示词，亲自创作一份可直接打开的完整"
                    "HTML 报告。不要使用、模拟或套用任何本系统的页面模板：视觉概念、布局、"
                    "色彩、排版、组件、装饰、动效与交互均由你从零决定，风格提示词是最高优先级。"
                    "必须输出单一的 <!doctype html> 文档，文档内部自行包含 head、body、CSS 与"
                    "所需 JavaScript；不要输出 Markdown、代码围栏、解释或 PPT/幻灯片界面。"
                    "默认使用原生 HTML/CSS/JS 与语义化 table 创作数据报表、Excel 风格表格、指标卡、"
                    "矩阵、关系图和数据大屏。也可按实际内容选用最多 4 个获准框架：Tailwind"
                    "（https://cdn.tailwindcss.com）、ECharts 5"
                    "（https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js，用于 2D 图表）、"
                    "ECharts GL（https://cdn.jsdelivr.net/npm/echarts-gl@2/dist/echarts-gl.min.js，"
                    "用于有业务意义的 3D 图表）、Three.js"
                    "（https://cdn.jsdelivr.net/npm/three@0.160.1/build/"
                    "three.min.js，用于原生几何 3D 场景）、"
                    "JsBarcode（https://cdn.jsdelivr.net/npm/jsbarcode@3.11.6/dist/JsBarcode.all.min.js）、"
                    "QRCode（https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js）或 SheetJS"
                    "（https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js）。"
                    "如使用 SheetJS，只能从文档内嵌数据生成离线 XLSX 下载；如使用条码/二维码，"
                    "只能编码输入材料中真实存在的值。3D 必须提供文本、表格或 2D 图的可访问降级，"
                    "不能加载外部模型、纹理或数据。不要引用其他 JavaScript CDN，"
                    "不要发起 fetch、XHR、WebSocket 或任何运行时网络请求；"
                    "不要使用 iframe、表单、storage、cookie、eval"
                    "或动态 import。"
                    "若输入提供 image_assets，请按语义实际使用其中至少 1 张（最多 3 张），"
                    "并保留有 credit 的署名；"
                    "不得杜撰、热链或请求任何其他图片 URL。没有可用图片时，优先原创 CSS、内联 SVG、"
                    "图案或渐变视觉。报告应有清晰的信息层级、真实可读的正文、合适的图表、数据卡片、"
                    "表格或时间线等表达；ECharts 的数据必须直接内嵌在文档脚本中，"
                    "图表只能使用来源支持的数据，缺少精确数据时用定性结构图并明确标示。"
                    '内部章节导航须使用 href="#section-id" 与对应 id，不能通过'
                    "location 改写页面地址。动效要克制、有意义，并尊重 prefers-reduced-motion。"
                    "最外层 JSON 只能有 html 字段，字段值必须是完整 HTML 源码。"
                ),
                user=json.dumps(
                    {
                        "title": payload.title,
                        "audience": payload.audience,
                        "tone": payload.tone,
                        "html_style_prompt": payload.style_prompt,
                        "outline": [item.model_dump() for item in payload.outline],
                        "sources": [item.model_dump() for item in payload.sections],
                        "image_assets": [item.model_dump() for item in payload.image_assets],
                    },
                    ensure_ascii=False,
                ),
                purpose="生成 HTML 报告",
            )
        except (InvalidModelOutputError, ValidationError) as error:
            raise InvalidModelOutputError("模型没有返回完整 HTML 文档") from error
        try:
            return validate_generated_document(
                draft.html,
                allowed_image_urls={asset.url for asset in payload.image_assets},
            )
        except ValueError as error:
            raise InvalidModelOutputError("模型生成的 HTML 未满足隔离运行要求") from error
