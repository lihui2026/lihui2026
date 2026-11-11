import asyncio

import tui.app as tui


class FakeClient:
    def get_context_window(self):
        return (128000, True)


class FakeConfig:
    def __init__(self, base_dir):
        self.base_dir = str(base_dir)
        self.session_dir = ".agents/sessions"
        self.session_list_limit = 50
        self.sidebar_width = 34
        self.command_palette_max = 8
        self.compact_threshold = 0.6
        self.model = "fake-model"


class FakeSessionStore:
    def __init__(self, *args, **kwargs):
        self.project_root = "."

    def list_sessions(self, limit=50):
        return [
            {
                "id": "20261111-100000",
                "title": "旧会话",
                "message_count": 3,
                "updated_at": "2026-11-11T10:00:00",
                "path": "old.jsonl",
            },
            {
                "id": "20261111-110000",
                "title": "新会话",
                "message_count": 1,
                "updated_at": "2026-11-11T11:00:00",
                "path": "new.jsonl",
            },
        ]

    def load(self, session_id):
        return {
            "id": session_id,
            "title": "旧会话",
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
            ],
            "message_count": 2,
            "path": "old.jsonl",
            "created_at": "2026-11-11T10:00:00",
            "updated_at": "2026-11-11T10:00:00",
        }

    def create(self, title=None):
        return {
            "id": "20261111-120000",
            "title": title or "新会话",
            "path": "new.jsonl",
            "message_count": 0,
        }

    def save_snapshot(self, *args, **kwargs):
        pass

    def append_message(self, *args, **kwargs):
        pass

    def update_title(self, *args, **kwargs):
        pass


class FakeAgent:
    def __init__(self, cfg, session_store=None, start_mcp=False):
        self.cfg = cfg
        self.client = FakeClient()
        self.paused = False
        self.compact_called = False
        self.session_store = session_store
        self.session = {"id": "fake-session", "title": "fake", "path": "fake"}
        self.messages = [{"role": "system", "content": "sys"}]
        self.project_root = "."
        self._agents_md_injected = False

    def get_context_status(self):
        return {
            "tokens": 1000,
            "window": 128000,
            "window_is_default": True,
            "ratio": 0.0078,
            "warning": False,
            "paused": False,
        }

    def get_session_info(self):
        return {
            "id": "fake-session",
            "title": "fake",
            "path": "fake",
            "message_count": len(self.messages),
            "agents_md_injected": False,
            "agents_md_path": None,
        }

    def process(self, text):
        self.messages.append({"role": "user", "content": text})
        yield {"type": "thought", "content": "fake reply"}
        yield {"type": "context", "status": self.get_context_status()}
        self.messages.append({"role": "assistant", "content": "fake reply"})

    def compact(self):
        self.compact_called = True
        return {
            "id": "20261022-153000",
            "original": "原始上下文",
            "summary": "压缩摘要",
            "status": self.get_context_status(),
        }

    def new_session(self, title=None):
        self.messages = [{"role": "system", "content": "sys"}]
        self.session = {"id": "new-session", "title": "新会话", "path": "new"}
        return self.get_session_info()

    def load_session(self, session_id):
        self.messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        self.session = {"id": session_id, "title": "旧会话", "path": "old"}
        return self.get_session_info()

    def save_session(self):
        return self.get_session_info()

    def clear_history(self):
        self.messages = [{"role": "system", "content": "sys"}]
        return self.get_session_info()

    def refresh_system_prompt(self):
        pass


class FakeMCP:
    def __init__(self):
        self.started = False

    def start(self, local_tool_names=None):
        self.started = True

    def describe(self):
        return ["MCP Server 'demo' 已连接，发现 1 个工具。"]

    def get_tools_info(self):
        return [
            {
                "name": "demo__ping",
                "server": "demo",
                "original": "ping",
                "description": "ping",
            }
        ]

    def get_errors(self):
        return []


def setup_app(monkeypatch, tmp_path, config_created=False):
    monkeypatch.setattr(tui, "Agent", FakeAgent)
    monkeypatch.setattr(tui, "SessionStore", FakeSessionStore)
    monkeypatch.setattr(
        tui, "ensure_config", lambda: (tmp_path / "config.ini", config_created)
    )
    monkeypatch.setattr(tui, "load_config", lambda path=None: FakeConfig(tmp_path))
    fake_mcp = FakeMCP()
    monkeypatch.setattr(tui, "mcp_manager", fake_mcp)
    return tui.xAgentApp(project_root=str(tmp_path)), fake_mcp


def test_tui_compact_flow(monkeypatch, tmp_path):
    app, fake_mcp = setup_app(monkeypatch, tmp_path)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#user-input").value = "hello"
            await pilot.press("enter")
            await pilot.pause()

            app.query_one("#user-input").value = "/compact"
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, tui.CompactPanelScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, tui.CompactPanelScreen)
            assert app.agent.compact_called
            assert fake_mcp.started

    asyncio.run(scenario())


def test_tui_command_palette_completion(monkeypatch, tmp_path):
    app, _ = setup_app(monkeypatch, tmp_path)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.pause()
            inp = app.query_one("#user-input")
            inp.value = "/ne"
            await pilot.pause()
            assert app._palette_visible
            assert app.query_one("#command-palette").display

            await pilot.press("tab")
            await pilot.pause()
            assert inp.value == "/new"

            await pilot.press("escape")
            await pilot.pause()
            assert not app._palette_visible

    asyncio.run(scenario())


def test_tui_session_list_and_resume(monkeypatch, tmp_path):
    app, _ = setup_app(monkeypatch, tmp_path)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.pause()
            app.query_one("#user-input").value = "/resume"
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, tui.SessionListScreen)

            await pilot.press("down")
            await pilot.pause()
            assert app.screen.index == 1

            await pilot.press("enter")
            await pilot.pause()
            assert not isinstance(app.screen, tui.SessionListScreen)
            assert app.agent.session["id"] == "20261111-110000"

    asyncio.run(scenario())


def test_tui_config_notice(monkeypatch, tmp_path):
    app, _ = setup_app(monkeypatch, tmp_path, config_created=True)

    async def scenario():
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, tui.ConfigNoticeScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, tui.ConfigNoticeScreen)

    asyncio.run(scenario())
