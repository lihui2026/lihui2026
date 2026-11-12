# LLM 技术与应用 · 期末项目

四个子项目，构成“把本地/第三方系统封装为 AI Agent 可调用工具”的完整链路：

| 目录 | 说明 | 技术栈 | 详见 |
| --- | --- | --- | --- |
| [`PetHospitalMCP/`](PetHospitalMCP) | 宠物医院 REST API → MCP Server（2 个业务工具，stdio + Streamable HTTP） | Python 3.10+ · MCP SDK v2 · httpx · pydantic | [`pet-hospital-mcp/README.md`](PetHospitalMCP/pet-hospital-mcp/README.md) |
| [`AnythingLLMMCP/`](AnythingLLMMCP) | AnythingLLM → MCP Server（工作区 / 文档向量化 / 检索问答，5 个工具） | Python 3.10+ · MCP SDK v2 · httpx | [`AnythingLLMMCP/README.md`](AnythingLLMMCP/README.md) |
| [`AnythingLLMServer/`](AnythingLLMServer) | AnythingLLM 网页控制台（单文件，直连 REST API） | 原生 HTML/CSS/JS | [`AnythingLLMServer/index.html`](AnythingLLMServer/index.html) |
| [`Agent/`](Agent) | 定制 Agent（xAgent）：TUI + 工具集 + 技能 + MCP 客户端 + 会话/压缩 | Python 3.10+ · Textual · MCP SDK v2 | [`Agent/xAgent/README.md`](Agent/xAgent/README.md) |

```
anythingllm_project/
├── README.md                     # 本文件：项目地图与总启动步骤
├── opencode.json                 # opencode 的 MCP 客户端配置示例
├── PetHospitalMCP/
│   ├── mcp-server-prompt.md      # 【历史设计稿】开发期提示词，与实际实现有差异
│   ├── opencode.json             # 单服务接入示例
│   ├── pet-hospital-mcp/         # MCP Server 本体
│   │   ├── README.md             # 该模块的配置与使用说明
│   │   ├── server.py             # 工具定义、参数校验、传输选择
│   │   ├── pet_hospital_client.py# 异步 HTTP 客户端（超时 / 重试 / 调用日志）
│   │   ├── pyproject.toml
│   │   └── test/                 # 单元 + 协议级测试
│   └── windows/                  # 宠物医院后端发行包（二进制，已 gitignore）
├── AnythingLLMMCP/               # AnythingLLM MCP Server（含 README）
├── AnythingLLMServer/
│   └── index.html                # 网页控制台
└── Agent/
    ├── Practice01/ Practice02/   # 课程练习（Function Call 演进过程）
    ├── xAgent/                   # 期末 Agent 主体（分层架构 + TUI）
    └── office/                   # Agent 工作目录：.mcp.json + .agents/skills
```

---

## 1. 环境依赖

| 依赖 | 版本/说明 | 用途 |
| --- | --- | --- |
| Python | ≥ 3.10（开发环境 3.13） | 全部 Python 子项目 |
| `mcp[cli]` | ≥ 2.0.0（v2 SDK：`MCPServer` / `ClientSession`） | MCP Server 与 Client |
| `httpx` `python-dotenv` | 最新 | AnythingLLM / 宠物医院 HTTP 调用 |
| `requests` `trafilatura` | 最新 | xAgent 的 `searchWeb` / `fetchWeb` |
| `textual` | ≥ 0.80 | xAgent 的 TUI |
| `curl` | 系统自带 | `fetchWeb` 抓取网页 |
| AnythingLLM | 本地或 Docker，默认 `http://localhost:3001` | B / C 的上游 |
| 宠物医院后端 | `PetHospitalMCP/windows/pethospital.exe`，默认 `127.0.0.1:8080` | A 的上游 |

> `PetHospitalMCP/windows/` 下的 `pethospital.exe`、`data/pet.db` 与发行 ZIP **不入库**
> （见 `.gitignore`），请从 Releases 下载，或按 `windows/README.md` 自行 `go build`。

一键装依赖：

```bash
pip install "mcp[cli]>=2.0.0" httpx python-dotenv requests trafilatura textual pytest
```

## 2. 配置矩阵

| 配置 | 位置 | 是否入库 | 字段 |
| --- | --- | --- | --- |
| 宠物医院 MCP | 环境变量 | — | `PET_HOSPITAL_URL`(默认 `http://127.0.0.1:8080`)、`MCP_TRANSPORT`(stdio / streamable-http)、`MCP_HOST`、`MCP_PORT`(默认 `8090`) |
| AnythingLLM MCP | 仓库根 `.env` | 否（`.gitignore`） | `ANYTHINGLLM_BASE_URL`、`ANYTHINGLLM_API_KEY`、`ANYTHINGLLM_WORKSPACE_SLUG`、`ANYTHINGLLM_TIMEOUT` |
| 网页控制台 | 页面顶部输入框 → `localStorage` | 否 | 服务地址、API Key（源码中不含密钥） |
| xAgent | `Agent/xAgent/config.ini` | 否（`config.ini` 被忽略，首次运行自动生成注释模板） | `[LLM]` `[MCP]` `[TOOLS]` `[search]` `[SESSION]` `[UI]`，见 [`Agent/xAgent/README.md`](Agent/xAgent/README.md) |
| MCP 客户端 | `Agent/office/.mcp.json` | 是（不含密钥） | `mcpServers.{name}.{type,url,command,args,env,cwd}` |

