"""学习进度 service (Phase 1b-2 · 学习复习模块 · /learn /review 路由对应)。

职责:
- SM-2 算法 (SRS 调度)
- QuestionProgress CRUD + upsert_from_interview (D5)
- 复习队列 (review_queue) — Redis 缓存
- 推荐 (recommend)
- 学习 session 记录
- 答题明细日志 (QuestionAnswerLog)

SM-2 简化:
  - quality 评分 0-5 (0=完全不会, 5=完美)
  - repetition_count 复习次数
  - ease_factor 默认 2.5, 最小 1.3
  - interval_days = 0, 1, 6, prev*ease, ...
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import cache
from models import (
    LearningSession,
    MonthlyReport,
    Question,
    QuestionAnswerLog,
    QuestionProgress,
    ReviewSchedule,
    StudyPlan,
    UserQuestion,
)

log = logging.getLogger("codemock.learning_progress")

REVIEW_QUEUE_TTL = 300  # 5 min
REVIEW_QUEUE_BATCH = 50
DEFAULT_EASE = 2.5
MIN_EASE = 1.3


# ════════════════════════════════════════════════════════════
#  SM-2 算法
# ════════════════════════════════════════════════════════════


def calculate_next_srs(
    quality: int,
    *,
    ease_factor: float = DEFAULT_EASE,
    interval_days: int = 0,
    repetition_count: int = 0,
) -> dict:
    """SM-2 简化: 根据答题质量算下次复习参数。

    Args:
        quality: 0-5 (0=完全不会, 3=及格, 5=完美)
        ease_factor: 当前 ease (默认 2.5)
        interval_days: 当前间隔
        repetition_count: 当前复习次数

    Returns:
        {"ease_factor", "interval_days", "repetition_count", "next_status"}
    """
    quality = max(0, min(5, quality))

    # 更新 ease_factor (SM-2 公式)
    new_ease = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ease = max(MIN_EASE, new_ease)

    if quality < 3:
        # 答错 → 重置 repetition, interval = 1
        new_repetition = 0
        new_interval = 1
        next_status = "learning"
    else:
        new_repetition = repetition_count + 1
        if new_repetition == 1:
            new_interval = 1
        elif new_repetition == 2:
            new_interval = 6
        else:
            new_interval = max(1, int(interval_days * new_ease))
        # status 升级: 3 次连对 → mastered
        if new_repetition >= 5:
            next_status = "mastered"
        elif new_repetition >= 1:
            next_status = "learning"
        else:
            next_status = "new"

    return {
        "ease_factor": round(new_ease, 2),
        "interval_days": new_interval,
        "repetition_count": new_repetition,
        "next_status": next_status,
    }


def calc_next_review_at(interval_days: int) -> datetime:
    """根据 interval_days 算下次复习时间 (UTC)。"""
    return datetime.now(timezone.utc) + timedelta(days=interval_days)


# ════════════════════════════════════════════════════════════
#  QuestionProgress CRUD
# ════════════════════════════════════════════════════════════


async def get_user_progress(
    db: AsyncSession, user_id: str, question_id: str
) -> Optional[QuestionProgress]:
    return (await db.execute(
        select(QuestionProgress).where(
            QuestionProgress.user_id == user_id,
            QuestionProgress.question_id == question_id,
        )
    )).scalar_one_or_none()


async def list_my_progress(
    db: AsyncSession, user_id: str, *,
    status: Optional[str] = None,
    topic: Optional[str] = None,
    bookmarked: Optional[bool] = None,
    page: int = 1,
    size: int = 20,
) -> dict:
    """列进度 (支持 status / topic / bookmarked 过滤)。"""
    q = select(QuestionProgress).where(QuestionProgress.user_id == user_id)
    if status:
        q = q.where(QuestionProgress.status == status)
    if bookmarked is not None:
        q = q.where(QuestionProgress.bookmarked == bookmarked)

    rows = (await db.execute(q.offset((page - 1) * size).limit(size))).scalars().all()
    total = (await db.execute(
        select(func.count()).select_from(QuestionProgress).where(
            QuestionProgress.user_id == user_id,
            *(QuestionProgress.status == status,) if status else (),
            *(QuestionProgress.bookmarked == bookmarked,) if bookmarked is not None else (),
        )
    )).scalar() or 0

    items = [
        {
            "question_id": p.question_id,
            "status": p.status,
            "practice_count": p.practice_count,
            "correct_count": p.correct_count,
            "bookmarked": p.bookmarked,
            "ease_factor": p.ease_factor,
            "interval_days": p.interval_days,
            "next_review_at": p.next_review_at.isoformat() if p.next_review_at else None,
            "last_practiced_at": p.last_practiced_at.isoformat() if p.last_practiced_at else None,
        }
        for p in rows
    ]
    return {"items": items, "total": total, "page": page, "size": size}


async def upsert_progress(
    db: AsyncSession, user_id: str, question_id: str, *,
    score: int,
    blind_spots: Optional[list] = None,
    user_answer: Optional[str] = None,
    duration_sec: int = 0,
    source: Optional[str] = "practice",
) -> QuestionProgress:
    """答完一题后调: 算 SM-2 → upsert progress → 写 answer_log。

    Returns: updated QuestionProgress
    """
    p = await get_user_progress(db, user_id, question_id)
    is_new = p is None
    if is_new:
        p = QuestionProgress(
            user_id=user_id, question_id=question_id,
            first_practiced_at=datetime.now(timezone.utc),
        )
        db.add(p)

    # SM-2 计算
    srs = calculate_next_srs(
        score,
        ease_factor=p.ease_factor,
        interval_days=p.interval_days,
        repetition_count=p.repetition_count,
    )
    next_review = calc_next_review_at(srs["interval_days"])

    # update progress
    p.status = srs["next_status"]
    p.practice_count += 1
    if score >= 3:
        p.correct_count += 1
    p.ease_factor = srs["ease_factor"]
    p.interval_days = srs["interval_days"]
    p.review_count = srs["repetition_count"]
    p.next_review_at = next_review
    p.last_practiced_at = datetime.now(timezone.utc)
    if not p.last_review_at:
        p.last_review_at = p.last_practiced_at
    if user_answer:
        p.user_answer = user_answer
    p.updated_at = datetime.now(timezone.utc)
    p.source = source

    # 写 answer_log (用于分数曲线分析)
    log_row = QuestionAnswerLog(
        user_id=user_id,
        question_id=question_id,
        score=score,
        blind_spots=blind_spots or [],
        duration_sec=duration_sec,
        source=source or "practice",
        answered_at=datetime.now(timezone.utc),
    )
    db.add(log_row)

    await db.commit()
    await db.refresh(p)

    # invalidate review_queue cache
    await cache.delete(f"review_queue:{user_id}")
    return p


async def upsert_from_interview(
    db: AsyncSession, user_id: str, question_id: str, *,
    correct: bool, interview_id: str,
) -> Optional[QuestionProgress]:
    """D5: 面试里答对题后调, 自动同步 question_progress。

    score 简化: correct=True → 4 (算对), False → 2 (不会)
    Returns: QuestionProgress (or None if progress 创建失败)
    """
    score = 4 if correct else 2
    try:
        p = await upsert_progress(
            db, user_id, question_id,
            score=score,
            source="mock_interview",
        )
        log.info(f"interview sync: user={user_id} q={question_id} score={score} interview={interview_id}")
        return p
    except Exception as e:
        log.warning(f"interview sync failed: user={user_id} q={question_id} {e}")
        await db.rollback()
        return None


# ════════════════════════════════════════════════════════════
#  复习队列 (Redis 缓存)
# ════════════════════════════════════════════════════════════


async def get_review_queue(
    db: AsyncSession, user_id: str, limit: int = REVIEW_QUEUE_BATCH
) -> list[dict]:
    """取该用户到期应复习的题 (next_review_at <= NOW())。

    走 idx_qp_review_covering 覆盖索引 (Phase 1a 加的)。
    """
    cache_key = f"review_queue:{user_id}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached[:limit]

    now = datetime.now(timezone.utc)
    rows = (await db.execute(
        select(QuestionProgress).where(
            QuestionProgress.user_id == user_id,
            QuestionProgress.status.in_(["new", "learning"]),
            QuestionProgress.next_review_at <= now,
        ).order_by(QuestionProgress.next_review_at).limit(REVIEW_QUEUE_BATCH)
    )).scalars().all()

    items = [
        {
            "question_id": p.question_id,
            "status": p.status,
            "ease_factor": p.ease_factor,
            "interval_days": p.interval_days,
            "next_review_at": p.next_review_at.isoformat() if p.next_review_at else None,
        }
        for p in rows
    ]
    await cache.set(cache_key, items, ttl=REVIEW_QUEUE_TTL)
    return items[:limit]


async def get_recommend(
    db: AsyncSession, user_id: str, n: int = 3
) -> list[dict]:
    """推荐 N 道题给用户练。

    策略:
    1. weak_topics (Profile 字段) 中抽 1-2 题
    2. status='new' 抽 1 题 (新题)
    3. status='learning' 抽 1 题 (老题)
    """
    import random

    # 1. weak topics
    profile = (await db.execute(
        select(func.json_extract).select_from(func)  # placeholder
    ))
    # 简化: 直接从 profile 字段读
    from models import Profile
    prof = (await db.execute(
        select(Profile).where(Profile.user_id == user_id)
    )).scalar_one_or_none()
    weak_topics = (prof.weak_topics if prof else []) or []

    picks: list[str] = []
    if weak_topics:
        topic = random.choice(weak_topics)
        rows = (await db.execute(
            select(Question).where(Question.topic == topic).limit(2)
        )).scalars().all()
        picks.extend([r.id for r in rows])

    # 2. new 题 (没练过的)
    new_rows = (await db.execute(
        select(QuestionProgress.question_id).where(
            QuestionProgress.user_id == user_id,
            QuestionProgress.status == "new",
        ).limit(2)
    )).scalars().all()
    picks.extend(list(new_rows))

    # 3. learning 题 (快到期)
    learning_rows = (await db.execute(
        select(QuestionProgress.question_id).where(
            QuestionProgress.user_id == user_id,
            QuestionProgress.status == "learning",
            QuestionProgress.next_review_at <= datetime.now(timezone.utc),
        ).limit(2)
    )).scalars().all()
    picks.extend(list(learning_rows))

    # 去重 + shuffle
    picks = list(dict.fromkeys(picks))
    random.shuffle(picks)
    picks = picks[:n]

    # 转 dict
    items = []
    for qid in picks:
        q_row = await db.get(Question, qid)
        if q_row is not None:
            items.append({
                "id": q_row.id,
                "topic": q_row.topic,
                "sub_topic": q_row.sub_topic,
                "difficulty": q_row.difficulty,
                "question_text": q_row.question_text,
                "source": "seed",
            })
        else:
            u_row = await db.get(UserQuestion, qid)
            if u_row is not None:
                items.append({
                    "id": u_row.id,
                    "topic": u_row.topic or "",
                    "sub_topic": u_row.sub_topic or "",
                    "difficulty": u_row.difficulty,
                    "question_text": u_row.question_text,
                    "source": u_row.source,
                })
    return items


# ════════════════════════════════════════════════════════════
#  LearningSession
# ════════════════════════════════════════════════════════════


async def start_session(
    db: AsyncSession, user_id: str, session_type: str = "practice"
) -> LearningSession:
    s = LearningSession(
        user_id=user_id, type=session_type, items=[],
        started_at=datetime.now(timezone.utc),
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def end_session(
    db: AsyncSession, user_id: str, session_id: str, items: list[dict]
) -> Optional[LearningSession]:
    s = await db.get(LearningSession, session_id)
    if s is None or s.user_id != user_id:
        return None
    s.ended_at = datetime.now(timezone.utc)
    if s.started_at:
        delta = s.ended_at - s.started_at
        s.duration_sec = int(delta.total_seconds())
    s.items = items
    await db.commit()
    await db.refresh(s)
    return s


async def get_recent_sessions(
    db: AsyncSession, user_id: str, days: int = 7
) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (await db.execute(
        select(LearningSession).where(
            LearningSession.user_id == user_id,
            LearningSession.started_at >= cutoff,
        ).order_by(LearningSession.started_at.desc())
    )).scalars().all()
    return {
        "items": [
            {
                "id": s.id,
                "type": s.type,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                "duration_sec": s.duration_sec,
                "item_count": len(s.items or []),
            }
            for s in rows
        ]
    }


# ════════════════════════════════════════════════════════════
#  学习统计
# ════════════════════════════════════════════════════════════


async def get_learn_stats(db: AsyncSession, user_id: str) -> dict:
    """学习统计 (dashboard 用)。走 Redis 缓存。"""
    cache_key = f"topic_stats:{user_id}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached

    # 1. 进度汇总
    progress_stats = (await db.execute(
        select(
            QuestionProgress.status,
            func.count().label("cnt"),
        ).where(
            QuestionProgress.user_id == user_id
        ).group_by(QuestionProgress.status)
    )).all()
    by_status = {row.status: row.cnt for row in progress_stats}

    # 2. 总练习数 / 答对数
    total = (await db.execute(
        select(
            func.coalesce(func.sum(QuestionProgress.practice_count), 0),
            func.coalesce(func.sum(QuestionProgress.correct_count), 0),
        ).where(QuestionProgress.user_id == user_id)
    )).first()
    total_practice = int(total[0] or 0)
    total_correct = int(total[1] or 0)

    # 3. 收藏数
    bookmarked = by_status.get("__bookmarked__", 0)
    bm = (await db.execute(
        select(func.count()).select_from(QuestionProgress).where(
            QuestionProgress.user_id == user_id,
            QuestionProgress.bookmarked == True,  # noqa: E712
        )
    )).scalar() or 0

    # 4. 本周 session 总时长
    week_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    session_sum = (await db.execute(
        select(func.coalesce(func.sum(LearningSession.duration_sec), 0)).where(
            LearningSession.user_id == user_id,
            LearningSession.started_at >= week_cutoff,
        )
    )).scalar() or 0

    result = {
        "total_practice": total_practice,
        "total_correct": total_correct,
        "accuracy": round(total_correct / total_practice * 100, 1) if total_practice > 0 else 0,
        "by_status": {
            "new": by_status.get("new", 0),
            "learning": by_status.get("learning", 0),
            "mastered": by_status.get("mastered", 0),
            "skipped": by_status.get("skipped", 0),
        },
        "bookmarked": int(bm),
        "week_session_sec": int(session_sum),
    }
    await cache.set(cache_key, result, ttl=600)  # 10 min
    return result


def invalidate_topic_stats(user_id: str):
    """topic_stats cache 失效 (progress 变更后调)。"""
    import asyncio
    asyncio.create_task(cache.delete(f"topic_stats:{user_id}"))


def invalidate_review_queue(user_id: str):
    """review_queue cache 失效 (progress 变更后调)。"""
    import asyncio
    asyncio.create_task(cache.delete(f"review_queue:{user_id}"))