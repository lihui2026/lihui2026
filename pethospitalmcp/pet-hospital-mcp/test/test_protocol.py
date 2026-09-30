"""Protocol-level integration tests against a real running server.

Spawns the server subprocess (streamable HTTP on a free port) and drives the
2026-07-28 wire protocol over real HTTP: server/discover, tools/list, tools/call.
"""

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
MCP_VERSION = "2026-07-28"
MCP_EXE = Path(sys.executable).parent / "Scripts" / "mcp.exe"

HEADERS = {
    "Content-Type": "application/json",
    "MCP-Protocol-Version": MCP_VERSION,
}


class ServerProc:
    def __init__(self):
        self.proc = None
        self.base_url = None

    def start(self) -> None:
        self.proc = subprocess.Popen(
            [
                str(MCP_EXE),
                "run",
                "server.py",
                "--transport",
                "streamable-http",
            ],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Read the startup log line that reports the bound URL.
        deadline = time.time() + 20
        while time.time() < deadline:
            line = self.proc.stderr.readline().decode("utf-8", "replace")
            if "Uvicorn running on http" in line:
                url = line.split("http://", 1)[1].strip().rstrip(")" ).split()[0]
                self.base_url = "http://" + url.rstrip(")")
                break
            time.sleep(0.1)
        else:
            out, err = self.proc.communicate()
            raise AssertionError(
                "server did not start; stdout=%r stderr=%r" % (out, err)
            )

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


@pytest.fixture(scope="module")
def server():
    proc = ServerProc()
    proc.start()
    yield proc
    proc.stop()


def _discover_url(server: "ServerProc") -> str:
    return server.base_url + "/mcp"


def mcp_post(
    server: "ServerProc", method: str, body: dict, mcp_name: str | None = None
) -> httpx.Response:
    _meta = body.get("params", {}).get("_meta", {})
    _meta.setdefault("io.modelcontextprotocol/protocolVersion", MCP_VERSION)
    _meta.setdefault("io.modelcontextprotocol/clientCapabilities", {})
    body.setdefault("params", {})["_meta"] = _meta
    headers = {**HEADERS, "Mcp-Method": method}
    if mcp_name:
        headers["Mcp-Name"] = mcp_name
    return httpx.post(
        _discover_url(server),
        content=json.dumps(body),
        headers=headers,
        timeout=30.0,
    )


@pytest.mark.anyio
async def test_server_discover(server) -> None:
    body = {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {}}
    resp = mcp_post(server, "server/discover", body)
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["resultType"] == "complete"
    assert MCP_VERSION in result["supportedVersions"]
    assert result["capabilities"]["tools"]["listChanged"] is True


@pytest.mark.anyio
async def test_tools_list(server) -> None:
    body = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    resp = mcp_post(server, "tools/list", body)
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["resultType"] == "complete"
    tools = result["tools"]
    names = [t["name"] for t in tools]
    assert set(names) == {"pet-hospital-list-pets", "pet-hospital-create-pet"}
    list_tool = next(t for t in tools if t["name"] == "pet-hospital-list-pets")
    schema = list_tool["inputSchema"]
    assert "species" in schema["properties"]
    assert "owner_name" in schema["properties"]


@pytest.mark.anyio
async def test_tools_call_list_pets(server) -> None:
    body = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "pet-hospital-list-pets",
            "arguments": {"species": "猫", "page_size": 5},
        },
    }
    resp = mcp_post(
        server, "tools/call", body, mcp_name="pet-hospital-list-pets"
    )
    assert resp.status_code == 200
    result = resp.json()["result"]
    assert result["resultType"] == "complete"
    assert result["isError"] is False
    structured = result["structuredContent"]
    assert structured["total"] > 0
    assert len(structured["pets"]) <= 5
    for pet in structured["pets"]:
        assert pet["species"] == "猫"


@pytest.mark.anyio
async def test_tools_call_unknown_tool(server) -> None:
    body = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "does-not-exist", "arguments": {}},
    }
    resp = mcp_post(server, "tools/call", body, mcp_name="does-not-exist")
    assert resp.status_code == 200
    assert resp.json()["result"]["isError"] is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))