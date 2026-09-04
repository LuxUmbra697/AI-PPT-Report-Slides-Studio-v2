from app.domain.content import BulletsBlock, Deck, Slide, TextBlock
from app.domain.theme import get_theme
from app.services.multiformat_export import (
    render_deck_to_html,
    render_deck_to_markdown,
    render_deck_to_pdf,
)


def _deck() -> Deck:
    return Deck(
        id="html-export",
        title="AI <报告>",
        theme_id="ivory",
        slides=[
            Slide(
                id="s1",
                layout_id="bullets",
                blocks=[
                    TextBlock(id="title", slot_id="title", text="增长 <复盘>"),
                    BulletsBlock(
                        id="bullets",
                        slot_id="body",
                        items=["营收增长 37%", "用户破千万"],
                    ),
                ],
            )
        ],
    )


def test_multiformat_renderers_keep_content_and_escape_html() -> None:
    deck = _deck()
    theme = get_theme("ivory")

    html = render_deck_to_html(
        deck,
        theme,
        {"layout": "bento", "motion": "energetic", "pattern": "sparkles"},
    ).decode("utf-8")
    markdown = render_deck_to_markdown(deck).decode("utf-8")
    pdf = render_deck_to_pdf(deck, theme)

    assert "增长 &lt;复盘&gt;" in html
    assert "IntersectionObserver" in html
    assert "@keyframes rise" in html
    assert "# AI <报告>" in markdown
    assert pdf.startswith(b"%PDF")
