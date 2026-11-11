"""Agent core logic separated from UI."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.context import (
    ContextManager,
    context_manager,
    estimate_messages_tokens,
    estimate_tools_tokens,
    render_messages,
)
from core.llm import LLMClient
from core.mcp.mcp_client import mcp_client_manager
from core.prompts import build_compaction_prompt
from core.session import SessionStore
from core.skills import skill_manager
from core.tools import LOCAL_TOOL_NAMES, call_tool, get_tools
from core.utils import getDate as _getDate


AGENTS_MD_MARKER = "以下是项目根目录中的 AGENTS.md 内容"


class Agent:
    def __init__(
        self,
        cfg,
        client: LLMClient | None = None,
        context_store: ContextManager | None = None,
        session_store: SessionStore | None = None,
        start_mcp: bool = False,
        project_root: str | Path | None = None,
    ):
        self.cfg = cfg
        self.client = client or LLMClient(cfg)
        self.context = context_store or context_manager
        self.session_store = session_store
        if session_store is not None:
            self.project_root = Path(session_store.project_root).resolve()
        elif project_root is not None:
            self.project_root = Path(project_root).resolve()
        elif context_store is not None:
            self.project_root = Path(context_store.project_root).resolve()
        else:
            self.project_root = Path(os.getcwd()).resolve()

        if start_mcp:
            mcp_client_manager.start(local_tool_names=LOCAL_TOOL_NAMES)

        self.session: Optional[Dict[str, Any]] = None
        self._agents_md_injected = False
        self.messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.build_system_prompt()}
        ]
        # 上下文压缩状态：压缩期间禁止处理普通任务和工具调用
        self.compacting = False
        # 上下文达到阈值后暂停接收新的普通提示词
        self.paused = False
        self._last_tokens = 0
        self._context_window = 0
        self._window_is_default = True

        if self.session_store is not None:
            self.session = self.session_store.create()
            self._inject_agents_md()
            self._persist_snapshot("init")

    # ---------- System Prompt 与 AGENTS.md ----------

    def build_system_prompt(self) -> str:
        base = (
            "你是一个本地文件操作助手。当前电脑的日期与时间是 "
            f"{_getDate()}。\n"
            "你可以使用以下工具：getCurrentWorkingDirectory、listDirectory、getFileType、"
            "getFileContent、createFile、editFileContent、createDirectory、"
            "removeDirectory、deleteFile、renamePath、getDate、isLeapYear、fetchWeb、searchWeb、RunCli、loadSkill、createSkill、createMCP、recallContext。\n"
            "当用户提供 MCP Server 配置（server_name、transport_type、url）时，请调用 createMCP 工具将其写入 office/.mcp.json，"
            "写入后会自动重连 MCP Server 并刷新工具列表（transport_type 目前支持 streamable-http）。\n"
            "对于文件内容操作，仅支持纯文本格式文件。\n"
            "当用户要求创建新的 Skill 时，请调用 createSkill 工具；若还需创建 references/、scripts/ 等附加目录或文件，"
            "请在创建 Skill 后继续使用 createFile、createDirectory 等文件工具完成。\n"
            "当需要运行本地命令行程序时，请使用 RunCli 工具，并通过 command 和 args 分别传入程序名和参数列表。\n"
            "当需要获取网页主要内容时，请使用 fetchWeb 工具；当需要获取互联网上的最新信息时，请使用 searchWeb 工具。\n"
            "当需要操作本地文件时，请先调用合适的工具获取必要信息再执行后续操作。\n"
            "当上下文压缩摘要缺少某些历史细节时，请使用 recallContext 工具检索原始上下文归档。\n"
        )
        skills_info = skill_manager.get_skills_info()
        if skills_info:
            skills_text = "\nYou have access to the following skills:\n\n"
            for s in skills_info:
                skills_text += f"- `{s['name']}`: {s['description']}\n"
            skills_text += "\nUse the `loadSkill` tool to load the full instructions of a skill when needed. You can also load additional files referenced by a skill.\n"
            base += skills_text
        else:
            base += "\nYou have access to the following skills:\n\n（无）\n\nUse the `loadSkill` tool to load the full instructions of a skill when needed. You can also load additional files referenced by a skill.\n"

        mcp_tools = mcp_client_manager.get_tools_info()
        if mcp_tools:
            limit = int(getattr(self.cfg, "mcp_tool_description_limit", 300) or 300)
            base += "\n你还可以调用以下通过 MCP 接入的外部工具（工具名格式为 服务名__原始工具名）：\n"
            for tool in mcp_tools:
                description = " ".join((tool.get("description") or "").split())
                if len(description) > limit:
                    description = description[:limit] + "..."
                base += f"- `{tool['name']}`（MCP Server: {tool['server']}）：{description}\n"
            base += "调用这些工具时请使用上面列出的名称，并严格按照工具参数 Schema 传参。\n"
        return base

    def _agents_md_path(self) -> Optional[Path]:
        for name in ("AGENTS.md", "agents.md"):
            path = self.project_root / name
            if path.is_file():
                return path
        return None

    @staticmethod
    def _read_text_file(path: Path) -> Optional[str]:
        for encoding in ("utf-8-sig", "utf-8", "gbk"):
            try:
                return path.read_text(encoding=encoding)
            except (UnicodeDecodeError, LookupError):
                continue
            except OSError:
                return None
        return None

    def _inject_agents_md(self) -> bool:
        if self._agents_md_injected:
            return False
        path = self._agents_md_path()
        if path is None:
            return False
        content = self._read_text_file(path)
        if not content or not content.strip():
            return False
        self.messages.append(
            {
                "role": "system",
                "content": (
                    f"{AGENTS_MD_MARKER}，请在本次会话中遵守其中的约定：\n\n"
                    + content.strip()
                ),
            }
        )
        self._agents_md_injected = True
        return True

    # ---------- 会话持久化 ----------

    def _append_message(self, message: Dict[str, Any]) -> None:
        self.messages.append(message)
        if self.session_store is None or self.session is None:
            return
        try:
            self.session_store.append_message(self.session["id"], message)
        except Exception:
            return
        if message.get("role") == "user" and self.session.get("title") in (
            None,
            "",
            "新会话",
        ):
            title = " ".join(str(message.get("content") or "").split())[:40]
            if title:
                self.session["title"] = title
                try:
                    self.session_store.update_title(self.session["id"], title)
                except Exception:
                    pass

    def _persist_snapshot(self, note: str = "") -> None:
        if self.session_store is None or self.session is None:
            return
        try:
            self.session_store.save_snapshot(
                self.session["id"], self.messages, note=note
            )
        except Exception:
            pass

    def _reset_context_state(self) -> None:
        self.paused = False
        self.compacting = False
        self._last_tokens = 0
        self._context_window = 0
        self._window_is_default = True

    def new_session(self, title: Optional[str] = None) -> Dict[str, Any]:
        """新建会话：旧会话已通过 write-through 自动保存。"""
        self.messages = [{"role": "system", "content": self.build_system_prompt()}]
        self._agents_md_injected = False
        self._reset_context_state()
        if self.session_store is not None:
            self.session = self.session_store.create(title=title)
            self._inject_agents_md()
            self._persist_snapshot("new-session")
        return self.get_session_info()

    def load_session(self, session_id: str) -> Dict[str, Any]:
        if self.session_store is None:
            raise RuntimeError("当前未启用会话持久化。")
        data = self.session_store.load(session_id)
        messages = [
            dict(message)
            for message in (data.get("messages") or [])
            if isinstance(message, dict)
        ]
        if messages and messages[0].get("role") == "system":
            messages[0] = {
                "role": "system",
                "content": self.build_system_prompt(),
            }
        else:
            messages.insert(
                0, {"role": "system", "content": self.build_system_prompt()}
            )
        self.messages = messages
        self.session = {
            key: value for key, value in data.items() if key != "messages"
        }
        self._agents_md_injected = any(
            message.get("role") == "system"
            and str(message.get("content") or "").startswith(AGENTS_MD_MARKER)
            for message in self.messages
        )
        self._inject_agents_md()
        self._reset_context_state()
        self._persist_snapshot("resume")
        return self.get_session_info()

    def save_session(self) -> Dict[str, Any]:
        if self.session_store is None or self.session is None:
            raise RuntimeError("当前没有可保存的会话。")
        self._persist_snapshot("manual-save")
        return self.get_session_info()

    def clear_history(self) -> Dict[str, Any]:
        """清空当前上下文（保留会话文件，并重新注入 AGENTS.md）。"""
        self.messages = [{"role": "system", "content": self.build_system_prompt()}]
        self._agents_md_injected = False
        self._inject_agents_md()
        self._reset_context_state()
        self._persist_snapshot("clear")
        return self.get_session_info()

    def refresh_system_prompt(self) -> None:
        """MCP 异步加载完成后刷新 System Prompt（通常在会话刚开始时调用）。"""
        if not self.messages:
            self.messages = [
                {"role": "system", "content": self.build_system_prompt()}
            ]
        else:
            self.messages[0] = {
                "role": "system",
                "content": self.build_system_prompt(),
            }
        self._inject_agents_md()
        self._persist_snapshot("refresh-system-prompt")

    def get_session_info(self) -> Dict[str, Any]:
        if self.session is None:
            return {
                "id": None,
                "title": None,
                "path": None,
                "message_count": len(self.messages),
                "agents_md_injected": self._agents_md_injected,
                "agents_md_path": (
                    str(self._agents_md_path())
                    if self._agents_md_path() is not None
                    else None
                ),
            }
        info = dict(self.session)
        info["message_count"] = len(self.messages)
        info["agents_md_injected"] = self._agents_md_injected
        path = self._agents_md_path()
        info["agents_md_path"] = str(path) if path is not None else None
        return info

    # ---------- 工具调用 ----------

    def run_tool_calls(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        tool_calls = message.get("tool_calls") or []
        results = []
        self._append_message(
            {
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": tool_calls,
            }
        )
        for call in tool_calls:
            fn = call.get("function") or {}
            name = fn.get("name", "")
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {}
            try:
                result = call_tool(name, args)
            except Exception as exc:
                result = f"工具调用失败（{name}）：{exc}"
            results.append({"tool": name, "args": args, "result": result})
            self._append_message(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "name": name,
                    "content": result,
                }
            )
        return results

    # ---------- 上下文长度监控 ----------

    def estimate_context_tokens(self) -> int:
        """无法从 API 获得用量时，估算当前上下文占用的 Token 数。"""
        return estimate_messages_tokens(self.messages) + estimate_tools_tokens(
            get_tools()
        )

    def update_context_status(
        self, usage: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """更新上下文用量；优先使用 API 返回的 usage，否则使用估算值。"""
        tokens: Optional[int] = None
        if isinstance(usage, dict):
            for key in ("total_tokens", "prompt_tokens"):
                value = usage.get(key)
                if isinstance(value, int) and value > 0:
                    tokens = value
                    break
        if tokens is None:
            tokens = self.estimate_context_tokens()
        window, is_default = self.client.get_context_window()
        self._last_tokens = tokens
        self._context_window = window
        self._window_is_default = is_default
        ratio = (tokens / window) if window else 0.0
        threshold = float(getattr(self.cfg, "compact_threshold", 0.6) or 0.6)
        self.paused = ratio >= threshold
        return self.get_context_status()

    def get_context_status(self) -> Dict[str, Any]:
        tokens = self._last_tokens or self.estimate_context_tokens()
        window = self._context_window
        if not window:
            window, is_default = self.client.get_context_window()
            self._context_window = window
            self._window_is_default = is_default
        ratio = (tokens / window) if window else 0.0
        threshold = float(getattr(self.cfg, "compact_threshold", 0.6) or 0.6)
        return {
            "tokens": tokens,
            "window": window,
            "window_is_default": self._window_is_default,
            "ratio": ratio,
            "warning": ratio >= threshold,
            "paused": self.paused,
        }

    # ---------- 上下文压缩 ----------

    def compact(self) -> Dict[str, Any]:
        """手动压缩上下文：归档原文 -> 调用 LLM 生成摘要 -> 替换历史消息。

        任一步失败都会保留原有上下文并抛出异常，允许用户重新执行 /compact。
        """
        if self.compacting:
            raise RuntimeError("已有一次上下文压缩正在进行。")
        system_messages: List[Dict[str, Any]] = []
        for message in self.messages:
            if message.get("role") == "system":
                system_messages.append(message)
            else:
                break
        if not any(
            message.get("role") != "system" for message in self.messages
        ):
            raise RuntimeError("当前会话没有可压缩的对话历史。")
        self.compacting = True
        try:
            original_messages = [dict(message) for message in self.messages]
            # 1) 先完整归档；保存失败则不继续
            archive_id, archive_path = self.context.save_archive(original_messages)
            original_text = render_messages(original_messages)
            # 2) 调用 LLM 生成摘要（不带工具，禁止 Function Calling）
            summary = self._generate_summary(original_messages)
            if not summary or not summary.strip():
                raise RuntimeError("模型没有返回有效的压缩摘要。")
            # 3) 摘要末尾追加归档说明
            now = datetime.now()
            note = (
                f"此前上下文已于 {now.strftime('%Y-%m-%d %H:%M:%S')} 完成压缩，"
                f"原始上下文保存在编号为 {archive_id} 的归档文件中。"
                "如需查找历史信息，请使用 recallContext 工具。"
            )
            summary_text = summary.strip() + "\n\n" + note
            # 4) 保留所有前导 System Prompt（含 AGENTS.md），用摘要替换其余历史消息
            if not system_messages:
                system_messages = [
                    {"role": "system", "content": self.build_system_prompt()}
                ]
            self.messages = system_messages + [
                {
                    "role": "user",
                    "content": (
                        "以下是对此前会话历史的压缩摘要，请基于它继续完成用户的后续任务：\n\n"
                        + summary_text
                    ),
                }
            ]
            self.paused = False
            self._last_tokens = 0
            status = self.update_context_status(None)
            self._persist_snapshot(f"compact:{archive_id}")
            return {
                "id": archive_id,
                "path": str(archive_path),
                "original": original_text,
                "summary": summary_text,
                "note": note,
                "status": status,
            }
        finally:
            self.compacting = False

    def _generate_summary(self, messages: List[Dict[str, Any]]) -> str:
        # 跳过所有前导 System Prompt（它们会被原样保留），只压缩对话历史
        start = 0
        while start < len(messages) and messages[start].get("role") == "system":
            start += 1
        content_limit = int(
            getattr(self.cfg, "compaction_message_char_limit", 20000) or 20000
        )
        history = render_messages(messages[start:], content_limit=content_limit)
        target_tokens = int(
            getattr(self.cfg, "summary_target_tokens", 5000) or 5000
        )
        prompt_messages = [
            {"role": "system", "content": build_compaction_prompt(target_tokens)},
            {
                "role": "user",
                "content": (
                    "以下是当前会话的完整历史上下文（按时间顺序，已跳过 System Prompt）：\n\n"
                    + history
                ),
            },
        ]
        result = self.client.complete(prompt_messages)
        choices = result.get("choices") or []
        if not choices:
            raise RuntimeError("模型没有返回任何结果。")
        return (choices[0].get("message") or {}).get("content") or ""

    # ---------- 主循环 ----------

    def process(self, user_input: str):
        if self.compacting:
            yield {
                "type": "error",
                "content": "正在进行上下文压缩，暂时无法处理新请求。",
            }
            return
        if self.paused:
            yield {
                "type": "paused",
                "content": "上下文使用量已达到阈值，请先执行 /compact 压缩上下文。",
                "status": self.get_context_status(),
            }
            return
        self._append_message({"role": "user", "content": user_input})
        max_rounds = int(getattr(self.cfg, "max_tool_rounds", 5) or 5)
        for _ in range(max_rounds):
            result = self.client.chat(self.messages)
            choices = result.get("choices") or []
            if not choices:
                yield {"type": "error", "content": "模型没有返回任何结果"}
                return
            message = choices[0].get("message") or {}
            usage = result.get("usage")
            if not message.get("tool_calls"):
                self._append_message(
                    {
                        "role": "assistant",
                        "content": message.get("content") or "",
                    }
                )
                yield {
                    "type": "context",
                    "status": self.update_context_status(usage),
                }
                yield {"type": "thought", "content": message.get("content") or ""}
                return
            tool_results = self.run_tool_calls(message)
            yield {
                "type": "context",
                "status": self.update_context_status(usage),
            }
            for tr in tool_results:
                yield {
                    "type": "tool_call",
                    "tool": tr["tool"],
                    "args": tr["args"],
                    "result": tr["result"],
                }
        yield {"type": "error", "content": "（工具调用轮次过多，已中止。）"}
