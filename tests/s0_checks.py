# -*- coding: utf-8 -*-
"""S0 离线检查：生产用 system prompt、禁用/未提供能力、关系阶段、三语策略、
Compose 端口绑定、安装脚本约定、敏感信息扫描。
仅用标准库，不联网、不连接任何 QQ/NapCat 服务。用法：
    python tests/s0_checks.py
"""
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
PERSONA = ROOT / "persona" / "dafeiyu-chat.md"
STAGES = ROOT / "config" / "relationship-stages.json"
LANG = ROOT / "config" / "language-policy.json"
COMPOSE = ROOT / "compose.example.yaml"
STATE = ROOT / "state" / "relationship.json"
INSTALLER = ROOT / "scripts" / "install_astrbot_persona.py"

PROMPT_BEGIN = "<!-- system_prompt:begin -->"
PROMPT_END = "<!-- system_prompt:end -->"

# 安装脚本必须使用的容器内路径（与 compose.yaml 的挂载一致）
DEFAULT_PERSONA_PATH = "/AstrBot/data/dfyqq/persona/dafeiyu-chat.md"
DEFAULT_DB_PATH = "/AstrBot/data/data_v4.db"
DEFAULT_CONFIG_PATH = "/AstrBot/data/cmd_config.json"

# 句子出现这些词就视为"已明确说明做不到"，不再当作能力承诺
NEGATION = re.compile(r"没有|暂时|不提供|做不到|发不了|看不到|去不了|不要|别|当前|如果|假设|例如|比如")

results = []


def check(name, ok, detail=""):
    results.append((ok, name, detail))
    print(("PASS " if ok else "FAIL ") + name + ((" :: " + detail) if detail else ""))


def load_persona_sections(text):
    sections = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"^## (.+)$", line.strip())
        if m:
            cur = m.group(1)
            sections[cur] = []
        elif cur is not None:
            sections[cur].append(line)
    return {k: "\n".join(v) for k, v in sections.items()}


def split_prompt(text):
    """返回 (提示词正文, 错误列表)。正文 = 一对标记之间的内容。"""
    begin, end = text.count(PROMPT_BEGIN), text.count(PROMPT_END)
    if begin != 1 or end != 1:
        return "", [f"system_prompt 标记应各出现一次（begin={begin}, end={end}）"]
    body = text.split(PROMPT_BEGIN, 1)[1].split(PROMPT_END, 1)[0]
    return body.strip("\r\n"), []


def find_capability_mentions(body, terms):
    """找出正文里把某项能力写成"自己能做/刚做过"的句子。

    - 「没有提供/不要声称」这类否定句整体跳过；
    - 用户台词（以「用户：」开头）与列举替代方案时提到的内容不算承诺；
    - 其余出现能力名词、又没有明确"做不到"措辞的句子，就视为虚假能力承诺。
    """
    hits = []
    for line in body.splitlines():
        text = line.strip()
        if not text or text.startswith("用户：") or NEGATION.search(text):
            continue
        for term in terms:
            if term in text:
                hits.append(f"{term} ← {text[:40]}")
    return hits


