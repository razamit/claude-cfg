import base64
import json

from claude_cfg.providers.base import StorageProvider

_API = "https://api.github.com/gists"


class GistProvider(StorageProvider):

    def __init__(self, cfg: dict) -> None:
        try:
            import requests
        except ImportError:
            raise ImportError(
                "requests required for Gist. Install: pip install claude-cfg[gist]"
            )
        self._requests = requests
        gist_cfg = cfg.get("gist", {})
        self._token = gist_cfg["token"]
        self._gist_id = gist_cfg.get("gist_id", "")
        self._headers = {
            "Authorization": f"token {self._token}",
            "Accept": "application/vnd.github+json",
        }
        self._cache: dict[str, str] = {}

    def _fetch_files(self) -> dict:
        if not self._gist_id:
            return {}
        r = self._requests.get(
            f"{_API}/{self._gist_id}", headers=self._headers, timeout=30
        )
        r.raise_for_status()
        return r.json().get("files", {})

    def _file_key(self, key: str) -> str:
        return key.replace("/", "__")

    def upload(self, key: str, data: bytes) -> None:
        encoded = base64.b64encode(data).decode("ascii")
        file_name = self._file_key(key)
        payload: dict = {"files": {file_name: {"content": encoded}}}

        if self._gist_id:
            r = self._requests.patch(
                f"{_API}/{self._gist_id}",
                headers=self._headers,
                json=payload,
                timeout=30,
            )
        else:
            payload["public"] = False
            payload["description"] = "claude-cfg snapshot store"
            r = self._requests.post(
                _API, headers=self._headers, json=payload, timeout=30
            )
            self._gist_id = r.json()["id"]

        r.raise_for_status()

    def download(self, key: str) -> bytes:
        files = self._fetch_files()
        file_name = self._file_key(key)
        if file_name not in files:
            raise FileNotFoundError(f"Key not found in Gist: {key}")
        raw_url = files[file_name]["raw_url"]
        r = self._requests.get(raw_url, headers=self._headers, timeout=30)
        r.raise_for_status()
        return base64.b64decode(r.text)

    def list_keys(self, prefix: str = "") -> list[str]:
        files = self._fetch_files()
        result = []
        for name in files:
            key = name.replace("__", "/")
            if not prefix or key.startswith(prefix):
                result.append(key)
        return result

    def exists(self, key: str) -> bool:
        files = self._fetch_files()
        return self._file_key(key) in files

    @property
    def gist_id(self) -> str:
        return self._gist_id
