# 两台 Windows 电脑通过 Tailscale 双向管理员 SSH 控制

这套方案让两台用户自有的 Windows 电脑互相执行管理员级命令，同时保留清晰的身份边界和撤销路径。

## 安全模型

- 每台电脑各自生成一把专用 ED25519 密钥；**私钥永远只留在生成它的电脑上**。
- GitHub 私密仓库或协调 Issue 只传公钥和 SHA256 指纹，不传私钥、密码、Token、二维码或聊天正文。
- SSH 入站防火墙只允许另一台电脑的 Tailscale IP，不向局域网或公网开放。
- 第一次登录前必须独立核对目标电脑的 ED25519 主机指纹；不一致立即停止。
- 管理员 SSH 能控制文件、服务、Docker、计划任务和普通桌面进程，但不能代替人在 UAC 安全桌面、QQ 扫码或 BIOS 界面上的确认。
- 这不是 SYSTEM 后门。它使用 Windows 官方 OpenSSH、管理员组、公钥 ACL 和防火墙规则，随时可撤销。

## 每个方向都执行一次

以下把发起连接的电脑称为 A，被控制的电脑称为 B。反向控制时交换 A/B。

### 1. 在 A 生成专用密钥

普通 PowerShell：

```powershell
ssh-keygen -t ed25519 -a 64 -f "$env:USERPROFILE\.ssh\id_ed25519_mutual_control" -C "mutual-control-$(Get-Date -Format yyyy-MM-dd)"
ssh-keygen -lf "$env:USERPROFILE\.ssh\id_ed25519_mutual_control.pub" -E sha256
Get-Content "$env:USERPROFILE\.ssh\id_ed25519_mutual_control.pub"
```

只把最后两条命令显示的**公钥行和公钥指纹**交给 B。不要读取或发送没有 `.pub` 后缀的文件。

### 2. 在 B 授权 A

在 B 打开“管理员 PowerShell”，进入仓库目录后执行：

```powershell
& .\scripts\windows\Install-MutualSshAdmin.ps1 `
  -AuthorizedPublicKey 'ssh-ed25519 AAAA... A的注释' `
  -AllowedRemoteTailscaleIp 'A的Tailscale-IP' `
  -AdminUser 'B上的管理员用户名' `
  -FirewallRuleName 'Dafeiyu-SSH-From-A'
```

脚本会保留已有授权公钥、添加 A 的公钥、修正管理员公钥文件 ACL、设置 PowerShell 为 SSH shell、验证 sshd 配置、限制防火墙来源并重启 sshd。它会输出 B 的主机公钥和 SHA256 指纹，供 A 固定验证。

### 3. 在 A 固定指纹并做只读测试

```powershell
& .\scripts\windows\Test-PinnedSsh.ps1 `
  -TargetHost 'B的Tailscale主机名或IP' `
  -User 'B上的管理员用户名' `
  -IdentityFile "$env:USERPROFILE\.ssh\id_ed25519_mutual_control" `
  -ExpectedHostFingerprint 'SHA256:由B输出的准确指纹'
```

脚本只在指纹完全一致后运行 `whoami; hostname`。通过后，A 才拥有对 B 的管理员命令行控制。

### 4. 建立反向控制

在 B 生成另一把专用密钥，只把 B 的 `.pub` 公钥交给 A；然后在 A 运行安装脚本，并在 B 运行固定指纹测试脚本。不要让两台电脑共用同一把私钥。

## 撤销某一个方向

在被控制电脑的管理员 PowerShell 中执行：

```powershell
& .\scripts\windows\Revoke-MutualSshAdmin.ps1 `
  -AuthorizedPublicKey '要撤销的完整 ssh-ed25519 公钥行' `
  -FirewallRuleName '对应规则名' `
  -RemoveFirewallRule
```

脚本只删除完全匹配的那一行公钥，并保留其他授权。它会先在 `C:\ProgramData\ssh` 留一份时间戳备份。

## 完成后的加固

两边都通过公钥测试后，可以另行评估关闭 SSH 密码登录。初次握手阶段不要关闭，以免同时把两边锁在外面。不要关闭 Windows Defender、防火墙或 UAC，也不要把 22 端口映射到公网。

