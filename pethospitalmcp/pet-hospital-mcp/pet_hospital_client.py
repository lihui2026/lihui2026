import httpx
from typing import Any, Dict


class PetHospitalError(Exception):
    """Pet Hospital REST API returned a business error."""


class PetHospitalClient:
    """Async HTTP client for the Pet Hospital REST API."""

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def get(self, path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Send a GET request and return the parsed response envelope."""
        try:
            response = await self._client.get(path, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PetHospitalError(f"HTTP request failed: {exc}") from exc

        return self._ensure_ok(response.json())

    async def post(
        self, path: str, payload: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Send a POST request and return the parsed response envelope."""
        try:
            response = await self._client.post(path, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PetHospitalError(f"HTTP request failed: {exc}") from exc

        return self._ensure_ok(response.json())

    @staticmethod
    def _ensure_ok(data: Dict[str, Any]) -> Dict[str, Any]:
        code = data.get("code")
        if isinstance(code, int) and not (200 <= code < 300):
            raise PetHospitalError(
                f"API error (code={code}): {data.get('message')}"
            )
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