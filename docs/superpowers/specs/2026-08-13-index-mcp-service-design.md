# 指数基础数据 MCP 服务设计

## 1. 背景与目标

在 Windows 主机上构建一个只读 MCP 服务，将 Oracle 数据库 `WIND_IMP.AINDEXDESCRIPTION` 中的股票类指数基础信息提供给智能体使用。服务必须同时支持：

- 本机智能体通过 `stdio` 连接；
- 局域网内其他智能体通过 Streamable HTTP 连接；
- HTTP 请求使用 Bearer API Key 鉴权；
- 后续可按相同模式扩展其他数据库表和 MCP 工具。

首版不提供任意 SQL、写操作、动态表名或动态排序能力，也不面向公网直接暴露。

## 2. 技术方案

采用 Python 官方 MCP SDK 与 `python-oracledb`：

- 官方 MCP SDK 提供 `stdio` 和 Streamable HTTP 两种传输；
- `python-oracledb` 默认使用 Thin 模式，避免强制安装 Oracle Client；
- Pydantic 用于配置与输入输出校验；
- pytest 用于自动化测试；
- `pyproject.toml` 管理依赖，同时支持 `uv` 和标准 `venv + pip`。

不采用第三方 MCP 抽象框架或 Node.js 实现，以减少依赖层级和 Windows Oracle 驱动复杂度。首版不引入 Docker。

## 3. 系统架构

```text
本机智能体 ── stdio ────────┐
                            ├── MCP 工具层 ── 领域服务/校验 ── Repository ── Oracle
局域网智能体 ── HTTP/API Key ┘
```

建议代码结构：

```text
src/index_mcp/
├─ core/
│  ├─ config.py
│  ├─ database.py
│  └─ auth.py
├─ domains/
│  └─ index_description/
│     ├─ models.py
│     ├─ repository.py
│     └─ tools.py
├─ server.py
├─ run_stdio.py
└─ run_http.py
```

职责边界：

- `core/config.py`：读取并验证环境变量；
- `core/database.py`：创建和关闭 Oracle 连接池，统一连接与调用超时；
- `core/auth.py`：校验 HTTP `Authorization: Bearer ...`；
- `models.py`：定义工具输入输出及 Oracle 值的 JSON 序列化；
- `repository.py`：保存固定 SQL，执行只读参数化查询；
- `tools.py`：把领域能力注册成 MCP 工具；
- `server.py`：组装所有领域模块；
- 两个运行入口只负责选择传输方式。

扩展其他表时，新建 `domains/<业务名>/` 并在 `server.py` 注册工具。新模块复用配置、连接池、鉴权和传输层，但必须拥有自己的固定参数化 SQL，不能演变成通用 SQL 网关。

## 4. MCP 工具契约

### 4.1 `get_index_by_code`

输入：

- `code: str`：指数代码，例如 `000300`。

行为：

- 去除首尾空格并转换为大写；
- 按 `S_INFO_CODE = :code` 精确查询；
- 固定增加 `S_INFO_INDEXTYPE = '股票类'`；
- 不接受空字符串。

输出：

```json
{
  "found": true,
  "data": {
    "S_INFO_CODE": "000300",
    "S_INFO_NAME": "沪深300"
  }
}
```

未找到时返回：

```json
{
  "found": false,
  "data": null
}
```

若异常数据导致同一代码出现多条记录，Repository 使用稳定排序取第一条，并写入不含数据内容的告警日志；首版不把重复记录暴露为不同响应结构。

### 4.2 `search_indices_by_name`

输入：

- `name: str`：指数名称片段；
- `limit: int = 20`：返回上限，允许范围为 1–100。

行为：

- 拒绝空名称；
- 使用绑定参数执行 `S_INFO_NAME LIKE :name_pattern`；
- 固定增加 `S_INFO_INDEXTYPE = '股票类'`；
- 按 `S_INFO_CODE`、`S_INFO_WINDCODE` 稳定排序；
- 内部最多读取 `limit + 1` 条，以判断是否截断。

输出：

```json
{
  "count": 1,
  "truncated": false,
  "items": []
}
```

`count` 是本次实际返回条数，不额外执行全量 `COUNT(*)`。

### 4.3 字段序列化

- Oracle 列名原样输出，便于与数据字典对应；
- `DATE`、`TIMESTAMP` 转为 ISO 8601 字符串；
- 数值保持 JSON 数值；
- `NULL` 转为 JSON `null`；
- 不返回数据库连接信息、SQL、绑定参数、API Key 或内部堆栈。

## 5. 数据访问与生命周期

