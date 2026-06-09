import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from claude_cfg import __version__
from claude_cfg import config as cfg_mod
from claude_cfg import core
from claude_cfg.config import DEFAULT_TRACKED
from claude_cfg.paths import config_file
from claude_cfg.providers import get_provider

app = typer.Typer(
    name="claude-cfg",
    help="Versioned snapshot sync for Claude Code config files.",
    no_args_is_help=True,
)
config_app = typer.Typer(help="Manage configuration.")
app.add_typer(config_app, name="config")

console = Console()


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"claude-cfg {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Versioned snapshot sync for Claude Code config files."""


@app.command()
def init() -> None:
    """Interactive wizard to set up claude-cfg."""
    console.print("[bold]claude-cfg init[/bold]\n")

    backends = ["r2", "s3", "local", "gist", "sftp"]
    console.print("Storage backends:")
    for i, b in enumerate(backends, 1):
        console.print(f"  {i}. {b}")
    choice = typer.prompt("Choose backend (number or name)", default="local")

    if choice.isdigit():
        storage = backends[int(choice) - 1]
    else:
        storage = choice.lower().strip()

    backend_cfg: dict = {}

    if storage in ("s3", "r2"):
        if storage == "r2":
            backend_cfg["account_id"] = typer.prompt("Cloudflare account ID")
        backend_cfg["access_key"] = typer.prompt("Access key ID")
        backend_cfg["secret_key"] = typer.prompt("Secret access key", hide_input=True)
        backend_cfg["bucket"] = typer.prompt("Bucket name", default="claude-cfg")
        if storage == "s3":
            backend_cfg["region"] = typer.prompt("AWS region", default="us-east-1")

    elif storage == "local":
        console.print(
            "[dim]Tip: use a folder inside a sync service (Dropbox, OneDrive, Google Drive, iCloud)\n"
            "so snapshots are available on all your machines automatically.[/dim]"
        )
        backend_cfg["path"] = typer.prompt("Folder path")

    elif storage == "gist":
        backend_cfg["token"] = typer.prompt("GitHub personal access token", hide_input=True)
        backend_cfg["gist_id"] = ""

    elif storage == "sftp":
        backend_cfg["host"] = typer.prompt("SFTP host")
        backend_cfg["port"] = int(typer.prompt("Port", default="22"))
        backend_cfg["username"] = typer.prompt("Username")
        backend_cfg["key_path"] = typer.prompt("SSH key path", default="~/.ssh/id_rsa")
        backend_cfg["remote_path"] = typer.prompt(
            "Remote path", default="/home/user/claude-cfg"
        )

    tracked_default = ", ".join(DEFAULT_TRACKED)
    console.print(f"\nDefault tracked files: {tracked_default}")
    customize = typer.confirm("Customize tracked files?", default=False)
    if customize:
        raw = typer.prompt("Enter comma-separated files/folders")
        tracked = [t.strip() for t in raw.split(",") if t.strip()]
    else:
        tracked = DEFAULT_TRACKED

    new_cfg: dict = {
        "storage": storage,
        "tracked": tracked,
        storage: backend_cfg,
    }

    console.print("\nTesting connection...")
    try:
        provider = get_provider(new_cfg)
        provider.list_keys()
        console.print("[green]Connection successful.[/green]")
    except Exception as e:
        console.print(f"[yellow]Warning: connection test failed: {e}[/yellow]")
        if not typer.confirm("Save config anyway?", default=False):
            raise typer.Abort()

    if storage == "gist":
        try:
            gist_id = getattr(provider, "gist_id", "")
            if gist_id:
                new_cfg["gist"]["gist_id"] = gist_id
        except Exception:
            pass

    cfg_mod.save(new_cfg)

    snapshot_dest = _describe_snapshot_dest(storage, backend_cfg)
    console.print(f"\n[green]Config saved to {config_file()}[/green]")
    console.print(f"[green]Snapshots will be stored in: {snapshot_dest}[/green]")

    console.print("\nCreating initial snapshot...")
    try:
        result = core.push("initial", new_cfg, provider)
        ts = result["timestamp"].replace("T", " ").replace("Z", "")
        size_kb = result["size_bytes"] / 1024
        console.print(
            f"[green]Snapshot #1 pushed ({ts}) — "
            f"{result['file_count']} files, {size_kb:.1f} KB[/green]"
        )
    except Exception as e:
        console.print(f"[yellow]Warning: initial snapshot failed: {e}[/yellow]")
        console.print("Run [bold]claude-cfg push[/bold] manually when ready.")


