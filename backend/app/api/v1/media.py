from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException, Response, status

from app.services.media import MEDIA_PREFIX, load_image

router = APIRouter(prefix="/media", tags=["media"])

CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


@router.get("/{key:path}")
async def get_media(key: str) -> Response:
    # 不鉴权：<img> 标签无法携带 Authorization 头；键包含随机 UUID 不可枚举，
    # 且端点只暴露 media/ 前缀，用户上传的原始文档存在 uploads/ 前缀下不受影响。
    if not key.startswith(MEDIA_PREFIX):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在")

    try:
        data = load_image(key)
    except FileNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资源不存在") from error

    extension = PurePosixPath(key).suffix.lower()
    media_type = CONTENT_TYPES.get(extension, "application/octet-stream")
    return Response(
        content=data,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
