# WIND 市场数据 MCP 服务

这是一个只读 MCP 服务，把 Oracle 中的股票类指数、A 股标的基础信息和股东大会信息提供给本机及局域网智能体。

目前提供四个工具：

- `get_index_by_code(code)`：按 `S_INFO_CODE` 精确查询，例如 `000300`；
- `search_indices_by_name(name, limit=20)`：按指数名称片段搜索，最多返回 100 条；
- `resolve_a_share(query, limit=10)`：按 Wind 代码、六位代码、证券简称、公司全称或名称片段识别 A 股公司；
- `get_shareholder_meetings(wind_code, meeting_date=None, limit=10)`：按代码或公司名称查询股东大会、召开时间、相关议案及表决结果。

服务不接受 SQL，不提供数据库写操作。查询使用固定 SQL 和 Oracle 绑定参数。

## A 股标的识别

`resolve_a_share` 是可供股东大会、行情、财务等领域复用的独立标的解析工具：

- `query="002311.SZ"`：按完整 Wind 代码精确识别；
- `query="002311"`：按六位股票代码精确识别；
- `query="海大集团"`：先按证券简称或公司全称精确识别；
- `query="海大"`：精确匹配不到时，对证券简称和公司全称做包含搜索；
- 唯一匹配时返回 `status="resolved"` 和公司基本资料；
- 多个匹配时返回 `status="ambiguous"` 和最多 `limit` 个候选，不会自动猜测；
- 无匹配时返回 `status="not_found"`；
- `limit` 默认 10、最大 50；输入中的 `%`、`_` 和 `\` 会按普通字符处理。

公司身份来自 `WIND_IMP.ASHAREDESCRIPTION`，公司简介来自 `WIND_IMP.ASHAREINTRODUCTION`，两表通过 `S_INFO_WINDCODE` 关联。存在多条公司简介时使用最新记录；没有简介时仍可返回代码、简称和全称。

## 股东大会查询

`get_shareholder_meetings` 的 `wind_code` 参数兼容原有完整 Wind 代码，同时支持六位代码、证券简称、公司全称和名称片段。例如，用户可以直接说“查询海大集团最近的股东大会议题”。名称存在多个候选时，服务会提示候选代码，用户指定后再查询。

- 不传 `meeting_date` 时，按会议日期倒序返回最近的股东大会；
- 传入 `meeting_date="20260820"` 时，只返回该日期召开的会议；
- `limit` 限制会议场数，默认 10、最大 50，不是议案条数；
- 每场会议的 `proposals` 包含议案序号、名称、表决方式、标准化结果和数据库原始结果；
- `result` 为 `passed`、`rejected` 或 `unknown`，分别表示通过、未通过和数据库未提供明确结果。
- 会议表只读取 `IS_NEW = 1` 或历史空值记录；`IS_NEW = 0` 表示已被更新版本替代，查询时会排除以免重复。

数据来自：

- `WIND_IMP.ASHAREDESCRIPTION`：Wind 代码、证券简称和公司全称；
- `WIND_IMP.ASHAREINTRODUCTION`：公司简介、地区、管理层、网站及主营业务等；
- `WIND_IMP.ASHAREHOLDERSMEETING`：大会日期、时间、类型、名称和会议内容；
- `WIND_IMP.ASHAREINTERNETVOTING`：逐项议案、表决方式和是否通过；
- 两表通过 `MEETEVENT_ID = S_EVENT_ID` 关联。

## 运行环境

- Windows 10/11；
- Python 3.11 或更高版本；
- 已准备可访问的 Oracle 主机、端口和 Service Name；
- 首版使用 `python-oracledb` Thin 模式，无需安装 Oracle Client。

## 安装

在 PowerShell 中运行：

```powershell
Set-Location 'D:\1.Project\19.CodexProject\9.MCP'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e '.[dev]'
```

将 `.env.example` 复制为 `.env` 并填写真实配置。本机已创建可运行的 `.env`；该文件被 `.gitignore` 排除，不会进入版本库。

## 本机 stdio 模式

手工启动时，进程会等待 MCP 客户端从标准输入发送消息：

```powershell
.\.venv\Scripts\python.exe -m index_mcp.run_stdio
```

Codex 使用项目级或用户级 `config.toml`。以下配置让 Codex 直接拉起本机服务：

```toml
[mcp_servers.wind_index]
command = 'D:\1.Project\19.CodexProject\9.MCP\.venv\Scripts\python.exe'
args = ["-m", "index_mcp.run_stdio"]
cwd = 'D:\1.Project\19.CodexProject\9.MCP'
required = true
default_tools_approval_mode = "auto"
```

保存配置后重启 Codex，在 `/mcp` 中检查 `wind_index`。Codex 官方文档说明其桌面端、CLI 和 IDE 扩展共享 MCP 配置，并支持 stdio 与 Streamable HTTP：[Codex MCP 文档](https://developers.openai.com/codex/mcp)。

## 局域网 HTTP 模式

启动服务：

```powershell
Set-Location 'D:\1.Project\19.CodexProject\9.MCP'
.\.venv\Scripts\python.exe -m index_mcp.run_http
```

当前配置：

- 本机地址：`http://127.0.0.1:8765/mcp`
- 局域网地址：`http://172.18.3.114:8765/mcp`
- 健康检查：`http://172.18.3.114:8765/health`
- MCP 端点必须携带 `Authorization: Bearer <MCP_API_KEY>`；
- `/health` 不要求 API Key，只返回 `{"status":"ok"}`。

