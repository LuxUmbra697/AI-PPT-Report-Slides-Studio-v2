"""后台任务的重试策略。

策略与 WorkerSettings 放在一起容易各写一份：任务里判断「这是最后一次」用的上限
必须和 ARQ 实际的 max_tries 同源，否则要么提前放弃、要么永远等不到收尾。
"""

from typing import Any

from arq import Retry

from app.llm.errors import LLMNotConfiguredError

__all__ = ["MAX_TRIES", "retry_after_failure"]

MAX_TRIES = 2
# 模型侧多为瞬时抖动或采样不稳，隔几秒重来即可，不需要指数退避
_RETRY_DELAY_SECONDS = 3.0


def retry_after_failure(ctx: dict[str, Any], error: Exception) -> Retry | None:
    """还能再试就返回 Retry 让调用方抛出，否则返回 None 表示已达终局。

    必须抛 arq.Retry 而不是原异常：ARQ 只对 Retry / RetryJob 重新入队，
    普通异常一律算永久失败，任务状态会永远停在「生成中」。
    """
    if isinstance(error, LLMNotConfiguredError):
        # 缺凭证重试多少次都不会自愈，直接落终态让用户去配置
        return None
    if int(ctx.get("job_try", 1)) >= MAX_TRIES:
        return None
    return Retry(defer=_RETRY_DELAY_SECONDS)
