"""上下文压缩、归档与检索（recallContext）。

实现刻意保持简单，方便理解和维护：
- Token 估算：不依赖 tiktoken 等第三方库，使用「CJK 字符约 1 Token、其他字符约 4 字符/Token」的启发式；
- 上下文归档：以 JSONL 形式把原始消息完整保存到项目 ``.agents/context/`` 目录；
- 历史检索：Python 本地全文关键词匹配，不使用向量数据库。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from core.config import get_config

# 归档编号仅允许安全字符，防止路径穿越
ARCHIVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

# CJK 字符（含中文标点、假名、全角符号），估算时约 1 字符 ≈ 1 Token
_CJK_RE = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]")


def estimate_tokens(text: Any) -> int:
    """粗略估算一段文本的 Token 数（中文约 1 字/Token，其他约 4 字符/Token）。"""
    if text is None:
        return 0
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    other = len(text) - cjk
    return max(1, int(round(cjk + other / 4.0)))


def estimate_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    """估算一组消息（System Prompt、对话历史、工具调用消息）的 Token 数。"""
    total = 0
    for message in messages:
        total += 4  # 角色、结构等固定开销
        content = message.get("content")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif content is not None:
            total += estimate_tokens(json.dumps(content, ensure_ascii=False))
        tool_calls = message.get("tool_calls")
        if tool_calls:
            total += estimate_tokens(json.dumps(tool_calls, ensure_ascii=False))
        if message.get("name"):
            total += estimate_tokens(str(message["name"]))
    return total


def estimate_tools_tokens(tools: List[Dict[str, Any]]) -> int:
    """估算工具定义（Function Calling Schema）占用的 Token 数。"""
    if not tools:
        return 0
    return estimate_tokens(json.dumps(tools, ensure_ascii=False))


def _clip(text: str, limit: Optional[int]) -> str:
    if not limit or len(text) <= limit:
        return text
    head = limit // 2
    tail = limit - head
    return (
        f"{text[:head]}\n"
        f"……（此处省略 {len(text) - limit} 个字符，完整内容保存在原始上下文归档中）……\n"
        f"{text[-tail:]}"
    )


def render_messages(messages: List[Dict[str, Any]], content_limit: Optional[int] = None) -> str:
    """把消息列表渲染为可读文本（用于压缩 LLM 输入和压缩面板展示）。"""
    lines: List[str] = []
    for index, message in enumerate(messages):
        header = f"--- [{index}] {message.get('role', 'unknown')}"
        if message.get("name"):
            header += f" ({message['name']})"
        if message.get("tool_call_id"):
            header += f" tool_call_id={message['tool_call_id']}"
        lines.append(header + " ---")
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            lines.append(_clip(content.rstrip(), content_limit))
        elif content not in (None, ""):
            lines.append(_clip(json.dumps(content, ensure_ascii=False), content_limit))
        for call in message.get("tool_calls") or []:
            fn = call.get("function") or {}
            lines.append(f"[tool_call] {fn.get('name', '')} 参数：{fn.get('arguments', '')}")
        lines.append("")
    return "\n".join(lines).strip() or "（空）"


class ContextManager:
    """负责上下文归档的保存、读取和关键词检索。"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(
            project_root if project_root is not None else os.getcwd()
        ).resolve()
        self.context_dir = self.project_root / ".agents" / "context"

    # ---------- 归档编号与文件 ----------

    def new_archive_id(self, now: Optional[datetime] = None) -> str:
        """生成形如 20261022-153000 的唯一归档编号（同一秒冲突时追加序号）。"""
        now = now or datetime.now()
        base = now.strftime("%Y%m%d-%H%M%S")
        candidate = base
        suffix = 2
        while (self.context_dir / f"{candidate}.jsonl").exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def _archive_path(self, archive_id: Any) -> Optional[Path]:
        if not isinstance(archive_id, str) or not ARCHIVE_ID_RE.match(archive_id):
            return None
        path = (self.context_dir / f"{archive_id}.jsonl").resolve()
        try:
            path.relative_to(self.context_dir.resolve())
        except ValueError:
            return None
        return path

    def list_archives(self) -> List[Path]:
        """列出全部归档文件（按编号从新到旧）。"""
        if not self.context_dir.is_dir():
            return []
        files = [p for p in self.context_dir.glob("*.jsonl") if p.is_file()]
        files.sort(key=lambda p: p.name, reverse=True)
        return files

    # ---------- 保存 / 读取 ----------

    def save_archive(
        self, messages: List[Dict[str, Any]], archive_id: Optional[str] = None
    ) -> Tuple[str, Path]:
        """把完整原始上下文保存为 JSONL 归档，返回 (编号, 路径)。

        保留原始消息的角色、内容、工具调用参数、工具返回结果和顺序；
        只有校验成功（能完整读回）才视为保存成功。
        """
        archive_id = archive_id or self.new_archive_id()
        if not ARCHIVE_ID_RE.match(archive_id):
            raise ValueError(f"非法的归档编号：{archive_id}")
        self.context_dir.mkdir(parents=True, exist_ok=True)
        path = self.context_dir / f"{archive_id}.jsonl"
        lines: List[str] = []
        for index, message in enumerate(messages):
            record: Dict[str, Any] = dict(message)
            record["index"] = index
            try:
                lines.append(json.dumps(record, ensure_ascii=False))
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"归档失败：第 {index} 条消息无法序列化：{exc}") from exc
        tmp_path = self.context_dir / f".{archive_id}.jsonl.tmp"
        try:
            tmp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            os.replace(tmp_path, path)
        except OSError as exc:
            try:
                tmp_path.unlink()
            except OSError:
                pass
            raise RuntimeError(f"归档失败：无法写入 {path}：{exc}") from exc
        saved = self.load_archive(archive_id)
        if len(saved) != len(messages):
            raise RuntimeError("归档校验失败：保存的消息数量与原始上下文不一致。")
        return archive_id, path

    def load_archive(self, archive_id: str) -> List[Dict[str, Any]]:
        """读取指定编号的归档，返回按顺序排列的消息列表。"""
        path = self._archive_path(archive_id)
        if path is None or not path.is_file():
            raise FileNotFoundError(f"未找到归档文件：{archive_id}")
        records: List[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))
        return records

    # ---------- 检索（recallContext 工具实现） ----------

    def recall(
        self,
        text: Any,
        archive_id: Any = None,
        max_hits: Optional[int] = None,
        snippet_chars: Optional[int] = None,
        total_chars: Optional[int] = None,
    ) -> str:
        """在归档中做本地全文关键词检索，返回带来源位置的片段。"""
        if not isinstance(text, str) or not text.strip():
            return "recallContext 参数错误：text 必须为非空字符串。"
        cfg = get_config()
        max_hits = cfg.recall_max_hits if max_hits is None else max_hits
        snippet_chars = (
            cfg.recall_snippet_chars if snippet_chars is None else snippet_chars
        )
        total_chars = cfg.recall_total_chars if total_chars is None else total_chars
        query = text.strip()
        terms = [t.lower() for t in re.split(r"\s+", query) if t]

        if isinstance(archive_id, str) and archive_id.strip():
            archive_id = archive_id.strip()
            path = self._archive_path(archive_id)
            if path is None or not path.is_file():
                available = ", ".join(p.stem for p in self.list_archives()) or "无"
                return f"未找到归档编号 '{archive_id}'。可用归档：{available}"
            files = [path]
            scope = f"指定归档 {archive_id}"
        else:
            files = self.list_archives()
            if not files:
                return "当前没有可检索的上下文归档（.agents/context/ 目录为空）。"
            scope = f"全部 {len(files)} 个归档"

        hits: List[Dict[str, Any]] = []
        for path in files:
            for line_no, record in self._iter_records(path):
                blob = self._record_text(record)
                if not blob:
                    continue
                lowered = blob.lower()
                matched = [t for t in terms if t in lowered]
                if not matched:
                    continue
                hits.append(
                    {
                        "archive": path.stem,
                        "line": line_no,
                        "record": record,
                        "blob": blob,
                        "matched": matched,
                        "score": sum(lowered.count(t) for t in matched),
                    }
                )

        if not hits:
            return f"在{scope}中未找到与「{query}」相关的内容。"

        full = [h for h in hits if len(h["matched"]) == len(terms)]
        results = full if full else hits
        results.sort(key=lambda h: h["score"], reverse=True)
        match_note = "" if full else "（仅部分关键词命中）"

        out: List[str] = [
            f"在{scope}中检索「{query}」：命中 {len(results)} 处{match_note}，"
            f"显示前 {min(len(results), max_hits)} 处：",
            "",
        ]
        total = sum(len(line) for line in out)
        shown = 0
        for hit in results:
            if shown >= max_hits:
                break
            record = hit["record"]
            header = (
                f"[归档 {hit['archive']} | 第 {hit['line']} 行 | "
                f"消息 #{record.get('index', '?')} | {record.get('role', '?')}]"
            )
            if record.get("name"):
                header += f"（工具：{record['name']}）"
            block = f"{header}\n{self._snippet(hit['blob'], hit['matched'], snippet_chars)}\n"
            if shown > 0 and total + len(block) > total_chars:
                out.append("……（检索结果较多，已截断；请使用更具体的关键词或指定归档编号）")
                break
            out.append(block)
            total += len(block)
            shown += 1
        if len(results) > shown:
            out.append(f"（共命中 {len(results)} 处，仅显示前 {shown} 处。）")
        return "\n".join(out).strip()

    @staticmethod
    def _iter_records(path: Path) -> Iterator[Tuple[int, Dict[str, Any]]]:
        try:
            with path.open("r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(record, dict):
                        yield line_no, record
        except OSError:
            return

    @staticmethod
    def _record_text(record: Dict[str, Any]) -> str:
        parts: List[str] = []
        for key in ("role", "name", "content"):
            value = record.get(key)
            if isinstance(value, str):
                parts.append(value)
        if record.get("tool_calls"):
            parts.append(json.dumps(record["tool_calls"], ensure_ascii=False))
        return "\n".join(parts)

    @staticmethod
    def _snippet(blob: str, matched: List[str], limit: int) -> str:
        lowered = blob.lower()
        pos = -1
        for term in matched:
            idx = lowered.find(term)
            if idx != -1 and (pos == -1 or idx < pos):
                pos = idx
        if pos == -1:
            pos = 0
        start = max(0, pos - limit // 3)
        end = min(len(blob), start + limit)
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(blob) else ""
        return prefix + blob[start:end].strip() + suffix


# 与 skill_manager 保持一致：以启动时的工作目录作为项目根目录
context_manager = ContextManager(project_root=os.getcwd())
