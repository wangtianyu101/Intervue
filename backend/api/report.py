from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from core.database import get_db
from core.dependencies import get_current_user
from models import User, Interview, Report, QuestionRecord, Profile
from agents.report_agent import report_agent
from services.seed_service import get_question_by_id

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/interview/{interview_id}")
async def get_report(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Report).where(
            Report.interview_id == str(interview_id),
            Report.user_id == user.id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.post("/interview/{interview_id}")
async def generate_report(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate (or regenerate) a real report from the interview's question records.

    Replaces the previous all-3s stub with a call to ReportAgent which produces:
      - radar_data: per-skill 1-5 scores (11 dimensions)
      - top_blind_spots: 3 highest-priority weak areas with suggestions
      - improvement_plan: actionable study plan with resources
    """
    # 1. Verify interview belongs to user
    result = await db.execute(
        select(Interview).where(
            Interview.id == str(interview_id),
            Interview.user_id == user.id,
        )
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    if interview.status != "completed":
        raise HTTPException(status_code=400, detail="Interview not yet completed")

    # 2. Load profile
    profile_result = await db.execute(
        select(Profile).where(Profile.user_id == user.id)
    )
    profile = profile_result.scalar_one_or_none()
    profile_dict = {
        "tech_stack": profile.tech_stack if profile else [],
        "years_of_exp": profile.years_of_exp if profile else 0,
        "current_level": profile.current_level if profile else "mid",
    }

    # 3. Load question records + look up topic from seed data
    records_result = await db.execute(
        select(QuestionRecord)
        .where(QuestionRecord.interview_id == str(interview_id))
        .order_by(QuestionRecord.created_at.asc())
    )
    records = records_result.scalars().all()

    questions_asked: list[dict] = []
    blind_spots: list[str] = []
    score_sum = 0
    score_count = 0
    for rec in records:
        # Prefer the question's topic from the seed bank; fall back to "" if
        # the seed has been edited or the id is unknown.
        q_meta = get_question_by_id(rec.question_id) if rec.question_id else None
        topic = (q_meta or {}).get("topic", "")
        sub_topic = (q_meta or {}).get("sub_topic", "")
        questions_asked.append({
            "id": rec.question_id,
            "question_text": rec.question_text,
            "topic": topic,
            "sub_topic": sub_topic,
            "score": rec.score,
        })
        if isinstance(rec.blind_spots, list):
            blind_spots.extend([str(x) for x in rec.blind_spots if x])
        if rec.score is not None:
            score_sum += rec.score
            score_count += 1

    total_score = (score_sum / score_count) if score_count else (interview.overall_score or 3.0)

    # 4. Run the real ReportAgent
    agent_result = await report_agent.generate_report(
        profile=profile_dict,
        questions_asked=questions_asked,
        blind_spots=blind_spots,
        total_score=total_score,
        round=interview.round or "round1",
    )

    # 5. Upsert: replace an existing report if present (idempotent re-generate)
    existing_result = await db.execute(
        select(Report).where(Report.interview_id == str(interview_id))
    )
    report = existing_result.scalar_one_or_none()
    if report is None:
        report = Report(
            interview_id=str(interview_id),
            user_id=user.id,
        )
        db.add(report)

    report.radar_data = agent_result.get("radar_data", {})
    report.top_blind_spots = agent_result.get("top_blind_spots", [])
    report.improvement_plan = agent_result.get("improvement_plan", [])
    report.overall_score = agent_result.get("overall_score", total_score)
    report.summary = agent_result.get("summary", "")

    await db.commit()
    await db.refresh(report)
    return report
