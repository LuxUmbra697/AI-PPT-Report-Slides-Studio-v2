from app.core.config import get_settings

# 以文件头判定类型，不信任文件名：图源下载回来的字节根本没有文件名，
# 用户上传也可以改后缀伪装，两端必须走同一条校验。
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"


class ImageRejected(Exception):
    """图片未通过校验，消息面向用户，可直接展示"""


def validate_image(data: bytes) -> tuple[str, str]:
    """校验图片字节并返回 (扩展名, content_type)。"""
    if not data:
        raise ImageRejected("图片内容为空")

    limit = get_settings().max_image_bytes
    if len(data) > limit:
        raise ImageRejected(f"图片超过 {limit // (1024 * 1024)} MB 上限")

    if data.startswith(PNG_MAGIC):
        return ".png", "image/png"
    if data.startswith(JPEG_MAGIC):
        return ".jpg", "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp", "image/webp"

    raise ImageRejected("不支持的图片类型，仅支持 PNG、JPEG、WebP")
