"""Dashboard API — aggregated overview data for the main dashboard page."""

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.dependencies import get_current_user
from models import User, Interview

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
async def get_dashboard(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return aggregated dashboard data."""

    # Interview stats
    result = await db.execute(
        select(Interview).where(Interview.user_id == user.id)
        .order_by(Interview.started_at.desc())
    )
    interviews = result.scalars().all()

    completed = [i for i in interviews if i.status == "completed"]
    completed_scores = [i.overall_score for i in completed if i.overall_score is not None]
    latest_score = completed_scores[0] if completed_scores else None
    trend = "up" if len(completed_scores) >= 2 and completed_scores[0] > completed_scores[-1] else "flat"

    return {
        "interview": {
            "total": len(interviews),
            "completed": len(completed),
            "in_progress": len([i for i in interviews if i.status == "in_progress"]),
            "latest_score": latest_score,
            "score_trend": trend,
        },
    }
