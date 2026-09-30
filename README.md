# MCP 项目集

基于 [Model Context Protocol](https://modelcontextprotocol.io/) 的三个 Python MCP Server 与配套 Web 控制台，用于把本地业务系统封装为 AI Agent 可调用的工具。

| 目录 | 说明 | 技术栈 |
| --- | --- | --- |
| [`anythingllm_mcp/`](anythingllm_mcp) | AnythingLLM 工作区问答 MCP Server | Python + MCP SDK + httpx |
| [`anythingllm_web/`](anythingllm_web) | AnythingLLM 网页管理控制台（单文件） | 原生 HTML/CSS/JS |
| [`pethospitalmcp/`](pethospitalmcp) | 宠物医院 REST API 数据代理 MCP Server | Python + MCP SDK v2 + httpx |

---

## 1. anythingllm_mcp — AnythingLLM 工作区问答

将 AnythingLLM 指定工作区的检索问答能力暴露为 MCP 工具 `ask_workspace`。

### 工具

| 工具名 | 参数 | 返回 |
| --- | --- | --- |
| `ask_workspace` | `question: str` | AI 回答文本 + 引用来源（JSON） |

### 配置

在**项目根目录**创建 `.env`（已被 `.gitignore` 忽略）：

```dotenv
ANYTHINGLLM_BASE_URL=http://localhost:3001
ANYTHINGLLM_API_KEY=your-api-key
ANYTHINGLLM_WORKSPACE_SLUG=your-workspace-slug
```

`ANYTHINGLLM_API_KEY` 与 `ANYTHINGLLM_WORKSPACE_SLUG` 为必填，缺失时工具调用会直接报错。

### 运行

```bash
pip install "mcp[cli]" httpx python-dotenv
python -m anythingllm_mcp          # stdio 传输，由 MCP Host 拉起
```

### 接入 MCP Host

```json
{
  "mcp": {
    "anythingllm": {
      "type": "local",
      "enabled": true,
      "command": ["python", "-m", "anythingllm_mcp"]
    }
  }
}
```

---

## 2. anythingllm_web — 网页管理控制台

单文件（`index.html`）的 AnythingLLM 管理界面，直接用浏览器打开即可。

### 功能

- 工作区列表查看 / 新建 / 切换
- 文档树（按目录分组）与列表两种视图
- 文档正文预览（元数据 + 全文）
- 多选批量删除 / 单条删除（兼容新版 `DELETE` 与旧版 `POST`）
- 多文件上传并自动嵌入当前工作区，带上传进度
- 配置（地址 / API Key）持久化到 `localStorage`

### 使用

```bash
# 打开页面
start anythingllm_web\index.html
```

在页面顶部填入 AnythingLLM 地址与 API Key 后点击「保存配置」。

> **API Key 不再硬编码在源码中**，请通过页面输入框填写。历史版本曾在 `index.html` 中内置过真实 Key，若你在其他地方复制过该文件，请到 AnythingLLM 后台**重新生成并吊销旧 Key**。

---

## 3. pethospitalmcp — 宠物医院数据代理

把 Go 编写的《宠物医院管理系统》REST API 包装为 MCP 2026-07-28 协议的 MCP Server，支持 stdio 与 Streamable HTTP 两种传输。

### 目录结构

```text
pethospitalmcp/
├── mcp-server-prompt.md        # MCP Server 开发提示词（协议规范与实现要求）
├── opencode.json               # opencode MCP 客户端配置示例
├── pet-hospital-mcp/           # MCP Server 本体（Python）
│   ├── pyproject.toml
│   ├── server.py               # 入口：工具定义、参数校验、传输选择
│   ├── pet_hospital_client.py  # 异步 HTTP 客户端 + 响应信封校验
│   └── test/
└── windows/                    # 宠物医院系统发行包（可执行文件 + 数据，已被 git 忽略）
```

### 工具

| 工具名 | REST 端点 | 说明 |
| --- | --- | --- |
| `pet-hospital-list-pets` | `GET /api/v1/pets` | 列出宠物档案，支持全文检索、多维筛选、排序、分页 |
| `pet-hospital-create-pet` | `POST /api/v1/pets` | 新增宠物档案（必填 `name`、`species`） |

`list_pets` 支持的过滤参数：`q` `name` `owner_name` `owner_phone` `species` `doctor` `disease` `status` `min` `max` `sort_by` `order` `page` `page_size`。

返回结构包含 `pets[]`、`total`、`page`、`page_size`、`total_pages`、`total_cost`，字段以 `snake_case` 暴露，调用 REST API 时自动转为 `camelCase`。

### 运行

需要先启动宠物医院后端（默认监听 `127.0.0.1:8080`）：

```bash
cd pethospitalmcp\pet-hospital-mcp

# stdio（默认，由 MCP Host 拉起）
uv run mcp run server.py --transport stdio

# Streamable HTTP
uv run mcp run server.py --transport streamable-http --host 127.0.0.1 --port 9090
```

也可以直接运行，环境变量控制后端地址与传输方式：

```bash
set PET_HOSPITAL_URL=http://127.0.0.1:8080
set MCP_TRANSPORT=streamable-http
set MCP_PORT=9090
python server.py
```

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PET_HOSPITAL_URL` | `http://127.0.0.1:8080` | 宠物医院 REST API 地址 |
| `MCP_TRANSPORT` | `stdio` | `stdio` 或 `streamable-http` |
| `MCP_HOST` / `MCP_PORT` | `127.0.0.1` / `9090` | HTTP 监听地址与端口 |

### 调试

```bash
uv run mcp dev server.py     # 启动 MCP Inspector
uv run pytest                # 运行测试
```

### 依赖的系统程序

`pethospitalmcp/windows/` 下是 Go 编译的 `pethospital.exe` 与 `data/pet.db`（含约 1000 条模拟数据）。二进制文件**不提交到仓库**，请从 [Releases](../../releases) 下载，或按 [`windows/README.md`](pethospitalmcp/windows/README.md) 中的说明自行编译。

---

## 快速开始（全部项目）

```bash
pip install "mcp[cli]" httpx python-dotenv pytest

# 1) AnythingLLM 问答
python -m anythingllm_mcp

# 2) 网页控制台：浏览器打开 anythingllm_web\index.html

# 3) 宠物医院 MCP（先启动 pethospital.exe）
cd pethospitalmcp\pet-hospital-mcp && python server.py
```

## 安全说明

- AnythingLLM 与宠物医院后端均为**明文 HTTP、本地/内网使用**设计，请勿直接暴露到公网。
- 凭据（API Key、`.env`）已加入 `.gitignore`，请勿硬编码进源码或提交到仓库。
- 宠物医院 REST API 无鉴权，MCP Server 同样不做鉴权，仅适用于可信网络环境。

## License

各子项目的授权以对应目录下的文件为准。
