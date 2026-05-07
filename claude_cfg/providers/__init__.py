from importlib import import_module
from typing import TYPE_CHECKING

from claude_cfg.providers.base import StorageProvider

_REGISTRY: dict[str, str] = {
    "s3":    "claude_cfg.providers.s3.S3Provider",
    "r2":    "claude_cfg.providers.s3.S3Provider",
    "local": "claude_cfg.providers.local.LocalProvider",
    "gist":  "claude_cfg.providers.gist.GistProvider",
    "sftp":  "claude_cfg.providers.sftp.SFTPProvider",
}


def get_provider(cfg: dict) -> StorageProvider:
    storage = cfg.get("storage")
    if not storage:
        raise ValueError("Config missing 'storage' key.")
    dotted = _REGISTRY.get(storage)
    if not dotted:
        raise ValueError(f"Unknown storage backend: {storage!r}")
    module_path, class_name = dotted.rsplit(".", 1)
    module = import_module(module_path)
    cls = getattr(module, class_name)
    return cls(cfg)
