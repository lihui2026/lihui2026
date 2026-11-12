"""Async HTTP client for the Pet Hospital REST API.

工程配套：
- 超时：连接/读超时由 ``timeout`` 统一控制；
- 重试：传输层 ``httpx.AsyncHTTPTransport(retries=2)`` 对连接级错误自动重试；
- 日志：每次调用记录方法、路径、耗时与结果，便于排查上游问题。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

import httpx

logger = logging.getLogger("pet_hospital")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[PetHospital] %(levelname)s %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

logging.getLogger("httpx").setLevel(logging.WARNING)


class PetHospitalError(Exception):
    """Pet Hospital REST API returned a business error."""


class PetHospitalClient:
    """Async HTTP client for the Pet Hospital REST API."""

    def __init__(self, base_url: str, timeout: float = 30.0, retries: int = 2):
        self.base_url = base_url
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            transport=httpx.AsyncHTTPTransport(retries=retries),
        )

    def _log(self, method: str, path: str, started: float, outcome: str) -> None:
        logger.info("%s %s → %s（%.0f ms）", method, path, outcome, (time.monotonic() - started) * 1000)

    async def get(self, path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Send a GET request and return the parsed response envelope."""
        started = time.monotonic()
        try:
            response = await self._client.get(path, params=params)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            self._log("GET", path, started, "超时")
            raise PetHospitalError(f"请求超时：GET {path}") from exc
        except httpx.HTTPError as exc:
            self._log("GET", path, started, f"HTTP 错误：{type(exc).__name__}")
            raise PetHospitalError(f"HTTP request failed: {exc}") from exc

        self._log("GET", path, started, f"HTTP {response.status_code}")
        return self._ensure_ok(response.json())

    async def post(
        self, path: str, payload: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Send a POST request and return the parsed response envelope."""
        started = time.monotonic()
        try:
            response = await self._client.post(path, json=payload)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            self._log("POST", path, started, "超时")
            raise PetHospitalError(f"请求超时：POST {path}") from exc
        except httpx.HTTPError as exc:
            self._log("POST", path, started, f"HTTP 错误：{type(exc).__name__}")
            raise PetHospitalError(f"HTTP request failed: {exc}") from exc

        self._log("POST", path, started, f"HTTP {response.status_code}")
        return self._ensure_ok(response.json())

    @staticmethod
    def _ensure_ok(data: Dict[str, Any]) -> Dict[str, Any]:
        code = data.get("code")
        if isinstance(code, int) and not (200 <= code < 300):
            raise PetHospitalError(f"API error (code={code}): {data.get('message')}")
        return data

    async def list_pets(self, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """GET /api/v1/pets — list pets with filtering / sorting / pagination."""
        envelope = await self.get("/api/v1/pets", params=params)
        return envelope["data"]

    async def create_pet(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/v1/pets — create a new pet profile (id auto-generated)."""
        envelope = await self.post("/api/v1/pets", payload=payload)
        return envelope["data"]

    async def aclose(self) -> None:
        await self._client.aclose()
