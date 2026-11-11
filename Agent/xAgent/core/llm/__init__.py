"""LLM HTTP client for OpenAI-compatible API."""
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except ImportError as e:
    raise ImportError("缺少 requests，请先安装：pip install requests") from e

from core.config import Config
from core.tools import get_tools


# 不同推理框架在 /models 中暴露上下文窗口时使用的字段名
CONTEXT_WINDOW_KEYS = (
    "context_length",
    "context_window",
    "max_context_length",
    "max_model_len",
    "max_input_tokens",
)


class LLMClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.base_url = cfg.base_url
        self.model = cfg.model
        self.api_key = cfg.api_key
        self.timeout = cfg.llm_timeout
        self.models_timeout = cfg.models_timeout
        self._context_window: Optional[int] = None
        self._window_is_default: bool = True

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def build_payload(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "model": self.model,
            "messages": messages,
            "tools": get_tools(),
            "tool_choice": "auto",
        }

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        resp = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"LLM 接口返回 {resp.status_code}：{resp.text}")
        return resp.json()

    def chat(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self._post(self.build_payload(messages))

    def complete(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """纯文本补全（不携带工具定义），用于上下文压缩等内部任务。"""
        return self._post({"model": self.model, "messages": messages})

    def get_context_window(self) -> Tuple[int, bool]:
        """返回 (上下文窗口大小, 是否为默认值)。

        优先使用 config.ini 中的 ``context_window``；否则尝试从 ``/models`` 探测；
        都失败时使用配置中的 ``default_context_window``。
        """
        if self._context_window is not None:
            return self._context_window, self._window_is_default
        configured = int(getattr(self.cfg, "context_window", 0) or 0)
        if configured > 0:
            self._context_window = configured
            self._window_is_default = False
            return self._context_window, self._window_is_default
        detected = self._detect_context_window()
        if detected:
            self._context_window = detected
            self._window_is_default = False
        else:
            fallback = int(getattr(self.cfg, "default_context_window", 128000) or 128000)
            self._context_window = fallback
            self._window_is_default = True
        return self._context_window, self._window_is_default

    def _detect_context_window(self) -> Optional[int]:
        try:
            resp = requests.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=self.models_timeout,
            )
            if resp.status_code >= 400:
                return None
            data = resp.json()
        except Exception:
            return None
        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return None
        found: List[int] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            value = _extract_window(item)
            if value is None:
                continue
            if str(item.get("id", "")) == self.model:
                return value
            found.append(value)
        # 只有一个模型时才使用它的窗口大小，避免多模型时误判
        if len(found) == 1:
            return found[0]
        return None


def _extract_window(item: Dict[str, Any]) -> Optional[int]:
    for key in CONTEXT_WINDOW_KEYS:
        value = item.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    return None
