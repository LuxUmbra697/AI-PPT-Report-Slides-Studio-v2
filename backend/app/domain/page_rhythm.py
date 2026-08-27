"""跨页节奏：按页序确定性分配版式骨架与 callout 配额。

各页是并发生成的，页间看不到彼此用了什么版式，所以"这份稿子不要十页长得
一样"这件事没法交给模型自觉，只能在派发之前分配好。

用 position 取模而不是随机：单页重试时算出来的还是同一份分配，重来一次
不会把这一页的版面换成另一副样子。
"""

from __future__ import annotations

# 内容页骨架轮换池。每条都是一句给模型的硬约束，说清块的组合与横向切分方式。
_CONTENT_SKELETONS = (
    "左文右卡：最外层 row 切两栏，左栏放标题与 bullets，右栏放 2–3 张 cards",
    "全宽要点：最外层 column，标题在上、bullets 在下铺满整幅，不切栏",
    "指标排布：标题在上，下面一个 row 并排 3 个 kpi，再补一段 text 做解读",
    "步骤推进：标题在上，下面用 cards 表达 3–4 个有先后关系的步骤",
    "表格对照：标题在上，下面一个 table 做横向对比，再补一句 text 给结论",
)

# 配图页固定走图文并列：配图必须占住一整栏，才不会被挤成窄条。
_VISUAL_SKELETON = "图文并列：最外层 row 切两栏，一栏放 image，另一栏放标题与要点"

# callout 每几页放行一次。它是强调，出现在每一页就不再是强调。
CALLOUT_EVERY = 3


def skeleton_hint(position: int, *, page_role: str, has_visual: bool) -> str | None:
    """本页该用的版式骨架。

    封面/目录/章节/总结页的版面由页型本身决定，不参与轮换，返回 None。
    """
    if page_role != "content":
        return None
    if has_visual:
        return _VISUAL_SKELETON
    return _CONTENT_SKELETONS[position % len(_CONTENT_SKELETONS)]


def allows_callout(position: int) -> bool:
    return position % CALLOUT_EVERY == 0
