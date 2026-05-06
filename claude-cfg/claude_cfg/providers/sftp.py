import io
from pathlib import PurePosixPath

from claude_cfg.providers.base import StorageProvider


class SFTPProvider(StorageProvider):

    def __init__(self, cfg: dict) -> None:
        try:
            import paramiko
        except ImportError:
            raise ImportError(
                "paramiko required for SFTP. Install: pip install claude-cfg[sftp]"
            )
        sftp_cfg = cfg.get("sftp", {})
        self._remote_root = sftp_cfg["remote_path"].rstrip("/")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict = {
            "hostname": sftp_cfg["host"],
            "port": sftp_cfg.get("port", 22),
            "username": sftp_cfg["username"],
        }
        key_path = sftp_cfg.get("key_path")
        password = sftp_cfg.get("password")
        if key_path:
            connect_kwargs["key_filename"] = str(
                PurePosixPath(key_path).expanduser()
                if not key_path.startswith("~")
                else key_path
            )
        elif password:
            connect_kwargs["password"] = password

        client.connect(**connect_kwargs)
        self._sftp = client.open_sftp()
        self._client = client

    def _remote_path(self, key: str) -> str:
        return f"{self._remote_root}/{key}"

    def _mkdir_p(self, remote_dir: str) -> None:
        parts = remote_dir.split("/")
        path = ""
        for part in parts:
            if not part:
                continue
            path = f"{path}/{part}"
            try:
                self._sftp.stat(path)
            except FileNotFoundError:
                self._sftp.mkdir(path)

    def upload(self, key: str, data: bytes) -> None:
        remote = self._remote_path(key)
        parent = "/".join(remote.split("/")[:-1])
        self._mkdir_p(parent)
        with self._sftp.open(remote, "wb") as f:
            f.write(data)

    def download(self, key: str) -> bytes:
        remote = self._remote_path(key)
        buf = io.BytesIO()
        self._sftp.getfo(remote, buf)
        return buf.getvalue()

    def list_keys(self, prefix: str = "") -> list[str]:
        base = self._remote_path(prefix) if prefix else self._remote_root
        keys: list[str] = []
        self._walk(base, self._remote_root, keys)
        return keys

    def _walk(self, path: str, root: str, keys: list[str]) -> None:
        try:
            entries = self._sftp.listdir_attr(path)
        except FileNotFoundError:
            return
        import stat
        for entry in entries:
            full = f"{path}/{entry.filename}"
            if stat.S_ISDIR(entry.st_mode):
                self._walk(full, root, keys)
            else:
                rel = full[len(root):].lstrip("/")
                keys.append(rel)

    def exists(self, key: str) -> bool:
        try:
            self._sftp.stat(self._remote_path(key))
            return True
        except FileNotFoundError:
            return False

    def close(self) -> None:
        self._sftp.close()
        self._client.close()
