"""Tool definitions and implementations (file ops, date, leap year, web)."""
import json
import locale
import os
import shutil
import subprocess
from pathlib import Path

from core.config import get_config
from core.context import context_manager
from core.mcp import mcp_manager, save_mcp_servers
from core.skills import skill_manager

try:
    import requests
except ImportError:
    requests = None

try:
    import trafilatura
except ImportError:
    trafilatura = None

def _get_search_api_key():
    try:
        return get_config().search_api_key.strip()
    except Exception:
        return ""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "RunCli",
            "description": "在本机执行已安装的命令行程序（CLI），并返回标准输出、标准错误和退出码。command 为程序名称或路径，args 为参数列表；不会经过 Shell，因此不支持管道、重定向等 Shell 语法。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的程序名称（需在 PATH 中）或完整路径。"},
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "传给程序的参数列表，每个参数为单独的字符串；无参数时传空列表。",
                    },
                },
                "required": ["command", "args"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "getDate",
            "description": "获取当前电脑的日期和时间。当用户询问今天日期、当前时间、现在几点、星期几等问题时调用本工具。",
            "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "getCurrentWorkingDirectory",
            "description": "获取当前工作目录的绝对路径。",
            "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listDirectory",
            "description": "列出指定目录下所有文件和子目录。",
            "parameters": {
                "type": "object",
                "properties": {"dir": {"type": "string", "description": "要列出的目录路径，可以是相对路径或绝对路径。"}},
                "required": ["dir"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "getFileType",
            "description": "获取指定路径的类型（文件、目录或其他）。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "文件或目录的路径。"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "getFileContent",
            "description": "获取指定文件的内容（仅支持纯文本格式文件）。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "要读取的纯文本文件路径。"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "createFile",
            "description": "根据指定的目录和文件名创建新文件（同时支持创建新目录）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dir": {"type": "string", "description": "文件所在的目录路径，如目录不存在会自动创建。"},
                    "filename": {"type": "string", "description": "要创建的文件名。"},
                    "content": {"type": "string", "description": "可选：文件的初始内容（纯文本）。"},
                    "overwrite": {"type": "boolean", "description": "可选：如果文件已存在是否覆盖，默认 false。"},
                },
                "required": ["dir", "filename"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "editFileContent",
            "description": "编辑指定文件的内容（仅支持纯文本格式文件），默认会覆盖整个文件内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要编辑的纯文本文件路径。"},
                    "content": {"type": "string", "description": "新的文件内容（纯文本）。"},
                    "append": {"type": "boolean", "description": "可选：true 表示追加到文件末尾，false（默认）表示覆盖整个文件。"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "createDirectory",
            "description": "创建新目录（如父目录不存在会自动创建）。",
            "parameters": {
                "type": "object",
                "properties": {"dir": {"type": "string", "description": "要创建的目录路径。"}},
                "required": ["dir"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "removeDirectory",
            "description": "删除目录。非空目录必须显式传 recursive=true 才会递归删除（不可恢复，删除前请确认路径）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dir": {"type": "string", "description": "要删除的目录路径。"},
                    "recursive": {
                        "type": "boolean",
                        "description": "可选：是否递归删除非空目录，默认 false（非空目录会被拒绝删除）。",
                    },
                },
                "required": ["dir"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deleteFile",
            "description": "删除文件。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "要删除的文件路径。"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "renamePath",
            "description": "重命名文件和目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "源文件或目录路径。"},
                    "dst": {"type": "string", "description": "目标文件或目录路径（新名称或新路径）。"},
                    "overwrite": {"type": "boolean", "description": "可选：如果目标已存在是否覆盖，默认 false。"},
                },
                "required": ["src", "dst"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetchWeb",
            "description": "获取指定网页的主要内容。通过本地 curl 获取 HTML，再用 trafilatura 提取正文并转换为 Markdown，去除导航栏、广告、页脚等无关内容，尽量保留标题、段落、列表、表格及链接。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要获取的网页 URL。"},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "searchWeb",
            "description": "通过百度千帆搜索 API 获取互联网上的最新信息。返回搜索摘要、参考来源的标题及 URL。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词或问题。"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "loadSkill",
            "description": "加载指定 Skill 的完整内容。仅提供 name 时读取该 Skill 的 SKILL.md 全文；同时提供 filename 时读取该 Skill 目录内的附件文件，不会再次加载 SKILL.md。filename 支持相对于 Skill 目录的路径、项目相对路径或绝对路径；仅提供文件名时会递归搜索该 Skill 目录，若有多个同名文件则返回候选路径。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill 的名称。"},
                    "filename": {"type": "string", "description": "可选：需要加载的 Skill 附件文件路径或名称。"},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recallContext",
            "description": "检索此前上下文压缩时保存的原始上下文归档（位于项目的 .agents/context/ 目录）。当压缩摘要缺少某些历史细节（如具体文件路径、命令输出、错误信息）时调用本工具。可指定归档编号 id 只检索该归档；不提供 id 时会在全部归档中进行全文关键词检索。",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "可选：上下文归档编号，如 20261022-153000；不提供时检索全部归档。"},
                    "text": {"type": "string", "description": "必需：需要查找的关键词或文本内容。"},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "createMCP",
            "description": "新增一个 MCP Server：将 server_name、transport_type、url 写入 office/.mcp.json（合并进 mcpServers），然后立即重新连接所有 MCP Server 并刷新工具列表。transport_type 目前支持 streamable-http。",
            "parameters": {
                "type": "object",
                "properties": {
                    "server_name": {"type": "string", "description": "MCP Server 名称，如 Bazi-MCP、PetHospitalMCP。"},
                    "transport_type": {"type": "string", "description": "传输协议类型，目前支持 streamable-http。"},
                    "url": {"type": "string", "description": "MCP Server 的 URL，如 https://example.com/mcp 或 http://127.0.0.1:8090/mcp。"},
                },
                "required": ["server_name", "transport_type", "url"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "createSkill",
            "description": "在项目的 .agents/skills/ 目录下创建新的 Skill，并生成符合 Agent Skills 规范的 SKILL.md。name 必须为小写字母、数字和连字符组成的英文名称；skillContext 为 SKILL.md 的完整内容（可包含 YAML Frontmatter）。如果目标 Skill 已存在则不会覆盖。如需创建 references/、scripts/ 等附加目录或文件，请在创建后继续使用 createFile、createDirectory 等文件工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill 名称，必须为小写字母、数字和连字符组成的英文名称，如 my-skill。"},
                    "skillContext": {"type": "string", "description": "要写入 SKILL.md 的完整内容，包含 YAML Frontmatter、name、description 和正文。"},
                },
                "required": ["name", "skillContext"],
                "additionalProperties": False,
            },
        },
    },
]

