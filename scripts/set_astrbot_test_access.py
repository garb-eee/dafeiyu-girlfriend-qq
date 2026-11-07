#!/usr/bin/env python3
"""Temporarily open AstrBot inbound access or lock it to one observed sender."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile


CONFIG = Path("/AstrBot/data/cmd_config.json")


def write_atomic(data: dict) -> None:
    fd, name = tempfile.mkstemp(prefix="cmd_config.", suffix=".tmp", dir=CONFIG.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, CONFIG)
    except Exception:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--open-once", action="store_true")
    group.add_argument("--lock-to")
    args = parser.parse_args()

    data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    settings = data.setdefault("platform_settings", {})
    if args.open_once:
        settings["enable_id_white_list"] = False
        settings["id_whitelist"] = []
        label = "temporary-open"
    else:
        sender = str(args.lock_to).strip()
        if not sender.isdigit():
            raise SystemExit("sender id must contain digits only")
        settings["enable_id_white_list"] = True
        settings["id_whitelist"] = [sender]
        label = "locked"

    backup = CONFIG.with_name(CONFIG.name + ".before-test-access")
    if not backup.exists():
        shutil.copy2(CONFIG, backup)
    write_atomic(data)
    print(f"ACCESS_MODE={label}")


if __name__ == "__main__":
    main()
