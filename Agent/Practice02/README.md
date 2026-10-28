# Practice02 — Function Call 工具集合

在 [Practice01](../Practice01) 的基础上新增 **function call 工具**，涵盖时间获取、闰年判断以及本地文件操作。

## 工具一览

| 工具 | 作用 | 实现方式 |
| --- | --- | --- |
| `getDate` | 获取当前电脑的日期和时间 | **调用系统本地的 `date` 命令**（Windows 用 `date /t & time /t`，其他平台用 `date`），不用 Python 计算 |
| `isLeapYear` | 判断指定年份是否为闰年 | **用 Python 代码计算**（公历规则：能被 4 整除但不能被 100 整除，或能被 400 整除） |
| `getCurrentWorkingDirectory` | 获取当前工作目录的绝对路径 | Python（`os.getcwd()`） |
| `listDirectory` | 列出指定目录下所有文件和子目录 | Python（`Path.iterdir()`） |
| `getFileType` | 获取指定路径的类型（文件、目录或其他） | Python（`Path.exists/is_dir/is_file`） |
| `getFileContent` | 获取指定文件的内容（仅支持纯文本格式文件） | Python（`Path.read_text`，尝试 UTF-8/GBK） |
| `createFile` | 根据指定的目录和文件名创建新文件（同时支持创建新目录） | Python（`Path.mkdir(parents=True)` + `write_text`） |
| `editFileContent` | 编辑指定文件的内容（仅支持纯文本格式文件） | Python（`write_text` 覆盖或 `open(a)` 追加） |
| `createDirectory` | 创建新目录（如父目录不存在会自动创建） | Python（`Path.mkdir(parents=True, exist_ok=True)`） |
| `removeDirectory` | 删除目录（非空目录也会被删除） | Python（`shutil.rmtree`） |
| `deleteFile` | 删除文件 | Python（`Path.unlink`） |
| `renamePath` | 重命名文件和目录 | Python（`Path.rename`，如目标存在且允许覆盖则先删除） |

## 文件说明

| 文件 | 说明 |
| --- | --- |
| `config.ini` | LLM 服务地址 / 模型 / API Key（沿用 Practice01 的 LM Studio 配置） |
| `tools.py` | 工具定义与实现：`getDate`、`isLeapYear` 以及全部本地文件操作工具，统一由 `call_tool` 分发 |
| `main.py` | 非流式 Agent 主程序：模型请求工具 → 执行工具 → 回传结果 → 输出最终回答（注册全部工具） |
| `main-stream.py` | 流式版本，回答逐字输出，同时支持工具调用 |
| `main-leap-year.py` | 闰年判断专用程序，只注册 `isLeapYear` 工具 |
| `main-file-ops.py` | 本地文件操作专用程序，注册全部文件操作工具及 `getDate`、`isLeapYear` |
| `main-file-ops-architecture.mmd` | `main-file-ops.py` 代码架构图（Mermaid 格式） |
| `requirements.txt` | 依赖（仅 `requests`） |

## 运行

```bash
pip install -r requirements.txt
python main.py            # 或 python main-stream.py
python main-leap-year.py  # 闰年判断（isLeapYear 工具）
python main-file-ops.py   # 本地文件操作（全部文件操作工具 + getDate/isLeapYear）
python main.py D:\path\to\other-config.ini   # 可选：指定其它配置文件
```

启动 LM Studio（或任意兼容 OpenAI 接口的服务）并加载模型后即可对话，例如：

```text
输入问题：现在几点了？
→ 调用工具 getDate，参数：{}
← 工具返回：2026/10/22 星期三 19:14
现在是 2026/10/22 星期三 19:14，这是通过 getDate 工具获得的。
```

## 工具定义

### getDate

```json
{
  "type": "function",
  "function": {
    "name": "getDate",
    "description": "获取当前电脑的日期和时间。当用户询问今天日期、当前时间、现在几点、星期几等问题时调用本工具。",
    "parameters": { "type": "object", "properties": {}, "required": [] }
  }
}
```

