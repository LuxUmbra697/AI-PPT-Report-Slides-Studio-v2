from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import REPO_ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    # 端口统一使用 39xxx 段，避开各服务默认端口，防止与本机已装的
    # PostgreSQL / Redis / 其他开发服务抢占端口
    database_url: str = "postgresql+asyncpg://luxumbra:luxumbra@localhost:39432/luxumbra"
    redis_url: str = "redis://localhost:39379/0"
    cors_origins: list[str] = ["http://localhost:39173"]
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-v4-flash"
    # 大纲默认关闭思考模式以满足首个结果 10 秒内返回的目标；
    # 遇到复杂主题时可通过环境变量开启，不把供应商参数写死在工作流里。
    llm_thinking_enabled: bool = False
    llm_timeout_seconds: float = 60
    # 单份 PPT 同时生成的页数。调高能缩短总时长，但容易触发供应商限流，
    # 且失败会成片出现；3 是延迟与稳定性之间比较稳妥的取值。
    slide_concurrency: int = 3
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    # 本项目不做 refresh token，access token 默认 7 天
    jwt_expire_minutes: int = 60 * 24 * 7

    # AI 生图与图库各自独立配置：两者是互相降级的关系，
    # 只配一个也要能正常工作，因此不共用 LLM 的凭证。
    # openai = OpenAI 兼容 /images/generations；bailian = 百炼 DashScope 原生接口
    image_provider: Literal["openai", "bailian"] = "openai"
    image_api_key: str = ""
    image_base_url: str = "https://api.openai.com/v1"
    image_model: str = "gpt-image-1"
    # 百炼业务空间 ID：填写后使用专属域名，覆盖 image_base_url
    image_workspace_id: str = ""
    unsplash_access_key: str = ""
    image_timeout_seconds: float = 60
    # HTML 报告也复用上述生图/图库链路，但在正文生成前只准备少量、与章节相关的
    # 视觉素材。0 可关闭自动配图，失败时不会影响报告正文生成。
    html_report_image_count: int = 2
    # 下载单文件 HTML 时把项目媒体转为 data URI，避免离线打开时图片丢失。
    # 上限防止一个异常报告制造过大的浏览器下载文件。
    html_export_embed_media_max_mb: int = 24

    # 外部 PPT 模板可按需调用 Qwen-VL 解读内嵌图片；默认复用百炼图片 Key，
    # 因此已有 IMAGE_API_KEY 时不必再额外配置。留出独立项是为了支持分账密钥。
    template_vision_api_key: str = ""
    template_vision_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    # Qwen3-VL 是百炼当前 OpenAI-compatible 文档中列出的视觉模型。
    template_vision_model: str = "qwen3-vl-plus"
    # 每次显式解析会按重要度选择的独立图片资产数；每个 Qwen 请求最多携带 3 张。
    # 24 足以覆盖常见封面、章节和正文插图，且不会让一次点击产生无限费用。
    template_analysis_max_images: int = 24

    storage_driver: Literal["local", "cos"] = "local"
    storage_local_dir: str = str(REPO_ROOT / "backend" / "var" / "storage")
    cos_bucket: str = ""
    cos_region: str = ""
    cos_secret_id: str = ""
    cos_secret_key: str = ""

    # 上传体积上限。定得过大会让解析长时间占住请求线程
    max_upload_mb: int = 10
    max_image_mb: int = 8

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_image_bytes(self) -> int:
        return self.max_image_mb * 1024 * 1024

    @property
    def html_export_embed_media_max_bytes(self) -> int:
        return self.html_export_embed_media_max_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    # 缓存避免每个请求重复解析环境变量
    return Settings()
