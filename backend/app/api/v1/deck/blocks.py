import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.v1.deck._shared import (
    SessionDep,
    _commit_slide_edit,
    _dump_layout_tree,
    _ensure_editable,
    _find_slide,
    _require_flex_tree,
)
from app.api.v1.projects import OwnedProject
from app.domain.flex_edit import default_block_dict, default_text_style_for_type
from app.domain.flex_layout import (
    FlexLeaf,
    insert_leaf,
    iter_leaf_block_ids,
    prune_empty_containers,
    remove_leaf_by_block_id,
)
from app.domain.flex_normalize import normalize
from app.images.validate import ImageRejected, validate_image
from app.models.slide import Slide
from app.schemas.deck import (
    BlockCreateRequest,
    BlockDeleteRequest,
    BlockStyleUpdate,
    BlockUpdate,
    SlidePublic,
)
from app.services.deck import load_slides
from app.services.media import media_url, store_image

router = APIRouter(prefix="/projects/{project_id}/deck", tags=["deck"])


@router.put(
    "/slides/{slide_id}/blocks/{block_id}/image",
    response_model=SlidePublic,
)
async def replace_slide_image(
    slide_id: uuid.UUID,
    block_id: str,
    project: OwnedProject,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    revision: Annotated[int, Form()],
) -> Slide:
    slides = await load_slides(session, project.id)
    slide = next((item for item in slides if item.id == slide_id), None)
    if slide is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="页面不存在")

    target = next((block for block in slide.blocks if block.get("id") == block_id), None)
    if target is None or target.get("type") != "image":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图片块不存在")

    # 页面生成完成时会整块覆盖 blocks，此时换图会被无声冲掉
    if slide.status == "generating":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="页面正在生成中，请稍后再换图",
        )

    if slide.revision != revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="页面已被其他操作更新，请刷新后重试",
        )

    data = await file.read()
    try:
        extension, _content_type = validate_image(data)
    except ImageRejected as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    key = store_image(
        user_id=project.user_id,
        project_id=project.id,
        data=data,
        extension=extension,
    )
    # 人工换过的图属于人工修改，后续 AI 修改不得覆盖
    updated = {
        **target,
        "url": media_url(key),
        "source": "upload",
        "credit": None,
        "locked": True,
    }
    # JSONB 就地改 dict 不会被 SQLAlchemy 感知，必须赋新列表
    slide.blocks = [updated if block.get("id") == block_id else block for block in slide.blocks]
    slide.revision += 1
    await session.commit()
    await session.refresh(slide)
    return SlidePublic.model_validate(slide)


@router.patch(
    "/slides/{slide_id}/blocks/{block_id}",
    response_model=SlidePublic,
)
async def update_slide_block(
    slide_id: uuid.UUID,
    block_id: str,
    body: BlockUpdate,
    project: OwnedProject,
    session: SessionDep,
) -> SlidePublic:
    slides = await load_slides(session, project.id)
    slide = _find_slide(slides, slide_id)
    target = next((block for block in slide.blocks if block.get("id") == block_id), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="内容块不存在")

    _ensure_editable(slide, body.revision)

    # 请求体按 type 判别；与存量块类型不符说明前端状态已过期
    if target.get("type") != body.type:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"块类型不匹配，当前为 {target.get('type')}，不能按 {body.type} 保存",
        )

    updated = {**target, "locked": True}
    if body.type == "text":
        updated["text"] = body.text
    elif body.type == "bullets":
        updated["items"] = body.items
    elif body.type == "kpi":
        updated["value"] = body.value
        updated["label"] = body.label
        updated["note"] = body.note
    elif body.type == "chart":
        updated["chart_type"] = body.chart_type
        updated["categories"] = body.categories
        updated["series"] = [item.model_dump() for item in body.series]
        updated["unit"] = body.unit
    elif body.type == "cards":
        updated["items"] = [item.model_dump() for item in body.items]
    elif body.type == "callout":
        updated["text"] = body.text
        updated["icon"] = body.icon
        updated["variant"] = body.variant
    else:
        updated["header"] = body.header
        updated["rows"] = body.rows

    slide.blocks = [updated if block.get("id") == block_id else block for block in slide.blocks]
    return await _commit_slide_edit(session, project, slide)


@router.patch(
    "/slides/{slide_id}/blocks/{block_id}/style",
    response_model=SlidePublic,
)
async def update_slide_block_style(
    slide_id: uuid.UUID,
    block_id: str,
    body: BlockStyleUpdate,
    project: OwnedProject,
    session: SessionDep,
) -> SlidePublic:
    """更新元素级样式覆盖。不置 locked：改颜色不该挡住 AI 改写文字。"""
    slides = await load_slides(session, project.id)
    slide = _find_slide(slides, slide_id)
    target = next((block for block in slide.blocks if block.get("id") == block_id), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="内容块不存在")

    _ensure_editable(slide, body.revision)

    # chart 不开放样式；其余类型允许（image 只消费边框字段）
    if target.get("type") == "chart":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="图表暂不支持元素级样式调整",
        )

    updated = {**target}
    if body.style is None or body.style.is_empty():
        updated["style"] = None
    else:
        updated["style"] = body.style.model_dump(mode="json", exclude_none=True)

    slide.blocks = [updated if block.get("id") == block_id else block for block in slide.blocks]
    return await _commit_slide_edit(session, project, slide)


@router.post(
    "/slides/{slide_id}/blocks",
    response_model=SlidePublic,
)
async def create_slide_block(
    slide_id: uuid.UUID,
    body: BlockCreateRequest,
    project: OwnedProject,
    session: SessionDep,
) -> SlidePublic:
    slides = await load_slides(session, project.id)
    slide = _find_slide(slides, slide_id)
    _ensure_editable(slide, body.revision)
    tree = _require_flex_tree(slide)

    block_id = uuid.uuid4().hex[:12]
    leaf = FlexLeaf(
        id=f"leaf-{block_id}",
        block_id=block_id,
        text_style=default_text_style_for_type(body.type),
    )
    if not insert_leaf(tree, body.parent_id, body.index, leaf):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="目标容器不存在",
        )

    slide.layout_tree = _dump_layout_tree(normalize(tree, clamp_title_grow=False))
    slide.blocks = [*slide.blocks, default_block_dict(body.type, block_id)]
    return await _commit_slide_edit(session, project, slide)


@router.delete(
    "/slides/{slide_id}/blocks/{block_id}",
    response_model=SlidePublic,
)
async def delete_slide_block(
    slide_id: uuid.UUID,
    block_id: str,
    body: BlockDeleteRequest,
    project: OwnedProject,
    session: SessionDep,
) -> SlidePublic:
    slides = await load_slides(session, project.id)
    slide = _find_slide(slides, slide_id)
    _ensure_editable(slide, body.revision)
    tree = _require_flex_tree(slide)

    if not any(block.get("id") == block_id for block in slide.blocks):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="内容块不存在")

    leaf_ids = iter_leaf_block_ids(tree)
    if block_id in leaf_ids and len(leaf_ids) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少保留一个内容块",
        )

    if not remove_leaf_by_block_id(tree, block_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="布局树中不存在该内容块",
        )
    pruned = prune_empty_containers(tree)
    if not iter_leaf_block_ids(pruned):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少保留一个内容块",
        )

    slide.layout_tree = _dump_layout_tree(normalize(pruned, clamp_title_grow=False))
    slide.blocks = [block for block in slide.blocks if block.get("id") != block_id]
    return await _commit_slide_edit(session, project, slide)