LOCAL_TOOL_NAMES = frozenset(tool["function"]["name"] for tool in TOOLS)


def _allowed_root():
    """读取 [TOOLS] tool_workspace_root；为空表示不限制（保持向后兼容）。"""
    try:
        raw = str(getattr(get_config(), "tool_workspace_root", "") or "").strip()
    except Exception:
        raw = ""
    if not raw:
        return None
    try:
        return Path(raw).expanduser().resolve()
    except OSError:
        return None


def _check_path(path):
    """写 / 删 / 改类操作的路径边界校验；返回错误串表示拒绝执行。"""
    root = _allowed_root()
    if not isinstance(path, str) or not path.strip():
        return "路径参数错误：必须是非空字符串。"
    if root is None:
        return None
    try:
        target = Path(path).expanduser().resolve()
    except OSError as exc:
        return f"路径解析失败：{exc}"
    try:
        target.relative_to(root)
    except ValueError:
        return (
            f"路径越界：{target} 不在允许的根目录 {root} 内，已拒绝执行。"
            "如需放开限制，请调整 config.ini 的 [TOOLS] tool_workspace_root。"
        )
    return None


def get_tools():
    """Return local tools plus dynamically discovered MCP tools."""
    tools = list(TOOLS)
    tools.extend(mcp_manager.get_tool_definitions())
    return tools


