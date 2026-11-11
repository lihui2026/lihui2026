from datetime import datetime

import pytest

from core.session import SessionStore


def test_create_append_load_and_list(tmp_path):
    store = SessionStore(project_root=tmp_path)
    created = store.create(
        title="测试会话", now=datetime(2026, 11, 11, 10, 0, 0)
    )
    session_id = created["id"]
    assert session_id == "20261111-100000"

    store.append_message(session_id, {"role": "user", "content": "你好"})
    store.append_message(session_id, {"role": "assistant", "content": "你好！"})

    loaded = store.load(session_id)
    assert loaded["id"] == session_id
    assert loaded["title"] == "测试会话"
    assert loaded["message_count"] == 2
    assert [message["content"] for message in loaded["messages"]] == [
        "你好",
        "你好！",
    ]

    sessions = store.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["id"] == session_id
    assert sessions[0]["message_count"] == 2


def test_session_id_collision_adds_suffix(tmp_path):
    store = SessionStore(project_root=tmp_path)
    now = datetime(2026, 11, 11, 10, 0, 0)

    first = store.create(now=now)
    second = store.create(now=now)

    assert first["id"] == "20261111-100000"
    assert second["id"] == "20261111-100000-2"


def test_snapshot_replaces_history_and_insert_event(tmp_path):
    store = SessionStore(project_root=tmp_path)
    session_id = store.create(
        now=datetime(2026, 11, 11, 10, 0, 0)
    )["id"]
    store.append_message(session_id, {"role": "user", "content": "旧消息"})

    store.save_snapshot(
        session_id,
        [
            {"role": "system", "content": "系统提示"},
            {"role": "user", "content": "压缩摘要"},
        ],
        note="compact",
    )
    store.append_event(
        session_id,
        {
            "type": "insert",
            "index": 1,
            "message": {"role": "assistant", "content": "补充消息"},
        },
    )

    loaded = store.load(session_id)
    assert [message["content"] for message in loaded["messages"]] == [
        "系统提示",
        "补充消息",
        "压缩摘要",
    ]
    assert all(message["content"] != "旧消息" for message in loaded["messages"])


def test_update_title_is_persisted(tmp_path):
    store = SessionStore(project_root=tmp_path)
    session_id = store.create(now=datetime(2026, 11, 11, 10, 0, 0))["id"]

    store.update_title(session_id, "新的标题")

    assert store.load(session_id)["title"] == "新的标题"


def test_invalid_session_id_is_rejected(tmp_path):
    store = SessionStore(project_root=tmp_path)

    with pytest.raises(ValueError):
        store.append_event("../escape", {"type": "message"})
    with pytest.raises(FileNotFoundError):
        store.load("../escape")
