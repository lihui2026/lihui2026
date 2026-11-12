# Pet Hospital MCP Server

把 Go 编写的《宠物医院管理系统》REST API 封装成符合 MCP 规范的 Server，
支持 `stdio` 与 `Streamable HTTP` 两种传输。

- 依赖：`mcp[cli]>=2.0.0`、`httpx`、`pydantic`（见 `pyproject.toml`）
- 上游：`pethospital.exe`，默认监听 `http://127.0.0.1:8080`
- 协议：MCP **2026-07-28**

## 1. 工具

| 工具 | REST 端点 | 说明 |
| --- | --- | --- |
| `pet-hospital-list-pets` | `GET /api/v1/pets` | 列出宠物档案，支持全文检索、多维筛选、排序、分页 |
| `pet-hospital-create-pet` | `POST /api/v1/pets` | 新增宠物档案（必填 `name`、`species`） |

`list-pets` 可选参数：`q` `name` `owner_name` `owner_phone` `species` `doctor` `disease`
`status` `min` `max` `sort_by` `order`（`asc`/`desc`）`page`（≥1）`page_size`（1–500）。

返回结构（`structuredContent`）：`pets[]`、`total`、`page`、`page_size`、`total_pages`、`total_cost`。
字段以 `snake_case` 暴露给模型，调用 REST API 时自动转成 `camelCase`（见 `server.py` 的 `FIELD_MAP`）。

## 2. 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PET_HOSPITAL_URL` | `http://127.0.0.1:8080` | 宠物医院 REST API 地址 |
| `MCP_TRANSPORT` | `stdio` | `stdio` 或 `streamable-http` |
| `MCP_HOST` | `127.0.0.1` | HTTP 监听地址 |
| `MCP_PORT` | `8090` | HTTP 监听端口（与 `../opencode.json`、`Agent/office/.mcp.json` 一致） |

## 3. 运行

```bash
# 前置：启动后端
..\windows\pethospital.exe

pip install -e ".[dev]"

python server.py                                                   # stdio
set MCP_TRANSPORT=streamable-http & set MCP_PORT=8090 & python server.py   # HTTP

uv run mcp dev server.py        # MCP Inspector 调试
python -m pytest test -v        # 测试（后端需在跑，否则依赖后端的用例自动 skip）
```

## 4. 接入示例

stdio（`opencode.json`）：

```json
{
  "mcp": {
    "pet-hospital": {
      "type": "local",
      "enabled": true,
      "command": ["python", "pet-hospital-mcp/server.py"]
    }
  }
}
```

Streamable HTTP：

```json
{
  "mcpServers": {
    "PetHospitalMCP": { "type": "streamable-http", "url": "http://127.0.0.1:8090/mcp" }
  }
}
```

## 5. 错误语义

| 场景 | 行为 |
| --- | --- |
| 参数不合法（如 `page_size=-1`） | pydantic 校验失败 → MCP `isError: true`，`content` 带字段名 |
| 上游业务错误（`code != 2xx`） | `PetHospitalError("API error (code=…): message")` → `ToolError` |
| 上游不可达 / 超时 | 传输层重试 2 次后 `ToolError("请求超时：GET …")` |
| 未知工具名 | MCP 层返回 `isError: true` |

## 6. 观测

- 首次启动打印 `[PetHospital] INFO GET /api/v1/pets → HTTP 200（120 ms）` 形式的调用日志（含耗时）；
- 连接池与重试在 `pet_hospital_client.py` 中统一配置（`httpx.AsyncHTTPTransport(retries=2)`）。

## 7. 测试

| 文件 | 覆盖 |
| --- | --- |
| `test/test_list_pets.py` | 工具注册与 schema、默认分页、筛选、最小花费、非法参数、stdio 端到端、创建后清理、字段映射单测 |
| `test/test_protocol.py` | 真实 HTTP 上的 `server/discover`、`tools/list`、`tools/call`、未知工具错误 |

需要后端的用例通过 `@requires_cost`（探测 `/health`）在无后端时自动跳过。
