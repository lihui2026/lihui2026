from core.agent import AGENTS_MD_MARKER, Agent
from core.config import load_config
from core.context import ContextManager
from core.session import SessionStore


class FakeClient:
    def get_context_window(self):
        return 128000, False

    def chat(self, messages):
        return {
            "choices": [
                {"message": {"role": "assistant", "content": "好的"}}
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "total_tokens": 110,
            },
        }

    def complete(self, messages):
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "压缩摘要",
                    }
                }
            ]
        }


def build_agent(tmp_path, agents_md=None):
    if agents_md is not None:
        (tmp_path / "AGENTS.md").write_text(agents_md, encoding="utf-8")
    store = SessionStore(project_root=tmp_path)
    context = ContextManager(project_root=str(tmp_path))
    agent = Agent(
        load_config(),
        client=FakeClient(),
        context_store=context,
        session_store=store,
        start_mcp=False,
    )
    return agent, store


def system_messages(agent):
    return [message for message in agent.messages if message.get("role") == "system"]


def agents_messages(agent):
    return [
        message
        for message in system_messages(agent)
        if str(message.get("content") or "").startswith(AGENTS_MD_MARKER)
    ]


def test_agents_md_is_injected_once_and_persisted(tmp_path):
    agent, store = build_agent(tmp_path, "使用中文回答")

    info = agent.get_session_info()
    assert info["agents_md_injected"] is True
    assert info["agents_md_path"].endswith("AGENTS.md")
    assert len(system_messages(agent)) == 2
    assert len(agents_messages(agent)) == 1
    assert "使用中文回答" in agents_messages(agent)[0]["content"]

    loaded = store.load(agent.session["id"])
    assert len(
        [
            message
            for message in loaded["messages"]
            if message.get("role") == "system"
        ]
    ) == 2


def test_no_agents_md_does_not_inject(tmp_path):
    agent, _ = build_agent(tmp_path)

    info = agent.get_session_info()
    assert info["agents_md_injected"] is False
    assert info["agents_md_path"] is None
    assert len(system_messages(agent)) == 1


def test_new_session_reinjects_agents_md_once(tmp_path):
    agent, _ = build_agent(tmp_path, "规则 A")
    first_id = agent.session["id"]

    info = agent.new_session()

    assert info["id"] != first_id
    assert info["agents_md_injected"] is True
    assert len(system_messages(agent)) == 2
    assert len(agents_messages(agent)) == 1


def test_load_session_does_not_duplicate_agents_md(tmp_path):
    agent, _ = build_agent(tmp_path, "规则 A")
    session_id = agent.session["id"]
    list(agent.process("你好"))
    agent.new_session("另一个会话")

    info = agent.load_session(session_id)

    assert info["agents_md_injected"] is True
    assert len(system_messages(agent)) == 2
    assert len(agents_messages(agent)) == 1
    assert any(
        message.get("role") == "user" and message.get("content") == "你好"
        for message in agent.messages
    )


def test_first_user_message_updates_session_title(tmp_path):
    agent, store = build_agent(tmp_path)

    list(agent.process("帮我创建一个文件"))

    assert agent.get_session_info()["title"] == "帮我创建一个文件"
    assert store.load(agent.session["id"])["title"] == "帮我创建一个文件"


def test_compact_preserves_all_leading_system_messages(tmp_path):
    agent, _ = build_agent(tmp_path, "规则 A")
    list(agent.process("你好"))

    result = agent.compact()

    assert result["id"]
    assert len(system_messages(agent)) == 2
    assert len(agents_messages(agent)) == 1
    assert agent.messages[-1]["role"] == "user"
    assert "压缩摘要" in agent.messages[-1]["content"]
    assert result["id"] in agent.messages[-1]["content"]
