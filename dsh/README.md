# 无 Docker 的 DSH 运行方式

当前大肥鱼可以直接运行在独立 DSH profile 中，不要求 Docker。隔离边界由独立 profile、固定工作区、GitHub CLI 凭据存储和只读工具配置共同提供。

## 安装 GitHub 能力

```powershell
python .\scripts\install_dsh_github.py `
  --profile "$env:USERPROFILE\.dsh\profiles\desktop" `
  --workspace "D:\DafeiyuGirlfriend\qqgf" `
  --clone-into "D:\DafeiyuGirlfriend\github-checkouts"

$env:CI='true'
pnpm --dir "$env:USERPROFILE\.dsh\profiles\desktop" install
```

重启 DeepSeek Harness 后，大肥鱼会获得以下只读工具：仓库信息、PR/Issue 列表和详情、代码/提交搜索，以及 GitHub REST GET。默认仓库是 `garb-eee/dafeiyu-girlfriend-qq`。

写入 GitHub、clone、评论、合并、关闭 Issue/PR 均默认禁用。插件通过本机 GitHub CLI 的凭据访问 GitHub，仓库内不保存 Token。

检查安装是否一致：

```powershell
python .\scripts\install_dsh_github.py `
  --profile "$env:USERPROFILE\.dsh\profiles\desktop" `
  --workspace "D:\DafeiyuGirlfriend\qqgf" `
  --clone-into "D:\DafeiyuGirlfriend\github-checkouts" `
  --check
```

## 虚拟空间边界

- 稳定工作区：`D:\DafeiyuGirlfriend\qqgf`
- 独立 DSH profile：`%USERPROFILE%\.dsh\profiles\desktop`
- GitHub 凭据：Windows Credential Manager 中的 GitHub CLI 登录态
- 默认 GitHub 权限：只读
- QQ、模型 Key、聊天记录和记忆不得提交到仓库或容器镜像
