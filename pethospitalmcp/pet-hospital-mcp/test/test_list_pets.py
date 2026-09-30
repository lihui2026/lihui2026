import asyncio
import sys
from pathlib import Path

import httpx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import server as server_mod
from mcp import Client, StdioServerParameters

PET_HOSPITAL_URL = server_mod.BASE_URL


def pet_hospital_reachable() -> bool:
    try:
        r = httpx.get(f"{PET_HOSPITAL_URL}/health", timeout=2)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


requires_cost = pytest.mark.skipif(
    not pet_hospital_reachable(),
    reason=f"Pet Hospital REST API unreachable at {PET_HOSPITAL_URL}",
)


@pytest.mark.anyio
async def test_list_tools() -> None:
    """tools/list 注册 list-pets 与 create-pet 两个工具，且带 input/output schema。"""
    tools = await server_mod.mcp.list_tools()
    names = [t.name for t in tools]
    assert set(names) == {"pet-hospital-list-pets", "pet-hospital-create-pet"}
    for tool in tools:
        assert tool.description
        assert tool.input_schema
        assert tool.output_schema or tool.input_schema
    props = next(t for t in tools if t.name == "pet-hospital-list-pets").input_schema[
        "properties"
    ]
    assert "q" in props
    assert "ownerName" not in props


@requires_cost
@pytest.mark.anyio
async def test_list_pets_default() -> None:
    async with Client(server_mod.mcp) as client:
        result = await client.call_tool("pet-hospital-list-pets", {})
        assert result.structured_content is not None
        data = result.structured_content
        assert data["total"] > 0
        assert len(data["pets"]) == data["page_size"]
        assert data["page"] == 1
        pet = data["pets"][0]
        assert pet["id"].startswith("PET-")


@requires_cost
@pytest.mark.anyio
async def test_list_pets_filter_pagination() -> None:
    args = {"species": "犬", "page": 1, "page_size": 5}
    async with Client(server_mod.mcp) as client:
        result = await client.call_tool("pet-hospital-list-pets", args)
        assert result.structured_content is not None
        data = result.structured_content
        assert len(data["pets"]) <= 5
        for pet in data["pets"]:
            assert pet["species"] == "犬"


@requires_cost
@pytest.mark.anyio
async def test_list_pets_search_mincost() -> None:
    args = {"min": 5000, "page_size": 10}
    async with Client(server_mod.mcp) as client:
        result = await client.call_tool("pet-hospital-list-pets", args)
        assert result.structured_content is not None
        data = result.structured_content
        for pet in data["pets"]:
            assert pet["total_cost"] >= 5000


@requires_cost
@pytest.mark.anyio
async def test_list_pets_invalid_args_error() -> None:
    """非法参数（page_size < 1）应返回 isError 结果而非崩溃。"""
    async with Client(server_mod.mcp) as client:
        result = await client.call_tool("pet-hospital-list-pets", {"page_size": -1})
        assert result.is_error is True
        assert result.content


@requires_cost
@pytest.mark.anyio
async def test_stdio_transport_end_to_end() -> None:
    """按生产方式由 stdio 子进程启动 server.py，MCP Host 通过标准输入输出通信。"""
    params = StdioServerParameters(
        command=sys.executable,
        args=["server.py"],
        cwd=str(PROJECT_ROOT),
        env={"PET_HOSPITAL_URL": PET_HOSPITAL_URL},
    )
    async with Client(params) as client:
        assert client.protocol_version == "2026-07-28"
        tools = (await client.list_tools()).tools
        names = [t.name for t in tools]
        assert set(names) == {"pet-hospital-list-pets", "pet-hospital-create-pet"}
        result = await client.call_tool("pet-hospital-list-pets", {"page": 1, "page_size": 3})
        assert result.structured_content is not None
        data = result.structured_content
        assert data["page"] == 1
        assert len(data["pets"]) == 3


@requires_cost
@pytest.mark.anyio
async def test_create_pet() -> None:
    """pet-hospital-create-pet 写入新档案并返回系统生成的 id。"""
    marker = f"测试-{__import__('time').time_ns()}"
    args = {
        "name": marker,
        "species": "猫",
        "gender": "母",
        "breed": "狸花猫",
        "owner_name": "张先生",
        "owner_phone": "18423456789",
        "doctor": "李医生",
        "disease": "呼吸道感染",
        "status": "就诊中",
    }
    created_id = None
    try:
        async with Client(server_mod.mcp) as client:
            result = await client.call_tool("pet-hospital-create-pet", args)
            assert result.is_error is False, result.content
            assert result.structured_content is not None
            pet = result.structured_content
            created_id = pet["id"]
            assert created_id.startswith("PET-")
            assert pet["name"] == marker
            assert pet["species"] == "猫"
            assert pet["status"] == "就诊中"
    finally:
        if created_id:
            httpx.delete(f"{PET_HOSPITAL_URL}/api/v1/pets/{created_id}", timeout=5)


def test_query_param_mapping() -> None:
    query = server_mod._to_query_params(
        {
            "owner_name": "张三",
            "owner_phone": "138",
            "sort_by": "totalCost",
            "page_size": 10,
            "page": 2,
            "q": None,
        }
    )
    assert query["ownerName"] == "张三"
    assert query["ownerPhone"] == "138"
    assert query["sortBy"] == "totalCost"
    assert query["pageSize"] == 10
    assert query["page"] == 2
    assert "owner_name" not in query
    assert "sort_by" not in query
    assert "q" not in query


if __name__ == "__main__":
    asyncio.run(test_list_pets_default())