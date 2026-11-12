"""AnythingLLM MCP Server。

把 AnythingLLM 的三类能力封装为 MCP 工具，全部请求打到其 REST API（/api/v1/...）：

- 工作区管理：``list_workspaces`` / ``create_workspace``
- 文档与向量化：``list_workspace_documents`` / ``upload_document``（上传 → 加入工作区 → 向量化）
- 检索问答：``ask_workspace``

失败统一转成 ``ToolError``（MCP 的结构化错误），不把上游 HTML 或裸异常抛给模型。
"""
from __future__ import annotations

import json
from typing import Annotated, Literal, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from . import anythingllm_client as api
from .config import resolve_workspace

server = MCPServer(
    name="anythingllm-mcp",
    version="1.0.0",
    description="AnythingLLM 工作区 / 文档向量化 / 检索问答 MCP Server",
    instructions=(
        "提供 AnythingLLM 数据访问：list_workspaces（列出工作区）、create_workspace（新建工作区）、"
        "list_workspace_documents（列出工作区文档）、upload_document（上传本地文件并向量化到工作区）、"
        "ask_workspace（基于工作区资料检索问答）。除 list_workspaces / create_workspace 外，"
        "其余工具都需要 workspace_slug（未传时回退到 .env 中的 ANYTHINGLLM_WORKSPACE_SLUG）。"
    ),
)


def _fail(action: str, exc: Exception) -> ToolError:
    return ToolError(f"{action}失败：{exc}")


@server.tool(
    name="list_workspaces",
    title="List Workspaces",
    description="列出 AnythingLLM 中全部工作区（slug、名称、文档数等），用于让模型在后续调用中选对 workspace_slug。",
)
async def list_workspaces() -> str:
    try:
        workspaces = api.list_workspaces()
    except Exception as exc:  # noqa: BLE001 - 统一转结构化错误
        raise _fail("列出工作区", exc) from exc

    if not workspaces:
        return "当前没有任何工作区，可先用 create_workspace 新建。"

    lines = [f"共 {len(workspaces)} 个工作区："]
    for item in workspaces:
        slug = item.get("slug") or ""
        name = item.get("name") or ""
        count = len(item.get("documents") or [])
        lines.append(f"- {name}（slug: {slug}，文档 {count} 个）")
    return "\n".join(lines)


@server.tool(
    name="create_workspace",
    title="Create Workspace",
    description="新建一个 AnythingLLM 工作区，返回其 slug。新工作区初始为空，需要再用 upload_document 上传并向量化文档。",
)
async def create_workspace(
    name: Annotated[str, Field(description="工作区名称（必填），例如 课程资料")],
) -> str:
    workspace_name = (name or "").strip()
    if not workspace_name:
        raise ToolError("新建工作区失败：name 不能为空。")
    try:
        workspace = api.create_workspace(workspace_name)
    except Exception as exc:  # noqa: BLE001
        raise _fail("新建工作区", exc) from exc

    slug = workspace.get("slug") or ""
    message = workspace.get("message") or "工作区已创建"
    return f"{message}\nname: {workspace.get('name') or workspace_name}\nslug: {slug}"


@server.tool(
    name="list_workspace_documents",
    title="List Workspace Documents",
    description="列出指定工作区已向量化的文档（文件名、docpath、字数 / token 估算），用于确认上传与向量化结果。",
)
async def list_workspace_documents(
    workspace_slug: Annotated[
        Optional[str],
        Field(description="工作区 slug；不传则使用 .env 中的 ANYTHINGLLM_WORKSPACE_SLUG"),
    ] = None,
) -> str:
    try:
        slug = resolve_workspace(workspace_slug)
        documents = api.list_documents(slug)
    except Exception as exc:  # noqa: BLE001
        raise _fail("列出工作区文档", exc) from exc

    if not documents:
        return f"工作区 {slug} 暂无文档，可用 upload_document 上传。"

    lines = [f"工作区 {slug} 共 {len(documents)} 个文档："]
    for doc in documents:
        title = doc.get("title") or doc.get("filename") or doc.get("docpath") or "(未命名)"
        meta = []
        if doc.get("wordCount"):
            meta.append(f"{doc['wordCount']} 字")
        if doc.get("token_count_estimate"):
            meta.append(f"{doc['token_count_estimate']} tokens")
        suffix = f"（{'，'.join(meta)}）" if meta else ""
        lines.append(f"- {title}{suffix}  [{doc.get('docpath') or '-'}]")
    return "\n".join(lines)


