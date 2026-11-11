import json
from datetime import datetime

from core.context import ContextManager, estimate_messages_tokens, estimate_tokens


def make_messages():
    return [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "帮我创建一个文件 hello.txt"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {
                        "name": "createFile",
                        "arguments": json.dumps({"dir": ".", "filename": "hello.txt"}),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "name": "createFile",
            "content": "已创建文件：hello.txt",
        },
    ]


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens(None) == 0
    assert estimate_tokens("hello world") >= 1
    assert estimate_tokens("你好，世界") >= 4


def test_estimate_messages_tokens():
    assert estimate_messages_tokens(make_messages()) > 0


def test_save_and_load_archive(tmp_path):
    manager = ContextManager(project_root=str(tmp_path))
    archive_id, path = manager.save_archive(
        make_messages(), archive_id="20261022-153000"
    )
    assert archive_id == "20261022-153000"
    assert path.is_file()

    loaded = manager.load_archive(archive_id)
    assert len(loaded) == 4
    assert [m["index"] for m in loaded] == [0, 1, 2, 3]
    assert loaded[1]["role"] == "user"
    assert loaded[2]["tool_calls"][0]["function"]["name"] == "createFile"
    assert loaded[3]["content"].startswith("已创建文件")


def test_archive_id_collision(tmp_path):
    manager = ContextManager(project_root=str(tmp_path))
    now = datetime(2026, 10, 22, 15, 30, 0)
    first = manager.new_archive_id(now)
    manager.save_archive(make_messages(), archive_id=first)
    second = manager.new_archive_id(now)
    assert first == "20261022-153000"
    assert second != first


def test_recall_by_id_and_all(tmp_path):
    manager = ContextManager(project_root=str(tmp_path))
    manager.save_archive(make_messages(), archive_id="20261022-153000")

    hit = manager.recall("hello.txt", archive_id="20261022-153000")
    assert "20261022-153000" in hit
    assert "hello.txt" in hit

    all_hit = manager.recall("createFile")
    assert "20261022-153000" in all_hit

    miss = manager.recall("不存在的关键词xyz")
    assert "未找到" in miss


def test_recall_rejects_path_traversal(tmp_path):
    manager = ContextManager(project_root=str(tmp_path))
    result = manager.recall("x", archive_id="../../etc/passwd")
    assert "未找到" in result
