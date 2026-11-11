"""Slash command registry and completion helpers."""
from __future__ import annotations

from typing import Any, Dict, List


COMMANDS: List[Dict[str, str]] = [
    {"name": "/new", "description": "新建会话（当前会话自动保存）"},
    {"name": "/resume", "description": "恢复历史会话"},
    {"name": "/save", "description": "保存当前会话快照"},
    {"name": "/compact", "description": "压缩当前上下文"},
    {"name": "/clear", "description": "清空当前上下文"},
    {"name": "/status", "description": "查看会话与上下文状态"},
    {"name": "/tools", "description": "列出可用工具"},
    {"name": "/mcp", "description": "刷新 MCP 侧栏"},
    {"name": "/agents", "description": "查看 AGENTS.md 状态"},
    {"name": "/help", "description": "显示命令帮助"},
    {"name": "/quit", "description": "退出 xAgent"},
    {"name": "/exit", "description": "退出 xAgent"},
]

COMMAND_NAMES = frozenset(command["name"] for command in COMMANDS)
COMMAND_MAP = {command["name"]: command for command in COMMANDS}


def match_commands(text: Any, limit: int = 8) -> List[Dict[str, str]]:
    """返回与当前输入前缀匹配的命令（仅在尚未输入参数时匹配）。"""
    if not isinstance(text, str):
        return []
    value = text.strip()
    if not value.startswith("/") or " " in value:
        return []
    matches = [command for command in COMMANDS if command["name"].startswith(value)]
    if limit and limit > 0:
        matches = matches[:limit]
    return matches


def render_help() -> str:
    lines = ["可用命令："]
    for command in COMMANDS:
        lines.append(f"  {command['name']:<10} {command['description']}")
    lines.append("")
    lines.append(
        "输入 / 会弹出命令补全面板；↑/↓ 选择，Tab 补全，Enter 执行，Esc 关闭。"
    )
    return "\n".join(lines)
