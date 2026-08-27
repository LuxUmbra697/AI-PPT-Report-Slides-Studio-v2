"""固定回归集核心断言。

字体缺失时跳过「溢出率 < 5%」的精确阈值，避免门禁依赖未提交的字体文件；
可编辑性 100% 与主题内容一致性不依赖字体，始终检查。
"""

from __future__ import annotations

from app.domain.layout import load_layouts
from app.domain.text_metrics import fonts_available
from app.domain.theme import load_themes
from app.regression.corpus import DENSITIES, load_corpus_decks
from app.regression.runner import (
    OVERFLOW_RATE_LIMIT,
    content_fingerprint,
    run_regression,
)


def test_corpus_covers_all_layouts_and_block_types() -> None:
    decks = load_corpus_decks()
    assert set(decks) == set(DENSITIES)
    all_layouts = set(load_layouts())
    seen_types: set[str] = set()
    for density, deck in decks.items():
        used = {slide.layout_id for slide in deck.slides}
        assert used == all_layouts, f"{density} 未覆盖全部布局：{sorted(all_layouts - used)}"
        for slide in deck.slides:
            for block in slide.blocks:
                seen_types.add(block.type)
    assert seen_types >= {"text", "bullets", "image", "chart", "table", "kpi"}


def test_theme_switch_keeps_content_fingerprint() -> None:
    decks = load_corpus_decks()
    themes = sorted(load_themes())
    for density, base in decks.items():
        fingerprints = [
            content_fingerprint(base.model_copy(update={"theme_id": theme_id}))
            for theme_id in themes
        ]
        assert len({tuple(fp) for fp in fingerprints}) == 1, density


def test_regression_editability_and_overflow_gate() -> None:
    report = run_regression()
    assert report.verify_pass_count == report.verify_total, "可编辑性未达 100%：\n" + "\n".join(
        f"{c.density}/{c.theme_id}: {c.verify_messages}"
        for c in report.combos
        if not c.verify_passed
    )
    assert not report.theme_mismatches, report.theme_mismatches

    if not fonts_available():
        # 估算路径下溢出判定可能偏严/偏松，不拿 5% 硬阈值卡死本地无字体环境
        return

    assert report.fonts_precise is True
    assert report.overflow_rate < OVERFLOW_RATE_LIMIT, (
        f"溢出率 {report.overflow_rate:.2%} 未低于 {OVERFLOW_RATE_LIMIT:.0%}："
        + "; ".join(
            f"{h.density}/{h.theme_id}/{h.layout_id}.{h.slot_id}" for h in report.overflow_hits
        )
    )
