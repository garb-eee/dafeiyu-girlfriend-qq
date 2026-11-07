#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本项目的人格文件装进 AstrBot（v4.29.0）：SQLite personas 表 + cmd_config.json。

在 AstrBot 容器内运行（不是宿主机）：

    # 预演 / 与现网对比，什么都不改
    python3 /AstrBot/data/dfyqq/scripts/install_astrbot_persona.py --check

    # 真正写入（容器内需要 sudo，因为文件属主通常是 root）
    sudo python3 /AstrBot/data/dfyqq/scripts/install_astrbot_persona.py

设计约束（与项目 S0 验收对齐）：
  - 只用标准库（sqlite3 / json / os / shutil），不联网、不连 QQ、不读任何密钥。
  - 人格文本的唯一来源是 /AstrBot/data/dfyqq/persona/dafeiyu-chat.md 中
    `<!-- system_prompt:begin -->` 与 `<!-- system_prompt:end -->` 之间的正文。
  - SQLite 用 UPSERT 写 personas 表，persona_id 固定为 dafeiyu-girlfriend；
    system_prompt 幂等覆盖，其余字段（folder_id / sort_order 等）首次写入后保持不动。
  - cmd_config.json 只改一个键：agent_runner.config.persona.persona_id。
    provider / platform / 白名单 / 凭证一个字节都不碰；写入用临时文件 + fsync + os.replace 原子替换。
  - 修改前各备份一次：data_v4.db 用 SQLite 在线备份 API 生成一致快照，
    cmd_config.json 直接复制；备份文件权限收到 0600。
  - `--check` 只读：既不写库也不写文件，退出码 0 = 已一致，1 = 有差异，2 = 有错误。

可选参数：--persona-file / --db / --config / --backup-dir，
方便在宿主机上对着临时目录做离线演练。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------- 常量

DEFAULT_DATA_DIR = "/AstrBot/data"
DEFAULT_PERSONA_FILE = "/AstrBot/data/dfyqq/persona/dafeiyu-chat.md"
DEFAULT_DB = "/AstrBot/data/data_v4.db"
DEFAULT_CONFIG = "/AstrBot/data/cmd_config.json"
DEFAULT_BACKUP_DIR = "/AstrBot/data/dfyqq/backups"

PERSONA_ID = "dafeiyu-girlfriend"
PROMPT_BEGIN = "<!-- system_prompt:begin -->"
PROMPT_END = "<!-- system_prompt:end -->"

# AstrBot Persona 模型里由本脚本负责维护的列（其余列原样保留）。
PERSONA_COLUMNS = (
    "persona_id",
    "system_prompt",
    "begin_dialogs",
    "tools",
    "skills",
    "custom_error_message",
    "folder_id",
    "sort_order",
)

EXIT_OK = 0
EXIT_DIFF = 1
EXIT_ERROR = 2


class InstallError(RuntimeError):
    """可预期的失败：参数、文件格式或环境问题。"""


# ---------------------------------------------------------------- 人格文本


def extract_system_prompt(text: str) -> str:
    """取 `system_prompt` 区段正文。

    必须恰好有一对标记；正文不能为空；同时拦截两类会让 AstrBot 误解析的字符
    （未转义的控制字符、Jinja 模板语法）。
    """
    begin = text.count(PROMPT_BEGIN)
    end = text.count(PROMPT_END)
    if begin != 1 or end != 1:
        raise InstallError(
            f"人格文件的 system_prompt 标记必须各出现一次（begin={begin}, end={end}）"
        )
    start = text.index(PROMPT_BEGIN) + len(PROMPT_BEGIN)
    stop = text.index(PROMPT_END)
    if stop < start:
        raise InstallError("system_prompt 结束标记出现在开始标记之前")
    body = text[start:stop]
    # 去掉标记行前后的空行
    body = body.strip("\r\n")
    if body.strip():
        body = body.rstrip() + "\n"
    if not body.strip():
        raise InstallError("system_prompt 正文为空")

    for needle, why in (
        ("\x00", "NUL 字符"),
        ("{%", "Jinja 语句标记"),
        ("{{", "Jinja 表达式标记"),
        ("{#", "Jinja 注释标记"),
    ):
        if needle in body:
            raise InstallError(f"system_prompt 正文包含 {why} {needle!r}，AstrBot 会误当模板解析")
    return body


