# MCP Server 开发提示词 — 宠物医院 Pet Hospital REST API 数据代理

> 版本：v2.0 | 协议版本：2026-07-28 | 语言：Python 3.10+ | 范围：仅实现 `pet-hospital-list-pets` 工具

---

## 一、项目背景与目标

### 源系统
**宠物医院管理系统（Pet Hospital REST API）** 是一个用 Go 标准库编写的本地宠物医院系统，核心文件位于 `D:\xitong\windows\`：

- `pethospital.exe` — 64位 Windows 可执行文件（已内嵌网页界面）
- `data/pet.db` — 内置嵌入式数据库（含 1008 条模拟数据）
- REST API 运行在 `http://127.0.0.1:8080`

### 建设目标
将 Pet Hospital 的 REST API 封装为符合 **MCP 2026-07-28 规范** 的 MCP Server。**本次仅实现 `pet-hospital-list-pets` 一个工具**——列出所有宠物档案，支持根据各种参数进行筛选。

### 核心约束
- MCP Server 通过 HTTP 调用 Pet Hospital REST API 获取数据
- **无鉴权**、**明文 HTTP**、仅限本地/内网
- 底层数据格式不变，MCP Server 仅做协议转换层
- **只实现 `pet-hospital-list-pets`，不实现其他工具**

---

## 二、MCP 协议规范要求（2026-07-28）

### 2.1 关键协议变更（必须遵守）

| 变更 | 说明 |
|------|------|
| **无状态协议核心** | 移除 `initialize`/`notifications/initialized` 握手；每个请求自包含 |
| **移除 `Mcp-Session-Id` 头** | 每个请求通过 `_meta` 携带协议版本和客户端信息 |
| **`resultType` 必填** | 所有结果必须包含 `resultType: "complete"` 或 `resultType: "input_required"` |
| **`server/discover` 替换 `initialize`** | 客户端通过 `server/discover` 获取服务能力 |
| **`_meta` 元数据** | 每个请求的 `_meta.io.modelcontextprotocol/*` 字段携带协议版本、客户端信息 |
| **`Mcp-Method` 和 `Mcp-Name` 头** | Streamable HTTP POST 请求必须包含 |
| **Standard Schema v4** | `inputSchema`/`outputSchema` 使用 Pydantic 模型生成 JSON Schema 2020-12 |
| **`listChanged` 能力** | `tools/list` 支持 `listChanged: true`，工具列表变化时发送通知 |
| **弃用：Roots/Sampling/Logging** | SEP-2577 弃用，不再使用 |

### 2.2 传输层要求
- 支持 **Streamable HTTP** 和 **stdio** 两种传输方式
- Streamable HTTP：`POST /mcp`，请求体为 JSON-RPC 2.0
- 请求头必须包含：
  ```
  MCP-Protocol-Version: 2026-07-28
  Mcp-Method: tools/call   (或 tools/list, server/discover 等)
  Mcp-Name: pet-hospital-list-pets
  Content-Type: application/json
  ```
- 响应体中 `_meta` 必须包含 `io.modelcontextprotocol/serverInfo`
- 无粘性会话、无状态 — 任何请求可被任何服务实例处理

### 2.3 工具定义规范
- **工具名**：`pet-hospital-list-pets`（1-128 字符，仅含字母、数字、下划线、连字符、点号）
- **`inputSchema`**：由 Pydantic 模型自动生成 JSON Schema 2020-12
- **`outputSchema`**：可选，定义结构化输出格式
- **`listChanged`**：设为 `true`，支持工具列表变更通知
- **工具结果**：必须包含 `resultType` 字段，内容放在 `content` 数组中

---

## 三、REST API → MCP Tool 映射

### 3.1 源 REST API 详情

基础 URL：`http://127.0.0.1:8080`

**统一响应信封**：
```json
{ "code": 200, "message": "ok", "data": { }, "time": "..." }
```

**核心接口**：`GET /api/v1/pets`

支持的查询参数：

