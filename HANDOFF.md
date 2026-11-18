# 大肥鱼 QQ 项目 · Codex 交接说明

更新时间：2026-11-18（Asia/Seoul）

## 当前结论

当前主运行方式已切换为 Windows 上的独立 DSH profile，不要求 Docker。稳定工作区是 `D:\DafeiyuGirlfriend\qqgf`；DeepSeek Harness 只在本机监听控制端口。旧 AstrBot、NapCat、Ollama 容器数据仍保留，可作为兼容部署方案，但 Docker Desktop 不再是当前大肥鱼的启动前提。

仓库和回复中不得出现 API Key、NapCat Token、QQ 号、群号、二维码、SSH 私钥或真实聊天正文。不要在两台电脑同时启动同一 QQ 账号。

## 已启用能力

| 能力 | 运行状态 |
|---|---|
| DSFlash + 大肥鱼人格 | 已加载，作为默认聊天模型与人格 |
| 目标群普通消息 | 已开放；Group Chat Plus 决定是否回应，无需 `/` |
| 关系阶段 | 自有插件持久化；主人当前为 `close`，其他人固定按 `stranger` |
| 长期记忆 | LivingMemory 2.9.2 + Ollama `bge-m3`；嵌入实测 1024 维 |
| 主动联系 | 私聊和目标群均启用，带间隔、免打扰和连续未回复上限 |
| 情绪与时间感知 | affective core + schedule awareness 已加载 |
| QQ 表情 | face convert 已加载 326 个映射 |
| 语音输出 | Edge TTS 已配置；全局约 15% 概率同时发送文本和语音 |
| 语音输入 | 未配置 ASR，不保证能听懂语音条 |
| GitHub | DSH 插件已启用；仓库、PR、Issue、搜索和 REST GET，只读 |
| 韩国公开资料 MCP | 默认启用；法律、判例、DART 与政府公开资料，只读 |
| Naver / 中国 / 全球商品 MCP | 已固化进镜像；仅在本机凭据完整时启用 |

所有社区插件均固定到具体 Git 提交，详见 `plugins.lock.json`。Python 运行依赖固化在 `requirements.runtime.txt` 和 `docker/astrbot-plugins.Dockerfile`，AstrBot 当前使用本地镜像 `dfyqq-astrbot:v4.29.0-plugins`。

## 当前 DSH 虚拟空间

- Profile：`%USERPROFILE%\.dsh\profiles\desktop`
- 工作区：`D:\DafeiyuGirlfriend\qqgf`
- GitHub 登录：本机 GitHub CLI / Windows Credential Manager，仓库不保存 Token
- GitHub 默认仓库：`garb-eee/dafeiyu-girlfriend-qq`
- GitHub 写操作和 clone：默认禁用

安装器和边界说明见 [`dsh/README.md`](dsh/README.md)。

## 跨设备容器镜像

`.github/workflows/publish-ghcr.yml` 在主分支相关文件变化或手动触发时构建：

```text
ghcr.io/garb-eee/dafeiyu-girlfriend-qq:latest
```

目标设备使用 `compose.yaml` 与 `compose.portable.override.yaml` 拉取。私有 GHCR 包需要先用具有 `read:packages` 的凭据执行 `docker login ghcr.io`；也可以在 GitHub 包设置中把镜像改为公开。

## MCP 工具层

统一工具层遵循“每个领域一个主来源”的路由，不把同类搜索服务器全部交给模型：

- 韩国公共资料使用 `dfyqq-korea-public`。
- 韩国购物、Cafe、Blog、News 与本地搜索使用 `dfyqq-naver-search`。
- 淘宝、京东、拼多多使用 `dfyqq-china-shopping`。
- 美国、东南亚与跨境商品比较使用 `dfyqq-global-shopping`。

浏览器购物自动化、商家后台、购物车、订单和支付能力未接入。凭据只放本机忽略文件 `.env.mcp`；AstrBot 的 `mcp_server.json` 不保存密钥。安装与后续补 Key 的命令见 [`mcp/README.md`](mcp/README.md)。

