from typing import Any

import httpx
from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import get_settings
from app.images.pipeline import create_image_pipeline
from app.llm.base import OutlineGenerator, SlideEditGenerator, SlideGenerator
from app.llm.client import create_chat_model
from app.llm.deepseek import DeepSeekOutlineGenerator
from app.llm.relayout import DeepSeekRelayoutGenerator
from app.llm.slide import DeepSeekSlideGenerator
from app.llm.slide_edit import DeepSeekSlideEditGenerator


def create_outline_generator(model: BaseChatModel | None = None) -> OutlineGenerator:
    settings = get_settings()
    return DeepSeekOutlineGenerator(
        model=model or create_chat_model(),
        api_key=settings.llm_api_key,
    )


def create_slide_generator(model: BaseChatModel | None = None) -> SlideGenerator:
    settings = get_settings()
    return DeepSeekSlideGenerator(
        model=model or create_chat_model(),
        api_key=settings.llm_api_key,
    )


def create_slide_edit_generator(model: BaseChatModel | None = None) -> SlideEditGenerator:
    settings = get_settings()
    return DeepSeekSlideEditGenerator(
        model=model or create_chat_model(),
        api_key=settings.llm_api_key,
    )


def create_relayout_generator(model: BaseChatModel | None = None) -> DeepSeekRelayoutGenerator:
    settings = get_settings()
    return DeepSeekRelayoutGenerator(
        model=model or create_chat_model(),
        api_key=settings.llm_api_key,
    )


async def startup(ctx: dict[str, Any]) -> None:
    # 模型在进程内复用：每个任务新建连接池会显著抬高首字节延迟
    model = create_chat_model()
    ctx["chat_model"] = model
    ctx["outline_generator"] = create_outline_generator(model)
    ctx["slide_generator"] = create_slide_generator(model)

    http_client = httpx.AsyncClient(trust_env=False, proxy=None)
    ctx["http_client"] = http_client
    ctx["image_pipeline"] = create_image_pipeline(http_client)


async def shutdown(ctx: dict[str, Any]) -> None:
    model = ctx.get("chat_model")
    client = getattr(model, "async_client", None) if model is not None else None
    if client is not None:
        close = getattr(client, "close", None)
        if close is not None:
            await close()

    http_client = ctx.get("http_client")
    if http_client is not None:
        await http_client.aclose()