| 参数 | 类型 | 说明 |
|------|------|------|
| `q` | string | 全文检索关键词（跨字段空格分词 AND，含病历全文） |
| `name` | string | 宠物姓名 |
| `ownerName` | string | 主人姓名 |
| `ownerPhone` | string | 主人电话 |
| `species` | string | 种类 |
| `doctor` | string | 医生 |
| `disease` | string | 疾病 |
| `status` | string | 就诊状态 |
| `min` | number | 最低总花费 |
| `max` | number | 最高总花费 |
| `sortBy` | string | 排序字段（如 `totalCost`, `name`） |
| `order` | string | 排序方向（`asc` / `desc`） |
| `page` | number | 页码（默认 1） |
| `pageSize` | number | 每页条数（默认 20） |

**Pet 档案字段**：`id`, `name`, `species`, `breed`, `gender`, `ageMonths`, `ownerName`, `ownerPhone`, `doctor`, `disease`, `status`, `totalCost`, `visitCount`

### 3.2 MCP Tool 设计

| MCP Tool Name | HTTP Method | REST Endpoint | 用途 |
|---|---|---|---|
| `pet-hospital-list-pets` | GET | `/api/v1/pets` | **唯一需要实现的工具**：列出宠物，支持全部过滤/排序/分页 |

---

## 四、技术栈

### Python MCP SDK v2

**安装**：
```bash
uv init pet-hospital-mcp
cd pet-hospital-mcp
uv add "mcp[cli]"
```

**关键依赖**：
- `mcp` — MCP Python SDK v2（已包含 pydantic, httpx, starlette, uvicorn）
- Python 3.10+

**启动方式**：
- **stdio 模式**（推荐，由 MCP Host 启动）：
  ```bash
  uv run mcp run server.py --transport stdio
  ```
- **Streamable HTTP 模式**：
  ```bash
  uv run mcp run server.py --transport streamable-http --host 127.0.0.1 --port 9090
  ```
  或在代码中：
  ```python
  await mcp.run(transport="streamable-http", host="127.0.0.1", port=9090)
  ```

### 数据获取
使用 `httpx` 异步 HTTP 客户端调用 Pet Hospital REST API（`mcp` 包已依赖 `httpx`）。

---

## 五、核心架构设计

```
┌─────────────────────────────────────────────┐
│              MCP Client (Agent)              │
│         tools/call, tools/list, discover     │
└──────────────────┬──────────────────────────┘
                   │  MCP 2026-07-28 (JSON-RPC over HTTP)
                   ▼
┌─────────────────────────────────────────────┐
│         Pet Hospital MCP Server              │
│                                              │
│  ┌─────────────┐    ┌────────────────────┐   │
│  │  MCPServer  │───▶│  @mcp.tool()      │   │
│  │  (Python)   │    │  pet-hospital-    │   │
│  │             │    │  list-pets        │   │
│  └─────────────┘    └────────┬───────────┘   │
│                              │               │
│  ┌───────────────────────────▼───────────┐   │
│  │  async list_pets()                    │   │
│  │  → httpx GET /api/v1/pets?...        │   │
│  │  → 转换响应为 MCP content            │   │
│  └───────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
                   │  HTTP GET
                   ▼
┌─────────────────────────────────────────────┐
│         Pet Hospital REST API               │
│              127.0.0.1:8080                  │
│         (pethospital.exe)                    │
└─────────────────────────────────────────────┘
```

---

## 六、代码实现要求

### 项目结构
```text
pet-hospital-mcp/
├── pyproject.toml
├── server.py              # 入口文件
├── pet_hospital_client.py # HTTP 客户端封装
└── test/
    └── test_list_pets.py  # 测试
```