`.env` 模板（复制到仓库根，切勿提交）：

```dotenv
ANYTHINGLLM_BASE_URL=http://localhost:3001
ANYTHINGLLM_API_KEY=your-api-key
ANYTHINGLLM_WORKSPACE_SLUG=your-workspace-slug
```

## 3. 分步启动

### 3.1 宠物医院 MCP（A）

```bash
# ① 启动上游后端（监听 127.0.0.1:8080）
PetHospitalMCP\windows\pethospital.exe

# ② 启动 MCP Server
cd PetHospitalMCP\pet-hospital-mcp
pip install -e ".[dev]"
python server.py                                    # stdio（默认）

# 或切到 Streamable HTTP（端口 8090，与 opencode.json / office/.mcp.json 一致）
set MCP_TRANSPORT=streamable-http & set MCP_PORT=8090 & python server.py

# ③ 验证
uv run mcp dev server.py        # MCP Inspector
python -m pytest test -v        # 需要后端在跑
```

工具：`pet-hospital-list-pets`（14 个过滤/排序/分页参数）、`pet-hospital-create-pet`。

### 3.2 AnythingLLM MCP（B）

```bash
cd anythingllm_project            # 确认根目录已有 .env
pip install "mcp[cli]>=2.0.0" httpx python-dotenv
python -m AnythingLLMMCP                                            # stdio
python -m AnythingLLMMCP --transport streamable-http --port 8091    # 供 .mcp.json 的 8091 端点
```

工具：`list_workspaces`、`create_workspace`、`list_workspace_documents`、`upload_document`、`ask_workspace`。

### 3.3 网页控制台（C）

```bash
start AnythingLLMServer\index.html
```

在页面顶部填 `http://localhost:3001` 与 API Key → 「保存配置」。
地址填 `.../api` 或 `.../api/v1` 也可以，页面会自动去掉多余前缀再拼 `/api/v1`。

### 3.4 xAgent（D）

```bash
cd Agent\xAgent
pip install textual requests trafilatura "mcp[cli]"
python main.py
```

首次运行会在 `Agent/xAgent/config.ini` 生成带注释的完整配置；改好 `[LLM]` 的
`base_url` / `model` / `api_key` 后重启。
MCP 侧从 `Agent/office/.mcp.json` 读取（可用环境变量 `XAGENT_MCP_CONFIG` 覆盖），
把上面的 MCP Server 接进来即可在对话里直接调用其工具。

## 4. 验证清单

| # | 验证项 | 期望 |
| --- | --- | --- |
| 1 | `cd PetHospitalMCP/pet-hospital-mcp && python -m pytest test -v`（后端已启动） | 全部通过，`tools/list` 恰好 2 个工具 |
| 2 | 网页填好地址+Key 后点「刷新」 | 列出工作区；上传文件有进度条与「上传成功 N 个文档」 |
| 3 | `python -m AnythingLLMMCP` 后由 Host 调 `list_workspaces` | 返回工作区清单（说明 `.env` 与鉴权正确） |
| 4 | xAgent 输入 `/status` | 显示会话号、AGENT.md 注入状态、上下文用量 |
| 5 | xAgent 输入 `/tools` | 同时列出本地工具与 `服务名__工具名` 形式的 MCP 工具 |
| 6 | xAgent 对非空目录调 `removeDirectory` | 被拒绝，提示需 `recursive=true` |

## 5. 安全说明

- 所有密钥经环境变量 / 页面输入注入，**源码中不含任何凭据**；`.env`、`config.ini`、`*.key` 均已加入 `.gitignore`。
- 若曾把 `index.html` 连同真实 Key 复制到别处，请到 AnythingLLM 后台**吊销旧 Key**。
- 宠物医院 REST API 与 AnythingLLM 均为本地/内网明文 HTTP，**不要直接暴露到公网**；宠物医院后端无鉴权，MCP Server 亦不做鉴权。
- xAgent 的写/删工具支持用 `config.ini` 的 `[TOOLS] tool_workspace_root` 限定路径根目录（留空=不限制）；删除非空目录必须显式 `recursive=true`。

## 6. 已知限制

- xAgent 的 LLM 调用为非流式，`/compact` 与长回答期间界面会短暂停顿。
- 网页控制台的文档正文预览依赖 AnythingLLM 的 `/api/v1/document/{name}`，部分版本不提供该接口，此时仅显示元数据（界面会提示原因）。
- 宠物医院 MCP 仅覆盖“查询 + 新增”，未实现改名 / 删除等写操作（后端支持，MCP 层未暴露）。
- `Agent/office/.agents/skills/officecli/officecli-win-x64.exe`（32MB）与宠物医院可执行包按 `.gitignore` 排除，
  克隆后需自行下载对应平台二进制；仅 Markdown 技能（`notice`、`生肖星座运势`、`guizang-ppt-skill`）可直接使用。

## License

各子项目授权以对应目录下的文件为准；`Agent/office/.agents/skills/guizang-ppt-skill`
为第三方 AGPL-3.0 技能包，版权归原作者。
