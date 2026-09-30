import json

from mcp.server.mcpserver import MCPServer

from .anythingllm_client import chat
from .config import require_config

server = MCPServer(name="anythingllm-mcp", version="0.1.0")


@server.tool()
async def ask_workspace(question: str) -> str:
    """基于 AnythingLLM 唯一工作区回答用户问题（检索工作区中的资料后由 AI 回答）。

    Args:
        question: 用户想询问的问题。
    """
    require_config()
    try:
        result = chat(question)
    except Exception as e:
        raise RuntimeError(f"调用 AnythingLLM 失败：{e}") from e

    text = result.get("textResponse") or result.get("text") or ""
    sources = result.get("sources") or []
    if sources:
        text += "\n\n[来源]\n" + json.dumps(sources, ensure_ascii=False, indent=2)
    return text