def _decode(raw):
    for enc in ("utf-8", locale.getpreferredencoding(False), "gbk"):
        if not enc:
            continue
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _truncate_output(text):
    limit = get_config().cli_output_limit
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    head = limit // 2
    tail = limit - head
    return (
        f"{text[:head]}\n"
        f"...（输出过长，已截断 {omitted} 个字符，保留开头和结尾）...\n"
        f"{text[-tail:]}"
    )


def RunCli(command, args=None):
    if not command or not isinstance(command, str):
        return "RunCli 参数错误：command 必须为非空字符串。"
    if args is None:
        args = []
    if not isinstance(args, list) or any(not isinstance(a, str) for a in args):
        return "RunCli 参数错误：args 必须为字符串列表。"
    cmd = [command] + args
    timeout = get_config().cli_timeout
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, shell=False)
    except subprocess.TimeoutExpired:
        return f"RunCli 失败：命令执行超时（超过 {timeout} 秒）。"
    except FileNotFoundError:
        return f"RunCli 失败：找不到程序“{command}”，请确认已安装且在 PATH 中。"
    except OSError as exc:
        return f"RunCli 失败：无法启动程序：{exc}"
    stdout = _truncate_output(_decode(proc.stdout))
    stderr = _truncate_output(_decode(proc.stderr))
    return (
        f"命令：{subprocess.list2cmdline(cmd)}\n"
        f"退出码：{proc.returncode}\n"
        f"标准输出：\n{stdout if stdout.strip() else '（空）'}\n"
        f"标准错误：\n{stderr if stderr.strip() else '（空）'}"
    )


def _date_command():
    if os.name == "nt":
        return ["cmd", "/c", "date /t & time /t"]
    return ["date"]


def getDate():
    cmd = _date_command()
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=get_config().tool_timeout)
    except FileNotFoundError as exc:
        return f"调用 date 命令失败：{exc}"
    except subprocess.TimeoutExpired:
        return "调用 date 命令超时。"
    if proc.returncode != 0:
        err = _decode(proc.stderr).strip()
        return f"date 命令执行失败（退出码 {proc.returncode}）：{err or '无错误输出'}"
    lines = [line.strip() for line in _decode(proc.stdout).splitlines() if line.strip()]
    if not lines:
        return "date 命令未返回任何内容。"
    return " ".join(lines)


def isLeapYear(year):
    if isinstance(year, bool):
        return f"年份参数无效：{year!r}，请传入整数年份。"
    if not isinstance(year, int):
        try:
            year = int(str(year).strip())
        except (TypeError, ValueError):
            return f"年份参数无效：{year!r}，请传入整数年份。"
    if year <= 0:
        return "年份必须为正整数。"
    is_leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
    return f"{year} 年是{'闰年' if is_leap else '平年'}。"


def getCurrentWorkingDirectory():
    return os.path.abspath(os.getcwd())


def listDirectory(dir):
    try:
        p = Path(dir)
        if not p.exists():
            return f"目录不存在：{p}"
        if not p.is_dir():
            return f"指定路径不是目录：{p}"
        entries = []
        for item in sorted(p.iterdir(), key=lambda x: x.name.lower()):
            if item.is_dir():
                entries.append(f"[DIR]  {item.name}/")
            elif item.is_file():
                entries.append(f"[FILE] {item.name}")
            else:
                entries.append(f"[OTHER] {item.name}")
        if not entries:
            return f"{p}（空目录）"
        return "\n".join(entries)
    except Exception as exc:
        return f"列出目录失败：{exc}"


def getFileType(path):
    try:
        p = Path(path)
        if not p.exists():
            return f"路径不存在：{p}"
        if p.is_dir():
            return f"{p}：目录"
        if p.is_file():
            return f"{p}：文件"
        return f"{p}：其他"
    except Exception as exc:
        return f"获取文件类型失败：{exc}"


