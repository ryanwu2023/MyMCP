# 2026-08-13 验收记录

环境：Windows、Python 3.14.2、MCP Python SDK 2.0.0、python-oracledb 4.0.2。

## 自动化测试

命令：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

结果：20 项测试全部通过。覆盖配置校验、Bearer API Key、Oracle 值序列化、SQL 绑定参数、`LIKE` 转义、业务边界和 MCP 工具注册/调用。

## Oracle 数据验证

- 已配置的 Oracle 测试环境连接成功；
- `SELECT 1 FROM DUAL` 成功；
- `S_INFO_CODE = '000300'` 返回 `000300.SH / 沪深300`；
- 名称片段“沪深300”查询成功；
- CLOB 字段 `INDEX_INTRO` 已读取为正文字符串，不返回 LOB 定位器对象；
- 查询使用固定 SQL 与绑定变量。

## stdio MCP

通过独立子进程启动 `python -m index_mcp.run_stdio`，结果：

- `list_tools` 返回 `get_index_by_code`、`search_indices_by_name`；
- 精确查询 `000300` 成功；
- 名称搜索“沪深300”、`limit=3` 返回 3 条并标记 `truncated=true`；
- 日志写入 `stderr`，协议输出未被污染。

## Streamable HTTP MCP

通过 `python -m index_mcp.run_http` 在 `0.0.0.0:8765` 临时启动并在验收后停止，结果：

- `GET /health` 返回 `{"status":"ok"}`；
- 未携带 API Key 的 `POST /mcp` 返回 HTTP 401；
- 携带正确 Bearer API Key 后，`list_tools` 和两个工具调用成功；
- 通过实际 WLAN 地址 `172.18.3.114:8765/mcp` 的带鉴权调用成功，验证监听地址与 Host 白名单；
- 精确查询返回 `000300 / 沪深300`；
- 名称搜索返回代码 `000300`、`000300CAD13`、`000300CAD14`；
- 测试完成后端口 8765 不再监听。

本记录不包含数据库密码或 MCP API Key。
