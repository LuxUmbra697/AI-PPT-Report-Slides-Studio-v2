from typing import TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.llm.errors import InvalidModelOutputError, LLMNotConfiguredError

T = TypeVar("T", bound=BaseModel)

# LCEL 负责一次结构化调用；有状态的校验/修复放在 LangGraph。
_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", "{system}"),
        ("human", "{user}"),
    ]
)


def create_chat_model(settings: Settings | None = None) -> ChatOpenAI:
    """用 ChatOpenAI 对接 DeepSeek 兼容接口，业务层不再持有 OpenAI SDK。"""
    cfg = settings or get_settings()
    kwargs: dict = {
        "model": cfg.llm_model,
        "api_key": cfg.llm_api_key or "not-configured",
        "base_url": cfg.llm_base_url,
        "timeout": cfg.llm_timeout_seconds,
        "max_retries": 2,
    }
    # 思考模式默认关闭；关闭时不要传 thinking，避免无谓地拉长延迟
    if cfg.llm_thinking_enabled:
        kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
    return ChatOpenAI(**kwargs)


class StructuredChatClient:
    """prompt | ChatOpenAI.with_structured_output(json_mode) 的薄封装。"""

    def __init__(self, *, model: BaseChatModel, api_key: str) -> None:
        self._model = model
        self._api_key = api_key

    async def complete(
        self,
        schema: type[T],
        *,
        system: str,
        user: str,
        purpose: str,
    ) -> T:
        if not self._api_key.strip():
            raise LLMNotConfiguredError(f"未配置 LLM API Key，无法{purpose}")

        chain = _PROMPT | self._model.with_structured_output(schema, method="json_mode")
        try:
            result = await chain.ainvoke({"system": system, "user": user})
        except Exception as error:
            raise InvalidModelOutputError("模型返回内容不符合约定结构") from error

        if isinstance(result, schema):
            return result
        if isinstance(result, BaseModel):
            try:
                return schema.model_validate(result.model_dump())
            except ValidationError as error:
                raise InvalidModelOutputError("模型返回内容不符合约定结构") from error
        if isinstance(result, dict):
            try:
                return schema.model_validate(result)
            except ValidationError as error:
                raise InvalidModelOutputError("模型返回内容不符合约定结构") from error
        raise InvalidModelOutputError("模型返回内容不符合约定结构")
