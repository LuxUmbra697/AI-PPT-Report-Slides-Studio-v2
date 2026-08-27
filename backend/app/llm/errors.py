class LLMNotConfiguredError(RuntimeError):
    """未配置可用的 LLM 凭证。上层应提示用户配置，禁止伪造内容。"""


class InvalidModelOutputError(ValueError):
    """模型返回内容无法通过契约校验。"""


class InvalidOutlineOutputError(InvalidModelOutputError):
    pass


class InvalidSlideOutputError(InvalidModelOutputError):
    pass


class InvalidSlideEditOutputError(InvalidModelOutputError):
    pass
