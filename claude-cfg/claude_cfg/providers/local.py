from pathlib import Path

from claude_cfg.providers.base import StorageProvider


class LocalProvider(StorageProvider):

    def __init__(self, cfg: dict) -> None:
        self._root = Path(cfg["local"]["path"]).expanduser()
        self._root.mkdir(parents=True, exist_ok=True)

    def upload(self, key: str, data: bytes) -> None:
        dest = self._root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def download(self, key: str) -> bytes:
        path = self._root / key
        if not path.exists():
            raise FileNotFoundError(f"Key not found in local store: {key}")
        return path.read_bytes()

    def list_keys(self, prefix: str = "") -> list[str]:
        base = self._root / prefix if prefix else self._root
        if not base.exists():
            return []
        return [
            str(p.relative_to(self._root)).replace("\\", "/")
            for p in base.rglob("*")
            if p.is_file()
        ]

    def exists(self, key: str) -> bool:
        return (self._root / key).exists()