def getFileContent(path):
    try:
        p = Path(path)
        if not p.exists():
            return f"文件不存在：{p}"
        if not p.is_file():
            return f"指定路径不是文件：{p}"
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeError:
            try:
                text = p.read_text(encoding="gbk")
            except UnicodeError:
                return "读取失败：不支持的文件编码（仅支持纯文本 UTF-8 或 GBK 编码的文件）"
        return text
    except Exception as exc:
        return f"读取文件失败：{exc}"


def createFile(dir, filename, content="", overwrite=False):
    guard = _check_path(dir)
    if guard:
        return guard
    try:
        d = Path(dir)
        d.mkdir(parents=True, exist_ok=True)
        p = d / filename
        if p.exists() and not overwrite:
            return f"文件已存在（如需覆盖请设置 overwrite=true）：{p}"
        p.write_text(content or "", encoding="utf-8")
        return f"已创建文件：{p}"
    except Exception as exc:
        return f"创建文件失败：{exc}"


def editFileContent(path, content="", append=False):
    guard = _check_path(path)
    if guard:
        return guard
    try:
        p = Path(path)
        if not p.exists():
            return f"文件不存在：{p}"
        if not p.is_file():
            return f"指定路径不是文件：{p}"
        if append:
            with p.open("a", encoding="utf-8") as f:
                f.write(content or "")
            return f"已追加内容到文件：{p}"
        p.write_text(content or "", encoding="utf-8")
        return f"已覆盖文件内容：{p}"
    except Exception as exc:
        return f"编辑文件失败：{exc}"


def createDirectory(dir):
    guard = _check_path(dir)
    if guard:
        return guard
    try:
        p = Path(dir)
        p.mkdir(parents=True, exist_ok=True)
        return f"已创建目录：{p}"
    except Exception as exc:
        return f"创建目录失败：{exc}"


def removeDirectory(dir, recursive=False):
    guard = _check_path(dir)
    if guard:
        return guard
    try:
        p = Path(dir)
        if not p.exists():
            return f"目录不存在：{p}"
        if not p.is_dir():
            return f"指定路径不是目录：{p}"
        try:
            has_entries = any(p.iterdir())
        except OSError as exc:
            return f"删除目录失败：无法读取目录内容：{exc}"
        if has_entries and not recursive:
            return (
                f"拒绝删除非空目录：{p}（该操作不可恢复）。"
                "确认无误后请以 recursive=true 重新调用。"
            )
        if has_entries:
            shutil.rmtree(p)
        else:
            p.rmdir()
        return f"已删除目录：{p}"
    except Exception as exc:
        return f"删除目录失败：{exc}"


def deleteFile(path):
    guard = _check_path(path)
    if guard:
        return guard
    try:
        p = Path(path)
        if not p.exists():
            return f"文件不存在：{p}"
        if not p.is_file():
            return f"指定路径不是文件：{p}"
        p.unlink()
        return f"已删除文件：{p}"
    except Exception as exc:
        return f"删除文件失败：{exc}"


def renamePath(src, dst, overwrite=False):
    for target in (src, dst):
        guard = _check_path(target)
        if guard:
            return guard
    try:
        s = Path(src)
        d = Path(dst)
        if not s.exists():
            return f"源路径不存在：{s}"
        if d.exists() and not overwrite:
            return f"目标路径已存在（如需覆盖请设置 overwrite=true）：{d}"
        if d.exists() and overwrite:
            if d.is_dir():
                shutil.rmtree(d)
            else:
                d.unlink()
        s.rename(d)
        return f"已重命名：{s} -> {d}"
    except Exception as exc:
        return f"重命名失败：{exc}"


