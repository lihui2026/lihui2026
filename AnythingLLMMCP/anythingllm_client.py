"""AnythingLLM REST API 客户端。

设计要点：
- 地址、密钥、超时全部来自环境变量，源码中不含任何凭据；
- 传输层重试（httpx.HTTPTransport(retries=2)）+ 显式超时；
- 所有失败统一翻译为 :class:`AnythingLLMError`，携带 HTTP 状态码与上游 message，
  供上层转成 MCP 的结构化错误，而不是把上游 HTML/裸异常抛给模型。
"""
from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from .config import (
    ANYTHINGLLM_API_KEY,
    ANYTHINGLLM_BASE_URL,
    ANYTHINGLLM_TIMEOUT,
    require_api_key,
)

API_PREFIX = "/api/v1"

logger = logging.getLogger("anythingllm_mcp")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[AnythingLLM] %(levelname)s %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

logging.getLogger("httpx").setLevel(logging.WARNING)


class AnythingLLMError(Exception):
    """AnythingLLM 调用失败（鉴权 / 校验 / 上游业务错误 / 网络）。"""

    def __init__(
        self, message: str, *, status: Optional[int] = None, code: str = "anythingllm_error"
    ):
        super().__init__(message)
        self.status = status
        self.code = code


def _client() -> httpx.Client:
    require_api_key()
    return httpx.Client(
        base_url=ANYTHINGLLM_BASE_URL,
        timeout=ANYTHINGLLM_TIMEOUT,
        transport=httpx.HTTPTransport(retries=2),
        headers={"Authorization": f"Bearer {ANYTHINGLLM_API_KEY}"},
    )


def _handle(resp: httpx.Response, action: str) -> Dict[str, Any]:
    """把响应转成 dict，或在失败时抛出带状态码的错误。"""
    try:
        data = resp.json()
    except ValueError:
        data = None

    if resp.status_code in (401, 403):
        raise AnythingLLMError(
            f"{action}失败：鉴权被拒绝（HTTP {resp.status_code}），请检查 ANYTHINGLLM_API_KEY",
            status=resp.status_code,
            code="unauthorized",
        )
    if resp.status_code >= 400:
        if isinstance(data, dict):
            detail = data.get("error") or data.get("message") or data
        else:
            detail = (resp.text or "")[:200]
        raise AnythingLLMError(
            f"{action}失败：AnythingLLM 返回 HTTP {resp.status_code}，{detail}",
            status=resp.status_code,
            code="upstream_error",
        )
    if not isinstance(data, dict):
        raise AnythingLLMError(
            f"{action}失败：响应不是 JSON 对象（HTTP {resp.status_code}）",
            status=resp.status_code,
            code="bad_response",
        )
    if data.get("success") is False:
        detail = data.get("error") or data.get("message") or "上游返回 success=false"
        raise AnythingLLMError(
            f"{action}失败：{detail}", status=resp.status_code, code="upstream_error"
        )
    return data


# ---------- 工作区管理 ----------


def list_workspaces() -> List[Dict[str, Any]]:
    with _client() as client:
        data = _handle(client.get(f"{API_PREFIX}/workspaces"), "获取工作区列表")
    workspaces = data.get("workspaces")
    if not isinstance(workspaces, list):
        raise AnythingLLMError("获取工作区列表失败：响应缺少 workspaces 字段", code="bad_response")
    return [w for w in workspaces if isinstance(w, dict)]


def create_workspace(name: str) -> Dict[str, Any]:
    with _client() as client:
        data = _handle(client.post(f"{API_PREFIX}/workspace/new", json={"name": name}), "新建工作区")
    workspace = data.get("workspace")
    if not isinstance(workspace, dict):
        raise AnythingLLMError(
            f"新建工作区成功但响应缺少 workspace 字段：{data}", code="bad_response"
        )
    return workspace


def get_workspace(slug: str) -> Dict[str, Any]:
    with _client() as client:
        data = _handle(client.get(f"{API_PREFIX}/workspace/{slug}"), f"读取工作区 {slug}")
    workspace = data.get("workspace")
    # 兼容旧版本把 workspace 返回为单元素数组的写法
    if isinstance(workspace, list) and workspace:
        workspace = workspace[0]
    if not isinstance(workspace, dict):
        raise AnythingLLMError("读取工作区失败：响应缺少 workspace 字段", code="bad_response")
    return workspace


def list_documents(slug: str) -> List[Dict[str, Any]]:
    workspace = get_workspace(slug)
    documents = workspace.get("documents") or []
    return [d for d in documents if isinstance(d, dict)]


# ---------- 文档与向量化 ----------


def upload_document(file_path: str, workspace_slug: Optional[str] = None) -> Dict[str, Any]:
    path = Path(file_path).expanduser()
    if not path.is_file():
        raise AnythingLLMError(f"上传失败：本地文件不存在 {path}", code="bad_request")
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    form: Dict[str, str] = {}
    if workspace_slug:
        form["addToWorkspaces"] = workspace_slug
    with _client() as client, path.open("rb") as handle:
        resp = client.post(
            f"{API_PREFIX}/document/upload",
            files={"file": (path.name, handle, mime)},
            data=form,
        )
        data = _handle(resp, "上传文档")
    return data


def update_embeddings(
    slug: str, adds: List[str], deletes: Optional[List[str]] = None
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"adds": adds, "deletes": deletes or []}
    with _client() as client:
        return _handle(
            client.post(f"{API_PREFIX}/workspace/{slug}/update-embeddings", json=payload),
            f"更新工作区 {slug} 的向量化",
        )


# ---------- 检索问答 ----------


def chat(question: str, workspace_slug: str, mode: str = "query") -> Dict[str, Any]:
    payload = {"message": question, "mode": mode, "stream": False}
    with _client() as client:
        return _handle(
            client.post(f"{API_PREFIX}/workspace/{workspace_slug}/chat", json=payload),
            f"工作区 {workspace_slug} 问答",
        )
