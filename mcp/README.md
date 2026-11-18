# 大肥鱼统一 MCP 工具层

这套配置面向 AstrBot 容器，只选择互补来源，不把功能相近的 MCP 全部暴露给模型。当前电脑上的无 Docker DSH 运行方式与 GitHub 工具见 [`../dsh/README.md`](../dsh/README.md)。

| 服务 | 覆盖范围 | 默认状态 |
|---|---|---|
| `dfyqq-korea-public` | 韩国法律、判例、DART、政府公开资料、贸易与金融公开数据 | 开启 |
| `dfyqq-naver-search` | Naver Shopping、Cafe、Blog、News、Local | 有 Naver Key 时开启 |
| `dfyqq-china-shopping` | 淘宝、京东、拼多多官方开放平台 | 任一平台凭据完整时开启 |
| `dfyqq-global-shopping` | 美国、东南亚及跨境商品比较 | 有 BuyWhere Key 时开启 |

没有接入 Coupang/淘宝浏览器自动化、商家后台和重复搜索服务器。原因是它们会重复已有搜索能力，部分还可接触账号登录态、购物车、订单或支付页面，不符合本项目的只读边界。

## 安装

```bash
cp .env.mcp.example .env.mcp
# 只在本机编辑 .env.mcp；没有的 Key 留空

sg docker -c 'docker compose build astrbot'
sg docker -c 'docker compose up -d astrbot'
sg docker -c "docker exec dfyqq-astrbot \
  python /AstrBot/data/dfyqq/scripts/install_mcp_suite.py"
sg docker -c 'docker restart dfyqq-astrbot'
```

查看启用原因，不显示任何凭据：

```bash
sg docker -c "docker exec dfyqq-astrbot \
  python /AstrBot/data/dfyqq/scripts/install_mcp_suite.py --status"
```

凭据后来补齐时，需要重建容器环境并重新生成启用状态：

```bash
sg docker -c 'docker compose up -d --force-recreate astrbot'
sg docker -c "docker exec dfyqq-astrbot \
  python /AstrBot/data/dfyqq/scripts/install_mcp_suite.py"
sg docker -c 'docker restart dfyqq-astrbot'
```

## 凭据与隐私

- `.env.mcp` 永不提交 Git。
- 生成的 `mcp_server.json` 不含 Key，stdio 子进程继承 AstrBot 容器环境。
- 韩国公共资料服务是第三方远程 MCP，只发送公开检索词；不得把 QQ 号、私聊、长期记忆、Key 或其他个人资料放进查询。
- 中国商品 MCP 的 mock 模式只用于本地测试，生产配置默认禁用 mock，避免把假商品返回给用户。
- 商品工具只用于搜索、详情和比价；不接入购物车、订单、账户管理和支付。