## 当前策略

- 只允许唯一主人私聊和一个目标群进入伴侣能力范围；具体号码仅存在本机私密配置。
- 平台全局唤醒前缀保持 `/`，供命令使用；目标群普通消息由 Group Chat Plus 独立接管，避免重复回复。
- 群消息全部进入决策器，但并不要求每条都回复；启用注意力、人类化、动态回复和密度限制。
- LivingMemory 只处理当前主人和目标群，群上下文上限为 80 条。
- 主动私聊最短约 3 小时，群主动参与更稀疏；23:00–08:00 免打扰，连续未回复会停止追发。
- 主动联系插件自己的 TTS 关闭，统一由 AstrBot 全局 15% TTS 策略控制。

## 可复现安装

```powershell
docker compose build astrbot
docker compose up -d ollama astrbot napcat
.\scripts\install_pinned_plugins.ps1
docker exec dfyqq-astrbot python /AstrBot/data/dfyqq/scripts/configure_companion_runtime.py --group-id <目标群号>
docker exec dfyqq-astrbot python /AstrBot/data/dfyqq/scripts/install_mcp_suite.py
docker restart dfyqq-astrbot
```

`configure_companion_runtime.py` 不包含固定 QQ/群号；群号必须在本机执行时传入。脚本会备份配置、原子写入，并且不打印凭证或号码。

## 验收证据

- 所有 7 个插件均出现在 AstrBot 启动日志并完成加载。
- LivingMemory provider 检查通过，数据库和会话管理器完成初始化。
- AstrBot 容器可访问 `http://ollama:11434`，`bge-m3` 嵌入返回 1024 维有限数值。
- FAISS CPU 1.15.1 可导入，`IndexFlatL2` 可用。
- Edge TTS 真实合成测试成功，生成了非空 MP3 后已删除测试文件。
- OneBot v11 在插件集成和容器重建后重新连接。

LivingMemory 初始化日志会先记录可选 `faiss.swigfaiss_avx2` 模块缺失，然后回退到通用 FAISS 并成功完成初始化；当前不影响索引能力。Group Chat Plus 也会记录一次依赖恢复提示，随后插件完整加载。

## 建议的真实聊天验收

1. 在目标群发送一条不带 `/` 的普通消息，确认它会自然判断是否加入，而不是每条机械回复。
2. 主人私聊发送 `/关系状态`，应显示 `close`。
3. 主人发送 `/lmem status`，确认长期记忆状态。
4. 主人发送 `/语音状态`，确认语音输出设置。
5. 连续试养 3–7 天，重点观察：群回复密度、主动消息是否克制、记忆是否串群、情侣口吻是否自然。

## 运维检查

```powershell
docker compose ps
docker inspect -f '{{.Name}} restart={{.RestartCount}} status={{.State.Status}}' dfyqq-astrbot dfyqq-napcat dfyqq-ollama
docker logs --since 10m dfyqq-astrbot 2>&1 | Select-String 'OneBot|LivingMemory|GroupChatPlus|ProactiveChat|DafeiyuRelationship|ERROR|Error'
python .\tests\s0_checks.py
```

展示日志前必须过滤 Token、Key、二维码和完整 QQ 号。

## 回滚

- 快速静默：在 AstrBot 面板关闭平台或主动联系插件。
- 停止本项目：`docker compose stop`，不删除卷。
- 单插件回滚：从 AstrBot 面板禁用相应插件并重启；固定提交仍保留在 `plugins.lock.json`。
- 完整恢复：使用 `/AstrBot/data/dfyqq/backups/` 中的本机备份恢复配置。备份可能含凭证，只能留在本机私密卷。

## 迁移状态

迁移目标机此前可通过 Tailscale 到达，SSH 22 端口可达，但迁移公钥尚未获目标机授权，尚未开始传输。迁移时必须先停止源机 NapCat/AstrBot，备份四个命名卷并核对哈希；目标机验收前不删除源备份，验收后源容器保持停止，避免 QQ 双登。
