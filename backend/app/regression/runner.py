"""固定回归集执行器：渲染 × 主题 × 密度，汇总可编辑性与溢出指标。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.domain.content import Block, Deck
from app.domain.export_check import run_export_check
from app.domain.slide_geometry import placed_by_block_id
from app.domain.text_metrics import fonts_available
from app.domain.theme import load_themes
from app.regression.corpus import DENSITIES, load_corpus_decks
from app.render.pptx import render_deck_to_pptx
from app.render.verify import verify_pptx

# 溢出槽位比例阈值：低于 5%
OVERFLOW_RATE_LIMIT = 0.05


class OverflowHit(BaseModel):
    density: str
    theme_id: str
    slide_id: str
    layout_id: str
    slot_id: str
    message: str


class ThemeMismatch(BaseModel):
    density: str
    detail: str


class ComboResult(BaseModel):
    density: str
    theme_id: str
    slide_count: int
    verify_passed: bool
    verify_issue_count: int
    verify_messages: list[str] = Field(default_factory=list)
    measurable_slots: int
    overflow_slots: int
    fonts_precise: bool


class RegressionReport(BaseModel):
    fonts_precise: bool
    combo_count: int
    verify_pass_count: int
    verify_total: int
    measurable_slots: int
    overflow_slots: int
    overflow_rate: float
    overflow_hits: list[OverflowHit] = Field(default_factory=list)
    theme_mismatches: list[ThemeMismatch] = Field(default_factory=list)
    combos: list[ComboResult] = Field(default_factory=list)

    @property
    def verify_pass_rate(self) -> float:
        if self.verify_total == 0:
            return 1.0
        return self.verify_pass_count / self.verify_total

    @property
    def passed(self) -> bool:
        return (
            self.verify_pass_count == self.verify_total
            and self.overflow_rate < OVERFLOW_RATE_LIMIT
            and not self.theme_mismatches
        )


@dataclass
class _Accumulator:
    fonts_precise: bool = True
    verify_pass_count: int = 0
    verify_total: int = 0
    measurable_slots: int = 0
    overflow_slots: int = 0
    overflow_hits: list[OverflowHit] = field(default_factory=list)
    theme_mismatches: list[ThemeMismatch] = field(default_factory=list)
    combos: list[ComboResult] = field(default_factory=list)


def content_fingerprint(deck: Deck) -> list[tuple]:
    """页序、块 id 与文字内容指纹；主题切换后必须完全一致。"""
    rows: list[tuple] = []
    for slide in deck.slides:
        blocks: list[tuple] = []
        for block in slide.blocks:
            blocks.append((block.id, block.slot_id, block.type, _block_payload(block)))
        rows.append((slide.id, slide.layout_id, tuple(blocks)))
    return rows


def _block_payload(block: Block) -> tuple:
    match block.type:
        case "text":
            return (block.text,)
        case "bullets":
            return tuple(block.items)
        case "kpi":
            return (block.value, block.label, block.note)
        case "table":
            return (tuple(block.header), tuple(tuple(row) for row in block.rows))
        case "chart":
            return (
                block.chart_type,
                tuple(block.categories),
                tuple((item.name, tuple(item.values)) for item in block.series),
                block.unit,
            )
        case "image":
            return (block.source, block.alt, block.url, block.credit)
        case _:
            return ()


def count_measurable_slots(deck: Deck) -> int:
    """可做文字溢出度量的槽位数（text/bullets 且布局声明了 text_style）。"""
    total = 0
    for slide in deck.slides:
        try:
            placements = placed_by_block_id(slide)
        except KeyError:
            continue
        for block in slide.blocks:
            if block.type not in {"text", "bullets"}:
                continue
            placed = placements.get(block.id)
            if placed is not None and placed.text_style is not None:
                total += 1
    return total


def run_regression(
    *,
    densities: Iterable[str] | None = None,
    theme_ids: Iterable[str] | None = None,
) -> RegressionReport:
    selected_densities = tuple(densities) if densities is not None else DENSITIES
    themes = list(theme_ids) if theme_ids is not None else sorted(load_themes())
    corpus = load_corpus_decks()
    acc = _Accumulator(fonts_precise=fonts_available())

    for density in selected_densities:
        base = corpus[density]
        fingerprints: dict[str, list[tuple]] = {}
        page_counts: dict[str, int] = {}

        for theme_id in themes:
            deck = base.model_copy(update={"theme_id": theme_id})
            fingerprints[theme_id] = content_fingerprint(deck)

            buffer = render_deck_to_pptx(deck, theme_id)
            pptx_bytes = buffer.getvalue()
            verify = verify_pptx(pptx_bytes, deck)
            export = run_export_check(deck)

            acc.fonts_precise = acc.fonts_precise and export.fonts_precise
            acc.verify_total += 1
            if verify.passed:
                acc.verify_pass_count += 1

            measurable = count_measurable_slots(deck)
            overflow_issues = [
                issue
                for issue in export.issues
                if issue.slot_id is not None and "溢出槽位" in issue.message
            ]
            acc.measurable_slots += measurable
            acc.overflow_slots += len(overflow_issues)
            for issue in overflow_issues:
                slide = deck.slide_by_id(issue.slide_id)
                acc.overflow_hits.append(
                    OverflowHit(
                        density=density,
                        theme_id=theme_id,
                        slide_id=issue.slide_id,
                        layout_id=slide.layout_id if slide else "",
                        slot_id=issue.slot_id or "",
                        message=issue.message,
                    )
                )

            page_counts[theme_id] = len(deck.slides)
            acc.combos.append(
                ComboResult(
                    density=density,
                    theme_id=theme_id,
                    slide_count=len(deck.slides),
                    verify_passed=verify.passed,
                    verify_issue_count=len(verify.issues),
                    verify_messages=[
                        f"[{item.check}] {item.message}" for item in verify.issues[:12]
                    ],
                    measurable_slots=measurable,
                    overflow_slots=len(overflow_issues),
                    fonts_precise=export.fonts_precise,
                )
            )

        reference_theme = themes[0]
        reference_fp = fingerprints[reference_theme]
        reference_pages = page_counts[reference_theme]
        for theme_id in themes[1:]:
            if page_counts[theme_id] != reference_pages:
                acc.theme_mismatches.append(
                    ThemeMismatch(
                        density=density,
                        detail=(
                            f"主题 {theme_id} 页数为 {page_counts[theme_id]}，"
                            f"与 {reference_theme} 的 {reference_pages} 不一致"
                        ),
                    )
                )
            if fingerprints[theme_id] != reference_fp:
                acc.theme_mismatches.append(
                    ThemeMismatch(
                        density=density,
                        detail=(
                            f"主题 {theme_id} 与 {reference_theme} 的内容指纹不一致"
                            f"（页序/块 id/文字被改变）"
                        ),
                    )
                )

    rate = (acc.overflow_slots / acc.measurable_slots) if acc.measurable_slots else 0.0
    return RegressionReport(
        fonts_precise=acc.fonts_precise,
        combo_count=len(acc.combos),
        verify_pass_count=acc.verify_pass_count,
        verify_total=acc.verify_total,
        measurable_slots=acc.measurable_slots,
        overflow_slots=acc.overflow_slots,
        overflow_rate=rate,
        overflow_hits=acc.overflow_hits,
        theme_mismatches=acc.theme_mismatches,
        combos=acc.combos,
    )


def format_report(report: RegressionReport) -> str:
    """中文可读报告。"""
    lines: list[str] = []
    lines.append("=== LuxUmbra Slides 固定回归集报告 ===")
    lines.append(
        f"度量路径：{'精确（Noto 字体就绪）' if report.fonts_precise else '估算（度量字体缺失）'}"
    )
    lines.append(f"组合数：{report.combo_count}（语料密度 × 主题）")
    lines.append(
        f"可编辑性通过率：{report.verify_pass_count}/{report.verify_total}"
        f"（{report.verify_pass_rate:.0%}）"
        f"　要求 100%"
    )
    lines.append(
        f"溢出槽位：{report.overflow_slots}/{report.measurable_slots}"
        f"（{report.overflow_rate:.2%}）"
        f"　要求 < {OVERFLOW_RATE_LIMIT:.0%}"
    )
    lines.append(f"主题内容一致性：{'通过' if not report.theme_mismatches else '失败'}")
    lines.append(f"总评：{'通过' if report.passed else '未通过'}")
    lines.append("")
    lines.append("--- 各组合明细 ---")
    for combo in report.combos:
        status = "OK" if combo.verify_passed and combo.overflow_slots == 0 else "!!"
        lines.append(
            f"[{status}] {combo.density}/{combo.theme_id}："
            f"页数 {combo.slide_count}，"
            f"可编辑性 {'通过' if combo.verify_passed else f'失败({combo.verify_issue_count})'}，"
            f"溢出 {combo.overflow_slots}/{combo.measurable_slots}，"
            f"度量 {'精确' if combo.fonts_precise else '估算'}"
        )
        for message in combo.verify_messages:
            lines.append(f"      可编辑性：{message}")

    if report.overflow_hits:
        lines.append("")
        lines.append("--- 溢出槽位明细 ---")
        for hit in report.overflow_hits:
            lines.append(
                f"- {hit.density}/{hit.theme_id} "
                f"布局={hit.layout_id} 页={hit.slide_id} 槽={hit.slot_id}：{hit.message}"
            )

    if report.theme_mismatches:
        lines.append("")
        lines.append("--- 主题一致性问题 ---")
        for item in report.theme_mismatches:
            lines.append(f"- {item.density}：{item.detail}")

    return "\n".join(lines) + "\n"
