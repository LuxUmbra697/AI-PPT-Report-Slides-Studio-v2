"""独立 HTML 报告数据与通用导出内容模型之间的受控转换。"""

from __future__ import annotations

from app.domain.content import (
    BulletsBlock,
    CalloutBlock,
    ChartBlock,
    ChartSeries,
    Deck,
    ImageBlock,
    Slide,
    TableBlock,
    TextBlock,
)
from app.domain.html_report import HtmlReportDraft
from app.models.project import Project


def load_html_report(project: Project) -> HtmlReportDraft:
    return HtmlReportDraft.model_validate(project.html_report_data or {})


def html_report_to_html_deck(project: Project, report: HtmlReportDraft) -> Deck:
    """保留报告段落与摘要，供 HTML/MD/PDF 阅读版使用。"""

    slides: list[Slide] = []
    for index, section in enumerate(report.sections, start=1):
        blocks = [
            TextBlock(id=f"html-{index}-title", slot_id="title", text=section.title),
            TextBlock(id=f"html-{index}-lead", slot_id="lead", text=section.lead),
            *[
                TextBlock(id=f"html-{index}-body-{part}", slot_id="body", text=paragraph)
                for part, paragraph in enumerate(section.paragraphs, start=1)
            ],
            BulletsBlock(
                id=f"html-{index}-highlights",
                slot_id="highlights",
                items=section.highlights,
            ),
        ]
        if section.image is not None:
            blocks.append(
                ImageBlock(
                    id=f"html-{index}-image",
                    slot_id="visual",
                    url=section.image.url,
                    alt=section.image.alt,
                    source="generated",
                    credit=section.image.credit,
                )
            )
        if index == 1:
            blocks.append(
                CalloutBlock(
                    id="html-report-summary",
                    slot_id="summary",
                    text=report.summary,
                    variant="source",
                )
            )
            # 这是由已确认大纲推导出的结构统计，不把它伪装成外部业务数据。
            blocks.append(
                ChartBlock(
                    id="html-report-outline-chart",
                    slot_id="structure-chart",
                    chart_type="bar",
                    categories=[item.title for item in report.sections[:6]],
                    series=[
                        ChartSeries(
                            name="每节已确认要点数",
                            values=[float(len(item.highlights)) for item in report.sections[:6]],
                        )
                    ],
                    unit="项",
                )
            )
            blocks.append(
                TableBlock(
                    id="html-report-section-table",
                    slot_id="section-map",
                    header=["章节", "阅读焦点"],
                    rows=[
                        [item.title, item.lead]
                        for item in report.sections[: min(6, len(report.sections))]
                    ],
                )
            )
        if section.callout:
            blocks.append(
                CalloutBlock(
                    id=f"html-{index}-callout",
                    slot_id="callout",
                    text=section.callout,
                    variant="note",
                )
            )
        slides.append(Slide(id=f"html-{index}", layout_id="report", blocks=blocks))
    return Deck(id=str(project.id), title=project.title, theme_id=project.theme_id, slides=slides)


def html_report_to_ppt_deck(project: Project, report: HtmlReportDraft) -> Deck:
    """仅在用户主动导出 PPTX 时，把报告压缩为兼容原生 PPT 版式的要点页。"""

    slides = [
        Slide(
            id=f"html-ppt-{index}",
            layout_id="bullets",
            blocks=[
                TextBlock(id=f"html-ppt-{index}-title", slot_id="title", text=section.title),
                BulletsBlock(
                    id=f"html-ppt-{index}-body",
                    slot_id="body",
                    items=[section.lead, *section.highlights],
                ),
            ],
        )
        for index, section in enumerate(report.sections, start=1)
    ]
    return Deck(id=str(project.id), title=project.title, theme_id=project.theme_id, slides=slides)
