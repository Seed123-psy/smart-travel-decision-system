from fastapi import APIRouter

from app.schemas.travel import RequirementValidation, TravelRequest

router = APIRouter(prefix="/requirements", tags=["requirements"])


@router.post("/validate", response_model=RequirementValidation)
async def validate_requirements(payload: TravelRequest) -> RequirementValidation:
    """Validate confirmed fields without saving personal input or invoking external APIs."""
    return RequirementValidation(request=payload, warnings=[
        "预算为全体出行人的目的地游玩总预算，不含往返目的地的大交通费用。",
        "本次仅校验字段和日期；目的地城市范围、地图数据及行程可执行性尚未验证。",
        "本次需求未保存；确认并生成后才会联网规划并保存到本机，费用精算仍未接入。",
    ])
