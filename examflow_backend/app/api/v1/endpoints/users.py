"""User management endpoints"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_roles
from app.core.security import get_password_hash
from app.schemas.schemas import UserCreate, UserOut
from app.repositories.user_repository import UserRepository
from app.models.models import User
from app.models.user import User

router = APIRouter()


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles("SUPER_ADMIN")),
):
    repo = UserRepository(db)
    existing = await repo.get_by_username(body.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")
    user = User(
        username=body.username,
        email=body.email,
        full_name=body.full_name,
        hashed_password=get_password_hash(body.password),
        role_id=body.role_id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.get("/me", response_model=UserOut)
async def get_me(
    current_user: User = Depends(require_roles(
        "SUPER_ADMIN", "EXAM_ADMIN", "EVALUATOR", "PROCTOR", "CANDIDATE", "AUDITOR"
    )),
):
    return current_user
