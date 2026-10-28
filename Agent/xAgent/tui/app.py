"""Textual TUI for xAgent."""
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, Static

from core.agent import Agent
from core.config import load_config


class Message(Static):
    def __init__(self, content: str, role: str = "assistant"):
        super().__init__(content)
        self.role = role


class xAgentApp(App):
    CSS_PATH = "styles/app.tcss"
    BINDINGS = [("ctrl+c", "quit", "退出")]

    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.agent = Agent(self.cfg)
        self.history = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Vertical(id="chat-log"),
            Horizontal(
                Input(placeholder="输入问题，按回车发送...", id="user-input"),
                Button("发送", id="send-btn", variant="primary"),
                id="input-bar",
            ),
            id="main",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#user-input").focus()
        self._log("系统：xAgent 已启动（TUI） | 已接入文件操作工具集")

    def _log(self, text: str):
        log = self.query_one("#chat-log")
        log.mount(Static(text))
        log.scroll_end(animate=False)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            await self._handle_send()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        await self._handle_send()

    async def _handle_send(self):
        inp = self.query_one("#user-input")
        text = inp.value.strip()
        if not text:
            return
        inp.value = ""
        self._log(f"你：{text}")
        try:
            for evt in self.agent.process(text):
                if evt["type"] == "tool_call":
                    self._log(f"→ 工具 {evt['tool']}({evt['args']})")
                    self._log(f"← {evt['result']}")
                elif evt["type"] == "thought":
                    self._log(f"助手：{evt['content']}")
                elif evt["type"] == "error":
                    self._log(f"错误：{evt['content']}")
        except Exception as e:
            self._log(f"错误：{e}")


def main():
    app = xAgentApp()
    app.run()


if __name__ == "__main__":
    main()
