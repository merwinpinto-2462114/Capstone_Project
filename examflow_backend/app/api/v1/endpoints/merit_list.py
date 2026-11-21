"""Merit list endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_roles, get_current_user
from app.schemas.schemas import GenerateMeritListRequest, MeritListOut
from app.services.merit_list_service import MeritListService
from app.models.user import User

router = APIRouter()


@router.post("/generate", response_model=MeritListOut, status_code=201)
async def generate_merit_list(
    body: GenerateMeritListRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN", "EXAM_ADMIN")),
):
    svc = MeritListService(db)
    return await svc.generate(body, actor=current_user)


@router.get("/{examination_id}/latest", response_model=MeritListOut)
async def get_latest_merit_list(
    examination_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = MeritListService(db)
    ml = await svc.get_latest(examination_id)
    if not ml:
        raise HTTPException(status_code=404, detail="No merit list found")
    return ml


@router.patch("/{merit_list_id}/publish")
async def publish_merit_list(
    merit_list_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN")),
):
    svc = MeritListService(db)
    return await svc.publish(merit_list_id, actor=current_user)
