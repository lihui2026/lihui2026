# xAgent

基于 Practice02（本地文件操作 Agent）重构的分层架构项目。

## 设计目标
- **核心与界面分离**：`core/` 实现业务逻辑（Agent、LLM、工具集），`tui/` 实现界面（Textual），`interfaces/` 为未来 Web/Desktop 等界面预留抽象
- **软件工程规范**：按领域模块化、层级化组织代码（agent/config/llm/models/prompts/tools/utils）
- **可扩展**：未来可新增 `web/`、`desktop/` 等目录，统一复用 `core/`

## 目录结构
```text
xAgent/
├── core/           # 核心业务逻辑
│   ├── agent/      # Agent 编排（工具调用循环）
│   ├── config/     # 配置加载
│   ├── llm/        # LLM 客户端（OpenAI 兼容）
│   ├── models/     # 数据模型（预留）
│   ├── prompts/    # 提示词（预留）
│   ├── tools/      # 工具定义与实现
│   └── utils/      # 工具函数
├── tui/            # Textual TUI 界面
│   ├── app.py
│   ├── screens/
│   ├── widgets/
│   ├── styles/
│   └── assets/
├── interfaces/     # UI 抽象接口（预留 Web/Desktop）
├── config.ini      # LLM 配置
└── main.py         # TUI 入口
```

## 运行
```bash
pip install textual requests
python main.py
```

## 核心功能
复用 Practice02 的全部本地文件操作工具：getDate、getCurrentWorkingDirectory、listDirectory、getFileType、getFileContent、createFile、editFileContent、createDirectory、removeDirectory、deleteFile、renamePath、isLeapYear。
