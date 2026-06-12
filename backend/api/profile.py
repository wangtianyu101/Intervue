from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.dependencies import get_current_user
from models import User, Profile
from schemas.profile import ProfileOut, ProfileUpdate

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("/me", response_model=ProfileOut)
async def get_my_profile(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Profile).where(Profile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        profile = Profile(user_id=user.id)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


@router.put("/me", response_model=ProfileOut)
async def update_profile(
    data: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Profile).where(Profile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        profile = Profile(user_id=user.id)
        db.add(profile)

    if data.tech_stack is not None:
        profile.tech_stack = data.tech_stack
    if data.years_of_exp is not None:
        profile.years_of_exp = data.years_of_exp
    if data.current_level is not None:
        profile.current_level = data.current_level
    if data.target_companies is not None:
        profile.target_companies = data.target_companies
    if data.resume_text is not None:
        profile.resume_summary = _extract_resume_summary(data.resume_text)

    await db.commit()
    await db.refresh(profile)
    return profile


@router.post("/resume")
async def upload_resume(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload resume PDF → extract text → LLM fills tech_stack/years/level."""
    from fastapi import UploadFile, File
    # This endpoint expects multipart form data
    return {"message": "Resume upload — requires multipart form. Use PUT /api/profile/me with resume_text for now."}


def _extract_resume_summary(resume_text: str) -> str:
    """Stub — will use LLM extraction in Week 2"""
    return resume_text[:2000]
