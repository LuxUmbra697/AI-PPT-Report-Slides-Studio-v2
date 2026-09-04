import pytest

import app.services.html_document as html_document
from app.services.html_document import (
    HtmlMediaBundleError,
    UnsafeGeneratedHtml,
    bundle_html_for_export,
    bundle_html_media,
    validate_generated_document,
    with_preview_hash_navigation_guard,
)


def test_document_keeps_ai_authored_markup_and_allows_optional_frameworks() -> None:
    raw = """<!doctype html>
<html lang="zh-CN"><head><title>自由设计</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>body { background: #170c31; }</style></head>
<body><a href="#intro">阅读正文</a><main id="intro"><h1>自由生成的网页</h1></main>
<script>document.title = '已加载'</script></body></html>"""

    document = validate_generated_document(raw)

    assert 'data-luxumbra-ai-document="true"' in document
    assert "Content-Security-Policy" in document
    assert "自由生成的网页" in document
    assert "#170c31" in document
    assert 'data-luxumbra-top-target="true"' in document
    assert 'id="top"' in document
    assert 'data-luxumbra-hash-navigation="true"' not in document

    preview = with_preview_hash_navigation_guard(document)
    assert 'data-luxumbra-hash-navigation="true"' in preview
    assert "scrollIntoView" in preview


@pytest.mark.parametrize(
    "raw",
    [
        "<!doctype html><html><head></head><body><script>fetch('/api')</script></body></html>",
        '<!doctype html><html><head><script src="https://evil.example/x.js"></script></head><body></body></html>',
        '<!doctype html><html><head></head><body><iframe src="https://example.com"></iframe></body></html>',
    ],
)
def test_document_rejects_unsafe_browser_capabilities(raw: str) -> None:
    with pytest.raises(UnsafeGeneratedHtml):
        validate_generated_document(raw)


@pytest.mark.parametrize(
    "raw",
    [
        '<!doctype html><html><head></head><body><img src="https://example.com/a.png"></body></html>',
        "<!doctype html><html><head><style>body{background:url(https://example.com/a.png)}</style></head><body></body></html>",
    ],
)
def test_document_rejects_unmanaged_image_urls(raw: str) -> None:
    with pytest.raises(UnsafeGeneratedHtml):
        validate_generated_document(raw)


def test_document_allows_only_supplied_project_media_urls() -> None:
    url = "/api/v1/media/media/user/project/hero.png"
    raw = (
        "<!doctype html><html><head></head><body>"
        f'<img src="{url}"><div style="background-image:url(\'{url}\')"></div>'
        "</body></html>"
    )

    document = validate_generated_document(raw, allowed_image_urls={url})

    assert url in document


def test_bundle_html_media_inlines_each_project_asset_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "/api/v1/media/media/user/project/hero.png"
    calls: list[str] = []

    def fake_load(key: str) -> bytes:
        calls.append(key)
        return b"png-bytes"

    monkeypatch.setattr(html_document, "load_image", fake_load)
    document = f'<img src="{url}"><div style="background:url(\'{url}\')"></div>'

    bundled = bundle_html_media(document)

    assert calls == ["media/user/project/hero.png"]
    assert url not in bundled
    assert bundled.count("data:image/png;base64,cG5nLWJ5dGVz") == 2


def test_bundle_html_media_reports_missing_asset(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_image(key: str) -> bytes:
        raise FileNotFoundError(key)

    monkeypatch.setattr(html_document, "load_image", missing_image)

    with pytest.raises(HtmlMediaBundleError, match="已不存在"):
        bundle_html_media('<img src="/api/v1/media/media/user/project/missing.webp">')


@pytest.mark.asyncio
async def test_html_export_inlines_allowed_framework_scripts() -> None:
    source = "https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"
    document = (
        f'<!doctype html><html><head><script src="{source}"></script></head><body></body></html>'
    )

    async def fake_download(url: str) -> str:
        assert url == source
        return "window.echarts = { init() {} };"

    bundled = await bundle_html_for_export(document, fetch_script=fake_download)

    assert source not in bundled
    assert "window.echarts" in bundled


@pytest.mark.asyncio
async def test_html_export_rejects_unknown_external_script() -> None:
    document = (
        "<!doctype html><html><head>"
        '<script src="https://example.invalid/application.js"></script>'
        "</head><body></body></html>"
    )

    with pytest.raises(HtmlMediaBundleError, match="不受支持"):
        await bundle_html_for_export(document)


@pytest.mark.parametrize(
    "source",
    [
        "https://cdn.tailwindcss.com",
        "https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js",
        "https://cdn.jsdelivr.net/npm/echarts-gl@2/dist/echarts-gl.min.js",
        "https://cdn.jsdelivr.net/npm/three@0.160.1/build/three.min.js",
        "https://cdn.jsdelivr.net/npm/jsbarcode@3.11.6/dist/JsBarcode.all.min.js",
        "https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js",
        "https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js",
    ],
)
def test_document_allows_supported_visualization_frameworks(source: str) -> None:
    raw = (
        "<!doctype html><html><head>"
        f'<script src="{source}"></script>'
        "</head><body><main>数据报告</main></body></html>"
    )

    assert source in validate_generated_document(raw)


@pytest.mark.asyncio
async def test_html_export_limits_the_number_of_external_frameworks() -> None:
    sources = [
        "https://cdn.tailwindcss.com",
        "https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js",
        "https://cdn.jsdelivr.net/npm/echarts-gl@2/dist/echarts-gl.min.js",
        "https://cdn.jsdelivr.net/npm/three@0.160.1/build/three.min.js",
        "https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js",
    ]
    document = (
        "<!doctype html><html><head>"
        + "".join(f'<script src="{source}"></script>' for source in sources)
        + "</head><body></body></html>"
    )

    with pytest.raises(HtmlMediaBundleError, match="过多"):
        await bundle_html_for_export(document)
