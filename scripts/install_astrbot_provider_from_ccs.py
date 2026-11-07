#!/usr/bin/env python3
"""Install the current CC Switch Codex provider into AstrBot without persisting its key.

Host mode reads the current Codex provider from CC Switch, performs a small
OpenAI-compatible request, and sends the resolved settings to the container over
stdin. Container mode atomically updates only the AstrBot provider entry and the
default model provider id.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import tomllib
import urllib.error
import urllib.request


PROVIDER_ID = "dfyqq-dsflash"
MODEL = "deepseek-v4.1-flash"
CONTAINER = "dfyqq-astrbot"
CONTAINER_SCRIPT = "/tmp/install_astrbot_provider_from_ccs.py"
CONTAINER_CONFIG = Path("/AstrBot/data/cmd_config.json")


def load_ccs() -> dict[str, str]:
    db_path = Path.home() / ".cc-switch" / "cc-switch.db"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT settings_config FROM providers "
            "WHERE app_type = 'codex' AND is_current = 1 LIMIT 1"
        ).fetchone()
    if not row:
        raise RuntimeError("CC Switch 中没有当前 Codex provider")
    settings = json.loads(row[0])
    auth = settings.get("auth")
    if isinstance(auth, str):
        auth = json.loads(auth)
    if not isinstance(auth, dict):
        raise RuntimeError("CC Switch 当前 provider 的 auth 格式无效")
    config_text = settings.get("config") or ""
    config = tomllib.loads(config_text) if isinstance(config_text, str) else config_text
    shell_set = ((config or {}).get("shell_environment_policy") or {}).get("set") or {}
    key = str(shell_set.get("ANTHROPIC_AUTH_TOKEN") or "").strip()
    model = MODEL
    base_url = str((config or {}).get("base_url") or "").rstrip("/")
    if not key or not base_url:
        raise RuntimeError("CC Switch 当前 provider 缺少 OPENAI_API_KEY 或 base_url")
    return {"key": key, "base_url": base_url, "model": model}


def test_provider(payload: dict[str, str]) -> None:
    body = json.dumps(
        {
            "model": payload["model"],
            "messages": [{"role": "user", "content": "只回复 OK"}],
            "stream": False,
            "max_tokens": 8,
        }
    ).encode()
    req = urllib.request.Request(
        payload["base_url"] + "/chat/completions",
        data=body,
        headers={
            "Authorization": "Bearer " + payload["key"],
            "Content-Type": "application/json",
            "User-Agent": "OpenAI/Python 1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read(512).decode("utf-8", "replace")
        raise RuntimeError(f"模型测试失败：HTTP {exc.code} {detail}") from exc
    choices = result.get("choices") if isinstance(result, dict) else None
    if not choices:
        raise RuntimeError("模型测试失败：响应中没有 choices")
    print("[test] CCS provider API 正常（密钥未显示）")


def atomic_json_write(path: Path, data: dict) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def install_inside(payload: dict[str, str]) -> None:
    config = json.loads(CONTAINER_CONFIG.read_text(encoding="utf-8"))
    providers = config.setdefault("provider", [])
    entry = {
        "id": PROVIDER_ID,
        "provider": "openai",
        "type": "openai_chat_completion",
        "provider_type": "chat_completion",
        "enable": True,
        "key": [payload["key"]],
        "api_base": payload["base_url"],
        "model": payload["model"],
        "timeout": 120,
        "proxy": "",
        "custom_headers": {},
    }
    for index, current in enumerate(providers):
        if current.get("id") == PROVIDER_ID:
            providers[index] = entry
            break
    else:
        providers.append(entry)
    model_cfg = config.setdefault("agent_runner", {}).setdefault("config", {}).setdefault("model", {})
    model_cfg["provider_id"] = PROVIDER_ID
    model_cfg.setdefault("fallback_provider_ids", [])
    model_cfg.setdefault("request_max_retries", 5)

    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = CONTAINER_CONFIG.with_name(CONTAINER_CONFIG.name + f".dfyqq-provider-backup-{stamp}")
    shutil.copy2(CONTAINER_CONFIG, backup)
    atomic_json_write(CONTAINER_CONFIG, config)
    print(f"[install] AstrBot provider 已更新：{PROVIDER_ID} / {payload['model']}")
    print(f"[install] 备份：{backup}")


def check_inside() -> None:
    config = json.loads(CONTAINER_CONFIG.read_text(encoding="utf-8"))
    entries = [p for p in config.get("provider", []) if p.get("id") == PROVIDER_ID]
    selected = (
        config.get("agent_runner", {})
        .get("config", {})
        .get("model", {})
        .get("provider_id")
    )
    ok = len(entries) == 1 and bool(entries[0].get("key")) and bool(entries[0].get("model")) and selected == PROVIDER_ID
    print(f"[check] provider={PROVIDER_ID} count={len(entries)} model={entries[0].get('model') if entries else '<missing>'} selected={selected == PROVIDER_ID} key_present={bool(entries and entries[0].get('key'))}")
    raise SystemExit(0 if ok else 1)


def host_install(script_path: Path) -> None:
    payload = load_ccs()
    test_provider(payload)
    subprocess.run(["docker", "cp", str(script_path), f"{CONTAINER}:{CONTAINER_SCRIPT}"], check=True)
    subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "python", CONTAINER_SCRIPT, "--inside"],
        input=json.dumps(payload).encode("utf-8"),
        check=True,
    )
    subprocess.run(["docker", "restart", CONTAINER], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(
        ["docker", "exec", CONTAINER, "python", CONTAINER_SCRIPT, "--check-inside"],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inside", action="store_true")
    parser.add_argument("--check-inside", action="store_true")
    args = parser.parse_args()
    if args.check_inside:
        check_inside()
    if args.inside:
        payload = json.load(sys.stdin)
        install_inside(payload)
        return
    host_install(Path(__file__).resolve())


if __name__ == "__main__":
    main()
