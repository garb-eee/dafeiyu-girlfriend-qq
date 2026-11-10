from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
import tempfile
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register


STAGES = ("stranger", "familiar", "close")


def _data_dir() -> Path:
    try:
        return Path(StarTools.get_data_dir("astrbot_plugin_dafeiyu_relationship"))
    except TypeError:
        return Path(StarTools.get_data_dir()) / "astrbot_plugin_dafeiyu_relationship"


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
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


@register(
    "astrbot_plugin_dafeiyu_relationship",
    "dafeiyu-girlfriend-qq",
    "持久化并注入大肥鱼的关系阶段",
    "1.0.0",
)
class DafeiyuRelationshipPlugin(Star):
    def __init__(self, context: Context, config: dict[str, Any] | None = None):
        super().__init__(context)
        self.context = context
        self.config = config if isinstance(config, dict) else {}
        self.folder = _data_dir()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.state_path = self.folder / "state.json"
        self.owner_id = str(self.config.get("owner_id") or "").strip() or self._discover_owner()
        self.state = self._load_state()
        logger.info(
            "[DafeiyuRelationship] ready: stage=%s owner_configured=%s",
            self.state["stage"],
            bool(self.owner_id),
        )

    def _discover_owner(self) -> str:
        config_path = self.folder.parent.parent / "cmd_config.json"
        try:
            data = json.loads(config_path.read_text(encoding="utf-8-sig"))
            admins = [str(item).strip() for item in data.get("admins_id", [])]
            return next((item for item in admins if item), "")
        except Exception as exc:
            logger.warning("[DafeiyuRelationship] owner discovery failed: %s", exc)
            return ""

    def _load_state(self) -> dict[str, Any]:
        initial = str(self.config.get("initial_stage") or "close")
        if initial not in STAGES:
            initial = "close"
        state: dict[str, Any] = {
            "version": 1,
            "owner_id": self.owner_id,
            "stage": initial,
            "turn_count": 0,
            "active_dates": [],
            "last_message_ids": [],
        }
        if self.state_path.exists():
            try:
                loaded = json.loads(self.state_path.read_text(encoding="utf-8-sig"))
                if isinstance(loaded, dict):
                    state.update(loaded)
            except Exception as exc:
                logger.warning("[DafeiyuRelationship] invalid state ignored: %s", exc)
        if state.get("stage") not in STAGES:
            state["stage"] = initial
        state["owner_id"] = self.owner_id
        state["active_dates"] = list(dict.fromkeys(str(x) for x in state.get("active_dates", [])))[-60:]
        state["last_message_ids"] = [str(x) for x in state.get("last_message_ids", [])][-128:]
        _atomic_json(self.state_path, state)
        return state

    def _is_owner(self, event: AstrMessageEvent) -> bool:
        return bool(self.owner_id) and str(event.get_sender_id()) == self.owner_id

    def _record_owner_turn(self, event: AstrMessageEvent) -> None:
        message_obj = getattr(event, "message_obj", None)
        message_id = str(getattr(message_obj, "message_id", "") or "")
        seen = self.state.setdefault("last_message_ids", [])
        if message_id and message_id in seen:
            return
        if message_id:
            seen.append(message_id)
            del seen[:-128]
        self.state["turn_count"] = int(self.state.get("turn_count", 0)) + 1
        today = datetime.now().astimezone().date().isoformat()
        dates = self.state.setdefault("active_dates", [])
        if today not in dates:
            dates.append(today)
            del dates[:-60]
        self._maybe_progress()
        _atomic_json(self.state_path, self.state)

    def _maybe_progress(self) -> None:
        if not bool(self.config.get("auto_progress", False)):
            return
        turns = int(self.state.get("turn_count", 0))
        days = len(self.state.get("active_dates", []))
        stage = str(self.state.get("stage", "stranger"))
        if turns >= int(self.config.get("close_turns", 300)) and days >= int(
            self.config.get("close_days", 14)
        ):
            stage = "close"
        elif stage == "stranger" and turns >= int(self.config.get("familiar_turns", 60)) and days >= int(
            self.config.get("familiar_days", 3)
        ):
            stage = "familiar"
        self.state["stage"] = stage

    def _prompt_block(self, *, stage: str, private: bool, owner: bool) -> str:
        if not owner:
            return (
                "\n\n【关系阶段插件】\n"
                "当前发言者不是主人，关系阶段为 stranger。把对方当普通群友或主人的朋友，"
                "自然友好但不使用情侣爱称，不泄露主人私聊、记忆或情绪账本。"
            )
        permissions = {
            "stranger": "礼貌自然地聊天，不使用爱称，不撒娇、不吃醋、不表达想念。",
            "familiar": "可以温和亲近、用自然昵称、开轻度玩笑并提及已确认的偏好，但不用情侣爱称。",
            "close": "这是已经确认的亲密情侣关系；可以自然使用爱称、撒娇、表达想念或轻微小委屈，但保持克制、不威胁、不索取、不贬低。",
        }[stage]
        place = (
            "当前是主人私聊，可以使用本会话内经过验证的私密记忆。"
            if private
            else "当前在群聊中；可以让人看出亲近，但不要公开主人私聊内容、长期记忆细节或内部状态。"
        )
        return f"\n\n【关系阶段插件】\n当前关系阶段：{stage}。{permissions}{place}"

    @filter.on_llm_request(priority=240)
    async def inject_relationship(self, event: AstrMessageEvent, req: Any):
        if not bool(self.config.get("enabled", True)):
            return
        owner = self._is_owner(event)
        if owner:
            self._record_owner_turn(event)
        stage = str(self.state.get("stage", "close")) if owner else "stranger"
        req.system_prompt = (req.system_prompt or "") + self._prompt_block(
            stage=stage,
            private=event.is_private_chat(),
            owner=owner,
        )

    @filter.command("关系状态")
    async def relationship_status(self, event: AstrMessageEvent):
        if not self._is_owner(event):
            yield event.plain_result("这个状态只给主人看。")
            return
        yield event.plain_result(
            f"当前关系阶段：{self.state['stage']}；互动 {int(self.state.get('turn_count', 0))} 轮；"
            f"跨 {len(self.state.get('active_dates', []))} 天。"
        )

    @filter.command("关系阶段")
    async def set_relationship_stage(self, event: AstrMessageEvent, stage: str = ""):
        if not self._is_owner(event):
            yield event.plain_result("只有主人能调整关系阶段。")
            return
        normalized = str(stage).strip().lower()
        if normalized not in STAGES:
            yield event.plain_result("用法：/关系阶段 stranger|familiar|close")
            return
        self.state["stage"] = normalized
        _atomic_json(self.state_path, self.state)
        yield event.plain_result(f"关系阶段已设为 {normalized}。")
