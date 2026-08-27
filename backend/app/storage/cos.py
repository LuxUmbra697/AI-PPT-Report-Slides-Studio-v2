from typing import Any


class CosStorage:
    """腾讯云 COS 驱动。

    SDK 采用惰性导入：本地开发与教学场景默认走 LocalStorage，
    不应因为一个用不到的可选依赖而装不上项目。
    """

    def __init__(self, bucket: str, region: str, secret_id: str, secret_key: str) -> None:
        if not all((bucket, region, secret_id, secret_key)):
            raise ValueError("启用 COS 存储需要配置 bucket、region 与密钥")

        self.bucket = bucket
        self._client = self._build_client(region, secret_id, secret_key)

    @staticmethod
    def _build_client(region: str, secret_id: str, secret_key: str) -> Any:
        try:
            from qcloud_cos import CosConfig, CosS3Client
        except ImportError as error:
            raise RuntimeError("未安装 COS SDK，请执行：uv add cos-python-sdk-v5") from error

        config = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key)
        return CosS3Client(config)

    def save(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data)

    def load(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].get_raw_stream().read()

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)
