"""HTML 展示样式的安全 AI 适配。

这里的模型只可选择有限的视觉令牌。用户提示绝不会原样拼接成 CSS、HTML 或
JavaScript，因此 HTML 导出仍是可离线打开、可控且无脚本注入面的单文件。
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.domain.theme import Theme
from app.llm.client import StructuredChatClient, create_chat_model

logger = logging.getLogger(__name__)

HtmlLayout = Literal["editorial", "bento", "magazine", "timeline", "minimal"]
HtmlMotion = Literal["soft", "energetic", "none"]
HtmlPattern = Literal["none", "grid", "dots", "waves", "sparkles"]
HtmlDensity = Literal["airy", "balanced", "compact"]
HtmlCorners = Literal["soft", "sharp", "pill"]
HtmlPalette = Literal["theme", "anime", "revolution", "cyber", "ink", "pastel", "dunhuang"]


class HtmlStyleProfile(BaseModel):
    """可直接投射为 CSS class 的白名单展示令牌。"""

    layout: HtmlLayout = "editorial"
    motion: HtmlMotion = "soft"
    pattern: HtmlPattern = "grid"
    density: HtmlDensity = "balanced"
    corners: HtmlCorners = "soft"
    # 主题提示词可明确要求一套与 PPT 基础主题无关的 HTML 调色板；它仍是有限枚举，
    # 不把用户输入直接当作 CSS。
    palette: HtmlPalette = "theme"
    mood: str = Field(default="主题自适应展示", max_length=48)


def default_html_style(theme: Theme, prompt: str | None = None) -> HtmlStyleProfile:
    """无模型或模型不可用时仍根据主题与提示词稳定适配。"""

    family = theme.visual.family.lower()
    profile = HtmlStyleProfile(
        layout={
            "dashboard": "bento",
            "magazine": "magazine",
            "panel": "bento",
            "notebook": "editorial",
        }.get(theme.visual.content_variant, "editorial"),
        motion="none" if theme.visual.transition == "none" else "soft",
        pattern=(
            "sparkles"
            if any(key in family for key in ("anime", "sakura", "fox", "shrine"))
            else "grid"
        ),
        density="balanced",
        corners="soft" if theme.shape.radius_pt >= 10 else "sharp",
        mood=f"{theme.name}自适应展示",
    )
    text = (prompt or "").lower()
    if any(word in text for word in ("敦煌", "莫高窟", "飞天", "壁画")):
        (
            profile.layout,
            profile.motion,
            profile.pattern,
            profile.corners,
            profile.palette,
            profile.mood,
        ) = (
            "magazine",
            "soft",
            "waves",
            "soft",
            "dunhuang",
            "敦煌壁画叙事展示",
        )
    elif any(word in text for word in ("革命", "红色", "党建", "党史", "中国红")):
        (
            profile.layout,
            profile.motion,
            profile.pattern,
            profile.corners,
            profile.palette,
            profile.mood,
        ) = (
            "timeline",
            "energetic",
            "waves",
            "sharp",
            "revolution",
            "红色革命叙事展示",
        )
    elif any(word in text for word in ("科技", "赛博", "未来", "neon", "cyber")) and not any(
        word in text for word in ("二次元", "动漫", "可爱", "魔法", "偶像")
    ):
        profile.layout, profile.motion, profile.pattern, profile.palette, profile.mood = (
            "bento",
            "energetic",
            "grid",
            "cyber",
            "科技感动态展示",
        )
    elif any(word in text for word in ("二次元", "动漫", "可爱", "魔法", "偶像")):
        (
            profile.layout,
            profile.motion,
            profile.pattern,
            profile.corners,
            profile.palette,
            profile.mood,
        ) = (
            "bento",
            "energetic",
            "sparkles",
            "pill",
            "anime",
            "二次元舞台展示",
        )
    elif any(word in text for word in ("古风", "国风", "中国风", "水墨")):
        profile.layout, profile.motion, profile.pattern, profile.palette, profile.mood = (
            "editorial",
            "soft",
            "waves",
            "ink",
            "国风卷轴展示",
        )
    elif any(word in text for word in ("极简", "留白", "minimal")):
        (
            profile.layout,
            profile.motion,
            profile.pattern,
            profile.density,
            profile.palette,
            profile.mood,
        ) = (
            "minimal",
            "soft",
            "none",
            "airy",
            "pastel",
            "极简留白展示",
        )
    elif any(word in text for word in ("杂志", "画册", "editorial")):
        profile.layout, profile.pattern, profile.mood = "magazine", "dots", "杂志画册展示"
    elif any(word in text for word in ("时间线", "历程", "路线图")):
        profile.layout, profile.mood = "timeline", "时间线叙事展示"
    return profile


def resolve_html_style(
    theme: Theme,
    prompt: str | None,
    saved: dict | HtmlStyleProfile | None,
) -> HtmlStyleProfile:
    """合并已保存的 AI 选择与用户明确写出的视觉意图。

    例如用户写“革命风”时，不能因为默认主题恰好是米白色，就让一次模型采样把
    红色叙事覆盖回商务风。明确提示优先于基础主题和模型的自由裁量。
    """

    intent = default_html_style(theme, prompt)
    if isinstance(saved, HtmlStyleProfile):
        profile = saved
    elif saved:
        profile = HtmlStyleProfile.model_validate(saved)
    else:
        profile = intent
    if intent.palette == "theme":
        return profile
    return profile.model_copy(
        update={
            "layout": intent.layout,
            "motion": intent.motion,
            "pattern": intent.pattern,
            "corners": intent.corners,
            "palette": intent.palette,
            "mood": intent.mood,
        }
    )


def html_palette(theme: Theme, profile: HtmlStyleProfile) -> dict[str, str]:
    """把安全的色板 token 映射为 CSS 变量，保留主题字体而不复用错误的商务配色。"""

    base = {
        "background": theme.palette.background,
        "surface": theme.palette.surface,
        "ink": theme.palette.ink,
        "ink_soft": theme.palette.ink_soft,
        "accent": theme.palette.accent,
        "accent_soft": theme.palette.accent_soft,
        "line": theme.palette.line,
    }
    palettes = {
        "anime": {
            "background": "#120d2f",
            "surface": "#21184c",
            "ink": "#fff8ff",
            "ink_soft": "#d9d0ff",
            "accent": "#ff72bd",
            "accent_soft": "#8d78ff",
            "line": "#5c4d91",
        },
        "revolution": {
            "background": "#2b060b",
            "surface": "#4a0b11",
            "ink": "#fff5de",
            "ink_soft": "#f2cfa6",
            "accent": "#ffd05b",
            "accent_soft": "#c72231",
            "line": "#87313a",
        },
        "cyber": {
            "background": "#071323",
            "surface": "#0d2035",
            "ink": "#e9fbff",
            "ink_soft": "#a9cce4",
            "accent": "#43e8ff",
            "accent_soft": "#8b5cff",
            "line": "#20506d",
        },
        "ink": {
            "background": "#f5f0e4",
            "surface": "#fffdf7",
            "ink": "#27231d",
            "ink_soft": "#625a4e",
            "accent": "#a33e2e",
            "accent_soft": "#c7d6cc",
            "line": "#cfc4b2",
        },
        "pastel": {
            "background": "#fff8fc",
            "surface": "#ffffff",
            "ink": "#392d4e",
            "ink_soft": "#746684",
            "accent": "#9e6cff",
            "accent_soft": "#ffc6e5",
            "line": "#eadcf4",
        },
        "dunhuang": {
            "background": "#21130f",
            "surface": "#3b2118",
            "ink": "#fff0cf",
            "ink_soft": "#e7bb82",
            "accent": "#e56e3c",
            "accent_soft": "#1b8c92",
            "line": "#81533a",
        },
    }
    return {**base, **palettes.get(profile.palette, {})}


async def generate_html_style(theme: Theme, prompt: str | None) -> HtmlStyleProfile:
    """调用 DeepSeek 作审美选择；失败时回落到本地规则而不影响生成。"""

    fallback = default_html_style(theme, prompt)
    settings = get_settings()
    if not settings.llm_api_key.strip():
        return fallback

    try:
        result = await StructuredChatClient(
            model=create_chat_model(settings), api_key=settings.llm_api_key
        ).complete(
            HtmlStyleProfile,
            system=(
                "你是网页报告艺术指导。根据主题配色、版式气质和用户要求，为单文件 HTML "
                "报告选择安全的离散视觉令牌。只返回符合 JSON Schema 的对象；不得输出 CSS、"
                "HTML、JavaScript、链接或额外字段。"
            ),
            user=(
                f"主题：{theme.name}；视觉家族：{theme.visual.family}；"
                f"内容骨架：{theme.visual.content_variant}；"
                f"颜色：背景 {theme.palette.background}，强调 {theme.palette.accent}。\n"
                f"用户风格提示：{(prompt or '未提供，按主题自动适配')[:1200]}\n"
                f"可用默认建议：{fallback.model_dump_json()}"
            ),
            purpose="生成 HTML 展示风格",
        )
        # mood 只用作人类可读说明，也仍由 Pydantic 限制长度；其余均为 Literal 白名单。
        return resolve_html_style(theme, prompt, result)
    except Exception as error:  # AI 风格不该阻断大纲或正文生成
        logger.info("HTML 风格 AI 适配失败，已使用主题规则：%s", error)
        return fallback
