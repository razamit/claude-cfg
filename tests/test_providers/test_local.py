import pytest

from claude_cfg.providers.local import LocalProvider


@pytest.fixture
def provider(tmp_path):
    cfg = {"local": {"path": str(tmp_path)}}
    return LocalProvider(cfg)


def test_upload_download_roundtrip(provider):
    provider.upload("test/file.bin", b"hello world")
    assert provider.download("test/file.bin") == b"hello world"


def test_exists_true(provider):
    provider.upload("exists.txt", b"data")
    assert provider.exists("exists.txt") is True


def test_exists_false(provider):
    assert provider.exists("nope.txt") is False


def test_list_keys_prefix(provider):
    provider.upload("snapshots/001_snap.zip", b"a")
    provider.upload("snapshots/002_snap.zip", b"b")
    provider.upload("index.json", b"c")
    keys = provider.list_keys("snapshots/")
    assert len(keys) == 2
    assert all(k.startswith("snapshots/") for k in keys)


def test_list_keys_empty(provider):
    assert provider.list_keys("nonexistent/") == []


def test_download_missing_raises(provider):
    with pytest.raises(FileNotFoundError):
        provider.download("missing.txt")


def test_upload_creates_parent_dirs(provider):
    provider.upload("deep/nested/dir/file.txt", b"data")
    assert provider.exists("deep/nested/dir/file.txt")
