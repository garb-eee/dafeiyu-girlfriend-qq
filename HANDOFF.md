# 大肥鱼 QQ 项目 · Codex 交接说明

更新时间：2026-11-10 11:35（Asia/Seoul）

## 目标与边界

这是“大肥鱼女朋友 QQ”独立项目，与七海人格、微信项目和旧大肥鱼实验完全分离。
目标是使用 AstrBot + NapCat + OneBot v11，在用户指定电脑上运行一个有明确边界、可回滚的 QQ 伴侣。

禁止把 API Key、NapCat Token、QQ 号、二维码、SSH 私钥或真实聊天正文写入仓库、交接包或回复。
不要同时在两台电脑启动同一个 QQ 账号，避免互踢与风控。

## 已有真实证据

- 当前运行主机：三星 Windows 11 电脑，Docker Desktop + WSL2。
- AstrBot：`soulter/astrbot:v4.29.0`，容器 `dfyqq-astrbot`。
- NapCat：`mlikiowa/napcat-docker:v4.18.37`，容器 `dfyqq-napcat`。
- 宿主端口仅绑定回环：AstrBot `127.0.0.1:28765`，NapCat `127.0.0.1:26099`。
- OneBot 使用 Docker 私网反向 WebSocket：`ws://astrbot:6199/ws`，6199 不映射宿主。
- QQ 曾完成扫码登录，AstrBot 历史日志出现 `aiocqhttp(OneBot v11) 适配器已连接`；这条是历史验收证据，不代表当前仍在线。
- DSFlash `deepseek-v4.1-flash` 已完成真实 API 请求并被 AstrBot 设为默认聊天模型。
- `dafeiyu-girlfriend` 人格已写入 AstrBot personas 表，重启后检查一致。
- 已真实收到一条主人私聊，并由 DSFlash 生成、大肥鱼人格回复、NapCat 实际发送成功。
- 白名单已重新锁定为唯一主人 QQ；本文不记录号码。
- 主动消息未安装、未开启；不会主动联系。
- 语音未安装、未开启。

## 2026-11-10 当前实测状态

- `dfyqq-astrbot` 与 `dfyqq-napcat` 容器都在运行，最近一次启动后重启计数均为 0；管理端口仍只绑定回环地址。
- **QQ 当前未登录。** NapCat 日志持续出现 `Login Error, ErrType: 1, ErrCode: 3`，并约每两分钟重新生成扫码二维码。
- 因 QQ 未登录，当前不能把“容器运行”解读为“OneBot 可收发”；恢复服务需要用户本人扫描 NapCat 当前二维码并在手机 QQ 授权。
- AstrBot 的历史日志仍能证明 OneBot、默认 DSFlash provider、人格与白名单曾成功加载，但扫码恢复后必须重新做一次真实收发验收。
- `dfyqq-ollama` 仍为停止状态；LivingMemory 工作保持暂停。

## 暂停状态

- 已新增隔离的 `dfyqq-ollama` 服务，镜像固定摘要，无宿主端口，限 3 GiB / 4 CPU。
- `bge-m3` 已下载并通过真实嵌入测试：1024 维，首次约 18 秒。
- 用户随后要求暂停，因此 `dfyqq-ollama` 当前已停止。
- LivingMemory 尚未安装，AstrBot 尚未配置 embedding provider。未经用户恢复授权不要继续这条线。

## 本地私密状态（不得上传）

- `.env.runtime`：NapCat 快速登录账号，本地存在并由 `.gitignore` 排除。
- AstrBot 命名卷：包含模型 provider、DSFlash Key、persona、白名单与数据库。
- NapCat 配置卷和 QQ 数据卷：包含 Token、QQ 身份与登录态。
- Ollama 模型卷：包含 `bge-m3`。

这些数据只能通过用户授权的 SSH 加密迁移，不得进入 GitHub 或交接 ZIP。

## 当前 compose 资源

- 网络：`dfyqq-network`
- 卷：
  - `dfyqq-astrbot-data`
  - `dfyqq-napcat-config`
  - `dfyqq-qq-data`
  - `dfyqq-ollama-data`