如 Windows 防火墙阻止局域网连接，可在管理员 PowerShell 中只为本地子网开放端口：

```powershell
New-NetFirewallRule -DisplayName 'WIND Index MCP 8765' `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 `
  -RemoteAddress LocalSubnet
```

不要把 8765 端口直接映射到公网。跨不可信网络使用时，应在前置代理启用 HTTPS，并升级为 OAuth。

### Codex 连接局域网服务

先在运行 Codex 的电脑上设置一个环境变量，其值为服务端 `.env` 中的 `MCP_API_KEY`：

```powershell
$env:WIND_INDEX_MCP_API_KEY = '<从服务端安全复制 API Key>'
```

然后在 Codex `config.toml` 中配置：

```toml
[mcp_servers.wind_index_lan]
url = "http://172.18.3.114:8765/mcp"
bearer_token_env_var = "WIND_INDEX_MCP_API_KEY"
required = true
default_tools_approval_mode = "auto"
```

官方配置项 `bearer_token_env_var` 会从环境变量读取 Bearer Token，避免把密钥直接写入 `config.toml`。其他支持 Streamable HTTP 的 MCP 客户端使用同一 URL，并设置相同的 `Authorization` 请求头即可。

## 验证

运行自动化测试：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

验证 stdio 端到端调用：

```powershell
.\.venv\Scripts\python.exe .\scripts\smoke_test.py stdio
```

HTTP 服务启动后，在另一个 PowerShell 窗口验证：

```powershell
.\.venv\Scripts\python.exe .\scripts\smoke_test.py http
```

## 配置项

| 变量 | 说明 | 默认/示例 |
|---|---|---|
| `ORACLE_HOST` | Oracle 主机 | `your_oracle_host` |
| `ORACLE_PORT` | Oracle 端口 | `1521` |
| `ORACLE_SERVICE_NAME` | Oracle Service Name | `your_service_name` |
| `ORACLE_USER` | 只读账号 | 必填 |
| `ORACLE_PASSWORD` | 数据库密码 | 必填、秘密 |
| `ORACLE_POOL_MIN` | 最小连接数 | `1` |
| `ORACLE_POOL_MAX` | 最大连接数 | `5` |
| `ORACLE_CONNECT_TIMEOUT_SECONDS` | TCP/取连接超时 | `10` |
| `ORACLE_CALL_TIMEOUT_MS` | 单次 Oracle 调用超时 | `30000` |
| `MCP_HTTP_HOST` | HTTP 监听地址 | `0.0.0.0` |
| `MCP_HTTP_PORT` | HTTP 端口 | `8765` |
| `MCP_HTTP_PATH` | MCP 路径 | `/mcp` |
| `MCP_API_KEY` | HTTP Bearer API Key | 至少 32 字符 |
| `MCP_ALLOWED_HOSTS` | Host 白名单，逗号分隔 | `localhost:*,127.0.0.1:*` |
| `LOG_LEVEL` | 日志等级 | `INFO` |

如果 DHCP 导致服务器局域网 IP 变化，需要同时更新 `.env` 中的 `MCP_ALLOWED_HOSTS` 和客户端 URL。

## API Key 轮换

生成新 Key：

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

把输出写入服务端 `.env` 的 `MCP_API_KEY`，重启 HTTP 服务，再更新各客户端的环境变量。不要把 Key 提交到 Git、聊天记录或日志。

## 扩展其他表

每张新表或每组紧密相关的查询建立独立领域模块：

```text
src/index_mcp/domains/<domain>/
├─ models.py
├─ repository.py
├─ service.py
└─ tools.py
```

Repository 只能保存固定、参数化的只读 SQL；Service 负责输入规范化和业务边界；Tools 负责 MCP 契约。在 `server.py` 注册新工具即可复用现有连接池、鉴权、日志和双传输入口。

## 安全说明

- `.env` 和 `.venv` 已被 Git 忽略；
- stdio 日志只写 `stderr`，不会污染 MCP 协议流；
- HTTP 使用 Bearer API Key 和 Host 白名单；
- CORS 默认关闭；
- API Key over HTTP 只适用于可信局域网，网络监听者仍可能截获明文流量；
- 数据库账号应在 Oracle 侧保持最小只读权限。
