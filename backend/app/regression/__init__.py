"""固定回归集：语料加载与指标计算，供脚本与 pytest 共用。"""

from app.regression.corpus import CORPUS_DIR, DENSITIES, load_corpus_decks
from app.regression.runner import (
    OVERFLOW_RATE_LIMIT,
    RegressionReport,
    content_fingerprint,
    run_regression,
)

__all__ = [
    "CORPUS_DIR",
    "DENSITIES",
    "OVERFLOW_RATE_LIMIT",
    "RegressionReport",
    "content_fingerprint",
    "load_corpus_decks",
    "run_regression",
]