def fetchWeb(url):
    if not url or not isinstance(url, str):
        return "fetchWeb 参数错误：url 必须为非空字符串。"
    if trafilatura is None:
        return "fetchWeb 失败：缺少 trafilatura 库，请先安装：pip install trafilatura"
    cfg = get_config()
    try:
        cmd = [
            "curl",
            "-L",
            "-sS",
            "--connect-timeout",
            str(cfg.fetch_connect_timeout),
            "--max-time",
            str(cfg.fetch_max_timeout),
            "-A",
            "Mozilla/5.0 (compatible; xAgent/1.0)",
            url,
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=cfg.fetch_timeout)
        if proc.returncode != 0:
            err = _decode(proc.stderr).strip()
            return f"fetchWeb 失败：curl 执行失败（退出码 {proc.returncode}）{': ' + err if err else '。'}"
        html = proc.stdout
        if not html:
            return "fetchWeb 失败：未获取到网页内容。"
        try:
            html_str = html.decode("utf-8", errors="replace")
        except Exception:
            html_str = _decode(html)
        try:
            markdown = trafilatura.extract(
                html_str,
                include_comments=False,
                include_tables=True,
                include_links=True,
                output_format="markdown",
                favor_precision=True,
            )
        except Exception as exc:
            return f"fetchWeb 失败：HTML 解析失败：{exc}"
        if not markdown or not markdown.strip():
            return "fetchWeb 失败：正文无法提取（可能为动态页面、登录页或纯脚本页面）。"
        return f"URL: {url}\n\n{markdown.strip()}"
    except subprocess.TimeoutExpired:
        return "fetchWeb 失败：请求超时。"
    except FileNotFoundError:
        return "fetchWeb 失败：未找到 curl，请确保 curl 已安装并在 PATH 中。"
    except Exception as exc:
        return f"fetchWeb 失败：{exc}"


def searchWeb(query):
    if not query or not isinstance(query, str):
        return "searchWeb 参数错误：query 必须为非空字符串。"
    if requests is None:
        return "searchWeb 失败：缺少 requests 库，请先安装：pip install requests"
    api_key = _get_search_api_key()
    if not api_key:
        return "searchWeb 失败：缺少配置。请在 xAgent/config.ini 的 [search] 小节中设置 baidu_qianfan_api_key。"
    url = "https://qianfan.baidubce.com/v2/ai_search/web_search"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"messages": [{"role": "user", "content": query}]}
    try:
        resp = requests.post(
            url, headers=headers, json=payload, timeout=get_config().search_timeout
        )
    except requests.Timeout:
        return "searchWeb 失败：网络请求超时。"
    except requests.RequestException as exc:
        return f"searchWeb 失败：网络请求失败：{exc}"
    try:
        data = resp.json()
    except ValueError:
        return f"searchWeb 失败：API 返回非 JSON 响应（状态码 {resp.status_code}）：{resp.text[:200]}"
    if resp.status_code >= 400:
        err_msg = data.get("error") or data.get("message") or data
        return f"searchWeb 失败：API 返回错误（状态码 {resp.status_code}）：{err_msg}"
    results = []
    # Try common response structures from Qianfan web search
    if isinstance(data, dict):
        if isinstance(data.get("references"), list):
            results = data.get("references") or []
        elif isinstance(data.get("results"), list):
            results = data.get("results") or []
        elif isinstance(data.get("data"), dict):
            d = data["data"]
            if isinstance(d.get("references"), list):
                results = d.get("references") or []
            elif isinstance(d.get("results"), list):
                results = d.get("results") or []
    if not results:
        return f"searchWeb 未获取到搜索结果。原始响应摘要：{json.dumps(data, ensure_ascii=False)[:500]}"
    lines = [f"搜索关键词：{query}", ""]
    for i, item in enumerate(results, 1):
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("name") or ""
        url_res = item.get("url") or item.get("link") or item.get("href") or ""
        snippet = item.get("snippet") or item.get("summary") or item.get("content") or item.get("abstract") or ""
        lines.append(f"{i}. {title}")
        if url_res:
            lines.append(f"   来源：{url_res}")
        if snippet:
            lines.append(f"   摘要：{snippet}")
        lines.append("")
    return "\n".join(lines).strip()


