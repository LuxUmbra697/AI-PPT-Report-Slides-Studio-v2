from typing import Protocol


class Storage(Protocol):
    """对象存储抽象。

    本地驱动用于开发与教学，COS 驱动用于部署。上层只依赖这个协议，
    换存储不需要改动业务代码。
    """

    def save(self, key: str, data: bytes) -> None: ...

    def load(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...
