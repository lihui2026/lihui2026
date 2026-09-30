import logging

import httpx

logging.getLogger("httpx").setLevel(logging.WARNING)


def chat(question: str) -> dict:
    from .config import (
        ANYTHINGLLM_API_KEY,
        ANYTHINGLLM_BASE_URL,
        ANYTHINGLLM_WORKSPACE_SLUG,
        require_config,
    )

    require_config()
    url = f"{ANYTHINGLLM_BASE_URL}/api/v1/workspace/{ANYTHINGLLM_WORKSPACE_SLUG}/chat"
    headers = {"Authorization": f"Bearer {ANYTHINGLLM_API_KEY}"}
    payload = {"message": question, "mode": "query", "stream": False}
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code == 401:
            raise RuntimeError("anythingllm 鉴权失败：请检查 ANYTHINGLLM_API_KEY")
        resp.raise_for_status()
        return resp.json()