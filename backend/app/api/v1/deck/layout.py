import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.v1.deck._shared import (
    SessionDep,
    _commit_slide_edit,
    _dump_layout_tree,
    _ensure_editable,
    _find_slide,
    _require_flex_tree,
)
from app.api.v1.projects import OwnedProject
from app.domain.flex_edit import build_flex_tree_from_fixed
from app.domain.flex_layout import FlexContainer, iter_leaf_block_ids, restrict_bleed
from app.domain.flex_normalize import normalize
from app.domain.layout import get_layout
from app.domain.layout_switch import LayoutSwitchOk, list_layout_candidates, plan_layout_switch
from app.domain.slide_draft import BLEEDABLE_TYPES
from app.llm.errors import InvalidSlideOutputError, LLMNotConfiguredError
from app.llm.relayout import build_relayout_candidates
from app.models.slide import Slide
from app.schemas.deck import (
    FlexLayoutUpdateRequest,
    FlexStateUpdateRequest,
    LayoutCandidatePublic,
    LayoutSwitchRequest,
    RelayoutApplyRequest,
    RelayoutCandidate,
    RelayoutProposalPublic,
    RelayoutRequest,
    SlidePublic,
    UnlockFlexRequest,
)
from app.services.deck import load_slides
from app.worker.context import create_relayout_generator

_PREFIX = "/projects/{project_id}/deck"
router = APIRouter(prefix=_PREFIX, tags=["deck"])
layouts_router = APIRouter(prefix=_PREFIX, tags=["deck"])


def _apply_flex_tree(slide: Slide, layout_tree: FlexContainer) -> None:
    # 用户显式调过的版面不再按标题上限回钳，否则拖出来的高度会被改回去
    tree = normalize(layout_tree, clamp_title_grow=False)
    leaf_ids = set(iter_leaf_block_ids(tree))
    block_ids = {str(block.get("id")) for block in slide.blocks}
    unknown = leaf_ids - block_ids
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"布局树引用了不存在的内容块：{', '.join(sorted(unknown))}",
        )
    unplaced = block_ids - leaf_ids
    if unplaced:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"仍有内容块未放入布局树：{', '.join(sorted(unplaced))}",
        )
    bleedable = {
        str(block.get("id"))
        for block in slide.blocks
        if str(block.get("type")) in BLEEDABLE_TYPES
    }
    slide.layout_tree = _dump_layout_tree(restrict_bleed(tree, bleedable))


@router.put(
    "/slides/{slide_id}/flex-layout",
    response_model=SlidePublic,
)
async def update_flex_layout(
    slide_id: uuid.UUID,
    body: FlexLayoutUpdateRequest,
    project: OwnedProject,
    session: SessionDep,
) -> SlidePublic:
    slides = await load_slides(session, project.id)
    slide = _find_slide(slides, slide_id)
    _ensure_editable(slide, body.revision)
    _require_flex_tree(slide)
    _apply_flex_tree(slide, body.layout_tree)
    return await _commit_slide_edit(session, project, slide)


@router.put(
    "/slides/{slide_id}/flex-state",
    response_model=SlidePublic,
)
async def update_flex_state(
    slide_id: uuid.UUID,
    body: FlexStateUpdateRequest,
    project: OwnedProject,
    session: SessionDep,
) -> SlidePublic:
    """原子写回 blocks + layout_tree，供撤销/重做恢复整页结构。"""
    slides = await load_slides(session, project.id)
    slide = _find_slide(slides, slide_id)
    _ensure_editable(slide, body.revision)
    _require_flex_tree(slide)

    blocks = [block.model_dump(mode="json") for block in body.blocks]
    if not blocks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少保留一个内容块",
        )
    slide.blocks = blocks
    slide.layout_mode = "flex"
    _apply_flex_tree(slide, body.layout_tree)
    return await _commit_slide_edit(session, project, slide)


