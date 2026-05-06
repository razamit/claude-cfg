from abc import ABC, abstractmethod


class StorageProvider(ABC):

    @abstractmethod
    def upload(self, key: str, data: bytes) -> None:
        """Upload bytes to the given key/path."""
        ...

    @abstractmethod
    def download(self, key: str) -> bytes:
        """Download and return bytes from the given key/path."""
        ...

    @abstractmethod
    def list_keys(self, prefix: str = "") -> list[str]:
        """List all keys under the given prefix."""
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        ...
