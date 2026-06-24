"""学习计划 service (Phase 1b-3 · /learn 路由 计划 tab)。

设计:
- 一条 plan = 用户一段时期的学习目标
- weekly_target: [{week_idx, target_count, target_topics}]
- progress: {done_count, mastered_count, weak_topics_remaining} (实时聚合)
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import QuestionProgress, StudyPlan

log = logging.getLogger("codemock.study_plan")


async def list_plans(db: AsyncSession, user_id: str) -> dict:
    rows = (await db.execute(
        select(StudyPlan).where(StudyPlan.user_id == user_id)
        .order_by(StudyPlan.start_date.desc())
    )).scalars().all()
    return {
        "items": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "goal": p.goal,
                "start_date": p.start_date.isoformat() if p.start_date else None,
                "end_date": p.end_date.isoformat() if p.end_date else None,
                "status": p.status,
                "weekly_target": p.weekly_target or [],
                "progress": p.progress or {},
            }
            for p in rows
        ]
    }


async def get_plan(db: AsyncSession, user_id: str, plan_id: str) -> Optional[StudyPlan]:
    p = await db.get(StudyPlan, plan_id)
    if p is None or p.user_id != user_id:
        return None
    return p


async def create_plan(
    db: AsyncSession, user_id: str, data: dict
) -> StudyPlan:
    p = StudyPlan(
        user_id=user_id,
        name=data["name"],
        description=data.get("description"),
        goal=data.get("goal"),
        start_date=date.fromisoformat(data["start_date"]) if isinstance(data.get("start_date"), str) else data.get("start_date"),
        end_date=date.fromisoformat(data["end_date"]) if isinstance(data.get("end_date"), str) else data.get("end_date"),
        status=data.get("status", "active"),
        weekly_target=data.get("weekly_target", []),
        progress=data.get("progress", {}),
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def update_plan(
    db: AsyncSession, user_id: str, plan_id: str, data: dict
) -> Optional[StudyPlan]:
    p = await get_plan(db, user_id, plan_id)
    if p is None:
        return None
    for field in ["name", "description", "goal", "status", "weekly_target", "progress"]:
        if field in data:
            setattr(p, field, data[field])
    if "start_date" in data and isinstance(data["start_date"], str):
        p.start_date = date.fromisoformat(data["start_date"])
    if "end_date" in data and isinstance(data["end_date"], str):
        p.end_date = date.fromisoformat(data["end_date"])
    p.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(p)
    return p


async def delete_plan(db: AsyncSession, user_id: str, plan_id: str) -> bool:
    p = await get_plan(db, user_id, plan_id)
    if p is None:
        return False
    await db.delete(p)
    await db.commit()
    return True


async def get_plan_progress(
    db: AsyncSession, user_id: str, plan_id: str
) -> Optional[dict]:
    """聚合 plan 的真实进度 (从 question_progress 算, 不依赖 plan.progress JSON 字段)。

    Returns:
        {
            "total_target": int,    # weekly_target 累计
            "mastered": int,        # 真实 mastered 题数
            "learning": int,
            "new_count": int,
            "completion_rate": float,  # 0-1
            "weak_topics_remaining": [str],
        }
    """
    p = await get_plan(db, user_id, plan_id)
    if p is None:
        return None

    # 累计 weekly_target
    total_target = sum(week.get("target_count", 0) for week in (p.weekly_target or []))

    # 真实进度聚合 (按 status)
    status_rows = (await db.execute(
        select(QuestionProgress.status, func.count())
        .where(QuestionProgress.user_id == user_id)
        .group_by(QuestionProgress.status)
    )).all()
    by_status = {row[0]: row[1] for row in status_rows}

    mastered = by_status.get("mastered", 0)
    learning = by_status.get("learning", 0)
    new_count = by_status.get("new", 0)

    # 涉及的 topics (从 weekly_target 提)
    target_topics = set()
    for week in (p.weekly_target or []):
        for t in week.get("target_topics", []):
            target_topics.add(t)

    # 弱项 topic: 在 target_topics 但 mastered < 50%
    weak_remaining = []
    for topic in target_topics:
        topic_total = (await db.execute(
            select(func.count()).select_from(QuestionProgress)
            .join(Question, Question.id == QuestionProgress.question_id)
            .where(
                QuestionProgress.user_id == user_id,
                Question.topic == topic,
            )
        )).scalar() or 0
        topic_mastered = (await db.execute(
            select(func.count()).select_from(QuestionProgress)
            .join(Question, Question.id == QuestionProgress.question_id)
            .where(
                QuestionProgress.user_id == user_id,
                Question.topic == topic,
                QuestionProgress.status == "mastered",
            )
        )).scalar() or 0
        if topic_total > 0 and topic_mastered / topic_total < 0.5:
            weak_remaining.append(topic)

    completion = mastered / total_target if total_target > 0 else 0

    return {
        "total_target": total_target,
        "mastered": mastered,
        "learning": learning,
        "new_count": new_count,
        "completion_rate": round(completion, 2),
        "weak_topics_remaining": weak_remaining,
    }