def read_persona_file(path: Path) -> str:
    if not path.is_file():
        raise InstallError(f"找不到人格文件：{path}")
    raw = path.read_bytes()
    try:
        return extract_system_prompt(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise InstallError(f"人格文件不是合法 UTF-8：{exc}") from exc


# ---------------------------------------------------------------- 备份


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _sqlite_timestamp() -> str:
    """与 AstrBot 存下来的 created_at / updated_at 同样的无时区 UTC 格式。"""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ", timespec="microseconds")


def _ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass  # 非 POSIX 文件系统（例如在宿主机上演练）忽略


def _unique_path(base: Path) -> Path:
    """避免同一秒内重复运行覆盖上一次备份。"""
    if not base.exists():
        return base
    stem, suffix = base.stem, base.suffix
    for i in range(1, 100):
        candidate = base.with_name(f"{stem}.{i}{suffix}")
        if not candidate.exists():
            return candidate
    raise InstallError(f"备份文件名冲突过多：{base}")


def backup_sqlite(db_path: Path, backup_dir: Path, stamp: str) -> Path:
    """在线备份 API：即使 AstrBot 正在写入，快照也是事务一致的。"""
    _ensure_private_dir(backup_dir)
    target = _unique_path(backup_dir / f"data_v4.before-persona-{stamp}.db")
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
            dst.commit()
        finally:
            dst.close()
    finally:
        src.close()
    os.chmod(target, 0o600)
    if target.stat().st_size == 0:
        raise InstallError(f"数据库备份为空：{target}")
    return target


def backup_file(path: Path, backup_dir: Path, stamp: str) -> Path:
    _ensure_private_dir(backup_dir)
    target = _unique_path(backup_dir / f"{path.name}.before-persona-{stamp}.bak")
    shutil.copy2(path, target)
    os.chmod(target, 0o600)
    if target.read_bytes() != path.read_bytes():
        raise InstallError(f"配置备份校验失败：{target}")
    return target


# ---------------------------------------------------------------- SQLite


def inspect_personas_table(con: sqlite3.Connection) -> set[str]:
    row = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='personas'"
    ).fetchone()
    if row is None:
        raise InstallError("库里没有 personas 表，AstrBot 可能还没初始化（先启动一次 AstrBot）")
    return {r[1] for r in con.execute("PRAGMA table_info(personas)")}


def get_persona(con: sqlite3.Connection, persona_id: str = PERSONA_ID) -> dict | None:
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT * FROM personas WHERE persona_id = ?", (persona_id,)
    ).fetchone()
    return dict(row) if row else None


def persona_diff(current: dict | None, prompt: str) -> list[str]:
    if current is None:
        return ["personas 表里还没有 " + PERSONA_ID]
    diffs = []
    stored = current.get("system_prompt") or ""
    if stored == prompt:
        pass
    elif stored.strip() == prompt.strip():
        diffs.append("system_prompt 仅首尾空白不同")
    else:
        diffs.append(
            "system_prompt 不一致（库内 %d 字符 / 文件 %d 字符）" % (len(stored), len(prompt))
        )
    return diffs


def upsert_persona(con: sqlite3.Connection, prompt: str) -> str:
    """幂等写入。返回 'inserted' 或 'updated' 或 'unchanged'。"""
    columns = inspect_personas_table(con)
    missing = [c for c in PERSONA_COLUMNS if c not in columns]
    if missing:
        raise InstallError(f"personas 表缺少列：{missing}（AstrBot 版本可能不匹配）")

    current = get_persona(con)
    now = _sqlite_timestamp()
    if current is None:
        con.execute(
            "INSERT INTO personas (persona_id, system_prompt, begin_dialogs, tools,"
            " skills, custom_error_message, folder_id, sort_order, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (PERSONA_ID, prompt, None, None, None, None, None, 0, now, now),
        )
        return "inserted"
    if (current.get("system_prompt") or "") == prompt:
        return "unchanged"
    con.execute(
        "UPDATE personas SET system_prompt = ?, updated_at = ? WHERE persona_id = ?",
        (prompt, now, PERSONA_ID),
    )
    return "updated"


# ---------------------------------------------------------------- cmd_config


