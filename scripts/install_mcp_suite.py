#!/usr/bin/env python3
"""Install the curated, read-only MCP suite into AstrBot.

The generated AstrBot MCP configuration never contains credentials.  Stdio
servers inherit credentials from the AstrBot container environment, populated
from the local-only .env.mcp file by Docker Compose.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping


MANAGED_PREFIX = "dfyqq-"
PUBLIC_DATA_URL = "https://public-data.up.railway.app/mcp"
DEFAULT_DATA_DIR = Path("/AstrBot/data")


def _present(env: Mapping[str, str], *names: str) -> bool:
    return all(str(env.get(name, "")).strip() for name in names)


def _on(value: str | None, *, default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def activation(env: Mapping[str, str]) -> dict[str, tuple[bool, str]]:
    naver = _present(env, "NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET")
    taobao = _present(
        env,
        "TAOBAO_APP_KEY",
        "TAOBAO_APP_SECRET",
        "TAOBAO_SESSION",
        "TAOBAO_PID",
    )
    jd = _present(
        env,
        "JD_APP_KEY",
        "JD_APP_SECRET",
        "JD_SITE_ID",
        "JD_POSITION_ID",
    )
    pdd = _present(env, "PDD_CLIENT_ID", "PDD_CLIENT_SECRET", "PDD_PID")
    real_china = taobao or jd or pdd
    allow_mock = _on(env.get("DFYQQ_MCP_ALLOW_MOCK"))
    force_mock = _on(env.get("SHOPPING_MCP_MOCK"))
    china = (real_china and not force_mock) or allow_mock
    buywhere = _present(env, "BUYWHERE_API_KEY")
    public = _on(env.get("DFYQQ_MCP_PUBLIC_DATA"), default=True)

    china_reason = "official platform credentials available"
    if allow_mock and not real_china:
        china_reason = "mock explicitly allowed for local testing"
    elif force_mock:
        china_reason = "disabled because SHOPPING_MCP_MOCK is enabled"
    elif not real_china:
        china_reason = "no complete Taobao, JD or PDD credential set"

    return {
        "dfyqq-korea-public": (
            public,
            "public remote read-only service" if public else "disabled by DFYQQ_MCP_PUBLIC_DATA",
        ),
        "dfyqq-naver-search": (
            naver,
            "Naver credentials available" if naver else "NAVER_CLIENT_ID/SECRET missing",
        ),
        "dfyqq-china-shopping": (china, china_reason),
        "dfyqq-global-shopping": (
            buywhere,
            "BuyWhere key available" if buywhere else "BUYWHERE_API_KEY missing",
        ),
    }


def desired_servers(env: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    state = activation(env)
    return {
        "dfyqq-korea-public": {
            "transport": "streamable_http",
            "url": PUBLIC_DATA_URL,
            "timeout": 30,
            "sse_read_timeout": 300,
            "active": state["dfyqq-korea-public"][0],
        },
        "dfyqq-naver-search": {
            "command": "python",
            "args": ["/opt/dfyqq-mcp/naver-search/server.py"],
            "active": state["dfyqq-naver-search"][0],
        },
        "dfyqq-china-shopping": {
            "command": "python",
            "args": ["-m", "shopping_mcp.server"],
            "active": state["dfyqq-china-shopping"][0],
        },
        "dfyqq-global-shopping": {
            "command": "buywhere-mcp",
            "args": [],
            "active": state["dfyqq-global-shopping"][0],
        },
    }


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"mcpServers": {}}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict) or not isinstance(value.get("mcpServers"), dict):
        raise ValueError(f"invalid AstrBot MCP config: {path}")
    return value


def merged_config(current: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    result = dict(current)
    servers = dict(result.get("mcpServers", {}))
    servers.update(desired_servers(env))
    result["mcpServers"] = servers
    return result


def is_current(path: Path, env: Mapping[str, str]) -> bool:
    current = load_config(path)
    desired = desired_servers(env)
    servers = current["mcpServers"]
    return all(servers.get(name) == config for name, config in desired.items())


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def install(path: Path, env: Mapping[str, str], backup_dir: Path) -> Path | None:
    current = load_config(path)
    desired = merged_config(current, env)
    if current == desired:
        return None

    backup: Path | None = None
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"mcp_server.before-suite-{stamp}.json"
        shutil.copy2(path, backup)
    _atomic_json(path, desired)
    return backup


def print_status(env: Mapping[str, str]) -> None:
    for name, (enabled, reason) in activation(env).items():
        print(f"{name}: {'enabled' if enabled else 'disabled'} ({reason})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="read-only config comparison")
    parser.add_argument("--status", action="store_true", help="show activation without secrets")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args(argv)

    config_path = args.data_dir / "mcp_server.json"
    backup_dir = args.data_dir / "dfyqq" / "backups"

    if args.status:
        print_status(os.environ)
        return 0
    if args.check:
        ok = is_current(config_path, os.environ)
        print("MCP suite config is current" if ok else "MCP suite config needs update")
        print_status(os.environ)
        return 0 if ok else 1

    backup = install(config_path, os.environ, backup_dir)
    if backup:
        print(f"Backed up previous MCP config to {backup}")
    print("Installed curated MCP suite; restart AstrBot to load changed services")
    print_status(os.environ)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
