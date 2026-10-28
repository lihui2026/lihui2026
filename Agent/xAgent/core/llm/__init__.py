"""LLM HTTP client for OpenAI-compatible API."""
import json
from typing import Any, Dict, List

try:
    import requests
except ImportError as e:
    raise ImportError("缺少 requests，请先安装：pip install requests") from e

from core.config import Config
from core.tools import TOOLS


class LLMClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.base_url = cfg.base_url
        self.model = cfg.model
        self.api_key = cfg.api_key
        self.timeout = 120

    def build_payload(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "model": self.model,
            "messages": messages,
            "tools": TOOLS,
            "tool_choice": "auto",
        }

    def chat(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(url, headers=headers, json=self.build_payload(messages), timeout=self.timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"LLM 接口返回 {resp.status_code}：{resp.text}")
        return resp.json()
