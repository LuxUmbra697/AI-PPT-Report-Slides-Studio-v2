import io
import zipfile
from pathlib import PurePosixPath

from app.core.config import get_settings
from app.ingest.registry import SUPPORTED_EXTENSIONS

# 二进制格式的文件头。仅凭扩展名判断类型是不够的，
# 改个后缀就能把任意文件送进解析器。
MAGIC_PREFIX = {
    ".pdf": b"%PDF-",
    ".docx": b"PK\x03\x04",
}


class UploadRejected(Exception):
    """上传未通过校验，消息面向用户，可直接展示"""


def _extension(filename: str) -> str:
    # 只取文件名部分，客户端传来的路径一律不信任
    return PurePosixPath(filename.replace("\\", "/")).suffix.lower()


def _reject_disguised_docx(data: bytes) -> None:
    """DOCX 是 zip 容器，仅校验文件头无法区分它与任意 zip。

    检查内部必须存在 word/document.xml，可挡掉改名的压缩包。
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile as error:
        raise UploadRejected("文件已损坏或不是有效的 DOCX") from error

    if "word/document.xml" not in names:
        raise UploadRejected("文件不是有效的 DOCX 文档")


def validate_upload(filename: str, data: bytes) -> str:
    """校验上传文件并返回归一化的扩展名"""
    if not data:
        raise UploadRejected("文件内容为空")

    limit = get_settings().max_upload_bytes
    if len(data) > limit:
        raise UploadRejected(f"文件超过 {limit // (1024 * 1024)} MB 上限")

    extension = _extension(filename)
    if extension not in SUPPORTED_EXTENSIONS:
        supported = "、".join(sorted(SUPPORTED_EXTENSIONS))
        raise UploadRejected(f"不支持的文件类型，仅支持 {supported}")

    expected = MAGIC_PREFIX.get(extension)
    if expected is not None and not data.startswith(expected):
        raise UploadRejected("文件内容与扩展名不符")

    if extension == ".docx":
        _reject_disguised_docx(data)

    return extension
