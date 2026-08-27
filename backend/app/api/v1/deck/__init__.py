from fastapi import APIRouter

from app.api.v1.deck import ai_edit, blocks, export, generation, layout, pages

# 各子 router 自带相同 prefix/tags；父 router 仅按原顺序聚合。
# 注册顺序必须与拆分前 decks.py 一致：静态 /slides/order 须排在
# 会抢匹配的 /slides/{slide_id} 之前。
router = APIRouter()
router.include_router(export.router)
router.include_router(generation.router)
router.include_router(blocks.router)
router.include_router(layout.router)
router.include_router(pages.router)
router.include_router(layout.layouts_router)
router.include_router(ai_edit.router)
router.include_router(generation.events_router)
