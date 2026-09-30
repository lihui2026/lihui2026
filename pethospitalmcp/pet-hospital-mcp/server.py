import os
from contextlib import asynccontextmanager
from typing import Annotated, Literal, Optional

from mcp.server import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from pet_hospital_client import PetHospitalClient, PetHospitalError

BASE_URL = os.environ.get("PET_HOSPITAL_URL", "http://127.0.0.1:8080")

FIELD_MAP = {
    "owner_name": "ownerName",
    "owner_phone": "ownerPhone",
    "owner_addr": "ownerAddr",
    "chip_no": "chipNo",
    "age_months": "ageMonths",
    "sort_by": "sortBy",
    "page_size": "pageSize",
}

STATUS_VALUES = ("待就诊", "就诊中", "住院中", "已康复", "慢性病随访")


class Pet(BaseModel):
    """Summary of a pet record."""

    id: str
    name: str
    species: str
    breed: str
    gender: str
    age_months: int
    owner_name: str
    owner_phone: str
    doctor: str
    disease: str
    status: str
    total_cost: float
    visit_count: int


class ListPetsResult(BaseModel):
    """Structured output of pet-hospital-list-pets."""

    pets: list[Pet]
    total: int
    page: int
    page_size: int
    total_pages: int
    total_cost: float


class CreatePetParams(BaseModel):
    """Input fields of pet-hospital-create-pet."""

    name: str = Field(description="宠物名称（必填）")
    species: str = Field(description="种类（必填，如 犬/猫/仓鼠/兔/鸟/爬宠/其他）")
    breed: Optional[str] = Field(default=None, description="品种")
    gender: Optional[str] = Field(default=None, description="性别（公/母）")
    age_months: Optional[int] = Field(default=None, ge=0, description="月龄")
    color: Optional[str] = Field(default=None, description="毛色")
    chip_no: Optional[str] = Field(default=None, description="芯片号")
    owner_name: Optional[str] = Field(default=None, description="主人姓名")
    owner_phone: Optional[str] = Field(default=None, description="主人电话")
    owner_addr: Optional[str] = Field(default=None, description="主人住址")
    doctor: Optional[str] = Field(default=None, description="主治医生")
    disease: Optional[str] = Field(default=None, description="疾病")
    status: Optional[str] = Field(
        default=None,
        description="就诊状态（待就诊/就诊中/住院中/已康复/慢性病随访）",
    )
    allergy: Optional[str] = Field(default=None, description="过敏史")
    note: Optional[str] = Field(default=None, description="备注")


def _to_query_params(kwargs: dict) -> dict:
    query = {}
    for key, value in kwargs.items():
        if value is None:
            continue
        api_key = FIELD_MAP.get(key, key)
        query[api_key] = value
    return query


def _to_pet(item: dict) -> Pet:
    return Pet(
        id=item["id"],
        name=item["name"],
        species=item["species"],
        breed=item.get("breed", ""),
        gender=item.get("gender", ""),
        age_months=item.get("ageMonths", 0),
        owner_name=item.get("ownerName", ""),
        owner_phone=item.get("ownerPhone", ""),
        doctor=item.get("doctor", ""),
        disease=item.get("disease", ""),
        status=item.get("status", ""),
        total_cost=item.get("totalCost", 0),
        visit_count=item.get("visitCount", 0),
    )


@asynccontextmanager
async def server_lifespan(server: MCPServer):
    client = PetHospitalClient(base_url=BASE_URL)
    try:
        yield client
    finally:
        await client.aclose()


mcp = MCPServer(
    "pet-hospital",
    version="1.0.0",
    description="Pet Hospital REST API data proxy (MCP 2026-07-28)",
    instructions=(
        "提供宠物医院数据访问。暴露 pet-hospital-list-pets（列出/筛选/排序/分页宠物档案）"
        "与 pet-hospital-create-pet（新增宠物档案）两个工具。"
    ),
    lifespan=server_lifespan,
)


