import json
from functools import lru_cache

from app.core.paths import SHARED_DIR
from app.domain.content import Deck

SAMPLE_DECK_PATH = SHARED_DIR / "sample-deck.json"


@lru_cache
def load_sample_deck() -> Deck:
    """覆盖全部布局与全部内容块类型的示例文稿。

    它同时充当三个角色：Web 渲染的演示数据、PPTX 导出的验证输入、
    以及溢出回归集的种子，因此必须保持对布局的完整覆盖。
    """
    return Deck.model_validate(json.loads(SAMPLE_DECK_PATH.read_text(encoding="utf-8")))
