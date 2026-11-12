# xAgent

基于 Practice02（本地文件操作 Agent）重构的分层架构项目，提供 Textual TUI、MCP 工具接入、会话持久化与上下文压缩能力。

## 设计目标
- **核心与界面分离**：`core/` 实现业务逻辑（Agent、LLM、工具集、会话、配置），`tui/` 实现界面，`interfaces/` 为未来 Web/Desktop 等界面预留抽象。
- **软件工程规范**：按领域模块化、层级化组织代码。
- **可扩展**：未来可新增 `web/`、`desktop/` 等目录，统一复用 `core/`。

## 目录结构
```text
xAgent/
├── core/           # 核心业务逻辑
│   ├── agent/      # Agent 编排（工具调用循环、会话、AGENTS.md）
│   ├── config/     # 配置加载、默认值、自动创建
│   ├── context/    # 上下文估算、归档、历史检索
│   ├── llm/        # LLM 客户端（OpenAI 兼容）
│   ├── mcp/        # MCP Client（stdio / Streamable HTTP）
│   ├── prompts/    # 提示词
│   ├── session/    # JSONL 会话事件日志
│   ├── skills/     # Agent Skills
│   ├── tools/      # 工具定义与实现
│   └── utils/      # 工具函数
├── tui/            # Textual TUI 界面
│   ├── app.py
│   ├── commands.py
│   └── styles/app.tcss
├── interfaces/     # UI 抽象接口（预留 Web/Desktop）
├── tests/
├── config.ini      # 运行配置（首次运行自动生成）
└── main.py         # TUI 入口
```

## 运行
```bash
pip install -r requirements.txt    # 依赖及版本约束
python main.py
```

首次运行若找不到 `xAgent/config.ini`，程序会自动生成完整配置模板，并弹窗提示修改 `base_url`、`model`、`api_key` 等配置后重启。

启动后建议依次验证：`/status`（会话与长期规则文件状态）→ `/tools`（本地工具是否齐全）→ `/mcp`（MCP 是否连上）→ `/compact`（压缩链路可用）。单测：
```bash
python -m pytest tests -q
```

## 配置
配置集中在 `xAgent/config.ini`，主要小节如下：

| 小节 | 主要配置 |
| --- | --- |
| `[LLM]` | `base_url`、`model`、`api_key`、`timeout`、`context_window`、`default_context_window`、`compact_threshold`、`summary_target_tokens`、`max_tool_rounds`、`agents_md_enabled`、`agents_md_filename`、`agents_md_max_chars` |
| `[MCP]` | `connect_timeout`、`call_timeout`、`output_limit` |
| `[TOOLS]` | `tool_timeout`、`cli_timeout`、`cli_output_limit`、`fetch_*`、`search_timeout`、`recall_*`、`skill_description_limit`、`skill_content_limit`、`tool_workspace_root` |
| `[search]` | `baidu_qianfan_api_key` |
| `[SESSION]` | `dir`、`auto_save`、`list_limit` |
| `[UI]` | `sidebar_width`、`command_palette_max` |

`context_window = 0` 表示自动探测模型窗口，探测失败时使用 `default_context_window`（默认 128k）。`compact_threshold = 0.6` 表示上下文占用达到 60% 时暂停接收新提示词。

几个直接影响行为的开关：

| 配置 | 默认 | 作用 |
| --- | --- | --- |
| `agents_md_filename` | `AGENT.md` | 长期规则文件名；找不到时依次回退 `AGENTS.md` / `agents.md` / `agent.md` |
| `agents_md_enabled` | `true` | 关闭后不注入任何长期规则文件 |
| `agents_md_max_chars` | `8000` | 注入内容的字符上限，超出截断并注明（防止规则文件挤占上下文） |
| `skill_content_limit` | `20000` | `loadSkill` 单次返回的最大字符数，超出截断 |
| `tool_workspace_root` | 空 | 填写后，`createFile` / `editFileContent` / `createDirectory` / `removeDirectory` / `deleteFile` / `renamePath` 的目标路径必须位于该目录内，越界直接拒绝 |

## 斜杠命令
输入 `/` 会弹出命令补全面板，支持 `↑/↓` 选择、`Tab` 补全、`Enter` 执行、`Esc` 关闭。

| 命令 | 说明 |
| --- | --- |
| `/new` | 新建会话（当前会话已自动保存） |
| `/resume` | 打开历史会话列表，选择后恢复 |
| `/resume <编号>` | 按编号或编号前缀直接恢复 |
| `/save` | 保存当前会话快照 |
| `/compact` | 压缩当前上下文 |
| `/clear` | 清空当前上下文，保留会话文件 |
| `/status` | 查看会话、长期规则文件、模型与上下文状态 |
| `/tools` | 列出本地与 MCP 工具 |
| `/mcp` | 刷新 MCP 侧栏并输出连接信息 |
| `/agents` | 查看长期规则文件路径与注入状态 |
| `/help` | 显示命令帮助 |
| `/quit`、`/exit` | 退出 xAgent |