### isLeapYear

```json
{
  "type": "function",
  "function": {
    "name": "isLeapYear",
    "description": "判断指定年份是否为闰年。当用户询问某一年是闰年还是平年时调用本工具。",
    "parameters": {
      "type": "object",
      "properties": { "year": { "type": "integer", "description": "需要判断的年份，例如 2024。" } },
      "required": ["year"]
    }
  }
}
```

`isLeapYear` 的判断过程**完全由 Python 代码完成**（`tools.py` 中 `isLeapYear()`），
按公历规则：能被 4 整除但不能被 100 整除，或能被 400 整除的年份是闰年。

| 年份 | 结果 | 年份 | 结果 |
| --- | --- | --- | --- |
| 2024 | 闰年 | 2023 | 平年 |
| 2000 | 闰年（400 的倍数） | 1900 | 平年（100 的倍数但不是 400 的倍数） |
| 2400 | 闰年 | 2100 | 平年 |

运行 `python main-leap-year.py` 时，程序会先把当前日期（由本地 `date` 命令获得）写进 system 消息，
便于模型把“今年是闰年吗”换算成具体年份再调用工具：

```text
输入问题：2024 年是闰年吗？
→ 调用工具 isLeapYear，参数：{'year': 2024}
← 工具返回：2024 年是闰年。
根据 isLeapYear 工具的结果：2024 年是闰年。
```

### 本地文件操作工具（节选）

| 工具 | 参数 | 说明 |
| --- | --- | --- |
| `getCurrentWorkingDirectory` | 无 | 获取当前工作目录绝对路径 |
| `listDirectory` | `dir` | 列出指定目录下所有文件和子目录 |
| `getFileType` | `path` | 获取路径类型（文件/目录/其他） |
| `getFileContent` | `path` | 读取纯文本文件内容（尝试 UTF-8/GBK） |
| `createFile` | `dir`, `filename`, `content?`, `overwrite?` | 创建文件（自动创建目录），可指定初始内容 |
| `editFileContent` | `path`, `content`, `append?` | 编辑纯文本文件（默认覆盖，可选追加） |
| `createDirectory` | `dir` | 创建目录（自动创建父目录） |
| `removeDirectory` | `dir` | 删除目录（非空也会删除） |
| `deleteFile` | `path` | 删除文件 |
| `renamePath` | `src`, `dst`, `overwrite?` | 重命名文件或目录（目标存在且允许覆盖时会先删除） |

代码架构图见 `main-file-ops-architecture.mmd`（Mermaid 格式）。

## date 命令的调用方式

`tools.py` 中的 `_date_command()` 按操作系统选择命令，**不使用 `datetime` 计算时间**：

| 平台 | 实际执行 | 输出示例 |
| --- | --- | --- |
| Windows | `cmd /c "date /t & time /t"` | `2026/10/22 星期三 19:14` |
| Linux / macOS | `date` | `Thu Oct 22 19:14:03 CST 2026` |

- Windows 下 `date` 直接执行会进入交互式修改日期的流程，因此使用 `date /t`（只显示、不修改），
  并配合 `time /t` 一起取到时间。
- 子进程输出按 `utf-8 → 系统默认编码 → gbk` 的顺序解码，兼容中文 Windows 控制台的 GBK 输出。

## 调用流程

1. 用户输入问题 → 以 `tools` 字段把工具函数定义随请求一起发给模型；
2. 模型返回 `tool_calls` → 本地执行对应工具（`getDate` 跑 `date` 命令，`isLeapYear` 和文件操作工具走 Python 实现）；
3. 以 `role: "tool"` 消息把结果回传，并再次请求模型；
4. 模型结合工具结果生成最终回答（最多 `MAX_TOOL_ROUNDS` 轮，防止工具循环）。

> 说明：函数调用需要模型本身支持 tool calling（例如 LM Studio 中加载支持工具模板的模型），
> 否则模型只会当作普通文本处理。
