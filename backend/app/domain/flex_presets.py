"""加载 flex 预设树，并按当前块列表做 best-effort 适配。"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from pydantic import BaseModel

from app.core.paths import SHARED_DIR
from app.domain.flex_layout import FlexContainer, FlexLeaf, FlexNode
from app.domain.flex_normalize import normalize

PRESETS_DIR = SHARED_DIR / "flex-presets"

# 预设叶子 block_id 暗示的类型偏好（用于匹配真实块）
_ROLE_TYPE_HINTS: dict[str, tuple[str, ...]] = {
    "title": ("text",),
    "kicker": ("text",),
    "lead": ("text",),
    "body": ("bullets", "text", "table", "cards"),
    "body_left": ("bullets", "text", "cards"),
    "body_right": ("bullets", "text", "cards"),
    "cards": ("cards",),
    "callout": ("callout",),
    "note": ("callout",),
    "source": ("callout",),
    "image": ("image", "chart"),
    "visual": ("image", "chart"),
    "kpi_1": ("kpi",),
    "kpi_2": ("kpi",),
    "kpi_3": ("kpi",),
    "kpi": ("kpi",),
}

_TYPE_TEXT_STYLE: dict[str, str | None] = {
    "text": "body",
    "bullets": "bullet",
    "kpi": None,
    "image": None,
    "chart": None,
    "table": None,
    "cards": None,
    "callout": None,
}


class FlexPreset(BaseModel):
    id: str
    name: str
    description: str = ""
    tree: FlexContainer
    expected_rects: dict[str, Any] | None = None


class BlockRef(BaseModel):
    """适配时只需要块 id 与类型。"""

    id: str
    type: str


@lru_cache(maxsize=4)
def load_presets() -> tuple[FlexPreset, ...]:
    if not PRESETS_DIR.is_dir():
        return ()
    presets: list[FlexPreset] = []
    for path in sorted(PRESETS_DIR.glob("*.json")):
        # 跳过 golden* 回归样本，不进入生产预设池
        if path.name.startswith("golden"):
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        presets.append(FlexPreset.model_validate(raw))
    return tuple(presets)


def pick_preset_for_blocks(
    blocks: list[BlockRef],
    *,
    page_role: str | None = None,
    key_points: list[str] | None = None,
) -> FlexPreset | None:
    """按块类型组成与语义信号挑选最合适的预设。"""
    presets = list(load_presets())
    if not presets:
        return None
    types = {block.type for block in blocks}
    scored: list[tuple[int, FlexPreset]] = []
    for preset in presets:
        score = _score_preset(
            preset,
            types,
            len(blocks),
            page_role=page_role,
            key_points=key_points,
        )
        scored.append((score, preset))
    scored.sort(key=lambda item: (-item[0], item[1].id))
    return scored[0][1]


def adapt_preset_to_blocks(
    tree: FlexContainer,
    blocks: list[BlockRef],
) -> FlexContainer:
    """把预设树的叶子改写为给定块 id；多余叶子删除，未放入的块追加到根下。"""
    if not blocks:
        raise ValueError("至少需要一个内容块")

    remaining = list(blocks)
    adapted = _remap_node(tree, remaining)
    # 未匹配到的块挂到根容器末尾
    children = list(adapted.children)
    for block in remaining:
        children.append(
            FlexLeaf(
                id=f"leaf-{block.id}",
                block_id=block.id,
                grow=1.0,
                text_style=_text_style_for(block),
            )
        )
    result = adapted.model_copy(update={"children": children})
    return normalize(result)


def seed_layout_for_blocks(
    blocks: list[BlockRef],
    *,
    page_role: str | None = None,
    key_points: list[str] | None = None,
) -> FlexContainer:
    """从预设池选出一棵树并适配到当前块。"""
    preset = pick_preset_for_blocks(
        blocks, page_role=page_role, key_points=key_points
    )
    if preset is None:
        return normalize(
            FlexContainer(
                type="column",
                id="root",
                children=[
                    FlexLeaf(
                        id=f"leaf-{block.id}",
                        block_id=block.id,
                        grow=0.5 if block.type == "text" else 1.0,
                        text_style=_text_style_for(block),
                    )
                    for block in blocks
                ],
            )
        )
    return adapt_preset_to_blocks(preset.tree, blocks)


def alternate_preset_trees(
    blocks: list[BlockRef],
    *,
    exclude_tree: FlexContainer | None = None,
    limit: int = 1,
) -> list[FlexContainer]:
    """返回若干与当前树不同的预设适配结果。"""
    current_sig = _tree_signature(exclude_tree) if exclude_tree is not None else None
    results: list[FlexContainer] = []
    for preset in load_presets():
        adapted = adapt_preset_to_blocks(preset.tree, list(blocks))
        if current_sig is not None and _tree_signature(adapted) == current_sig:
            continue
        results.append(adapted)
        if len(results) >= limit:
            break
    return results


_STEP_KEYWORDS = ("步骤", "流程", "清单", "方法", "怎么做", "如何")
_TIMELINE_KEYWORDS = ("阶段", "时间", "里程碑", "路线", "演进", "历程", "节奏")


def _score_preset(
    preset: FlexPreset,
    types: set[str],
    block_count: int,
    *,
    page_role: str | None = None,
    key_points: list[str] | None = None,
) -> int:
    leaf_roles = _collect_roles(preset.tree)
    leaf_count = len(leaf_roles)
    preset_skins = _collect_presets(preset.tree)
    score = 0
    if "image" in types and any(role in ("image", "visual") for role in leaf_roles):
        score += 3
    if "chart" in types and any(role in ("image", "visual") for role in leaf_roles):
        score += 2
    if "kpi" in types and any(role.startswith("kpi") for role in leaf_roles):
        score += 3
    if "bullets" in types and any(role.startswith("body") for role in leaf_roles):
        score += 2
    if "cards" in types and any(role == "cards" or "cards" in role for role in leaf_roles):
        score += 4
    if "callout" in types and any(
        role in ("callout", "note", "source") for role in leaf_roles
    ):
        score += 3
    # 叶子数接近加分；多块页面偏好更密预设
    score -= abs(leaf_count - block_count) * 2
    if block_count >= 4 and leaf_count >= 4:
        score += 2
    if block_count >= 5 and leaf_count >= 5:
        score += 2

    # 语义信号：步骤/时间类文案加权对应皮肤预设
    blob = " ".join(key_points or [])
    if any(word in blob for word in _STEP_KEYWORDS) and "numbered_steps" in preset_skins:
        score += 4
    if any(word in blob for word in _TIMELINE_KEYWORDS) and "timeline" in preset_skins:
        score += 4
    if page_role == "summary" and "callout" in types:
        score += 1
    if page_role == "content" and "kicker" in leaf_roles and "text" in types:
        score += 1
    return score


def _collect_presets(node: FlexNode) -> set[str]:
    if isinstance(node, FlexLeaf):
        return set()
    found: set[str] = set()
    if node.preset is not None:
        found.add(node.preset)
    for child in node.children:
        found |= _collect_presets(child)
    return found


def _collect_roles(node: FlexNode) -> list[str]:
    if isinstance(node, FlexLeaf):
        return [node.block_id]
    roles: list[str] = []
    for child in node.children:
        roles.extend(_collect_roles(child))
    return roles


def _remap_node(node: FlexNode, remaining: list[BlockRef]) -> FlexNode:
    if isinstance(node, FlexLeaf):
        match = _claim_block(node.block_id, remaining)
        if match is None:
            # 空 id 叶子由父级过滤
            return node.model_copy(update={"block_id": ""})
        return FlexLeaf(
            id=f"leaf-{match.id}",
            block_id=match.id,
            grow=node.grow,
            text_style=node.text_style or _text_style_for(match),
        )

    children: list[FlexNode] = []
    for child in node.children:
        remapped = _remap_node(child, remaining)
        if isinstance(remapped, FlexLeaf) and remapped.block_id == "":
            continue
        if isinstance(remapped, FlexContainer) and not remapped.children:
            continue
        children.append(remapped)
    return node.model_copy(update={"children": children})


def _claim_block(role: str, remaining: list[BlockRef]) -> BlockRef | None:
    hints = _ROLE_TYPE_HINTS.get(role, ())
    for preferred in hints:
        for index, block in enumerate(remaining):
            if block.type == preferred:
                return remaining.pop(index)
    # 角色名与类型对不上时，按常见语义再试：title→text，其余取第一个
    if role == "title":
        for index, block in enumerate(remaining):
            if block.type == "text":
                return remaining.pop(index)
    if remaining:
        return remaining.pop(0)
    return None


def _text_style_for(block: BlockRef) -> str | None:
    lower = block.id.lower()
    if block.type == "text":
        if "kicker" in lower or "eyebrow" in lower:
            return "caption"
        if "lead" in lower or "subtitle" in lower:
            return "subtitle"
        if "title" in lower or lower.endswith("-title") or lower == "title":
            return "title"
    return _TYPE_TEXT_STYLE.get(block.type)


def _tree_signature(tree: FlexContainer) -> str:
    """结构签名：忽略叶子 id，保留方向与叶子顺序类型占位。"""

    def walk(node: FlexNode) -> Any:
        if isinstance(node, FlexLeaf):
            return ("block",)
        return (node.type, [walk(child) for child in node.children], node.ratios)

    return json.dumps(walk(tree), ensure_ascii=False)
