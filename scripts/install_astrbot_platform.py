#!/usr/bin/env python3
"""Install the isolated OneBot v11 platform entry for this project."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path


CONFIG = Path("/AstrBot/data/cmd_config.json")
PLATFORM_ID = "dfyqq-qq"
EXPECTED = {
    "id": PLATFORM_ID,
    "type": "aiocqhttp",
    "enable": True,
    "ws_reverse_host": "0.0.0.0",
    "ws_reverse_port": 6199,
    "ws_reverse_token": "",
}


def load_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8-sig"))


def is_installed(config: dict) -> bool:
    return any(item == EXPECTED for item in config.get("platform", []))


def atomic_write(config: dict) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    backup = CONFIG.with_suffix(".json.before-dfyqq-platform.bak")
    if not backup.exists():
        shutil.copy2(CONFIG, backup)
    payload = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix="cmd_config.", suffix=".tmp", dir=CONFIG.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, CONFIG)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    config = load_config()
    installed = is_installed(config)
    if args.check:
        print("PLATFORM_OK" if installed else "PLATFORM_MISSING")
        return 0 if installed else 1
    platforms = [item for item in config.get("platform", []) if item.get("id") != PLATFORM_ID]
    platforms.append(EXPECTED)
    config["platform"] = platforms
    config["timezone"] = "Asia/Seoul"
    atomic_write(config)
    print("PLATFORM_INSTALLED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
