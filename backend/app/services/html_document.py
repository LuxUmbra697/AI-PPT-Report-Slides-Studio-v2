"""AI 直出 HTML 文档的存取与隔离前安全检查。

这里不提供任何页面模板或 PPT 主题：模型产出的文档就是最终报告。检查只限制它访问
宿主页面、账号数据与任意网络请求的能力，视觉、布局、CSS 与交互实现完全由模型决定。
"""

from __future__ import annotations

import re
from base64 import b64encode
from collections.abc import Awaitable, Callable

import httpx

from app.core.config import get_settings
from app.models.project import Project
from app.services.media import load_image, media_key_from_url

DOCUMENT_KEY = "document_html"
_MAX_DOCUMENT_CHARS = 420_000
_ALLOWED_SCRIPT_SOURCES = (
    "https://cdn.tailwindcss.com",
    "https://cdn.jsdelivr.net/npm/echarts@",
    "https://cdn.jsdelivr.net/npm/echarts-gl@",
    "https://cdn.jsdelivr.net/npm/three@0.160.1/",
    "https://cdn.jsdelivr.net/npm/jsbarcode@3.11.6/",
    "https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/",
    "https://cdn.jsdelivr.net/npm/xlsx@0.18.5/",
)
_MAX_EXTERNAL_SCRIPTS = 4
_MAX_EXTERNAL_SCRIPT_BYTES = 8 * 1024 * 1024
_FORBIDDEN_PATTERNS = (
    r"<\s*(?:iframe|object|embed|frame|form)\b",
    r"<\s*base\b",
    r"<\s*meta\b[^>]*http-equiv\s*=\s*['\"]?refresh",
    r"\bon[a-z]+\s*=",
    r"\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|navigator\.sendBeacon)\s*\(",
    r"\b(?:window\.(?:top|parent|opener)|document\.cookie|localStorage|sessionStorage)\b",
    r"\b(?:eval|Function|import)\s*\(",
    r"\b(?:location\.(?:assign|replace)|window\.open)\s*\(",
)
_IMAGE_SOURCE_PATTERN = re.compile(
    r"<(?:img|source|image)\b[^>]*\b(?:src|href)\s*=\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
_CSS_URL_PATTERN = re.compile(r"url\(\s*['\"]?([^'\")\s]+)['\"]?\s*\)", re.IGNORECASE)
_MEDIA_URL_PATTERN = re.compile(r"/api/v1/media/media/[A-Za-z0-9_./-]+\.(?:png|jpe?g|webp)")
_SCRIPT_TAG_PATTERN = re.compile(r"<script\b(?P<attrs>[^>]*)>\s*</script\s*>", re.IGNORECASE)
_SCRIPT_SRC_ATTRIBUTE = re.compile(r"\bsrc\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
_CSP = (
    "default-src 'none'; img-src data: https: http:; font-src data: https:; "
    "style-src 'unsafe-inline'; script-src 'unsafe-inline' https://cdn.tailwindcss.com "
    "https://cdn.jsdelivr.net; connect-src 'none'; media-src 'none'; "
    "object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
_TOP_TARGET_MARKER = 'data-luxumbra-top-target="true"'
_TOP_TARGET = (
    '<span id="top" data-luxumbra-top-target="true" aria-hidden="true" '
    'style="position:absolute;top:0;left:0;width:1px;height:1px;overflow:hidden"></span>'
)
_HASH_NAVIGATION_MARKER = 'data-luxumbra-hash-navigation="true"'
_HASH_NAVIGATION_GUARD = f"""
<script {_HASH_NAVIGATION_MARKER}>
(() => {{
  document.addEventListener("click", (event) => {{
    const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
    const href = link?.getAttribute("href");
    if (!href || !href.startsWith("#")) return;
    event.preventDefault();
    const targetId = decodeURIComponent(href.slice(1));
    const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!targetId) {{
      window.scrollTo({{ top: 0, behavior: reducedMotion ? "auto" : "smooth" }});
      return;
    }}
    document.getElementById(targetId)?.scrollIntoView({{
      behavior: reducedMotion ? "auto" : "smooth",
      block: "start",
    }});
  }}, true);
}})();
</script>"""


class UnsafeGeneratedHtml(ValueError):
    """AI 文档包含不适合在隔离预览中执行的能力。"""


class HtmlMediaBundleError(ValueError):
    """将单文件 HTML 依赖打包时发生了错误。"""


def generated_document(project: Project) -> str | None:
    data = project.html_report_data or {}
    value = data.get(DOCUMENT_KEY)
    if not isinstance(value, str) or not value.strip():
        return None
    # 已生成的历史直出报告不必强制重跑模型；补齐 #top 的无视觉目标，让下载版
    # 仍沿用浏览器原生锚点行为。srcDoc 的防空白导航只在预览响应时额外注入。
    return _add_top_target(value)


def validate_generated_document(value: str, *, allowed_image_urls: set[str] | None = None) -> str:
    """规范化模型输出并添加 CSP；不改写其视觉结构或 CSS。"""

    document = value.strip()
    if document.startswith("```"):
        document = re.sub(r"^```(?:html)?\s*", "", document, flags=re.IGNORECASE)
        document = re.sub(r"\s*```$", "", document).strip()
    if len(document) > _MAX_DOCUMENT_CHARS:
        raise UnsafeGeneratedHtml("生成的 HTML 文档过大")
    if not re.match(r"<!doctype\s+html\b", document, flags=re.IGNORECASE):
        raise UnsafeGeneratedHtml("模型未返回完整 HTML 文档")
    if not all(
        re.search(pattern, document, flags=re.IGNORECASE)
        for pattern in (r"<html\b", r"</html\s*>", r"<body\b", r"</body\s*>")
    ):
        raise UnsafeGeneratedHtml("模型返回的 HTML 缺少完整文档结构")

    for pattern in _FORBIDDEN_PATTERNS:
        if re.search(pattern, document, flags=re.IGNORECASE):
            raise UnsafeGeneratedHtml("生成的 HTML 包含受限浏览器能力")

    for source in re.findall(
        r"<script\b[^>]*\bsrc\s*=\s*['\"]([^'\"]+)['\"]", document, flags=re.IGNORECASE
    ):
        if not any(source.startswith(allowed) for allowed in _ALLOWED_SCRIPT_SOURCES):
            raise UnsafeGeneratedHtml("生成的 HTML 引用了未允许的脚本来源")

    _validate_image_sources(document, allowed_image_urls=allowed_image_urls)

    csp_tag = f'<meta http-equiv="Content-Security-Policy" content="{_CSP}">'
    marker = 'data-luxumbra-ai-document="true"'
    if "</head>" in document.lower():
        document = re.sub(r"</head>", f"{csp_tag}</head>", document, count=1, flags=re.IGNORECASE)
    else:
        document = re.sub(
            r"(<!doctype\s+html[^>]*>)",
            rf"\1<head>{csp_tag}</head>",
            document,
            count=1,
            flags=re.IGNORECASE,
        )
    if "<html" in document.lower():
        document = re.sub(r"<html\b", f"<html {marker}", document, count=1, flags=re.IGNORECASE)
    return _add_top_target(document)


def bundle_html_media(document: str) -> str:
    """把报告引用的项目媒体内嵌到下载版 HTML，确保离线打开仍完整可见。"""

    urls = set(_MEDIA_URL_PATTERN.findall(document))
    if not urls:
        return document

    replacements: dict[str, str] = {}
    total_bytes = 0
    max_bytes = get_settings().html_export_embed_media_max_bytes
    for url in urls:
        key = media_key_from_url(url)
        if key is None:
            raise HtmlMediaBundleError("HTML 包含无法识别的项目图片地址")
        try:
            data = load_image(key)
        except (FileNotFoundError, ValueError) as error:
            raise HtmlMediaBundleError("报告图片资源已不存在，请重新生成报告") from error
        total_bytes += len(data)
        if total_bytes > max_bytes:
            raise HtmlMediaBundleError(
                f"报告图片超过 {get_settings().html_export_embed_media_max_mb} MB 离线导出上限"
            )
        mime_type = _image_mime_type(url)
        replacements[url] = f"data:{mime_type};base64,{b64encode(data).decode('ascii')}"

    for url, data_uri in replacements.items():
        document = document.replace(url, data_uri)
    return document


async def bundle_html_for_export(
    document: str,
    *,
    fetch_script: Callable[[str], Awaitable[str]] | None = None,
) -> str:
    """生成真正可离线打开的单文件：项目图片转 data URI，白名单脚本转内联。"""

    document = bundle_html_media(document)
    sources = _external_script_sources(document)
    if not sources:
        return document
    if len(sources) > _MAX_EXTERNAL_SCRIPTS:
        raise HtmlMediaBundleError("HTML 使用的外部框架过多，无法安全打包")
    for source in sources:
        if not _is_allowed_script_source(source):
            raise HtmlMediaBundleError("HTML 包含不受支持的外部脚本，无法安全离线导出")

    downloader = fetch_script or _download_allowed_script
    scripts: dict[str, str] = {}
    try:
        for source in sources:
            scripts[source] = await downloader(source)
    except (httpx.HTTPError, UnicodeDecodeError, ValueError) as error:
        raise HtmlMediaBundleError("无法下载网页运行依赖，请检查网络后重试导出") from error

    def inline_script(match: re.Match[str]) -> str:
        attrs = match.group("attrs")
        source_match = _SCRIPT_SRC_ATTRIBUTE.search(attrs)
        if source_match is None:
            return match.group(0)
        source = source_match.group(1)
        body = scripts.get(source)
        if body is None:
            return match.group(0)
        # integrity/crossorigin 仅适用于外链脚本，内联后去掉避免浏览器误解。
        safe_attrs = re.sub(
            r"\s+(?:src|integrity|crossorigin)\s*=\s*(['\"])[^'\"]*\1",
            "",
            attrs,
            flags=re.IGNORECASE,
        )
        return f"<script{safe_attrs}>\n{body}\n</script>"

    bundled = _SCRIPT_TAG_PATTERN.sub(inline_script, document)
    if _external_script_sources(bundled):
        raise HtmlMediaBundleError("HTML 脚本标签格式不完整，无法安全离线导出")
    return bundled


def _validate_image_sources(document: str, *, allowed_image_urls: set[str] | None) -> None:
    """只允许模型使用提供的项目媒体或自行内嵌的数据 URI。

    所有在线图片均由后端先下载、校验并保存，再交给模型引用；这保证可控、可导出，
    也避免发布后依赖第三方临时 URL。
    """

    allowed = allowed_image_urls or set()
    sources = _IMAGE_SOURCE_PATTERN.findall(document) + _CSS_URL_PATTERN.findall(document)
    for source in sources:
        normalized = source.strip()
        if normalized.startswith("data:image/") or normalized in allowed:
            continue
        # CSS 的片段引用不是外部资源，例如 filter: url(#shadow)。
        if normalized.startswith("#"):
            continue
        raise UnsafeGeneratedHtml("生成的 HTML 使用了未托管的图片资源")


def _image_mime_type(url: str) -> str:
    extension = url.rsplit(".", 1)[-1].lower()
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
    }.get(extension, "application/octet-stream")


def _external_script_sources(document: str) -> set[str]:
    return set(
        re.findall(
            r"<script\b[^>]*\bsrc\s*=\s*['\"]([^'\"]+)['\"]",
            document,
            flags=re.IGNORECASE,
        )
    )


def _is_allowed_script_source(source: str) -> bool:
    return any(source.startswith(allowed) for allowed in _ALLOWED_SCRIPT_SOURCES)


async def _download_allowed_script(source: str) -> str:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, trust_env=False) as client:
        response = await client.get(source)
        response.raise_for_status()
        if len(response.content) > _MAX_EXTERNAL_SCRIPT_BYTES:
            raise ValueError("网页运行依赖过大")
        return response.content.decode("utf-8")


def with_preview_hash_navigation_guard(document: str) -> str:
    """仅为站内 srcDoc iframe 注入内部锚点滚动保护。

    导出的文件不使用此拦截器，因而完整保留浏览器的链接与 History 行为。
    """

    return _add_hash_navigation_guard(document)


def _add_top_target(document: str) -> str:
    """补足模型常生成但容易遗漏目标的 `href="#top"`。"""

    if _TOP_TARGET_MARKER in document or re.search(
        r"<[^>]+\bid\s*=\s*['\"]top['\"]", document, flags=re.IGNORECASE
    ):
        return document
    return re.sub(
        r"(<body\b[^>]*>)",
        rf"\1{_TOP_TARGET}",
        document,
        count=1,
        flags=re.IGNORECASE,
    )


def _add_hash_navigation_guard(document: str) -> str:
    """让 `href="#section"` 在隔离 srcDoc iframe 内稳定滚动而不发生页面导航。"""

    if _HASH_NAVIGATION_MARKER in document:
        return document
    return re.sub(
        r"</body\s*>",
        f"{_HASH_NAVIGATION_GUARD}</body>",
        document,
        count=1,
        flags=re.IGNORECASE,
    )