- 容器：
  - `dfyqq-astrbot`：运行，重启计数 0
  - `dfyqq-napcat`：运行，重启计数 0；QQ 登录态失效，等待扫码
  - `dfyqq-ollama`：停止

## 迁移目标现状

- Tailscale 中在线候选：`laptop-r1mnf5n3`。
- Tailscale 当前在线且直连已建立。
- 目标机 Windows OpenSSH 已运行，SSH 22 端口可达；ED25519 主机指纹已与源机固定记录核对一致。
- 使用迁移专用密钥做只读 `whoami; hostname` 测试时被目标机拒绝为 `Permission denied (publickey,...)`，说明迁移公钥尚未写入目标机管理员授权文件，因此尚未开始传输。
- 当前源实例仍在三星电脑运行。
- 迁移专用 SSH 公钥已在源电脑创建；私钥只留在源电脑。

目标机已知管理员用户名为 `sanalover`。下一步只需把源机迁移公钥写入
`C:\ProgramData\ssh\administrators_authorized_keys` 并修正 ACL；公钥认证通过后，才能只读确认目标机的 Docker Desktop/Compose/WSL、磁盘和端口状态。

## 迁移时的硬性顺序

1. 只读检查目标机磁盘、Docker、端口和现有同名资源，禁止覆盖。
2. 在源机确认 OneBot、DSFlash、persona 和白名单仍健康。
3. 通知用户即将产生短暂停机。
4. 停止源机 `dfyqq-napcat` 与 `dfyqq-astrbot`，一致性导出四个命名卷和项目文件。
5. 通过 Tailscale SSH/SCP 传输；传输后核对哈希。
6. 在目标机创建独立目录、网络和卷并恢复数据。
7. 先启动 AstrBot，再启动 NapCat；Ollama 保持停止，除非用户明确恢复记忆工作。
8. 如果 QQ 快速登录失败，只请求用户重新扫码一次。
9. 验证 OneBot、模型、人设、白名单和真实 QQ 收发。
10. 目标验收前不得删除源备份；目标验收后源容器保持停止，避免 QQ 双登。

## 接手后的首轮只读检查

```powershell
docker compose ps
docker inspect -f '{{.Name}} restart={{.RestartCount}} status={{.State.Status}}' dfyqq-astrbot dfyqq-napcat
docker logs --since 10m dfyqq-astrbot 2>&1 | Select-String 'OneBot|dfyqq-dsflash|ERROR|Error'
docker logs --since 10m dfyqq-napcat 2>&1 | Select-String 'WebSocket|Login|ERROR|Error'
python .\tests\s0_checks.py
```

不要在日志输出中展示 Token、Key、二维码或完整 QQ 号。

## 重要文件

- `compose.yaml`：当前三星运行架构；包含停止中的 Ollama 服务。
- `persona/dafeiyu-chat.md`：生产人格唯一来源。
- `scripts/install_astrbot_persona.py`：人格安装与校验。
- `scripts/install_astrbot_platform.py`：OneBot 平台安装。
- `scripts/install_astrbot_provider_from_ccs.py`：从源机 CCS 安装 DSFlash，目标机不一定有 CCS；迁移时优先恢复 AstrBot 卷。
- `scripts/set_astrbot_test_access.py`：首次识别主人后收紧白名单。
- `tests/s0_checks.py`：离线约束检查。
- `README.md`：仍含部分早期 5060 规划文字；顶部状态已更新，但运行与迁移判断仍以本文和实时检查为准。

## 当前下一步

1. 用户在源机 NapCat WebUI 或本机二维码中重新扫码，恢复 QQ 登录；随后验证 OneBot 连接和一次真实收发。
2. 在目标机授权源机迁移公钥并修正管理员公钥文件 ACL，再重跑固定指纹只读 SSH 测试。
3. 两项都通过后，按上面的硬性顺序完成一致性备份、传输、恢复和目标机真实验收。