def load_config(path: Path) -> dict:
    if not path.is_file():
        raise InstallError(f"找不到配置文件：{path}")
    raw = path.read_bytes()
    # AstrBot 历史上写过 utf-8-sig，读时容忍 BOM。
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstallError(f"cmd_config.json 不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise InstallError("cmd_config.json 根节点不是对象")
    return data


def get_persona_id(config: dict) -> str | None:
    node = config
    for key in ("agent_runner", "config", "persona", "persona_id"):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
        if key == "persona_id":
            return node if isinstance(node, str) else None
    return None


def set_persona_id(config: dict) -> dict:
    """只动 agent_runner.config.persona.persona_id，其余节点原样带过。"""
    if "agent_runner" not in config:
        raise InstallError("cmd_config.json 里没有 agent_runner 段")
    if not isinstance(config["agent_runner"], dict):
        raise InstallError("agent_runner 不是对象")
    node = config["agent_runner"].setdefault("config", {})
    if not isinstance(node, dict):
        raise InstallError("agent_runner.config 不是对象")
    persona = node.setdefault("persona", {})
    if not isinstance(persona, dict):
        raise InstallError("agent_runner.config.persona 不是对象")
    persona["persona_id"] = PERSONA_ID
    return config


def _fingerprint(config: dict) -> tuple[str, str]:
    """除了 persona.persona_id，还随手记下两条必须原样保留的证据。"""
    providers = config.get("provider")
    platforms = config.get("platform")
    platform_settings = config.get("platform_settings") or {}
    whitelist = platform_settings.get("id_whitelist") if isinstance(platform_settings, dict) else None
    try:
        pv = json.dumps(providers, ensure_ascii=False, sort_keys=True)
    except TypeError:
        pv = repr(providers)
    try:
        pl = json.dumps(platforms, ensure_ascii=False, sort_keys=True)
    except TypeError:
        pl = repr(platforms)
    try:
        wl = json.dumps(whitelist, ensure_ascii=False, sort_keys=True)
    except TypeError:
        wl = repr(whitelist)
    return pv, pl + "|" + wl


def write_json_atomic(path: Path, data: dict) -> None:
    """同目录临时文件 + fsync + os.replace，保留原文件权限。"""
    mode = path.stat().st_mode & 0o7777 if path.exists() else 0o644
    payload = json.dumps(data, ensure_ascii=False, indent=4).encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    try:
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
    except OSError:
        return  # Windows 不支持目录 fsync，忽略
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


# ---------------------------------------------------------------- 主流程


def check_only(persona_file: Path, db_path: Path, config_path: Path) -> int:
    failures: list[str] = []
    print("[check] 只读预演，不会修改任何文件")

    try:
        prompt = read_persona_file(persona_file)
        print(f"[check] 人格正文 OK：{len(prompt)} 字符（{persona_file}）")
    except InstallError as exc:
        print(f"[check] FAIL 人格文件：{exc}")
        return EXIT_ERROR

    if not db_path.is_file():
        failures.append(f"数据库不存在：{db_path}")
    else:
        try:
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                inspect_personas_table(con)
                current = get_persona(con)
                diffs = persona_diff(current, prompt)
                if diffs:
                    failures.extend(diffs)
                else:
                    print(f"[check] personas OK：{PERSONA_ID} 的 system_prompt 与文件一致")
            finally:
                con.close()
        except sqlite3.Error as exc:
            failures.append(f"读数据库失败：{exc}")
        except InstallError as exc:
            failures.append(str(exc))

    if not config_path.is_file():
        failures.append(f"配置不存在：{config_path}")
    else:
        try:
            config = load_config(config_path)
            current_id = get_persona_id(config)
            if current_id == PERSONA_ID:
                print(f"[check] cmd_config OK：agent_runner.config.persona.persona_id = {PERSONA_ID}")
            else:
                failures.append(
                    "cmd_config 的 persona_id 是 %r，应为 %r" % (current_id, PERSONA_ID)
                )
        except InstallError as exc:
            failures.append(str(exc))

    if failures:
        for item in failures:
            print("[check] DIFF " + item)
        print("[check] 结果：需要安装或修复（退出码 1）")
        return EXIT_DIFF
    print("[check] 结果：已与文件一致，无需改动（退出码 0）")
    return EXIT_OK


def install(persona_file: Path, db_path: Path, config_path: Path, backup_dir: Path) -> int:
    if not db_path.is_file():
        raise InstallError(f"数据库不存在：{db_path}，先启动一次 AstrBot 初始化库")
    if not config_path.is_file():
        raise InstallError(f"配置不存在：{config_path}")

    # 1) 先把所有输入读一遍并校验，不通过就一行都不写。
    prompt = read_persona_file(persona_file)
    config = load_config(config_path)
    config_needs_write = get_persona_id(config) != PERSONA_ID
    if config_needs_write:
        before = _fingerprint(config)
        set_persona_id(config)
        if _fingerprint(config) != before:
            raise InstallError("内部错误：改 persona_id 时碰到了 provider/platform/白名单，已中止")

    stamp = _timestamp()
    con = sqlite3.connect(str(db_path), timeout=30)
    try:
        inspect_personas_table(con)
        db_will_change = persona_diff(get_persona(con), prompt) != []

        # 2) 备份：确实要改的每一项各备份一次。
        if db_will_change:
            path = backup_sqlite(db_path, backup_dir, stamp)
            print(f"[install] 已备份数据库 → {path}")
        if config_needs_write:
            path = backup_file(config_path, backup_dir, stamp)
            print(f"[install] 已备份配置 → {path}")

        # 3) 写库（UPSERT，单事务）
        if db_will_change:
            changed = upsert_persona(con, prompt)
            con.commit()
            print(f"[install] personas 表：{changed}（persona_id={PERSONA_ID}）")
        else:
            print("[install] personas 表：unchanged")

        # 4) 写配置（原子替换 + 回读校验）
        if config_needs_write:
            write_json_atomic(config_path, config)
            if get_persona_id(load_config(config_path)) != PERSONA_ID:
                raise InstallError("写完回读 cmd_config.json 失败：persona_id 没有生效")
            print(f"[install] cmd_config.json：persona_id 已设为 {PERSONA_ID}")
        else:
            print("[install] cmd_config.json：unchanged")
    except BaseException:
        try:
            con.rollback()
        except sqlite3.Error:
            pass
        raise
    finally:
        con.close()

    print("[install] 完成。AstrBot 重启（容器内通常是进程重启）后才会重新读取人格。")
    print("[install] 重启后运行 --check 应返回退出码 0。")
    return EXIT_OK


def _default_paths() -> tuple[Path, Path, Path, Path]:
    """默认路径就是容器内的固定位置；ASTRBOT_DATA_DIR 只用于离线演练。"""
    data_dir = os.environ.get("ASTRBOT_DATA_DIR")
    if data_dir:
        base = Path(data_dir.rstrip("/"))
        return (
            Path(os.environ.get("DFYQQ_PERSONA_FILE", str(base / "dfyqq/persona/dafeiyu-chat.md"))),
            base / "data_v4.db",
            base / "cmd_config.json",
            base / "dfyqq/backups",
        )
    return (
        Path(os.environ.get("DFYQQ_PERSONA_FILE", DEFAULT_PERSONA_FILE)),
        Path(DEFAULT_DB),
        Path(DEFAULT_CONFIG),
        Path(DEFAULT_BACKUP_DIR),
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    persona_file, db, config, backup_dir = _default_paths()
    parser = argparse.ArgumentParser(
        description="把 dafeiyu-chat.md 装进 AstrBot 的 personas 表并设为默认人格（幂等）。"
    )
    parser.add_argument("--persona-file", type=Path, default=persona_file)
    parser.add_argument("--db", type=Path, default=db)
    parser.add_argument("--config", type=Path, default=config)
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=backup_dir,
        help="备份目录，默认 <data>/dfyqq/backups",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只读预演：对比文件、数据库与配置，不做任何修改；0=一致，1=有差异，2=有错误",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.check:
            return check_only(args.persona_file, args.db, args.config)
        return install(args.persona_file, args.db, args.config, args.backup_dir)
    except InstallError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return EXIT_ERROR
    except sqlite3.Error as exc:
        print(f"[error] SQLite：{exc}", file=sys.stderr)
        return EXIT_ERROR
    except OSError as exc:
        print(f"[error] 文件操作失败：{exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