### server.py — 入口文件
```python
from mcp.server import MCPServer
from pet_hospital_client import PetHospitalClient
from pydantic import BaseModel, Field
from typing import Optional

# Pydantic 模型定义输入参数
class ListPetsParams(BaseModel):
    q: Optional[str] = Field(default=None, description="全文检索关键词")
    name: Optional[str] = Field(default=None, description="宠物姓名")
    owner_name: Optional[str] = Field(default=None, description="主人姓名")
    owner_phone: Optional[str] = Field(default=None, description="主人电话")
    species: Optional[str] = Field(default=None, description="种类")
    doctor: Optional[str] = Field(default=None, description="医生")
    disease: Optional[str] = Field(default=None, description="疾病")
    status: Optional[str] = Field(default=None, description="就诊状态")
    min: Optional[float] = Field(default=None, description="最低总花费")
    max: Optional[float] = Field(default=None, description="最高总花费")
    sort_by: Optional[str] = Field(default=None, description="排序字段")
    order: Optional[str] = Field(default=None, description="排序方向 asc/desc")
    page: Optional[int] = Field(default=1, description="页码")
    page_size: Optional[int] = Field(default=20, description="每页条数")

# Pydantic 模型定义输出结构
class Pet(BaseModel):
    id: str
    name: str
    species: str
    breed: str
    gender: str
    age_months: int
    owner_name: str
    owner_phone: str
    doctor: str
    disease: str
    status: str
    total_cost: float
    visit_count: int

class ListPetsResult(BaseModel):
    pets: list[Pet]
    total: int
    page: int
    page_size: int

# 创建 MCP Server
mcp = MCPServer("pet-hospital", version="1.0.0")
client = PetHospitalClient(base_url="http://127.0.0.1:8080")

@mcp.tool()
async def list_pets(params: ListPetsParams) -> ListPetsResult:
    """
    列出宠物档案，支持根据各种参数进行筛选。

    支持的筛选条件包括：
    - 全文检索（q）
    - 按宠物姓名、主人姓名/电话、种类、医生、疾病、就诊状态筛选
    - 按总花费区间（min/max）筛选
    - 排序（sortBy/order）
    - 分页（page/pageSize）
    """
    # 构建查询参数
    query_params = {}
    if params.q:
        query_params["q"] = params.q
    if params.name:
        query_params["name"] = params.name
    if params.owner_name:
        query_params["ownerName"] = params.owner_name
    if params.owner_phone:
        query_params["ownerPhone"] = params.owner_phone
    if params.species:
        query_params["species"] = params.species
    if params.doctor:
        query_params["doctor"] = params.doctor
    if params.disease:
        query_params["disease"] = params.disease
    if params.status:
        query_params["status"] = params.status
    if params.min is not None:
        query_params["min"] = str(params.min)
    if params.max is not None:
        query_params["max"] = str(params.max)
    if params.sort_by:
        query_params["sortBy"] = params.sort_by
    if params.order:
        query_params["order"] = params.order
    if params.page:
        query_params["page"] = str(params.page)
    if params.page_size:
        query_params["pageSize"] = str(params.page_size)

    # 调用 Pet Hospital REST API
    response = await client.get("/api/v1/pets", params=query_params)

    # 解析并返回结构化结果
    data = response["data"]
    return ListPetsResult(
        pets=[Pet(**pet) for pet in data["pets"]],
        total=data["total"],
        page=data["page"],
        page_size=data["pageSize"],
    )

# stdio 模式运行（由 MCP Host 启动）
import asyncio
async def main():
    await mcp.run(transport="stdio")

if __name__ == "__main__":
    asyncio.run(main())
```

### pet_hospital_client.py — HTTP 客户端
```python
import httpx
from typing import Any, Dict

class PetHospitalClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self._client = httpx.AsyncClient(base_url=base_url, timeout=30.0)

    async def get(self, path: str, params: Dict[str, Any] = None) -> Dict:
        """发送 GET 请求到 Pet Hospital REST API"""
        response = await self._client.get(path, params=params)
        response.raise_for_status()
        data = response.json()
        # 验证响应信封
        if data.get("code") != 200:
            raise Exception(f"API error: {data.get('message')}")
        return data

    async def close(self):
        await self._client.aclose()
```

---

## 七、`server/discover` 实现

Python SDK 的 `MCPServer` 自动处理 `tools/list`、`server/discover` 等请求：
- `mcp = MCPServer("pet-hospital", version="1.0.0")` 声明服务标识
- `@mcp.tool()` 装饰器自动注册工具到 `tools/list` 响应
- `listChanged: true` 在装饰器中默认启用

