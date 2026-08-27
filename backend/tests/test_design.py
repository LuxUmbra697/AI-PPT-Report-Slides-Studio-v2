import pytest
from httpx import ASGITransport, AsyncClient

from app.domain.layout import load_layouts
from app.domain.sample import load_sample_deck
from app.domain.theme import load_themes
from app.domain.validation import has_blocking_issue, validate_deck
from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def test_themes_are_complete() -> None:
    layouts = load_layouts()
    themes = load_themes()

    assert len(themes) >= 3

    # 每个布局用到的文本样式，三套主题都必须定义，
    # 否则换主题时会出现某个槽位无样式可用
    required_styles = {
        slot.text_style
        for layout in layouts.values()
        for slot in layout.slots
        if slot.text_style is not None
    }
    for theme in themes.values():
        missing = required_styles - set(theme.text_styles)
        assert not missing, f"主题 {theme.id} 缺少文本样式：{missing}"


def test_slots_stay_inside_canvas() -> None:
    for layout in load_layouts().values():
        for slot in layout.slots:
            assert slot.rect.x + slot.rect.w <= 1.0001, f"{layout.id}/{slot.id} 水平越界"
            assert slot.rect.y + slot.rect.h <= 1.0001, f"{layout.id}/{slot.id} 垂直越界"


def test_sample_deck_covers_every_layout() -> None:
    deck = load_sample_deck()
    used = {slide.layout_id for slide in deck.slides}
    assert used == set(load_layouts()), "示例文稿必须覆盖全部布局，否则回归集会漏掉页面类型"


def test_sample_deck_covers_every_block_type() -> None:
    deck = load_sample_deck()
    used = {block.type for slide in deck.slides for block in slide.blocks}
    assert used == {
        "text",
        "bullets",
        "image",
        "chart",
        "table",
        "kpi",
        "cards",
        "callout",
    }


def test_sample_deck_has_no_structure_error() -> None:
    issues = validate_deck(load_sample_deck())
    assert not has_blocking_issue(issues), [issue.message for issue in issues]


@pytest.mark.asyncio
async def test_switching_theme_keeps_content_and_order(client: AsyncClient) -> None:
    original = (await client.get("/api/v1/design/sample-deck")).json()
    switched = (await client.get("/api/v1/design/sample-deck?theme_id=midnight")).json()

    assert switched["theme_id"] == "midnight"
    assert [slide["id"] for slide in switched["slides"]] == [
        slide["id"] for slide in original["slides"]
    ]
    assert switched["slides"] == original["slides"]


@pytest.mark.asyncio
async def test_unknown_theme_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/v1/design/sample-deck?theme_id=nope")
    assert response.status_code == 404
