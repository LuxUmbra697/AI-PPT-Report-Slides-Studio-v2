from io import BytesIO

import pytest
from pptx import Presentation
from pptx.oxml.ns import qn

from app.domain.geometry import Rect
from app.domain.sample import load_sample_deck
from app.domain.template_skin import iter_template_decorations
from app.domain.theme import get_theme, load_themes
from app.render.pptx import PptxRenderer

OCCUPIED = [
    Rect(x=0.08, y=0.08, w=0.72, h=0.12),
    Rect(x=0.08, y=0.28, w=0.38, h=0.52),
    Rect(x=0.52, y=0.28, w=0.4, h=0.52),
]


def test_catalog_exposes_all_template_dimensions() -> None:
    themes = list(load_themes().values())
    assert len(themes) == 16
    assert len({theme.visual.family for theme in themes}) >= 12
    assert {theme.visual.cover_variant for theme in themes} == {
        "editorial",
        "split",
        "poster",
        "framed",
        "spotlight",
        "ribbon",
    }
    assert {theme.visual.content_variant for theme in themes} == {
        "clean",
        "cards",
        "notebook",
        "dashboard",
        "magazine",
        "panel",
    }
    assert {theme.visual.transition for theme in themes} == {
        "fade",
        "push",
        "wipe",
        "split",
    }


@pytest.mark.parametrize(
    ("theme_id", "expected_kind"),
    [
        ("anime-sakura-dream", "fill_box"),
        ("anime-neon-idol", "outline_box"),
        ("anime-shrine-spring", "timeline_dot"),
        ("anime-celestial-library", "side_line"),
        ("anime-foxfire-festival", "outline_box"),
    ],
)
def test_anime_templates_have_distinct_content_components(
    theme_id: str, expected_kind: str
) -> None:
    decorations = iter_template_decorations(
        get_theme(theme_id), "two_column", OCCUPIED
    )
    assert expected_kind in {decoration.kind for decoration in decorations}
    for decoration in decorations:
        assert 0 <= decoration.rect.x < decoration.rect.right <= 1
        assert 0 <= decoration.rect.y < decoration.rect.bottom <= 1


def test_all_cover_variants_produce_different_native_geometry() -> None:
    signatures: dict[str, tuple[tuple[str, float, float, float, float], ...]] = {}
    for theme in load_themes().values():
        variant = theme.visual.cover_variant
        if variant in signatures:
            continue
        decorations = iter_template_decorations(theme, "cover", [])
        signatures[variant] = tuple(
            (item.kind, item.rect.x, item.rect.y, item.rect.w, item.rect.h)
            for item in decorations
        )
    assert len(signatures) == 6
    assert len(set(signatures.values())) == 6


@pytest.mark.parametrize(
    ("theme_id", "effect_tag"),
    [
        ("anime-sakura-dream", "fade"),
        ("anime-neon-idol", "push"),
        ("anime-shrine-spring", "wipe"),
        ("anime-foxfire-festival", "split"),
    ],
)
def test_pptx_contains_theme_native_transition(theme_id: str, effect_tag: str) -> None:
    deck = load_sample_deck().model_copy(update={"theme_id": theme_id})
    payload = PptxRenderer(get_theme(theme_id)).render(deck)
    presentation = Presentation(BytesIO(payload.getvalue()))
    transition = presentation.slides[0]._element.find(qn("p:transition"))
    assert transition is not None
    assert transition.find(qn(f"p:{effect_tag}")) is not None