SDK 会自动生成 `server/discover` 响应，包含：
- `protocolVersion: "2026-07-28"`
- `serverInfo: { name: "pet-hospital", version: "1.0.0" }`
- `capabilities: { tools: { listChanged: true } }`
- 工具列表及其 `inputSchema`（由 Pydantic 模型自动生成 JSON Schema）

---

## 八、错误处理规范

### 协议错误
| 场景 | Error Code | 说明 |
|------|-----------|------|
| 未知工具 | `-32602` | Invalid params |
| 缺少必需能力 | `-32021` | MissingRequiredClientCapability |
| 不支持的协议版本 | `-32022` | UnsupportedProtocolVersion |
| 服务器内部错误 | `-32603` | Internal error |

### 业务错误映射
Pet Hospital REST API 返回 `{ code, message, data, time }`：
- `code === 200` → `resultType: "complete"`，`isError: false`
- `code !== 200` → 抛出异常，SDK 自动转为 `resultType: "complete"`，`isError: true`

---

## 九、结果格式规范

`pet-hospital-list-pets` 工具的返回值必须符合 `ListPetsResult` 模型：

```python
ListPetsResult(
    pets=[...],   # Pet 对象列表
    total=100,    # 总记录数
    page=1,       # 当前页
    page_size=20  # 每页条数
)
```

SDK 会自动将返回值转为 MCP 结果格式，包含 `resultType: "complete"` 和 `structuredContent`。

---

## 十、开发步骤

1. **创建项目**：
   ```bash
   uv init pet-hospital-mcp
   cd pet-hospital-mcp
   uv add "mcp[cli]"
   ```

2. **编写 `pet_hospital_client.py`**：封装对 Pet Hospital REST API 的 HTTP 调用

3. **编写 `server.py`**：
   - 定义 `ListPetsParams` Pydantic 输入模型（含所有可选过滤参数）
   - 定义 `Pet` 和 `ListPetsResult` Pydantic 输出模型
   - 用 `@mcp.tool()` 装饰 `async def list_pets(params: ListPetsParams)`
   - 构建查询参数并调用 REST API
   - 返回结构化结果

4. **测试**：
   ```bash
   uv run mcp dev server.py
   ```
   打开 MCP Inspector，验证 `pet-hospital-list-pets` 工具的各种参数组合

5. **运行**：
   ```bash
   # stdio 模式
   uv run mcp run server.py --transport stdio

   # Streamable HTTP 模式
   uv run mcp run server.py --transport streamable-http
   ```

---

## 十一、参考资源

- MCP 规范：https://modelcontextprotocol.io/specification/2026-07-28/
- Python SDK v2 文档：https://py.sdk.modelcontextprotocol.io/
- Python SDK GitHub：https://github.com/modelcontextprotocol/python-sdk
- 宠物医院 REST API 文档：`D:\xitong\windows\README.md`
- 源项目：`D:\xitong\windows\`（Go 编写的 `pethospital.exe`）

---

## 十二、补充说明

1. **`pet-hospital-list-pets` 与 `pet-hospital-search-pets` 的区别**（后续迭代）：
   - `list-pets` 使用 `/api/v1/pets` 的结构化过滤参数（species, doctor, status 等）
   - `search-pets` 使用 `/api/v1/pets/search?q=` 的全文检索
   - 本次只实现 `list-pets`，`search-pets` 留待后续迭代

2. **Pydantic 字段命名**：Pydantic 模型字段名使用 snake_case（如 `owner_name`），但调用 REST API 时需要转为 camelCase（`ownerName`），可在 `pet_hospital_client.py` 中做转换

3. **由于源系统无鉴权**，MCP Server 也无需鉴权，但建议在 `description` 中提醒客户端注意安全

4. **`min`/`max` 参数**：Python 中 `min` 是内置函数名，模型中需使用 `min_val` 或保持为 `min` 并在文档中说明

5. **`mcp[cli]` 包含 `mcp dev` 命令**，用于启动 MCP Inspector 进行调试
