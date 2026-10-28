"""Function Call 工具集合。

Practice02 在 Practice01 的基础上新增的工具：

- `getDate`：日期与时间一律通过调用操作系统本地的 `date` 命令获得，
  不在 Python 代码里用 datetime 自行计算。
- `isLeapYear`：判断某一年是否为闰年，判断过程完全由 Python 代码完成。
- 本地文件操作工具：获取工作目录、列出目录、获取文件类型、读取纯文本内容、
  创建文件（支持创建目录）、编辑纯文本文件、创建目录、删除非空目录、删除文件、重命名文件/目录。
"""

import locale
import os
import shutil
import subprocess
from pathlib import Path

TOOL_TIMEOUT = 10

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "getDate",
            "description": "获取当前电脑的日期和时间。当用户询问今天日期、当前时间、现在几点、星期几等问题时调用本工具。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "getCurrentWorkingDirectory",
            "description": "获取当前工作目录的绝对路径。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listDirectory",
            "description": "列出指定目录下所有文件和子目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dir": {
                        "type": "string",
                        "description": "要列出的目录路径，可以是相对路径或绝对路径。",
                    }
                },
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
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件或目录的路径。",
                    }
                },
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
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取的纯文本文件路径。",
                    }
                },
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
                    "dir": {
                        "type": "string",
                        "description": "文件所在的目录路径，如目录不存在会自动创建。",
                    },
                    "filename": {
                        "type": "string",
                        "description": "要创建的文件名。",
                    },
                    "content": {
                        "type": "string",
                        "description": "可选：文件的初始内容（纯文本）。",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "可选：如果文件已存在是否覆盖，默认 false。",
                    },
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
                    "path": {
                        "type": "string",
                        "description": "要编辑的纯文本文件路径。",
                    },
                    "content": {
                        "type": "string",
                        "description": "新的文件内容（纯文本）。",
                    },
                    "append": {
                        "type": "boolean",
                        "description": "可选：true 表示追加到文件末尾，false（默认）表示覆盖整个文件。",
                    },
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
                "properties": {
                    "dir": {
                        "type": "string",
                        "description": "要创建的目录路径。",
                    }
                },
                "required": ["dir"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "removeDirectory",
            "description": "删除目录（非空目录也会被删除）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dir": {
                        "type": "string",
                        "description": "要删除的目录路径。",
                    }
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
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要删除的文件路径。",
                    }
                },
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
                    "src": {
                        "type": "string",
                        "description": "源文件或目录路径。",
                    },
                    "dst": {
                        "type": "string",
                        "description": "目标文件或目录路径（新名称或新路径）。",
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "可选：如果目标已存在是否覆盖，默认 false。",
                    },
                },
                "required": ["src", "dst"],
                "additionalProperties": False,
            },
        },
    },
]

IS_LEAP_YEAR_TOOL = {
    "type": "function",
    "function": {
        "name": "isLeapYear",
        "description": "判断指定年份是否为闰年。当用户询问某一年是闰年还是平年时调用本工具。",
        "parameters": {
            "type": "object",
            "properties": {
                "year": {
                    "type": "integer",
                    "description": "需要判断的年份，例如 2024。",
                }
            },
            "required": ["year"],
        },
    },
}


def _decode(raw):
    """按 UTF-8、系统默认编码、GBK 的顺序解码子进程输出，兼容中文 Windows 控制台。"""
    for enc in ("utf-8", locale.getpreferredencoding(False), "gbk"):
        if not enc:
            continue
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _date_command():
    """返回调用本地 date 命令的方式。"""
    if os.name == "nt":
        # Windows：cmd.exe 内置的 date / time 命令。
        # date 直接执行会进入交互式修改日期，因此用 date /t 只显示、不修改；time /t 同理。
        return ["cmd", "/c", "date /t & time /t"]
    # Linux / macOS：date 命令自身即输出完整的日期与时间
    return ["date"]


def getDate():
    """调用本地 date 命令，返回当前电脑的日期与时间文本。"""
    cmd = _date_command()
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=TOOL_TIMEOUT)
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
    """用 Python 代码判断给定年份是否为闰年。

    公历闰年规则：能被 4 整除但不能被 100 整除，或能被 400 整除。
    """
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
    """获取当前工作目录的绝对路径。"""
    return os.path.abspath(os.getcwd())


def listDirectory(dir):
    """列出指定目录下所有文件和子目录。"""
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
    """获取指定路径的类型（文件、目录或其他）。"""
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
    """获取指定文件的内容（仅支持纯文本格式文件）。"""
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
    """根据指定的目录和文件名创建新文件（同时支持创建新目录）。"""
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
    """编辑指定文件的内容（仅支持纯文本格式文件）。"""
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
    """创建新目录（如父目录不存在会自动创建）。"""
    try:
        p = Path(dir)
        p.mkdir(parents=True, exist_ok=True)
        return f"已创建目录：{p}"
    except Exception as exc:
        return f"创建目录失败：{exc}"


def removeDirectory(dir):
    """删除目录（非空目录也会被删除）。"""
    try:
        p = Path(dir)
        if not p.exists():
            return f"目录不存在：{p}"
        if not p.is_dir():
            return f"指定路径不是目录：{p}"
        shutil.rmtree(p)
        return f"已删除目录：{p}"
    except Exception as exc:
        return f"删除目录失败：{exc}"


def deleteFile(path):
    """删除文件。"""
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
    """重命名文件和目录。"""
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


def call_tool(name, arguments=None):
    """按工具名分发调用，返回工具输出文本。"""
    args = arguments or {}
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
        return removeDirectory(args.get("dir"))
    if name == "deleteFile":
        return deleteFile(args.get("path"))
    if name == "renamePath":
        return renamePath(args.get("src"), args.get("dst"), bool(args.get("overwrite")))
    return f"未知的工具：{name}"