## 会话与 AGENTS.md
- 会话文件保存在项目根目录的 `.agents/sessions/`，文件名即会话编号（如 `20261111-100000.jsonl`）。
- 每条消息在产生时立即追加写入 JSONL；压缩、手动保存、恢复等操作会写入 `snapshot` 事件，恢复时以最后一个快照为准。
- 会话标题默认取第一条用户消息，可用 `/status` 查看当前会话编号与文件路径。
- 若项目根目录存在长期规则文件，启动新会话（或 `/clear`）时会作为额外的 `system` 消息注入**一次**，并随会话快照持久化；恢复会话或压缩上下文时不会重复注入。文件名优先取 `AGENT.md`（可用 `[LLM] agents_md_filename` 改名），找不到时依次回退 `AGENTS.md` / `agents.md` / `agent.md`；内容超过 `agents_md_max_chars` 会截断并注明，文件缺失不报错。
- 每次工具调用会向 `.agents/logs/tool_calls.jsonl` 追加一行结构化记录（时间、会话号、工具名、是否成功、耗时 ms、结果字符数），便于复盘与排查。
- TUI 顶部显示当前会话编号与上下文用量；MCP 侧栏在后台异步加载，不会阻塞首次渲染。

## MCP Client
xAgent 启动时会读取 `office/.mcp.json`（找不到时回退到运行目录 / xAgent 目录下的 `.mcp.json`；也可用环境变量 `XAGENT_MCP_CONFIG` 指定），通过官方 MCP Python SDK 连接配置的 MCP Server（`McpClientManager`，见 `core/mcp/mcp_client.py`），支持 `streamable-http`（注意是横杠）和 `stdio` 两种传输方式。

示例 `office/.mcp.json`：
```json
{
  "mcpServers": {
    "Bazi-MCP": {
      "type": "streamable-http",
      "url": "https://mcp.api-inference.modelscope.net/a205b6fc740d4a/mcp"
    },
    "PetHospitalMCP": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:8090/mcp"
    },
    "AnythingLLMMCP": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:8091/mcp"
    }
  }
}
```

连接成功后，xAgent 会调用 `list_tools()` 发现工具，并将它们动态加入 Function Calling 工具列表。MCP 工具名统一加 `服务名__原始工具名` 前缀（并维护映射表），因此跨服务重名不会冲突；LLM 调用带 `__` 前缀的工具时会转发到对应的 MCP Server。MCP 工具与本地工具（如 `RunCli`、`fetchWeb`、`loadSkill`）统一参与 Agent 的工具调用流程。单个 MCP Server 连接失败时只会记录 `[MCP]` 告警日志并在界面上报告该服务器的错误，不会影响其他工具。也可以在对话中让 Agent 调用 `createMCP` 工具（参数：server_name、transport_type、url），把新的 MCP Server 写入 `office/.mcp.json` 并自动重连刷新工具列表。

stdio 服务器配置示例：
```json
{
  "mcpServers": {
    "my-local-server": {
      "type": "stdio",
      "command": "python",
      "args": ["path/to/server.py"],
      "env": {},
      "cwd": "."
    }
  }
}
```

## 核心功能
复用 Practice02 的全部本地文件操作工具：getDate、getCurrentWorkingDirectory、listDirectory、getFileType、getFileContent、createFile、editFileContent、createDirectory、removeDirectory、deleteFile、renamePath、isLeapYear，以及网页工具 fetchWeb、searchWeb、本地命令行工具 RunCli 和 Skill 工具 loadSkill、createSkill。createSkill 可在项目的 `.agents/skills/` 目录下创建符合 Agent Skills 规范的新 Skill。MCP 工具会自动与上述本地工具合并。

安全性：`removeDirectory` 对非空目录默认拒绝删除，必须显式传 `recursive=true`；配置 `[TOOLS] tool_workspace_root` 后，所有写/删/改操作的目标路径必须位于该目录内，越界直接返回拒绝原因。

## 上下文压缩与历史检索
当会话较长时，可以用 `/compact` 手动压缩上下文，把历史对话整理成约 `summary_target_tokens`（默认 5,000）Tokens 的工作摘要，从而在有限的上下文窗口内继续执行长任务。

- **长度监控**：每次 LLM 响应后检查上下文用量（包含 System Prompt、对话历史与工具调用消息）。优先使用模型 API 返回的 Token 用量，无法获得时使用本地估算。TUI 顶部会显示「当前上下文长度k / 模型窗口大小k（占用百分比）」；无法探测窗口大小时默认按 128k 计算并标注「默认」。
- **阈值暂停**：达到模型窗口的 `compact_threshold`（默认 60%）时界面会告警，并暂停接收新的普通提示词，直到压缩成功完成。
- **原始归档**：压缩前会把完整原始上下文以 JSONL 保存到项目的 `.agents/context/` 目录，文件名即归档编号（如 `20261022-153000.jsonl`），保留消息角色、内容、工具调用参数、工具返回结果与顺序。只有归档成功后才继续压缩。
- **压缩流程**：`/compact` 期间禁止其他工具调用与普通任务处理，只调用 LLM 生成摘要；成功后保留所有前导 System Prompt（含 AGENTS.md），用摘要替换其余历史消息，并弹出左右两栏的压缩前后对照面板，可滚动查看、点击「关闭」收起。失败时保留原上下文，可重新执行。
- **历史检索**：压缩摘要中会追加归档说明。LLM 可调用 `recallContext` 工具（参数 `text` 必填、`id` 可选）在全部或指定归档中做本地全文关键词检索，返回相关片段、归档编号与消息位置。
