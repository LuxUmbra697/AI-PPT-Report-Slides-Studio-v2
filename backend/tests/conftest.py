import os
import tempfile

# 必须在导入任何读取配置的模块之前改环境变量：Settings 与 Storage 都是
# lru_cache 单例，一旦构造好就不会再看环境。否则测试会往真实的
# backend/var/storage 落文件。
_STORAGE_DIR = tempfile.mkdtemp(prefix="luxumbra-test-storage-")
os.environ["STORAGE_LOCAL_DIR"] = _STORAGE_DIR

import pytest  # noqa: E402

from app.core.db import engine  # noqa: E402


@pytest.fixture(autouse=True)
async def _reset_async_engine() -> None:
    # 每个用例独立事件循环，用完后释放连接池，避免 asyncpg 绑到旧 loop
    yield
    await engine.dispose()
