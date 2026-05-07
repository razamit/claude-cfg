from claude_cfg.providers.base import StorageProvider


class S3Provider(StorageProvider):

    def __init__(self, cfg: dict) -> None:
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 required for S3/R2. Install: pip install claude-cfg[s3]"
            )

        storage = cfg["storage"]
        backend_cfg = cfg.get(storage, {})

        kwargs = {
            "aws_access_key_id": backend_cfg["access_key"],
            "aws_secret_access_key": backend_cfg["secret_key"],
        }

        if storage == "r2":
            account_id = backend_cfg["account_id"]
            kwargs["endpoint_url"] = (
                f"https://{account_id}.r2.cloudflarestorage.com"
            )
        else:
            kwargs["region_name"] = backend_cfg.get("region", "us-east-1")

        self._bucket = backend_cfg["bucket"]
        self._s3 = boto3.client("s3", **kwargs)

    def upload(self, key: str, data: bytes) -> None:
        self._s3.put_object(Bucket=self._bucket, Key=key, Body=data)

    def download(self, key: str) -> bytes:
        response = self._s3.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    def list_keys(self, prefix: str = "") -> list[str]:
        paginator = self._s3.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def exists(self, key: str) -> bool:
        try:
            self._s3.head_object(Bucket=self._bucket, Key=key)
            return True
        except self._s3.exceptions.ClientError:
            return False
