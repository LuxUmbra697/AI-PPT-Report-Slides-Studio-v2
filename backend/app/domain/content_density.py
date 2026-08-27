"""文字量三档与页型角色：供大纲/正文 prompt 与充实度 QA 共用。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

ContentDensity = Literal["concise", "medium", "detailed"]
PageRole = Literal["cover", "toc", "section", "content", "summary"]

PAGE_ROLES: tuple[PageRole, ...] = ("cover", "toc", "section", "content", "summary")

DEFAULT_CONTENT_DENSITY: ContentDensity = "medium"
DEFAULT_PAGE_ROLE: PageRole = "content"

# 空话 / 占位（prompt 禁写 + QA 检出）
EMPTY_PHRASE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"本页介绍"),
    re.compile(r"待补充"),
    re.compile(r"xxxx+", re.IGNORECASE),
    re.compile(r"lorem\s*ipsum", re.IGNORECASE),
    re.compile(r"placeholder", re.IGNORECASE),
    re.compile(r"这里填写"),
    re.compile(r"内容稍后"),
    re.compile(r"暂无内容"),
)


@dataclass(frozen=True)
class DensityProfile:
    """单档写作目标（内容页基准；封面/目录会再下调）。"""

    id: ContentDensity
    label: str
    min_blocks: int
    max_blocks: int
    target_bullets: tuple[int, int]
    min_chars_per_bullet: int
    max_chars_per_bullet: int
    prefer_block_mix: str
    prompt_hint: str


PROFILES: dict[ContentDensity, DensityProfile] = {
    "concise": DensityProfile(
        id="concise",
        label="简洁",
        min_blocks=3,
        max_blocks=4,
        target_bullets=(2, 3),
        min_chars_per_bullet=12,
        max_chars_per_bullet=40,
        prefer_block_mix="kicker + 标题 + 要点，可选配图或 callout",
        prompt_hint="克制篇幅：每条要点一句说清结论，避免铺陈。",
    ),
    "medium": DensityProfile(
        id="medium",
        label="中等",
        min_blocks=4,
        max_blocks=6,
        target_bullets=(3, 4),
        min_chars_per_bullet=18,
        max_chars_per_bullet=56,
        prefer_block_mix="kicker + 标题 + 引言/要点 + KPI、cards 或配图至少一类",
        prompt_hint="均衡充实：结论 + 支撑细节，多用具体事实与机制说明。",
    ),
    "detailed": DensityProfile(
        id="detailed",
        label="详细",
        min_blocks=5,
        max_blocks=8,
        target_bullets=(4, 6),
        min_chars_per_bullet=22,
        max_chars_per_bullet=72,
        prefer_block_mix="kicker + 标题 + 引言 + cards/双栏要点 + KPI 或表/图 + 可选 callout",
        prompt_hint="信息更满：展开论证、对比或步骤，可含表格/图表（有数据时）。",
    ),
}

_ROLE_HINTS: dict[PageRole, str] = {
    "cover": "封面：大标题 + 一句副标题/场合信息即可，块数宜少，勿堆要点列表。",
    "toc": "目录：列出 3–6 个章节标题，可带一行短说明，结构清晰可扫读。",
    "section": "章节分隔：章节名 + 可选一句过渡，极简，勿展开正文。",
    "content": (
        "内容页：信息层级为 kicker（caption，≤6 字主题标签）→ 大标题 → "
        "可选引言（subtitle，一句话）→ 内容区（cards/要点/KPI/图/表）；"
        "一页一主信息，用多个内容块支撑。"
    ),
    "summary": (
        "总结页：收束结论 + 可执行下一步；可用要点、KPI 或 note callout 收束，避免新开话题。"
    ),
}


def normalize_density(value: str | None) -> ContentDensity:
    if value in PROFILES:
        return value  # type: ignore[return-value]
    return DEFAULT_CONTENT_DENSITY


def normalize_page_role(value: str | None) -> PageRole:
    if value in PAGE_ROLES:
        return value  # type: ignore[return-value]
    return DEFAULT_PAGE_ROLE


def get_profile(density: str | None) -> DensityProfile:
    return PROFILES[normalize_density(density)]


def role_writing_hint(role: str | None) -> str:
    return _ROLE_HINTS[normalize_page_role(role)]


def effective_block_targets(density: str | None, role: str | None) -> tuple[int, int]:
    """按页型下调封面/目录/分隔的块数目标。"""
    profile = get_profile(density)
    page_role = normalize_page_role(role)
    if page_role in {"cover", "section"}:
        return (2, 3)
    if page_role == "toc":
        return (2, 4)
    if page_role == "summary":
        lo = max(3, profile.min_blocks - 1)
        hi = max(lo, profile.max_blocks - 1)
        return (lo, hi)
    return (profile.min_blocks, profile.max_blocks)


def density_prompt_block(density: str | None, role: str | None) -> str:
    """写入单页 user/system 的密度与角色约束段落。"""
    profile = get_profile(density)
    page_role = normalize_page_role(role)
    min_blocks, max_blocks = effective_block_targets(density, role)
    b_lo, b_hi = profile.target_bullets
    lines = [
        f"文字量档位：{profile.label}（{profile.id}）。{profile.prompt_hint}",
        f"页型角色：{page_role}。{role_writing_hint(page_role)}",
        f"内容块数量目标：{min_blocks}–{max_blocks} 个；推荐组合：{profile.prefer_block_mix}。",
        f"要点条目目标：{b_lo}–{b_hi} 条；每条约 {profile.min_chars_per_bullet}–"
        f"{profile.max_chars_per_bullet} 字，写具体结论与事实。",
        "用 key_points 展开论证，不要复述标题；禁止「本页介绍……」「待补充」等空话。",
        "在槽位/画布容量上限内尽量贴近目标中上沿，不要为了「少写」而留下空洞页面。",
        "数字须来自给定来源；缺数据时用定性机制、对比或步骤充实，禁止编造数字。",
    ]
    if page_role == "content":
        lines.append(
            "内容页必须有 kicker：单独 text 块，text_style=caption，不超过 6 字；"
            "可选 lead 引言：text 块，text_style=subtitle，一句话。"
        )
    if page_role == "content" and profile.id in {"medium", "detailed"}:
        lines.append(
            "禁止仅输出「标题 + 一段正文」两块；至少包含要点列表或 cards，"
            "并尽量再加 KPI/图/表/callout 之一。"
        )
    return "\n".join(lines)


def contains_empty_phrase(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return any(pattern.search(stripped) for pattern in EMPTY_PHRASE_PATTERNS)


def outline_density_hint(density: str | None) -> str:
    profile = get_profile(density)
    if profile.id == "concise":
        return "文字量偏简洁：每页 key_points 抓住核心结论，短而具体。"
    if profile.id == "detailed":
        return "文字量偏详细：每页 key_points 写可展开的事实/数据线索/对比维度，避免空泛主题词。"
    return "文字量中等：每页 key_points 写可展开的具体结论，便于正文充实。"
