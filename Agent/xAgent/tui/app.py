"""Textual TUI for xAgent."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Static

from core.agent import Agent
from core.config import ensure_config, load_config
from core.mcp import mcp_manager
from core.session import SessionStore
from core.tools import LOCAL_TOOL_NAMES
from tui.commands import COMMAND_NAMES, match_commands, render_help


def format_tokens(value: int) -> str:
    """把 Token 数格式化为 k 单位，例如 128000 -> 128k、12500 -> 12.5k。"""
    if value >= 1000:
        number = value / 1000
        return f"{number:.0f}k" if number == int(number) else f"{number:.1f}k"
    return str(value)


class CompactPanelScreen(ModalScreen):
    """上下文压缩结果浮动面板：左侧压缩前原文，右侧压缩后摘要。"""

    BINDINGS = [("escape", "close_panel", "关闭")]

    def __init__(self, original: str, summary: str, archive_id: str):
        super().__init__()
        self.original = original
        self.summary = summary
        self.archive_id = archive_id

    def compose(self) -> ComposeResult:
        with Container(id="compact-panel"):
            yield Static(
                f"上下文压缩预览　归档编号：{self.archive_id}", id="compact-title"
            )
            with Horizontal(id="compact-columns"):
                with Vertical(classes="compact-pane"):
                    yield Static("压缩前原文", classes="compact-pane-title")
                    with VerticalScroll(classes="compact-body"):
                        yield Static(self.original)
                with Vertical(classes="compact-pane"):
                    yield Static(
                        "压缩后结果（末尾已追加归档说明）", classes="compact-pane-title"
                    )
                    with VerticalScroll(classes="compact-body"):
                        yield Static(self.summary)
            yield Button("关闭", id="compact-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "compact-close":
            self.dismiss()

    def action_close_panel(self) -> None:
        self.dismiss()


class SessionListScreen(ModalScreen):
    """历史会话列表：上下键选择，回车恢复，ESC 取消。"""

    BINDINGS = [
        Binding("up", "move(-1)", "上移", show=False),
        Binding("down", "move(1)", "下移", show=False),
        Binding("enter", "select", "恢复"),
        Binding("escape", "cancel", "取消"),
    ]

    def __init__(self, sessions, current_id: Optional[str] = None):
        super().__init__()
        self.sessions = list(sessions)
        self.current_id = current_id
        self.index = 0
        for index, session in enumerate(self.sessions):
            if session.get("id") == current_id:
                self.index = index
                break

    def compose(self) -> ComposeResult:
        with Container(id="session-panel"):
            yield Static("历史会话", id="session-title")
            with VerticalScroll(id="session-list-scroll"):
                yield Static(self._render_list(), id="session-list", markup=False)
            yield Static(
                "↑/↓ 选择　Enter 恢复　Esc 取消", id="session-help"
            )

    def _render_list(self) -> str:
        if not self.sessions:
            return "暂无历史会话。"
        lines = []
        for index, session in enumerate(self.sessions):
            marker = "▶" if index == self.index else " "
            current = "●" if session.get("id") == self.current_id else " "
            title = str(session.get("title") or "新会话")
            if len(title) > 36:
                title = title[:36] + "…"
            updated = str(session.get("updated_at") or session.get("created_at") or "")
            lines.append(
                f"{marker}{current} {session.get('id', '')}  {title}  "
                f"({session.get('message_count', 0)} 条)  {updated}"
            )
        return "\n".join(lines)

    def _refresh(self) -> None:
        try:
            self.query_one("#session-list", Static).update(self._render_list())
        except Exception:
            pass

    def action_move(self, delta: int) -> None:
        if not self.sessions:
            return
        self.index = (self.index + delta) % len(self.sessions)
        self._refresh()

    def action_select(self) -> None:
        if not self.sessions:
            return
        self.dismiss(self.sessions[self.index].get("id"))

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfigNoticeScreen(ModalScreen):
    """配置文件自动创建后的提示对话框。"""

    BINDINGS = [Binding("escape", "continue_app", "继续", show=False)]

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def compose(self) -> ComposeResult:
        with Container(id="config-panel"):
            yield Static("已创建默认配置文件", id="config-title")
            yield Static(
                f"未找到配置文件，已在以下位置创建：\n\n{self.path}\n\n"
                "请修改 LLM 的 base_url、model、api_key 等配置后重新启动 xAgent，"
                "否则无法正常调用模型。",
                id="config-body",
            )
            with Horizontal(id="config-buttons"):
                yield Button(
                    "退出并修改配置", id="config-exit", variant="primary"
                )
                yield Button("继续使用", id="config-continue")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "config-exit":
            self.app.exit()
        else:
            self.dismiss()

    def action_continue_app(self) -> None:
        self.dismiss()


class xAgentApp(App):
    CSS_PATH = "styles/app.tcss"
    BINDINGS = [
        Binding("ctrl+c", "quit", "退出"),
        Binding("up", "palette_up", "上移", show=False, priority=True),
        Binding("down", "palette_down", "下移", show=False, priority=True),
        Binding("tab", "palette_complete", "补全", show=False, priority=True),
        Binding("escape", "palette_close", "关闭补全", show=False, priority=True),
    ]

    def __init__(self, project_root: str | Path | None = None):
        super().__init__()
        self.config_path, self._config_created = ensure_config()
        self.cfg = load_config(self.config_path)
        self.project_root = Path(project_root or os.getcwd()).resolve()
        self.session_store = SessionStore(
            project_root=self.project_root,
            session_dir=self.cfg.session_dir,
        )
        self.agent = Agent(
            self.cfg,
            session_store=self.session_store,
            start_mcp=False,
        )
        self.history = []
        self._compacting = False
        self._warning_shown = False
        self._palette_visible = False
        self._palette_matches = []
        self._palette_index = 0
        self._mcp_loaded = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main"):
            with Vertical(id="content"):
                yield Static("上下文：计算中…", id="context-status")
                yield Vertical(id="chat-log")
                with Vertical(id="input-area"):
                    yield Static("", id="command-palette", markup=False)
                    with Horizontal(id="input-bar"):
                        yield Input(
                            placeholder="输入问题，按回车发送；输入 / 查看命令…",
                            id="user-input",
                        )
                        yield Button("发送", id="send-btn", variant="primary")
            with VerticalScroll(id="mcp-sidebar"):
                yield Static("MCP 服务器", id="mcp-sidebar-title")
                yield Static(
                    "MCP：正在加载…", id="mcp-sidebar-body", markup=False
                )
        yield Footer()

    async def on_mount(self) -> None:
        self.query_one("#user-input").focus()
        try:
            self.query_one("#mcp-sidebar").styles.width = self.cfg.sidebar_width
        except Exception:
            pass
        self._log("系统：xAgent 已启动（TUI） | 已接入文件操作工具集")
        info = self.agent.get_session_info()
        if info.get("id"):
            self._log(
                f"系统：当前会话 {info['id']}（{info.get('title') or '新会话'}）"
            )
        if info.get("agents_md_path"):
            self._log(f"系统：已加载 AGENTS.md：{info['agents_md_path']}")
        self._log("系统：输入 / 查看命令补全，/help 查看全部命令。")
        self._refresh_mcp_sidebar(loading=True)
        # 探测模型上下文窗口（失败时回退到默认值）
        try:
            await asyncio.to_thread(self.agent.client.get_context_window)
        except Exception:
            pass
        self._update_context_status()
        self.run_worker(self._load_mcp_async(), name="mcp-load", exclusive=False)
        if self._config_created:
            self.push_screen(ConfigNoticeScreen(str(self.config_path)))

    async def _load_mcp_async(self) -> None:
        """在后台线程加载 MCP，避免阻塞 TUI 首次渲染。"""
        try:
            await asyncio.to_thread(mcp_manager.start, LOCAL_TOOL_NAMES)
        except Exception as exc:
            self._log(f"系统：MCP 加载失败：{exc}")
        self._mcp_loaded = True
        self._refresh_mcp_sidebar()
        for line in mcp_manager.describe():
            self._log(f"系统：{line}")
        try:
            self.agent.refresh_system_prompt()
        except Exception:
            pass
        self._update_context_status()

    def _log(self, text: str) -> None:
        log = self.query_one("#chat-log")
        log.mount(Static(text))
        log.scroll_end(animate=False)

    # ---------- MCP 侧栏 ----------

    def _refresh_mcp_sidebar(self, loading: bool = False) -> None:
        try:
            body = self.query_one("#mcp-sidebar-body", Static)
        except Exception:
            return
        if loading:
            body.update(
                "MCP：正在后台连接服务器…\n\n界面已可用，连接完成后会自动刷新。"
            )
            return
        grouped = {}
        for tool in mcp_manager.get_tools_info():
            grouped.setdefault(tool.get("server", "?"), []).append(tool)
        lines = []
        if grouped:
            for server in sorted(grouped):
                lines.append(f"● {server}（{len(grouped[server])} 个工具）")
                for tool in grouped[server]:
                    lines.append(f"  - {tool.get('name', '')}")
        else:
            lines.append("（暂无已连接的 MCP 工具）")
        errors = mcp_manager.get_errors()
        if errors:
            lines.append("")
            lines.append("错误：")
            for error in errors:
                lines.append(f"- {error}")
        body.update("\n".join(lines))

    # ---------- 状态栏 ----------

    def _update_context_status(self, status: Optional[dict] = None) -> None:
        status = status or self.agent.get_context_status()
        window_text = format_tokens(status["window"])
        if status.get("window_is_default"):
            window_text += "（默认）"
        percent = status["ratio"] * 100
        session = getattr(self.agent, "session", None) or {}
        prefix = f"会话 {session.get('id')}　|　" if session.get("id") else ""
        threshold = int(
            float(getattr(self.cfg, "compact_threshold", 0.6) or 0.6) * 100
        )
        text = (
            f"{prefix}上下文：{format_tokens(status['tokens'])} / {window_text}，"
            f"已占用 {percent:.1f}%"
        )
        if status.get("warning"):
            text += f"　|　已达 {threshold}% 阈值，请执行 /compact"
        try:
            widget = self.query_one("#context-status", Static)
            widget.update(text)
            if status.get("warning"):
                widget.add_class("warning")
            else:
                widget.remove_class("warning")
        except Exception:
            pass

    # ---------- 输入与命令 ----------

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            await self._handle_send()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "user-input":
            self._update_palette(event.value)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        await self._handle_send()

    async def _handle_send(self) -> None:
        inp = self.query_one("#user-input", Input)
        text = inp.value.strip()
        if not text:
            return
        if text.startswith("/"):
            token = text.split(maxsplit=1)[0]
            if (
                token not in COMMAND_NAMES
                and self._palette_visible
                and self._palette_matches
            ):
                selected = self._palette_matches[self._palette_index]["name"]
                text = selected + text[len(token):]
            inp.value = ""
            self._hide_palette()
            await self._handle_command(text)
            return
        if self._compacting:
            self._log("系统：正在压缩上下文，请稍候。")
            return
        if self.agent.paused:
            threshold = int(
                float(getattr(self.cfg, "compact_threshold", 0.6) or 0.6) * 100
            )
            self._log(
                f"系统：上下文已达到 {threshold}% 阈值，暂停接收新的提示词，"
                "请先执行 /compact。"
            )
            return
        inp.value = ""
        self._hide_palette()
        self._log(f"你：{text}")
        try:
            for evt in self.agent.process(text):
                self._handle_event(evt)
        except Exception as e:
            self._log(f"错误：{e}")
        self._update_context_status()

    async def _handle_command(self, text: str) -> None:
        parts = text.split(maxsplit=1)
        name = parts[0]
        arg = parts[1].strip() if len(parts) > 1 else ""
        if name not in COMMAND_NAMES:
            self._log(f"系统：未知命令 {name}。输入 /help 查看可用命令。")
            return
        if name == "/new":
            await self._cmd_new()
        elif name == "/resume":
            await self._cmd_resume(arg)
        elif name == "/save":
            await self._cmd_save()
        elif name == "/compact":
            await self._handle_compact()
        elif name == "/clear":
            await self._cmd_clear()
        elif name == "/status":
            self._cmd_status()
        elif name == "/tools":
            self._cmd_tools()
        elif name == "/mcp":
            self._cmd_mcp()
        elif name == "/agents":
            self._cmd_agents()
        elif name == "/help":
            self._log("系统：\n" + render_help())
        elif name in ("/quit", "/exit"):
            self.exit()

    async def _cmd_new(self) -> None:
        info = self.agent.new_session()
        await self._clear_chat_log()
        self._warning_shown = False
        self._log(
            f"系统：已创建新会话 {info.get('id')}（{info.get('title') or '新会话'}）。"
        )
        self._log("系统：输入 /resume 可恢复历史会话。")
        self._update_context_status()
        self._refresh_mcp_sidebar()

    async def _cmd_resume(self, arg: str = "") -> None:
        if not self.agent.session_store:
            self._log("系统：当前未启用会话持久化。")
            return
        sessions = self.agent.session_store.list_sessions(
            limit=self.cfg.session_list_limit
        )
        if not sessions:
            self._log("系统：暂无历史会话。")
            return
        if arg:
            exact = [s for s in sessions if s.get("id") == arg]
            prefix = [s for s in sessions if str(s.get("id", "")).startswith(arg)]
            chosen = exact or prefix
            if not chosen:
                self._log(f"系统：未找到会话 {arg}。")
                return
            await self._resume_session(chosen[0].get("id"))
            return
        current = (self.agent.session or {}).get("id")
        self.push_screen(
            SessionListScreen(sessions, current_id=current),
            callback=self._on_session_selected,
        )

    async def _on_session_selected(self, session_id) -> None:
        if session_id:
            await self._resume_session(session_id)

    async def _resume_session(self, session_id: str) -> None:
        info = self.agent.load_session(session_id)
        await self._clear_chat_log()
        self._replay_session()
        self._warning_shown = False
        self._log(
            f"系统：已恢复会话 {info.get('id')}（{info.get('message_count', 0)} 条消息）。"
        )
        self._update_context_status()

    async def _cmd_save(self) -> None:
        try:
            info = self.agent.save_session()
        except Exception as exc:
            self._log(f"错误：保存会话失败：{exc}")
            return
        self._log(f"系统：会话已保存：{info.get('path')}")

    async def _cmd_clear(self) -> None:
        info = self.agent.clear_history()
        await self._clear_chat_log()
        self._warning_shown = False
        self._log(f"系统：已清空当前上下文（会话 {info.get('id')} 保留）。")
        self._update_context_status()

    def _cmd_status(self) -> None:
        info = self.agent.get_session_info()
        status = self.agent.get_context_status()
        lines = [
            f"会话：{info.get('id') or '-'}（{info.get('title') or '-'}）",
            f"文件：{info.get('path') or '-'}",
            f"消息数：{info.get('message_count', 0)}",
            (
                "AGENTS.md："
                + (info.get("agents_md_path") or "未找到")
                + ("（已注入）" if info.get("agents_md_injected") else "")
            ),
            f"模型：{self.cfg.model}",
            (
                f"上下文：{format_tokens(status['tokens'])} / "
                f"{format_tokens(status['window'])}"
                f"（{status['ratio'] * 100:.1f}%）"
            ),
            (
                f"MCP：{len(mcp_manager.get_tools_info())} 个工具，"
                f"{len(mcp_manager.get_errors())} 个错误"
            ),
        ]
        self._log("系统：\n" + "\n".join(lines))

    def _cmd_tools(self) -> None:
        lines = ["本地工具：" + ", ".join(sorted(LOCAL_TOOL_NAMES))]
        mcp_tools = mcp_manager.get_tools_info()
        if mcp_tools:
            lines.append("MCP 工具：")
            for tool in mcp_tools:
                lines.append(f"- {tool.get('name')}（{tool.get('server')}）")
        else:
            lines.append("MCP 工具：（无）")
        self._log("系统：\n" + "\n".join(lines))

    def _cmd_mcp(self) -> None:
        self._refresh_mcp_sidebar()
        lines = mcp_manager.describe() or ["MCP：无可用信息。"]
        self._log("系统：\n" + "\n".join(lines))

    def _cmd_agents(self) -> None:
        info = self.agent.get_session_info()
        path = info.get("agents_md_path")
        if path:
            self._log(f"系统：AGENTS.md 路径：{path}")
            injected = "已" if info.get("agents_md_injected") else "尚未"
            self._log(f"系统：AGENTS.md {injected}注入当前会话。")
        else:
            self._log(
                f"系统：未在当前目录找到 AGENTS.md（{self.agent.project_root}）。"
            )

    def _replay_session(self) -> None:
        for message in self.agent.messages:
            role = message.get("role")
            content = str(message.get("content") or "").strip()
            if role == "user":
                self._log(f"你：{content}")
            elif role == "assistant":
                if content:
                    self._log(f"助手：{content}")
                for call in message.get("tool_calls") or []:
                    fn = call.get("function") or {}
                    self._log(
                        f"→ 工具 {fn.get('name', '')}({fn.get('arguments', '')})"
                    )
            elif role == "tool":
                text = content
                if len(text) > 1000:
                    text = text[:500] + "\n……\n" + text[-500:]
                self._log(f"← {text}")

    async def _clear_chat_log(self) -> None:
        log = self.query_one("#chat-log")
        try:
            await log.remove_children()
        except Exception:
            for child in list(log.children):
                child.remove()

    # ---------- 命令补全 ----------

    def _palette_widget(self) -> Static:
        return self.query_one("#command-palette", Static)

    def _show_palette(self, matches) -> None:
        self._palette_matches = list(matches)
        if not self._palette_matches:
            self._hide_palette()
            return
        self._palette_index = min(
            self._palette_index, len(self._palette_matches) - 1
        )
        self._palette_visible = True
        self._render_palette()
        try:
            self._palette_widget().display = True
        except Exception:
            pass

    def _hide_palette(self) -> None:
        self._palette_visible = False
        self._palette_matches = []
        self._palette_index = 0
        try:
            self._palette_widget().display = False
        except Exception:
            pass

    def _render_palette(self) -> None:
        if not self._palette_matches:
            return
        lines = []
        for index, command in enumerate(self._palette_matches):
            marker = "▶" if index == self._palette_index else " "
            lines.append(
                f"{marker} {command['name']:<12} {command['description']}"
            )
        lines.append("↑/↓ 选择　Tab 补全　Enter 执行　Esc 关闭")
        try:
            self._palette_widget().update("\n".join(lines))
        except Exception:
            pass

    def _update_palette(self, text: str) -> None:
        limit = int(getattr(self.cfg, "command_palette_max", 8) or 8)
        matches = match_commands(text, limit=limit)
        if matches:
            self._show_palette(matches)
        else:
            self._hide_palette()

    def action_palette_up(self) -> None:
        if not self._palette_visible or not self._palette_matches:
            return
        self._palette_index = (
            self._palette_index - 1
        ) % len(self._palette_matches)
        self._render_palette()

    def action_palette_down(self) -> None:
        if not self._palette_visible or not self._palette_matches:
            return
        self._palette_index = (
            self._palette_index + 1
        ) % len(self._palette_matches)
        self._render_palette()

    def action_palette_complete(self) -> None:
        if not self._palette_visible or not self._palette_matches:
            return
        command = self._palette_matches[self._palette_index]["name"]
        inp = self.query_one("#user-input", Input)
        inp.value = command
        inp.cursor_position = len(command)
        inp.focus()
        self._update_palette(command)

    def action_palette_close(self) -> None:
        self._hide_palette()

    def check_action(self, action: str, parameters: tuple) -> bool:
        if action.startswith("palette_"):
            return self._palette_visible
        return True

    # ---------- 事件处理 ----------

    def _handle_event(self, evt: dict) -> None:
        kind = evt.get("type")
        if kind == "tool_call":
            self._log(f"→ 工具 {evt['tool']}({evt['args']})")
            self._log(f"← {evt['result']}")
            if evt.get("tool") == "createMCP":
                self._refresh_mcp_sidebar()
                try:
                    self.agent.refresh_system_prompt()
                except Exception:
                    pass
        elif kind == "thought":
            self._log(f"助手：{evt['content']}")
        elif kind == "context":
            status = evt["status"]
            self._update_context_status(status)
            if status.get("warning") and not self._warning_shown:
                self._warning_shown = True
                threshold = int(
                    float(getattr(self.cfg, "compact_threshold", 0.6) or 0.6)
                    * 100
                )
                self._log(
                    f"系统：上下文使用量已达模型窗口的 {threshold}%，"
                    "请执行 /compact 压缩上下文；压缩完成前将暂停接收新的提示词。"
                )
        elif kind == "paused":
            self._update_context_status(evt.get("status"))
            self._log(f"系统：{evt['content']}")
        elif kind == "error":
            self._log(f"错误：{evt['content']}")

    async def _handle_compact(self) -> None:
        if self._compacting:
            self._log("系统：正在压缩上下文，请稍候。")
            return
        self._compacting = True
        inp = self.query_one("#user-input", Input)
        btn = self.query_one("#send-btn", Button)
        inp.disabled = True
        btn.disabled = True
        self._hide_palette()
        self._log("系统：开始压缩上下文（期间暂停接收输入与工具调用）……")
        try:
            result = await asyncio.to_thread(self.agent.compact)
        except Exception as exc:
            self._log(f"错误：上下文压缩失败：{exc}")
            self._log("系统：已保留原有上下文，可重新执行 /compact。")
            self._update_context_status()
            return
        finally:
            self._compacting = False
            inp.disabled = False
            btn.disabled = False
            inp.focus()
        self._warning_shown = False
        self._update_context_status(result.get("status"))
        self._log(
            f"系统：上下文压缩完成，归档编号 {result['id']}；已恢复接收输入。"
        )
        self.push_screen(
            CompactPanelScreen(
                result["original"], result["summary"], result["id"]
            )
        )


def main():
    app = xAgentApp()
    app.run()


if __name__ == "__main__":
    main()
