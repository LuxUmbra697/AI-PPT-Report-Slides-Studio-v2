import logging
import uuid

from app.domain.content import ImageBlock, Slide
from app.domain.geometry import CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, Rect
from app.domain.slide_geometry import placed_by_block_id
from app.images.base import ImageRequest
from app.images.pipeline import ImagePipeline
from app.images.validate import validate_image
from app.services.media import media_url, store_image

logger = logging.getLogger(__name__)


def _image_aspect(rect: Rect) -> float:
    height = rect.h * CANVAS_HEIGHT_PT
    if height <= 0:
        return 16 / 9
    return (rect.w * CANVAS_WIDTH_PT) / height


async def resolve_slide_images(
    pipeline: ImagePipeline,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    deck_title: str,
    page_title: str,
    slide: Slide,
) -> Slide:
    """为尚未填充的图片块拉取真实图源；失败则保留占位，绝不打断整页。"""
    placements = placed_by_block_id(slide)
    blocks = []
    for block in slide.blocks:
        if not isinstance(block, ImageBlock) or block.url is not None or block.locked:
            blocks.append(block)
            continue
        placed = placements.get(block.id)
        if placed is None:
            logger.warning("图片块无几何位置，保留占位图：%s", block.id)
            blocks.append(block)
            continue
        resolved = await _resolve_one(
            pipeline,
            block=block,
            user_id=user_id,
            project_id=project_id,
            deck_title=deck_title,
            page_title=page_title,
            rect=placed.rect,
        )
        blocks.append(resolved)
    return slide.model_copy(update={"blocks": blocks})


async def _resolve_one(
    pipeline: ImagePipeline,
    *,
    block: ImageBlock,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    deck_title: str,
    page_title: str,
    rect: Rect,
) -> ImageBlock:
    try:
        aspect = _image_aspect(rect)
        # prompt 给生图、query 给图库：同一语义在两边的最佳措辞不同
        asset = await pipeline.fetch(
            ImageRequest(
                prompt=(
                    f"{block.alt}。用作主题为「{deck_title}」的商务演示页面"
                    f"「{page_title}」的配图，构图简洁、留白充足，画面中不要出现任何文字。"
                ),
                query=block.alt,
                aspect_ratio=aspect,
            )
        )
        if asset is None:
            return block

        extension, _content_type = validate_image(asset.data)
        key = store_image(
            user_id=user_id,
            project_id=project_id,
            data=asset.data,
            extension=extension,
        )
        return block.model_copy(
            update={
                "url": media_url(key),
                "source": asset.source,
                "credit": asset.credit,
            }
        )
    except Exception as error:
        # 一张图不该让整页失败：校验、存储、甚至意外异常都只降级到占位
        logger.warning("配图异常，保留占位图：%s", error)
        return block