def main():
    # 1) 人格必需字段（生产用 AstrBot system prompt）
    persona = PERSONA.read_text(encoding="utf-8")
    sec = load_persona_sections(persona)
    body, split_errors = split_prompt(persona)
    check("persona 文件存在且可读", PERSONA.is_file())
    check("人格含唯一一对 system_prompt 标记", not split_errors, str(split_errors))
    check("system_prompt 正文非空", len(body) > 1500, f"{len(body)} 字符")
    for field in ["name: 大肥鱼", "persona_id: dafeiyu-girlfriend", "default_stage: stranger",
                  "ai_disclosure:", "romance_safe: true", "version: 2",
                  "stage_source: config/relationship-stages.json",
                  "language_source: config/language-policy.json"]:
        check(f"人格必需字段 {field.split(':')[0]}", field in persona)
    for mode in ["stranger", "familiar", "close"]:
        check(f"meta.stage_modes 含 {mode}", re.search(r"^\s*-\s*" + mode + r"(（|\s|$)", persona, re.M) is not None)
    check("人格含禁止事项章节", any("禁止事项" in k for k in sec))
    check("人格含语言策略章节", any("语言策略" in k for k in sec))
    check("人格默认陌生阶段", "default_stage: stranger" in persona)

    # 2) 上游人设基因必须保留
    upstream_markers = {
        "蓝色小鲸鱼娘": "蓝色小鲸鱼娘",
        "鲸鱼尾巴外形": "鲸鱼尾巴",
        "白饭": "白饭",
        "嘴硬心软": "嘴硬心软",
        "短句节奏": "一到三句自然短句",
        "简体中文标点": "标点按简体中文习惯",
        "真实能力边界": "【实际能力与工具】",
        "AI 身份如实披露": "如实说明自己是 AI",
        "不编造共同经历": "不编造共同经历",
        "不虚构执行结果": "只有执行结果确认成功",
    }
    for label, needle in upstream_markers.items():
        check(f"保留上游人设：{label}", needle in body)

    # 3) 关系阶段：默认 stranger，模型不得自升级，不得写"主人"亲密默认
    check("正文默认 stranger 且礼貌称呼", "默认处于 stranger 阶段" in body and '称呼对方为"你"' in body)
    check("三阶段在正文都有定义",
          all(f"{s} 阶段" in body for s in ("stranger", "familiar", "close")))
    check("模型不得自行升级/降级", "不能自行宣布升级或降级" in body)
    check("无阶段信息时按 stranger", "一律按 stranger 处理" in body)
    check("身份不因自称改变", "自称" in body and ("不因用户文本里自称" in body or "不因用户自己写" in body))
    # 「主人」只允许出现在"用户自称不改变身份"的否定语境里，不允许成为默认称呼
    master_lines = [ln for ln in body.splitlines() if "主人" in ln]
    master_ok = all(("自称" in ln or "不因" in ln) for ln in master_lines)
    check("无「主人」亲密默认", master_ok, str(master_lines))
    check("正文禁止把「主人」当默认称呼", "不把每个人都当主人" in body)
    check("meta 里没有「主人」亲密默认",
          "主人" not in "\n".join(v for k, v in sec.items() if k == "meta"))

    # 4) 未提供的能力：名词必须被明确划为"没有"，且不得以第一人称承诺
    unavailable = ["逛 B 站", "刷 B 站", "操作 App", "控制手机", "截图", "看屏幕",
                   "把文字合成为语音", "发送图片", "表情包", "定时任务", "未来任务", "主动发消息",
                   "联网搜索"]
    capability_line = next((ln for ln in body.splitlines() if ln.startswith("以下能力目前没有提供")), "")
    for term in unavailable:
        check(f"明示未提供能力：{term}", term in capability_line)
    check("未提供能力统一给出替代方案", "给出一个文字层面能做的替代" in body)

    fake_promises = find_capability_mentions(body, [
        "get_screenshot", "send_message_to_user", "tts_speak", "listen_audio",
        "df_bili_navigate", "df_bili_read", "df_bili_watch", "future_task",
        "memorize_long_term_memory", "ADB", "雷电模拟器", "虚拟安卓手机",
    ])
    check("正文不承诺未提供的工具/设备能力", not fake_promises, str(fake_promises))
    check("不声称刷过 B 站/看过视频",
          find_capability_mentions(body, ["刷了 B 站", "看过视频", "刷过 B 站"]) == [])
    check("不把已执行结果说成已完成",
          "只有执行结果确认成功" in body and "不能用角色台词冒充完成" in body)
    check("语音能力如实说明", "如果本轮没有语音工具，就直接说明现在只能打字" in body)

    # 5) 文本健壮性：AstrBot 会把 system prompt 当 Jinja 模板渲染，也不能被命令前缀切走
    jinja_hits = [m for m in ("{{", "{%", "{#") if m in body]
    check("正文不含 Jinja 模板语法", not jinja_hits, str(jinja_hits))
    check("正文不含反斜杠", "\\" not in body)
    check("正文不用日式直角引号", "「" not in body and "」" not in body)
    check("正文控制字符干净", not any(ord(c) < 32 and c not in "\n\t" for c in body))

    # 6) 禁用语：示例与正文都必须为零
    #         正文里"已经发出、已经保存"是讲规则的禁止语句，不当作承诺命中。
    banned_patterns = [
        r"你不回我我就消失", r"你只能有我", r"不想活", r"红包发我", r"转我钱",
        r"打钱", r"把钱转给", r"我查过了", r"已经记住了", r"已经发出(?!、)",
    ]
    example_text = "\n".join(v for k, v in sec.items() if "示例" in k)
    for p in banned_patterns:
        check(f"示例口吻不含禁用语 {p!r}", not re.search(p, example_text))
        check(f"system prompt 不含禁用语 {p!r}", not re.search(p, body))
    check("示例里的发语音/发图请求被拒绝",
          "暂时发不了图" in example_text)
    check("状态文件初始为 stranger",
          json.loads(STATE.read_text(encoding="utf-8"))["stage"] == "stranger")

    # 7) 安装脚本：存在、只依赖标准库、默认路径与 persona_id 对得上
    check("安装脚本存在", INSTALLER.is_file())
    script = INSTALLER.read_text(encoding="utf-8") if INSTALLER.is_file() else ""
    check("安装脚本只用标准库（无第三方 import）",
          not re.search(r"^\s*(import|from)\s+(requests|aiohttp|yaml|sqlmodel|astrbot)\b", script, re.M))
    conventions = {
        "容器内人格文件路径": DEFAULT_PERSONA_PATH,
        "容器内数据库路径": DEFAULT_DB_PATH,
        "容器内配置路径": DEFAULT_CONFIG_PATH,
        "persona_id 常量": 'PERSONA_ID = "dafeiyu-girlfriend"',
        "--check 开关": '"--check"',
        "原子替换": "os.replace",
        "SQLite 在线备份": "backup(",
        "UPSERT 写入": "INSERT INTO personas" in script and "UPDATE personas" in script,
        "只改 persona_id": "agent_runner.config.persona.persona_id",
    }
    for label, needle in conventions.items():
        found = needle if isinstance(needle, bool) else (needle in script)
        check(f"安装脚本含约定：{label}", found)
    check("安装脚本不出现密钥字段名",
          not re.search(r"api_key|password|sk-|token", script, re.I))
    check("安装脚本不 import 网络库", not re.search(r"^\s*(import|from)\s+(socket|http|urllib|ssl)\b", script, re.M))

    # 8) 关系阶段配置
    stages = json.loads(STAGES.read_text(encoding="utf-8"))
    check("阶段配置含三阶段", set(stages["stages"]) == {"stranger", "familiar", "close"})
    check("默认阶段为 stranger", stages["default_stage"] == "stranger")
    check("stranger 阶段禁止爱称与主动联系",
          stages["stages"]["stranger"]["allow"]["pet_names"] is False
          and stages["stages"]["stranger"]["allow"]["proactive_contact"] is False)
    check("close 阶段主动联系需用户开启",
          stages["stages"]["close"]["allow"]["proactive_contact"] == "user_opt_in")
    orders = [s["order"] for s in stages["stages"].values()]
    check("阶段顺序单调", orders == [0, 1, 2])

    # 9) 三语策略
    lang = json.loads(LANG.read_text(encoding="utf-8"))
    check("中文策略：中文跟中文", lang["rules"]["zh"]["reply_language"] == "zh")
    check("韩语策略：韩语跟韩语", lang["rules"]["ko"]["reply_language"] == "ko")
    check("日语策略：仅短句", lang["rules"]["ja"]["reply_language"] == "ja_short_only"
          and lang["rules"]["ja"]["max_kana_chars"] <= 20)
    check("韩语敬语随阶段", "formal" in json.dumps(lang["rules"]["ko"]["korean_register_by_stage"]))
    check("非日语输入禁假名长串", lang["guard"]["max_kana_chars_when_input_not_ja"] == 0)

    # 人格正文与语言策略配置必须一致
    check("正文写明中文跟中文", "中文输入 → 简体中文回复" in persona)
    check("正文写明韩语跟韩语", "한국어 입력 → 한국어 회신" in persona)
    check("正文写明日语仅短句", "仅自然、短的寒暄" in persona)
    check("正文写明混合输入跟随主句", "跟随主句语言" in persona)
    check("正文韩语示例用 존댓말",
          "한국어로 답할 수 있어요" in body and "편하게 물어봐 주세요" in body)

    # 语言策略函数最小用例
    kana = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")
    hangul = re.compile(r"[\uac00-\ud7a3]")
    han = re.compile(r"[\u4e00-\u9fff]")

    def detect(text):
        ja_short_limit = lang["rules"]["ja"].get("input_short_kana", 8)
        if hangul.search(text):
            return "ko"
        kana_chars = kana.findall(text)
        if kana_chars:
            if len(kana_chars) > ja_short_limit:
                return "ja_long"
            return "ja_short"
        if han.search(text):
            return "zh"
        return "unknown"

    cases = [
        ("你好，今天吃了什么？", "zh"),
        ("안녕, 오늘 뭐 했어?", "ko"),
        ("お疲れさま", "ja_short"),
        ("今日はいい天気ですね、散歩に行きました", "ja_long"),
    ]
    for text, expect in cases:
        got = detect(text)
        check(f"语言检测 {text[:12]}… → {expect}", got == expect, f"got {got}")

    # 10) Compose 端口只绑 127.0.0.1
    compose = COMPOSE.read_text(encoding="utf-8")
    port_lines = re.findall(r'^\s*-\s*"([^"]*)"', compose, re.M)
    port_lines += re.findall(r"^\s*-\s*'([^']*)'", compose, re.M)
    host_ports = [l for l in port_lines if re.match(r"^(\d{1,3}\.){3}\d{1,3}:\d+:\d+$", l)]
    check("存在端口映射（两个容器各一个）", len(host_ports) >= 2, str(host_ports))
    bad = [l for l in host_ports if not l.startswith("127.0.0.1:")]
    check("所有宿主端口绑 127.0.0.1", not bad, "违规: " + str(bad))
    forbidden = ["18765", "16099", "13001", "6099:", "3001:", "6185:", "6199"]
    bad_ports = [f for f in forbidden if re.search(r"^(\S+:)?" + re.escape(f.rstrip(':')) + r":", compose, re.M)]
    check("宿主端口不与旧项目/上游冲突", not bad_ports, str(bad_ports))

    # 11) 敏感信息扫描（vendor/ 是第三方只读副本，临时演练目录也不属于产物）
    sensitive_patterns = [
        (r"sk-[A-Za-z0-9]{16,}", "API Key (sk-…)"),
        (r"(?<![\w.])1[3-9]\d{9}(?![\w.])", "疑似手机号"),
        (r"(?<![\d])[1-9]\d{4,10}(?![\d])\s*(号|QQ|qq)", "疑似 QQ 号"),
        (r"(100\.[0-9]+|tail[a]?scale)", "疑似 Tailscale 地址"),
    ]
    violations = []
    skip_dirs = {".git", ".tmp-smoke", "__pycache__", "node_modules", ".venv", "backups", "vendor"}
    for f in ROOT.rglob("*"):
        if not f.is_file() or f.suffix in {".png", ".jpg", ".zip", ".db", ".pyc"}:
            continue
        if skip_dirs & set(f.parts):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if f.name == "s0_checks.py":
            continue  # 扫描脚本自身写着这些模式定义
        for pat, label in sensitive_patterns:
            if re.search(pat, text):
                violations.append(f"{f.relative_to(ROOT)}: {label}")
    check("仓库无敏感信息", not violations, str(violations))

    failed = [r for r in results if not r[0]]
    print()
    print(f"共 {len(results)} 项检查，通过 {len(results) - len(failed)}，失败 {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