def call_tool(name, arguments=None):
    args = arguments or {}
    if name == "RunCli":
        return RunCli(args.get("command"), args.get("args"))
    if name == "getDate":
        return getDate()
    if name == "isLeapYear":
        year = args.get("year")
        return isLeapYear(year)
    if name == "getCurrentWorkingDirectory":
        return getCurrentWorkingDirectory()
    if name == "listDirectory":
        return listDirectory(args.get("dir"))
    if name == "getFileType":
        return getFileType(args.get("path"))
    if name == "getFileContent":
        return getFileContent(args.get("path"))
    if name == "createFile":
        return createFile(
            args.get("dir"),
            args.get("filename"),
            args.get("content") or "",
            bool(args.get("overwrite")),
        )
    if name == "editFileContent":
        return editFileContent(
            args.get("path"),
            args.get("content") or "",
            bool(args.get("append")),
        )
    if name == "createDirectory":
        return createDirectory(args.get("dir"))
    if name == "removeDirectory":
        return removeDirectory(args.get("dir"), bool(args.get("recursive")))
    if name == "deleteFile":
        return deleteFile(args.get("path"))
    if name == "renamePath":
        return renamePath(args.get("src"), args.get("dst"), bool(args.get("overwrite")))
    if name == "fetchWeb":
        return fetchWeb(args.get("url"))
    if name == "searchWeb":
        return searchWeb(args.get("query"))
    if name == "loadSkill":
        return loadSkill(args.get("name"), args.get("filename"))
    if name == "createSkill":
        return createSkill(args.get("name"), args.get("skillContext"))
    if name == "createMCP":
        return createMCP(args.get("server_name"), args.get("transport_type"), args.get("url"))
    if name == "recallContext":
        return recallContext(args.get("id"), args.get("text"))
    if "__" in name or mcp_manager.has_tool(name):
        return mcp_manager.call_tool(name, args)
    return f"未知的工具：{name}"


def recallContext(archive_id=None, text=None):
    try:
        return context_manager.recall(text, archive_id)
    except Exception as exc:
        return f"recallContext 失败：{exc}"


def loadSkill(name, filename=None):
    try:
        return skill_manager.load_skill(name, filename)
    except Exception as exc:
        return f"加载 Skill 失败：{exc}"


def createSkill(name, skillContext):
    try:
        return skill_manager.create_skill(name, skillContext)
    except Exception as exc:
        return f"创建 Skill 失败：{exc}"


def createMCP(server_name=None, transport_type=None, url=None):
    try:
        name = str(server_name or "").strip()
        url_text = str(url or "").strip()
        transport = str(transport_type or "").strip()
        if not name:
            return "createMCP 参数错误：server_name 不能为空。"
        if not url_text:
            return "createMCP 参数错误：url 不能为空。"
        normalized = transport.lower().replace("-", "_")
        if normalized not in ("streamable_http", "streamablehttp", "http"):
            return (
                "createMCP 参数错误：transport_type 仅支持 streamable-http"
                f"（收到：{transport or '（空）'}）。"
            )
        entry = {"type": "streamable-http", "url": url_text}
        path, saved = save_mcp_servers(
            {name: entry}, mcp_manager.config_path, mcp_manager.project_root
        )
        mcp_manager.reload()
        lines = [f"已写入 MCP 配置：{path}", f"已保存服务器：{', '.join(saved)}"]
        discovered = [
            t["name"] for t in mcp_manager.get_tools_info() if t["server"] in saved
        ]
        if discovered:
            lines.append("已发现工具：" + ", ".join(discovered))
        errors = [
            message
            for message in mcp_manager.get_errors()
            if any(server in message for server in saved)
        ]
        if errors:
            lines.extend(errors)
        elif discovered:
            lines.append("连接成功。")
        else:
            lines.append("未能从该服务器发现工具（服务可能未启动；仅告警，不影响其他工具）。")
        return "\n".join(lines)
    except Exception as exc:
        return f"createMCP 失败：{exc}"