@server.tool(
    name="upload_document",
    title="Upload And Embed Document",
    description=(
        "把本机的一个文档上传到 AnythingLLM 并加入指定工作区完成向量化。"
        "支持 pdf/txt/md/docx 等 AnythingLLM 可解析格式；文件不存在或向量化失败会返回明确错误。"
    ),
)
async def upload_document(
    file_path: Annotated[str, Field(description="本机待上传文件的绝对路径或相对路径")],
    workspace_slug: Annotated[
        Optional[str],
        Field(description="目标工作区 slug；不传则使用 .env 中的 ANYTHINGLLM_WORKSPACE_SLUG"),
    ] = None,
    embed: Annotated[
        bool, Field(description="是否在上传后立即触发向量化，默认 true")
    ] = True,
) -> str:
    if not (file_path or "").strip():
        raise ToolError("上传文档失败：file_path 不能为空。")
    try:
        slug = resolve_workspace(workspace_slug)
    except Exception as exc:  # noqa: BLE001
        raise _fail("上传文档", exc) from exc

    try:
        result = api.upload_document(file_path, slug)
    except Exception as exc:  # noqa: BLE001
        raise _fail("上传文档", exc) from exc

    documents = result.get("documents") or []
    if not documents:
        raise ToolError(f"上传文档失败：AnythingLLM 未返回 documents 字段（原始响应：{result}）")

    lines = [f"已上传 {len(documents)} 个文档到工作区 {slug}："]
    locations = []
    for doc in documents:
        if not isinstance(doc, dict):
            continue
        location = doc.get("location") or ""
        if location:
            locations.append(location)
        lines.append(f"- {doc.get('title') or doc.get('name') or location}")

    if embed and locations:
        try:
            api.update_embeddings(slug, locations)
        except Exception as exc:  # noqa: BLE001
            raise _fail("上传成功但向量化失败", exc) from exc
        lines.append(f"已完成向量化：{', '.join(locations)}")
    elif locations:
        lines.append("已跳过向量化（embed=false），需向量化后才能被检索。")

    return "\n".join(lines)


@server.tool(
    name="ask_workspace",
    title="Ask Workspace",
    description=(
        "基于指定工作区中已向量化的资料回答问题（检索增强）。返回回答正文，"
        "并在有引用时附上来源片段。"
    ),
)
async def ask_workspace(
    question: Annotated[str, Field(description="要询问的问题")],
    workspace_slug: Annotated[
        Optional[str],
        Field(description="工作区 slug；不传则使用 .env 中的 ANYTHINGLLM_WORKSPACE_SLUG"),
    ] = None,
    mode: Annotated[
        Literal["query", "chat"],
        Field(description="query=仅依据工作区资料回答；chat=允许模型自身知识，默认 query"),
    ] = "query",
) -> str:
    if not (question or "").strip():
        raise ToolError("问答失败：question 不能为空。")
    try:
        slug = resolve_workspace(workspace_slug)
        result = api.chat(question, slug, mode)
    except Exception as exc:  # noqa: BLE001
        raise _fail("工作区问答", exc) from exc

    text = result.get("textResponse") or result.get("text") or ""
    if not text:
        raise ToolError(f"问答失败：AnythingLLM 未返回回答正文（原始响应：{result}）")

    sources = result.get("sources") or []
    if sources:
        text += "\n\n[来源]\n" + json.dumps(sources, ensure_ascii=False, indent=2)
    return text