@router.post(
    "/slides/{slide_id}/relayout",
    response_model=RelayoutProposalPublic,
)
async def propose_relayout(
    slide_id: uuid.UUID,
    body: RelayoutRequest,
    project: OwnedProject,
    session: SessionDep,
) -> RelayoutProposalPublic:
    slides = await load_slides(session, project.id)
    slide = _find_slide(slides, slide_id)
    _ensure_editable(slide, body.revision)
    tree = _require_flex_tree(slide)

    generator = create_relayout_generator()
    try:
        llm_trees = await generator.propose(
            blocks=slide.blocks,
            current_tree=tree,
            page_title=slide.title,
            count=2,
        )
    except LLMNotConfiguredError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except InvalidSlideOutputError:
        llm_trees = []

    pairs = build_relayout_candidates(
        llm_trees=llm_trees,
        blocks=slide.blocks,
        current_tree=tree,
        limit=3,
    )
    return RelayoutProposalPublic(
        revision=slide.revision,
        candidates=[
            RelayoutCandidate(id=candidate_id, layout_tree=candidate_tree)
            for candidate_id, candidate_tree in pairs
        ],
    )


@router.post(
    "/slides/{slide_id}/relayout/apply",
    response_model=SlidePublic,
)
async def apply_relayout(
    slide_id: uuid.UUID,
    body: RelayoutApplyRequest,
    project: OwnedProject,
    session: SessionDep,
) -> SlidePublic:
    slides = await load_slides(session, project.id)
    slide = _find_slide(slides, slide_id)
    _ensure_editable(slide, body.revision)
    _require_flex_tree(slide)
    _apply_flex_tree(slide, body.layout_tree)
    return await _commit_slide_edit(session, project, slide)


@router.post(
    "/slides/{slide_id}/unlock-flex",
    response_model=SlidePublic,
)
async def unlock_flex(
    slide_id: uuid.UUID,
    body: UnlockFlexRequest,
    project: OwnedProject,
    session: SessionDep,
) -> SlidePublic:
    slides = await load_slides(session, project.id)
    slide = _find_slide(slides, slide_id)
    _ensure_editable(slide, body.revision)
    if slide.layout_mode == "flex" and slide.layout_tree is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="页面已是灵活布局",
        )

    layout = get_layout(slide.layout_id)
    # 高度来自固定布局的真实槽位矩形，回钳标题会让解锁瞬间重排版面
    tree = normalize(build_flex_tree_from_fixed(layout, slide.blocks), clamp_title_grow=False)
    if not iter_leaf_block_ids(tree):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法从当前页面生成灵活布局",
        )

    slide.layout_mode = "flex"
    slide.layout_tree = _dump_layout_tree(tree)
    return await _commit_slide_edit(session, project, slide)


@layouts_router.get(
    "/slides/{slide_id}/layouts",
    response_model=list[LayoutCandidatePublic],
)
async def list_slide_layouts(
    slide_id: uuid.UUID,
    project: OwnedProject,
    session: SessionDep,
) -> list[LayoutCandidatePublic]:
    slides = await load_slides(session, project.id)
    slide = _find_slide(slides, slide_id)
    return [
        LayoutCandidatePublic(
            layout_id=item.layout_id,
            name=item.name,
            usage=item.usage,
            compatible=item.compatible,
            reason=item.reason,
            current=item.current,
        )
        for item in list_layout_candidates(slide.blocks, slide.layout_id)
    ]


@layouts_router.put("/slides/{slide_id}/layout", response_model=SlidePublic)
async def switch_slide_layout(
    slide_id: uuid.UUID,
    body: LayoutSwitchRequest,
    project: OwnedProject,
    session: SessionDep,
) -> SlidePublic:
    slides = await load_slides(session, project.id)
    slide = _find_slide(slides, slide_id)
    _ensure_editable(slide, body.revision)

    try:
        get_layout(body.layout_id)
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="布局不存在",
        ) from error

    result = plan_layout_switch(slide.blocks, slide.layout_id, body.layout_id)
    if not isinstance(result, LayoutSwitchOk):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result.reason)

    # 只改槽位归属，不改块内容与 locked
    slide.blocks = [{**block, "slot_id": result.mapping[block["id"]]} for block in slide.blocks]
    slide.layout_id = body.layout_id
    return await _commit_slide_edit(session, project, slide)