所有 SQL 都由 Repository 常量定义。用户输入仅作为 Oracle 绑定变量，不能影响表名、字段名、过滤器或排序规则。

HTTP 进程启动时创建连接池，停止时关闭连接池。每次工具调用从池中借用连接，完成后立即归还。`stdio` 入口复用同一生命周期设计，因此两种传输调用相同业务代码并返回相同结构。

配置包括连接池最小/最大连接数、连接超时和调用超时，默认值保持保守。数据库账号应由数据库侧限制为只读权限；应用不执行 DDL、DML 或 PL/SQL。

## 6. 配置与秘密管理

本地 `.env` 保存实际数据库配置和 HTTP API Key，并由 `.gitignore` 排除。`.env.example` 只包含占位符和说明。

计划使用的环境变量：

```text
ORACLE_HOST
ORACLE_PORT
ORACLE_SERVICE_NAME
ORACLE_USER
ORACLE_PASSWORD
ORACLE_POOL_MIN
ORACLE_POOL_MAX
ORACLE_CONNECT_TIMEOUT_SECONDS
ORACLE_CALL_TIMEOUT_MS
MCP_HTTP_HOST
MCP_HTTP_PORT
MCP_HTTP_PATH
MCP_API_KEY
MCP_ALLOWED_HOSTS
LOG_LEVEL
```

API Key 不复用数据库密码。实现时生成一个高熵随机 Key 写入本地 `.env`，README 说明如何轮换。日志、异常和启动摘要均不得输出秘密值。

## 7. HTTP 安全设计

- MCP HTTP 端点默认路径为 `/mcp`；
- 所有 MCP HTTP 方法均要求 `Authorization: Bearer <API_KEY>`；
- 使用恒定时间比较校验 API Key；
- 未携带、格式错误或不匹配时返回未授权响应；
- `/health` 仅返回进程存活状态，不返回数据库状态、版本、主机名或配置内容；
- 使用可配置 Host 白名单保护服务，包含本机地址与实际局域网地址；
- CORS 默认关闭，因为首版面向原生 MCP 客户端而非浏览器页面；
- 服务只部署在可信局域网。若跨不可信网络或公网使用，必须在前置代理启用 HTTPS，并优先升级到 MCP OAuth 授权模式。

Bearer API Key 是本项目明确选择的简化鉴权方式，并非完整 OAuth 流程。客户端必须支持为 MCP HTTP 连接设置自定义 `Authorization` 请求头。

## 8. 错误处理与日志

- 缺少或无效配置：启动失败并指出变量名，不输出变量值；
- 输入无效：返回清晰的 MCP 工具错误；
- 未找到数据：返回正常的 `found: false` 或空列表；
- Oracle 连接、超时或查询错误：映射为稳定的服务错误消息，具体诊断只写服务端日志；
- HTTP 鉴权失败：不透露是 Key 缺失还是 Key 不匹配；
- 日志统一写入 `stderr`，确保不会污染 `stdio` 协议流；
- 访问日志不得包含 Authorization 头、Oracle 密码或完整连接描述符。

## 9. 测试与验收

自动化测试：

- 配置读取与缺失变量校验；
- 指数代码和名称的规范化；
- `limit` 边界；
- Oracle 日期、时间、数值及空值序列化；
- API Key Bearer 解析和恒定时间校验；
- Repository 使用绑定参数，输入不会出现在 SQL 文本中；
- 查无数据、数据库异常和结果截断行为；
- MCP 工具注册和返回结构。

真实环境验证：

1. 执行 `SELECT 1 FROM DUAL` 验证数据库连通性；
2. 按代码 `000300` 查询；
3. 按名称 `沪深300` 模糊搜索；
4. 通过 `stdio` 客户端执行 `list_tools` 与两个工具；
5. 通过 Streamable HTTP 客户端携带 Bearer Key 执行相同操作；
6. 验证不携带或携带错误 Key 的 HTTP 请求被拒绝；
7. 验证两种传输返回一致的业务数据。

## 10. 交付内容

- 可安装的 Python 项目与锁定的依赖范围；
- `.env.example`、本地 `.env` 和 `.gitignore`；
- `stdio` 与 HTTP 启动入口；
- 两个指数查询 MCP 工具；
- 自动化测试；
- Windows 安装、启动、客户端配置、API Key 轮换和扩展领域模块的 README；
- 数据库连通及双传输验收记录。

## 11. 非目标

- 任意 SQL 查询；
- 数据库写操作；
- 公网直接部署；
- 浏览器端 MCP 客户端与 CORS；
- 用户管理、多租户、细粒度授权或完整 OAuth；
- Docker/Kubernetes 部署；
- 首版同时封装其他数据表。