@mcp.tool(
    name="pet-hospital-list-pets",
    title="List Pets",
    description=(
        "列出宠物档案，支持根据各种参数进行筛选。\n"
        "支持：全文检索（q）、按宠物姓名/主人姓名/电话/种类/医生/疾病/就诊状态筛选，\n"
        "按总花费区间（min/max）筛选、排序（sortBy/order）与分页（page/pageSize）。"
    ),
)
async def list_pets(
    ctx: Context,
    q: Annotated[Optional[str], Field(description="全文检索关键词（跨字段，含病历全文）")] = None,
    name: Annotated[Optional[str], Field(description="宠物姓名")] = None,
    owner_name: Annotated[Optional[str], Field(description="主人姓名")] = None,
    owner_phone: Annotated[Optional[str], Field(description="主人电话")] = None,
    species: Annotated[
        Optional[str], Field(description="种类（如 犬/猫/仓鼠）")
    ] = None,
    doctor: Annotated[Optional[str], Field(description="主治医生")] = None,
    disease: Annotated[Optional[str], Field(description="疾病")] = None,
    status: Annotated[
        Optional[str],
        Field(description="就诊状态（待就诊/就诊中/住院中/已康复/慢性病随访）"),
    ] = None,
    min: Annotated[Optional[float], Field(description="最低总花费")] = None,
    max: Annotated[Optional[float], Field(description="最高总花费")] = None,
    sort_by: Annotated[
        Optional[str], Field(description="排序字段（如 totalCost / name / ageMonths）")
    ] = None,
    order: Annotated[
        Optional[Literal["asc", "desc"]],
        Field(description="排序方向：asc 升序 / desc 降序"),
    ] = None,
    page: Annotated[int, Field(ge=1, description="页码（从 1 开始）")] = 1,
    page_size: Annotated[
        int, Field(ge=1, le=500, description="每页条数（1-500）")
    ] = 20,
) -> ListPetsResult:
    """List pet profiles from the Pet Hospital REST API with filters."""
    client: PetHospitalClient = ctx.request_context.lifespan_context
    query = _to_query_params(
        {
            "q": q,
            "name": name,
            "owner_name": owner_name,
            "owner_phone": owner_phone,
            "species": species,
            "doctor": doctor,
            "disease": disease,
            "status": status,
            "min": min,
            "max": max,
            "sort_by": sort_by,
            "order": order,
            "page": page,
            "page_size": page_size,
        }
    )
    try:
        data = await client.list_pets(params=query)
    except PetHospitalError as exc:
        raise ToolError(f"Pet Hospital API 调用失败：{exc}") from exc

    return ListPetsResult(
        pets=[_to_pet(item) for item in data["items"]],
        total=data["total"],
        page=data["page"],
        page_size=data["pageSize"],
        total_pages=data["totalPages"],
        total_cost=data["totalCost"],
    )


@mcp.tool(
    name="pet-hospital-create-pet",
    title="Create Pet",
    description=(
        "新增一条宠物档案。必填：name（宠物名称）、species（种类）。\n"
        "可选：品种/性别/月龄/毛色/芯片号/主人姓名/电话/住址/主治医生/疾病/就诊状态/过敏史/备注。\n"
        f"就诊状态枚举：{'/'.join(STATUS_VALUES)}；id 由系统自动生成（如 PET-000001）。"
    ),
)
async def create_pet(
    ctx: Context,
    name: Annotated[str, Field(description="宠物名称（必填）")],
    species: Annotated[
        str, Field(description="种类（必填，如 犬/猫/仓鼠/兔/鸟/爬宠/其他）")
    ],
    breed: Annotated[Optional[str], Field(description="品种")] = None,
    gender: Annotated[Optional[str], Field(description="性别（公/母）")] = None,
    age_months: Annotated[
        Optional[int], Field(ge=0, description="月龄（非负整数）")
    ] = None,
    color: Annotated[Optional[str], Field(description="毛色")] = None,
    chip_no: Annotated[Optional[str], Field(description="芯片号")] = None,
    owner_name: Annotated[Optional[str], Field(description="主人姓名")] = None,
    owner_phone: Annotated[Optional[str], Field(description="主人电话")] = None,
    owner_addr: Annotated[Optional[str], Field(description="主人住址")] = None,
    doctor: Annotated[Optional[str], Field(description="主治医生")] = None,
    disease: Annotated[Optional[str], Field(description="疾病")] = None,
    status: Annotated[
        Optional[str],
        Field(description="就诊状态（待就诊/就诊中/住院中/已康复/慢性病随访）"),
    ] = None,
    allergy: Annotated[Optional[str], Field(description="过敏史")] = None,
    note: Annotated[Optional[str], Field(description="备注")] = None,
) -> Pet:
    """Create a pet profile via the Pet Hospital REST API."""
    client: PetHospitalClient = ctx.request_context.lifespan_context
    payload = _to_query_params(
        {
            "name": name,
            "species": species,
            "breed": breed,
            "gender": gender,
            "age_months": age_months,
            "color": color,
            "chip_no": chip_no,
            "owner_name": owner_name,
            "owner_phone": owner_phone,
            "owner_addr": owner_addr,
            "doctor": doctor,
            "disease": disease,
            "status": status,
            "allergy": allergy,
            "note": note,
        }
    )
    try:
        created = await client.create_pet(payload)
    except PetHospitalError as exc:
        raise ToolError(f"Pet Hospital API 调用失败：{exc}") from exc

    return _to_pet(created)


def main() -> None:
    """Run the MCP server.

    默认 stdio 模式（由 MCP Host 启动）；设置环境变量可切换传输：
      MCP_TRANSPORT=streamable-http  → Streamable HTTP
      MCP_HOST / MCP_PORT             → 监听地址与端口（默认 127.0.0.1:9090）
    """
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host=os.environ.get("MCP_HOST", "127.0.0.1"),
            port=int(os.environ.get("MCP_PORT", "9090")),
            json_response=True,
            stateless_http=True,
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()