# AnythingLLM MCP Server

把 [AnythingLLM](https://anythingllm.com/) 的**工作区管理、文档上传与向量化、检索问答**三类能力
封装为 MCP 工具，供任意 MCP 客户端（xAgent / opencode / Claude Desktop 等）调用。

- 传输：`stdio`（默认）与 `streamable-http` 两种
- 依赖：`mcp[cli]>=2.0.0`、`httpx`、`python-dotenv`
- 上游：AnythingLLM Desktop / Docker，默认 `http://localhost:3001`

## 1. 工具清单

| 工具 | 能力类别 | 请求的 AnythingLLM 端点 | 说明 |
| --- | --- | --- | --- |
| `list_workspaces` | 工作区管理 | `GET /api/v1/workspaces` | 返回 slug / 名称 / 文档数，供模型选工作区 |
| `create_workspace` | 工作区管理 | `POST /api/v1/workspace/new` | 新建工作区，返回 slug |
| `list_workspace_documents` | 文档管理 | `GET /api/v1/workspace/{slug}` | 列出已向量化文档、字数与 token 估算 |
| `upload_document` | 文档上传 + 向量化 | `POST /api/v1/document/upload`<br>`POST /api/v1/workspace/{slug}/update-embeddings` | 上传本地文件 → 加入工作区 → 触发向量化（`embed=false` 可跳过） |
| `ask_workspace` | 检索问答 | `POST /api/v1/workspace/{slug}/chat` | `mode=query` 仅依据资料回答，`chat` 允许模型自身知识 |

除 `list_workspaces` / `create_workspace` 外，其余工具都接受可选的 `workspace_slug`；
不传时回退到环境变量 `ANYTHINGLLM_WORKSPACE_SLUG`。

## 2. 配置

在**仓库根目录**创建 `.env`（已被 `.gitignore` 忽略，切勿提交）：

```dotenv
ANYTHINGLLM_BASE_URL=http://localhost:3001
ANYTHINGLLM_API_KEY=your-api-key
ANYTHINGLLM_WORKSPACE_SLUG=your-workspace-slug
ANYTHINGLLM_TIMEOUT=120
```

| 变量 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `ANYTHINGLLM_BASE_URL` | 否 | `http://localhost:3001` | 服务地址，末尾不要带 `/api` |
| `ANYTHINGLLM_API_KEY` | **是** | 空 | AnythingLLM 后台 → Settings → API Keys 生成 |
| `ANYTHINGLLM_WORKSPACE_SLUG` | 否 | 空 | 未在工具参数里指定工作区时使用 |
| `ANYTHINGLLM_TIMEOUT` | 否 | `120` | 单次请求超时（秒） |

缺少 `ANYTHINGLLM_API_KEY` 时，工具调用会立即返回
`ANYTHINGLLM_API_KEY 未设置：请在项目根目录 .env 中配置…`，不会发出空鉴权请求。

## 3. 运行

```bash
pip install "mcp[cli]>=2.0.0" httpx python-dotenv

# stdio（默认，由 MCP Host 拉起）
python -m AnythingLLMMCP

# Streamable HTTP（供 Agent/office/.mcp.json 的 8091 端点使用）
python -m AnythingLLMMCP --transport streamable-http --host 127.0.0.1 --port 8091
```

## 4. 接入 MCP 客户端

`stdio`：

```json
{
  "mcpServers": {
    "AnythingLLMMCP": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "AnythingLLMMCP"]
    }
  }
}
```

`streamable-http`（与 `Agent/office/.mcp.json` 一致）：

```json
{
  "mcpServers": {
    "AnythingLLMMCP": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:8091/mcp"
    }
  }
}
```

## 5. 调用示例

```text
# 1) 看有哪些工作区
list_workspaces()
→ 共 2 个工作区：
  - 课程资料（slug: course-notes，文档 12 个）
  - 临时（slug: tmp，文档 0 个）

# 2) 上传并向量化
upload_document(file_path="D:/notes/llm.md", workspace_slug="course-notes")
→ 已上传 1 个文档到工作区 course-notes：
  - llm.md
  已完成向量化：custom-documents/llm.md-1a2b3c.json

# 3) 检索问答
ask_workspace(question="MCP 的传输方式有哪几种？", workspace_slug="course-notes")
→ <回答正文>
  [来源] [...]
```

## 6. 失败场景

| 场景 | 返回 |
| --- | --- |
| 未配置 API Key | `ANYTHINGLLM_API_KEY 未设置：…`（本地前置校验，不发请求） |
| Key 无效 / 无权限 | `…失败：鉴权被拒绝（HTTP 401/403），请检查 ANYTHINGLLM_API_KEY` |
| 工作区 slug 不存在 | `…失败：AnythingLLM 返回 HTTP 404，…` |
| 上传路径不存在 | `上传文档失败：本地文件不存在 <path>` |
| 上传成功但向量化失败 | `上传成功但向量化失败：…`（明确区分两个阶段） |
| 上游 5xx / 网络抖动 | 传输层自动重试 2 次；仍失败则返回带状态码的错误 |
