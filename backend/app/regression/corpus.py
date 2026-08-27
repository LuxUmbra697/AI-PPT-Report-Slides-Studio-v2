"""加载手写固定回归语料。

语料放在 backend/regression/corpus/，与单元测试 fixtures 分开：
它既是 make regression 门禁输入，也被 pytest 断言复用，属于一等公民回归资产。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.core.paths import REPO_ROOT
from app.domain.content import Deck
from app.domain.layout import load_layouts

CORPUS_DIR = REPO_ROOT / "backend" / "regression" / "corpus"
DENSITIES = ("full", "short")


@lru_cache
def load_corpus_decks() -> dict[str, Deck]:
    """返回 density → Deck；每份语料覆盖全部布局。"""
    decks: dict[str, Deck] = {}
    for density in DENSITIES:
        path = CORPUS_DIR / f"{density}.json"
        deck = Deck.model_validate(json.loads(path.read_text(encoding="utf-8")))
        _assert_layout_coverage(deck, path)
        decks[density] = deck
    return decks


def _assert_layout_coverage(deck: Deck, path: Path) -> None:
    used = {slide.layout_id for slide in deck.slides}
    missing = set(load_layouts()) - used
    if missing:
        raise ValueError(f"回归语料 {path.name} 未覆盖布局：{sorted(missing)}")
