from core.agent import Agent
from core.config import load_config
from core.context import ContextManager


class FakeClient:
    def __init__(self, window=128000):
        self.window = window
        self.is_default = False
        self.complete_calls = []

    def get_context_window(self):
        return self.window, self.is_default

    def chat(self, messages):
        return {
            "choices": [{"message": {"role": "assistant", "content": "好的"}}],
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 50,
                "total_tokens": 1050,
            },
        }

    def complete(self, messages):
        self.complete_calls.append(messages)
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "# 摘要\n\n- 目标：创建文件\n- 下一步：继续",
                    }
                }
            ]
        }


def build_agent(tmp_path, window=128000):
    cfg = load_config()
    store = ContextManager(project_root=str(tmp_path))
    client = FakeClient(window=window)
    agent = Agent(cfg, client=client, context_store=store, start_mcp=False)
    return agent, client, store


def test_process_appends_assistant_and_reports_context(tmp_path):
    agent, _, _ = build_agent(tmp_path)
    events = list(agent.process("你好"))
    kinds = [e["type"] for e in events]
    assert "thought" in kinds
    assert "context" in kinds
    assert agent.messages[-1]["role"] == "assistant"


def test_compact_replaces_context_and_archives(tmp_path):
    agent, client, _ = build_agent(tmp_path)
    list(agent.process("帮我创建 hello.txt"))

    result = agent.compact()

    archive_path = tmp_path / ".agents" / "context" / f"{result['id']}.jsonl"
    assert archive_path.is_file()
    assert len(agent.messages) == 2
    assert agent.messages[0]["role"] == "system"
    assert "压缩" in agent.messages[1]["content"]
    assert "recallContext" in agent.messages[1]["content"]
    assert result["id"] in agent.messages[1]["content"]
    assert client.complete_calls
    assert not agent.paused


def test_compact_requires_history(tmp_path):
    agent, _, _ = build_agent(tmp_path)
    try:
        agent.compact()
        assert False, "没有历史时应当抛出异常"
    except RuntimeError:
        pass


def test_paused_blocks_new_prompt(tmp_path):
    agent, _, _ = build_agent(tmp_path, window=1000)
    list(agent.process("你好"))
    assert agent.paused

    blocked = list(agent.process("再来一次"))
    assert blocked and blocked[0]["type"] == "paused"


class ScriptedClient(FakeClient):
    """第一次返回工具调用，第二次返回最终回答。"""

    def __init__(self):
        super().__init__()
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        if self.calls == 1:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "getCurrentWorkingDirectory",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            }
        return super().chat(messages)


def test_tool_call_loop_reports_context(tmp_path):
    cfg = load_config()
    store = ContextManager(project_root=str(tmp_path))
    agent = Agent(
        cfg, client=ScriptedClient(), context_store=store, start_mcp=False
    )
    events = list(agent.process("当前目录是哪里？"))
    kinds = [e["type"] for e in events]
    assert kinds.count("context") == 2
    assert "tool_call" in kinds
    assert "thought" in kinds
    roles = [m["role"] for m in agent.messages]
    assert roles == ["system", "user", "assistant", "tool", "assistant"]


def test_recall_context_tool(tmp_path, monkeypatch):
    import core.tools as tools

    store = ContextManager(project_root=str(tmp_path))
    store.save_archive(
        [{"role": "user", "content": "记住密码是 hunter2"}],
        archive_id="20261022-153000",
    )
    monkeypatch.setattr(tools, "context_manager", store)

    output = tools.call_tool("recallContext", {"text": "hunter2"})
    assert "20261022-153000" in output
    assert "hunter2" in output
