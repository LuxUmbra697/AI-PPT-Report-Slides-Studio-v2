import uuid

from app.storage import get_storage

MEDIA_PREFIX = "media/"
MEDIA_URL_PREFIX = "/api/v1/media/"


def media_url(key: str) -> str:
    return f"{MEDIA_URL_PREFIX}{key}"


def media_key_from_url(url: str) -> str | None:
    if not url.startswith(MEDIA_URL_PREFIX):
        return None
    key = url[len(MEDIA_URL_PREFIX) :]
    return key or None


def store_image(
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    data: bytes,
    extension: str,
) -> str:
    # 键完全由服务端生成，不含任何客户端传来的路径成分
    key = f"{MEDIA_PREFIX}{user_id}/{project_id}/{uuid.uuid4().hex}{extension}"
    get_storage().save(key, data)
    return key


def load_image(key: str) -> bytes:
    if not key.startswith(MEDIA_PREFIX):
        raise FileNotFoundError(key)
    return get_storage().load(key)
