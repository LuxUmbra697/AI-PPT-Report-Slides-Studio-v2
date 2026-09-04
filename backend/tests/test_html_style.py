from app.domain.theme import get_theme
from app.services.html_style import html_palette, resolve_html_style


def test_explicit_revolution_prompt_overrides_saved_ivory_style() -> None:
    theme = get_theme("ivory")
    profile = resolve_html_style(
        theme,
        "革命风",
        {
            "mood": "米白商务自适应展示",
            "layout": "editorial",
            "motion": "soft",
            "corners": "sharp",
            "density": "balanced",
            "pattern": "grid",
        },
    )

    palette = html_palette(theme, profile)

    assert profile.palette == "revolution"
    assert profile.mood == "红色革命叙事展示"
    assert palette["background"] == "#2b060b"


def test_anime_prompt_wins_over_technology_keyword() -> None:
    profile = resolve_html_style(get_theme("ivory"), "二次元星空科技发布会", None)

    assert profile.palette == "anime"
    assert profile.pattern == "sparkles"


def test_dunhuang_prompt_overrides_saved_ivory_style() -> None:
    theme = get_theme("ivory")
    profile = resolve_html_style(theme, "敦煌莫高窟风格", {"palette": "theme"})

    assert profile.palette == "dunhuang"
    assert profile.mood == "敦煌壁画叙事展示"
    assert html_palette(theme, profile)["background"] == "#21130f"
