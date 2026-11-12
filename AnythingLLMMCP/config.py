"""配置读取：地址、密钥、默认工作区、超时。

全部来自环境变量（可用项目根目录的 .env 提供），缺失时给出明确报错，
不允许把密钥写死进源码。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

ANYTHINGLLM_BASE_URL = os.getenv("ANYTHINGLLM_BASE_URL", "http://localhost:3001").rstrip("/")
ANYTHINGLLM_API_KEY = os.getenv("ANYTHINGLLM_API_KEY", "")
ANYTHINGLLM_WORKSPACE_SLUG = os.getenv("ANYTHINGLLM_WORKSPACE_SLUG", "")
ANYTHINGLLM_TIMEOUT = float(os.getenv("ANYTHINGLLM_TIMEOUT", "120"))


def require_api_key() -> None:
    """鉴权信息缺失时立即抛出可读错误，避免把 401 透传成上游 HTML。"""
    if not ANYTHINGLLM_API_KEY:
        raise RuntimeError(
            "ANYTHINGLLM_API_KEY 未设置：请在项目根目录 .env 中配置"
            "（ANYTHINGLLM_API_KEY=your-api-key）后重启 MCP Server。"
        )


def resolve_workspace(slug: str | None) -> str:
    """工具参数优先，其次回退到 .env 中的默认工作区。"""
    value = (slug or "").strip() or ANYTHINGLLM_WORKSPACE_SLUG.strip()
    if not value:
        raise RuntimeError(
            "未指定工作区：请传入 workspace_slug 参数，或在 .env 中设置 "
            "ANYTHINGLLM_WORKSPACE_SLUG。"
        )
    return value
