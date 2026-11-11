"""会话事件日志：把消息、快照和元信息持久化到 JSONL 文件。

设计目标：
- 每条消息立即追加（write-through），异常退出也能保留大部分历史；
- 压缩上下文时写入 ``snapshot`` 事件，恢复会话时以最后一个快照为准；
- 会话文件位于 ``<project_root>/.agents/sessions/``，文件名即会话编号。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class SessionStore:
    def __init__(
        self,
        project_root: str | Path | None = None,
        session_dir: str | Path | None = None,
    ):
        self.project_root = Path(project_root or os.getcwd()).resolve()
        if session_dir is None:
            self.session_dir = self.project_root / ".agents" / "sessions"
        else:
            path = Path(session_dir)
            if not path.is_absolute():
                path = self.project_root / path
            self.session_dir = path.resolve()

    # ---------- 编号与路径 ----------

    def new_session_id(self, now: Optional[datetime] = None) -> str:
        now = now or datetime.now()
        base = now.strftime("%Y%m%d-%H%M%S")
        candidate = base
        suffix = 2
        while (self.session_dir / f"{candidate}.jsonl").exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def _path(self, session_id: Any) -> Optional[Path]:
        if not isinstance(session_id, str) or not SESSION_ID_RE.match(session_id):
            return None
        path = (self.session_dir / f"{session_id}.jsonl").resolve()
        try:
            path.relative_to(self.session_dir)
        except ValueError:
            return None
        return path

    # ---------- 写入 ----------

    @staticmethod
    def _write_event(path: Path, event: Dict[str, Any]) -> None:
        record = dict(event)
        record.setdefault("time", _now())
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def create(self, title: Optional[str] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
        now = now or datetime.now()
        session_id = self.new_session_id(now)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        path = self.session_dir / f"{session_id}.jsonl"
        meta = {
            "id": session_id,
            "title": (title or "新会话").strip() or "新会话",
            "created_at": now.isoformat(timespec="seconds"),
            "updated_at": now.isoformat(timespec="seconds"),
        }
        self._write_event(path, {"type": "meta", **meta})
        return {**meta, "path": str(path), "message_count": 0}

    def append_event(self, session_id: str, event: Dict[str, Any]) -> None:
        path = self._path(session_id)
        if path is None:
            raise ValueError(f"非法的会话编号：{session_id}")
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._write_event(path, event)

    def append_message(self, session_id: str, message: Dict[str, Any]) -> None:
        self.append_event(session_id, {"type": "message", "message": message})

    def save_snapshot(
        self,
        session_id: str,
        messages: List[Dict[str, Any]],
        note: str = "",
    ) -> None:
        self.append_event(
            session_id,
            {
                "type": "snapshot",
                "messages": [dict(message) for message in messages],
                "note": note,
            },
        )

    def update_title(self, session_id: str, title: str) -> None:
        self.append_event(
            session_id,
            {
                "type": "meta",
                "id": session_id,
                "title": title.strip() or "新会话",
                "updated_at": _now(),
            },
        )

    # ---------- 读取 ----------

    def load(self, session_id: str) -> Dict[str, Any]:
        path = self._path(session_id)
        if path is None or not path.is_file():
            raise FileNotFoundError(f"未找到会话：{session_id}")
        meta: Dict[str, Any] = {
            "id": session_id,
            "title": "新会话",
            "created_at": None,
            "updated_at": None,
        }
        messages: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                kind = event.get("type")
                if kind == "meta":
                    for key, value in event.items():
                        if key not in ("type", "time"):
                            meta[key] = value
                elif kind == "message":
                    message = event.get("message")
                    if isinstance(message, dict):
                        messages.append(dict(message))
                elif kind == "snapshot":
                    snapshot = event.get("messages")
                    if isinstance(snapshot, list):
                        messages = [
                            dict(message)
                            for message in snapshot
                            if isinstance(message, dict)
                        ]
                elif kind == "insert":
                    message = event.get("message")
                    if isinstance(message, dict):
                        try:
                            index = int(event.get("index", len(messages)))
                        except (TypeError, ValueError):
                            index = len(messages)
                        index = max(0, min(index, len(messages)))
                        messages.insert(index, dict(message))
        if not meta.get("updated_at"):
            try:
                meta["updated_at"] = datetime.fromtimestamp(
                    path.stat().st_mtime
                ).isoformat(timespec="seconds")
            except OSError:
                pass
        return {
            **meta,
            "id": session_id,
            "path": str(path),
            "messages": messages,
            "message_count": len(messages),
        }

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.session_dir.is_dir():
            return []
        try:
            files = sorted(
                (path for path in self.session_dir.glob("*.jsonl") if path.is_file()),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return []
        if limit and limit > 0:
            files = files[:limit]
        sessions: List[Dict[str, Any]] = []
        for path in files:
            try:
                data = self.load(path.stem)
            except (OSError, FileNotFoundError):
                continue
            sessions.append(
                {
                    "id": data.get("id", path.stem),
                    "title": data.get("title", "新会话"),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "message_count": data.get("message_count", 0),
                    "path": data.get("path", str(path)),
                }
            )
        return sessions