@app.command()
def push(message: str = typer.Argument("", help="Snapshot message")) -> None:
    """Push current ~/.claude/ config as a new snapshot."""
    cfg = _load_cfg()
    provider = get_provider(cfg)

    with console.status("Pushing snapshot..."):
        result = core.push(message, cfg, provider)

    ts = result["timestamp"].replace("T", " ").replace("Z", "")
    size_kb = result["size_bytes"] / 1024
    console.print(
        f"[green]Snapshot #{result['id']} pushed "
        f"({ts}) — {result['file_count']} files, {size_kb:.1f} KB[/green]"
    )


@app.command()
def pull(
    point: Optional[int] = typer.Option(None, "--point", help="Snapshot ID to pull"),
) -> None:
    """Pull a snapshot and restore to ~/.claude/."""
    cfg = _load_cfg()
    provider = get_provider(cfg)

    with console.status("Pulling snapshot..."):
        result = core.pull(point, cfg, provider)

    ts = result["timestamp"].replace("T", " ").replace("Z", "")
    console.print(
        f"[green]Snapshot #{result['id']} restored "
        f"({ts}) — {result['files_restored']} files[/green]"
    )
    if result["message"]:
        console.print(f"  Message: {result['message']}")

    src, tgt = result.get("source_platform"), result.get("target_platform")
    if src and tgt and src != tgt:
        console.print(f"  [dim]Adapted {src} → {tgt} (paths re-tokenized).[/dim]")
    if result.get("is_wsl"):
        console.print(
            "  [yellow]WSL detected: this is the Linux home, distinct from any "
            "Windows-native ~/.claude.[/yellow]"
        )
    console.print(
        "  [yellow]Credentials are never synced — run [bold]claude[/bold] "
        "to re-authenticate.[/yellow]"
    )


@app.command("list")
def list_cmd() -> None:
    """List all snapshots."""
    cfg = _load_cfg()
    provider = get_provider(cfg)

    snapshots = core.list_snapshots(provider)
    if not snapshots:
        console.print("No snapshots found.")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("ID", style="cyan", width=4)
    table.add_column("Timestamp", width=21)
    table.add_column("Message", width=30)
    table.add_column("Machine")

    for s in snapshots:
        ts = s["timestamp"].replace("T", " ").replace("Z", "")
        table.add_row(
            str(s["id"]),
            ts,
            s.get("message", ""),
            s.get("machine", ""),
        )

    console.print(table)


@config_app.command("show")
def config_show() -> None:
    """Print current config (credentials masked)."""
    cfg = _load_cfg()
    console.print_json(json.dumps(cfg_mod.masked(cfg), indent=2))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Dot-separated key, e.g. r2.bucket"),
    value: str = typer.Argument(..., help="New value"),
) -> None:
    """Set a config value."""
    cfg_mod.set_value(key, value)
    leaf = key.rsplit(".", 1)[-1]
    shown = "***" if leaf in cfg_mod._MASKED_KEYS else value
    console.print(f"[green]Set {key} = {shown}[/green]")


def _describe_snapshot_dest(storage: str, backend_cfg: dict) -> str:
    if storage == "local":
        return backend_cfg.get("path", "")
    if storage in ("s3", "r2"):
        bucket = backend_cfg.get("bucket", "")
        if storage == "r2":
            account = backend_cfg.get("account_id", "")
            return f"r2://{account}/{bucket}"
        region = backend_cfg.get("region", "us-east-1")
        return f"s3://{bucket} ({region})"
    if storage == "gist":
        return "GitHub Gist (private)"
    if storage == "sftp":
        host = backend_cfg.get("host", "")
        path = backend_cfg.get("remote_path", "")
        return f"sftp://{host}{path}"
    return storage


def _load_cfg() -> dict:
    try:
        return cfg_mod.load()
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
