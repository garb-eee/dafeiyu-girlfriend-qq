#!/usr/bin/env python3
"""Configure the private Dafeiyu runtime after pinned plugins are installed.

This script runs inside the AstrBot container. It never prints IDs or secrets and
keeps a timestamped backup beside every JSON file it changes.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any


DATA = Path("/AstrBot/data")
MAIN_CONFIG = DATA / "cmd_config.json"
PLUGIN_CONFIG = DATA / "config"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def write_json(path: Path, value: dict[str, Any], stamp: str) -> None:
    backup = path.with_name(f"{path.name}.before-companion-{stamp}.bak")
    shutil.copy2(path, backup)
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


def upsert_provider(providers: list[dict[str, Any]], entry: dict[str, Any]) -> None:
    for index, existing in enumerate(providers):
        if str(existing.get("id")) == str(entry["id"]):
            providers[index] = entry
            return
    providers.append(entry)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group-id", required=True)
    args = parser.parse_args()
    group_id = str(args.group_id).strip()
    if not group_id.isdigit():
        raise SystemExit("--group-id must contain digits only")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    main_config = load_json(MAIN_CONFIG)
    admins = [str(item).strip() for item in main_config.get("admins_id", [])]
    owner_id = next((item for item in admins if item.isdigit()), "")
    if not owner_id:
        whitelist = [
            str(item).strip()
            for item in main_config.get("platform_settings", {}).get("id_whitelist", [])
        ]
        private_candidates = [
            item for item in whitelist if item.isdigit() and item != group_id
        ]
        if len(private_candidates) == 1:
            owner_id = private_candidates[0]
    if not owner_id:
        raise SystemExit(
            "could not identify exactly one numeric owner from admins or the private whitelist"
        )

    providers = main_config.setdefault("provider", [])
    upsert_provider(
        providers,
        {
            "id": "dfyqq-ollama-bge-m3",
            "type": "ollama_embedding",
            "provider": "ollama",
            "provider_type": "embedding",
            "enable": True,
            "embedding_api_base": "http://ollama:11434",
            "embedding_model": "bge-m3",
            "embedding_dimensions": 1024,
            "timeout": 90,
            "proxy": "",
        },
    )
    upsert_provider(
        providers,
        {
            "id": "dfyqq-edge-tts",
            "provider": "microsoft",
            "type": "edge_tts",
            "provider_type": "text_to_speech",
            "enable": True,
            "edge-tts-voice": "zh-CN-XiaoxiaoNeural",
            "rate": "+3%",
            "volume": "+0%",
            "pitch": "+2Hz",
            "timeout": 30,
            "proxy": "",
        },
    )
    main_config.setdefault("platform_settings", {})["empty_mention_waiting"] = False
    main_config["wake_prefix"] = ["/"]
    provider_settings = main_config.setdefault("provider_settings", {})
    provider_settings["group_name_display"] = True
    ltm = main_config.setdefault("provider_ltm_settings", {})
    ltm["group_message_history_enable"] = True
    ltm["group_message_history_max_cnt"] = 80
    tts = main_config.setdefault("provider_tts_settings", {})
    tts.update(
        {
            "enable": True,
            "provider_id": "dfyqq-edge-tts",
            "dual_output": True,
            "use_file_service": False,
            "trigger_probability": 0.15,
        }
    )
    write_json(MAIN_CONFIG, main_config, stamp)

    living_path = PLUGIN_CONFIG / "astrbot_plugin_livingmemory_config.json"
    living = load_json(living_path)
    living.setdefault("access_control", {}).update(
        {
            "whitelist_enabled": True,
            "allowed_ids": f"{owner_id}\n{group_id}",
        }
    )
    living.setdefault("provider_settings", {}).update(
        {
            "embedding_provider_id": "dfyqq-ollama-bge-m3",
            "llm_provider_id": "dfyqq-dsflash",
            "llm_stream_mode": "auto",
        }
    )
    living.setdefault("session_manager", {}).update(
        {
            "enable_full_group_capture": True,
            "context_window_size": 80,
            "max_messages_per_session": 2000,
        }
    )
    write_json(living_path, living, stamp)

    proactive_path = PLUGIN_CONFIG / "astrbot_plugin_proactive_chat_config.json"
    proactive = load_json(proactive_path)
    friend = proactive.setdefault("friend_settings", {})
    friend.update(
        {
            "enable": True,
            "session_list": [f"dfyqq-qq:FriendMessage:{owner_id}"],
        }
    )
    friend.setdefault("auto_trigger_settings", {}).update(
        {"enable_auto_trigger": True, "auto_trigger_after_minutes": 180}
    )
    friend.setdefault("schedule_settings", {}).update(
        {
            "min_interval_minutes": 180,
            "max_interval_minutes": 720,
            "quiet_hours": "23-8",
            "max_unanswered_times": 2,
        }
    )
    friend.setdefault("tts_settings", {}).update(
        {"enable_tts": False, "always_send_text": True}
    )
    group = proactive.setdefault("group_settings", {})
    group.update(
        {
            "enable": True,
            "session_list": [f"dfyqq-qq:GroupMessage:{group_id}"],
            "group_idle_trigger_minutes": 180,
        }
    )
    group.setdefault("auto_trigger_settings", {}).update(
        {"enable_auto_trigger": True, "auto_trigger_after_minutes": 180}
    )
    group.setdefault("schedule_settings", {}).update(
        {
            "min_interval_minutes": 360,
            "max_interval_minutes": 720,
            "quiet_hours": "23-8",
            "max_unanswered_times": 1,
        }
    )
    group.setdefault("tts_settings", {}).update(
        {"enable_tts": False, "always_send_text": True}
    )
    proactive.setdefault("web_admin", {})["enabled"] = False
    proactive.setdefault("telemetry_config", {})["enabled"] = False
    proactive.setdefault("notification_settings", {})["enabled"] = False
    write_json(proactive_path, proactive, stamp)

    group_plus_path = PLUGIN_CONFIG / "astrbot_plugin_group_chat_plus_config.json"
    group_plus = load_json(group_plus_path)
    group_plus.update(
        {
            "enable_web_panel": False,
            "enable_group_chat": True,
            "enabled_groups": [group_id],
            "decision_ai_provider_id": "dfyqq-dsflash",
            "initial_probability": 1.0,
            "after_reply_probability": 1.0,
            "concurrent_mode": "smart",
            "enable_smart_batch_reply_hint": True,
            "enable_memory_injection": True,
            "memory_plugin_mode": "auto",
            "livingmemory_version": "v2",
            "livingmemory_persona_compat_mode": "auto",
            "livingmemory_top_k": 8,
            "memory_insertion_timing": "post_decision",
            "max_context_messages": 80,
            "trigger_keywords": ["大肥鱼", "鲸八", "小玹"],
            "keyword_smart_mode": True,
            "enable_attention_mechanism": True,
            "enable_typo_generator": False,
            "enable_typing_simulator": True,
            "enable_dynamic_reply_probability": True,
            "enable_reply_density_limit": True,
            "reply_density_window_seconds": 300,
            "reply_density_max_replies": 4,
            "enable_message_quality_scoring": True,
            "enable_humanize_mode": True,
            "enable_group_wait_window": True,
            "group_wait_window_timeout_ms": 2500,
            "group_wait_window_max_extra_messages": 3,
            "enable_proactive_chat": False,
            "enable_private_chat": False,
        }
    )
    write_json(group_plus_path, group_plus, stamp)

    affective_path = PLUGIN_CONFIG / "astrbot_plugin_affective_core_config.json"
    affective = load_json(affective_path)
    affective.update(
        {
            "enabled": True,
            "inject_prompt_memo": True,
            "appraisal_mode": "sync_pre",
            "appraisal_provider_id": "dfyqq-dsflash",
            "appraisal_timeout_seconds": 2.5,
            "owner_scope": f"dfyqq-qq:FriendMessage:{owner_id}",
            "owner_id": owner_id,
        }
    )
    write_json(affective_path, affective, stamp)

    relationship_path = PLUGIN_CONFIG / "astrbot_plugin_dafeiyu_relationship_config.json"
    relationship = load_json(relationship_path)
    relationship.update(
        {
            "enabled": True,
            "owner_id": owner_id,
            "initial_stage": "close",
            "auto_progress": False,
        }
    )
    write_json(relationship_path, relationship, stamp)

    print("CONFIGURED=true")
    print("FILES_CHANGED=6")
    print("OWNER_CONFIGURED=true")
    print("GROUP_CONFIGURED=true")


if __name__ == "__main__":
    main()
