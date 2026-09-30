import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

ANYTHINGLLM_BASE_URL = os.getenv("ANYTHINGLLM_BASE_URL", "http://localhost:3001")
ANYTHINGLLM_API_KEY = os.getenv("ANYTHINGLLM_API_KEY", "")
ANYTHINGLLM_WORKSPACE_SLUG = os.getenv("ANYTHINGLLM_WORKSPACE_SLUG", "")


def require_config():
    if not ANYTHINGLLM_API_KEY:
        raise RuntimeError("ANYTHINGLLM_API_KEY 未设置")
    if not ANYTHINGLLM_WORKSPACE_SLUG:
        raise RuntimeError("ANYTHINGLLM_WORKSPACE_SLUG 未设置")