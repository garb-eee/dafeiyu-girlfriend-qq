#!/usr/bin/env python3
"""Install the read-only DSH GitHub plugin into an isolated DSH profile."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SOURCE = ROOT / "dsh" / "dsh-github"
MANAGED_BEGIN = "# dfyqq-github:begin"
MANAGED_END = "# dfyqq-github:end"


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def yaml_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def managed_block(gh_path: str, git_path: str, default_repo: str, clone_into: str) -> str:
    return (
        f"{MANAGED_BEGIN}\n"
        "- id: github\n"
        "  config:\n"
        f"    ghPath: {yaml_quote(gh_path)}\n"
        f"    gitPath: {yaml_quote(git_path)}\n"
        f"    defaultRepo: {default_repo}\n"
        "    timeoutMs: 60000\n"
        "    maxBuffer: 8388608\n"
        "    allowWrite: false\n"
        f"    cloneInto: {yaml_quote(clone_into)}\n"
        f"{MANAGED_END}\n"
    )


def update_patch(text: str, block: str, workspace: str | None) -> str:
    marked = re.compile(
        rf"(?ms)^{re.escape(MANAGED_BEGIN)}\n.*?^{re.escape(MANAGED_END)}\n?"
    )
    plain = re.compile(r"(?ms)^- id: github\n(?:(?!^- id: ).)*(?=^- id: |\Z)")
    # Normalize every previous managed or hand-written GitHub block to exactly
    # one block. This also repairs profiles left with duplicate overlays.
    text = marked.sub("", text)
    text = plain.sub("", text)
    text = text.rstrip() + "\n" + block

    if workspace:
        onebot = re.compile(
            r"(?ms)(^- id: dsh-onebot\n(?:(?!^- id: ).)*?^\s+workspacePath:)\s*[^\r\n]*"
        )
        if not onebot.search(text):
            raise ValueError("cannot find dsh-onebot workspacePath in cordis.patch.yml")
        text = onebot.sub(lambda match: f"{match.group(1)} {workspace}", text, count=1)
    return text if text.endswith("\n") else text + "\n"


def desired_package(current: dict, profile: Path) -> dict:
    result = dict(current)
    dependencies = dict(result.get("dependencies", {}))
    plugin_path = (profile / "_local-plugins" / "dsh-github").as_posix()
    dependencies["dsh-github"] = f"link:{plugin_path}"
    result["dependencies"] = dict(sorted(dependencies.items()))

    dsh = dict(result.get("dsh", {}))
    profile_config = dict(dsh.get("profile", {}))
    bundles = list(profile_config.get("bundles", []))
    if "dsh-github" not in bundles:
        bundles.append("dsh-github")
    profile_config["bundles"] = bundles
    dsh["profile"] = profile_config
    result["dsh"] = dsh
    return result


def same_tree(left: Path, right: Path) -> bool:
    wanted = sorted(path.relative_to(left) for path in left.rglob("*") if path.is_file())
    actual = sorted(path.relative_to(right) for path in right.rglob("*") if path.is_file()) if right.exists() else []
    return wanted == actual and all(
        (left / rel).read_bytes() == (right / rel).read_bytes() for rel in wanted
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True, help="DSH profile directory")
    parser.add_argument("--default-repo", default="garb-eee/dafeiyu-girlfriend-qq")
    parser.add_argument("--workspace", help="optional dsh-onebot workspacePath")
    parser.add_argument("--gh-path", default=shutil.which("gh") or "gh")
    parser.add_argument("--git-path", default=shutil.which("git") or "git")
    parser.add_argument("--clone-into", default="")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    profile = args.profile.resolve()
    package_path = profile / "package.json"
    patch_path = profile / "cordis.patch.yml"
    if not package_path.is_file() or not patch_path.is_file():
        raise SystemExit("profile must contain package.json and cordis.patch.yml")
    if not PLUGIN_SOURCE.is_dir():
        raise SystemExit(f"plugin source missing: {PLUGIN_SOURCE}")

    package = json.loads(package_path.read_text(encoding="utf-8-sig"))
    wanted_package = desired_package(package, profile)
    current_patch = patch_path.read_text(encoding="utf-8-sig")
    clone_into = args.clone_into or str(profile / "github-checkouts")
    wanted_patch = update_patch(
        current_patch,
        managed_block(args.gh_path, args.git_path, args.default_repo, clone_into),
        args.workspace,
    )
    target_plugin = profile / "_local-plugins" / "dsh-github"

    package_ok = package == wanted_package
    patch_ok = current_patch == wanted_patch
    plugin_ok = same_tree(PLUGIN_SOURCE, target_plugin)
    if args.check:
        print(f"package_current={str(package_ok).lower()}")
        print(f"patch_current={str(patch_ok).lower()}")
        print(f"plugin_current={str(plugin_ok).lower()}")
        return 0 if package_ok and patch_ok and plugin_ok else 1

    shutil.copytree(PLUGIN_SOURCE, target_plugin, dirs_exist_ok=True)
    atomic_text(package_path, json.dumps(wanted_package, ensure_ascii=False, indent=2) + "\n")
    atomic_text(patch_path, wanted_patch)
    print("installed read-only dsh-github profile integration")
    print("run pnpm install in the profile, then restart DeepSeek Harness")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
