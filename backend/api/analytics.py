"""Analytics API — interview performance, radar data, trends, recommendations."""

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.dependencies import get_current_user
from models import User, Interview, QuestionRecord

logger = logging.getLogger("codemock")
router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# Topic labels for radar chart
RADAR_TOPICS = [
    "agent_architecture", "tool_use", "memory", "mcp",
    "retrieval", "chunking", "advanced_rag", "rag_evaluation",
    "langchain", "langgraph", "java"
]

TOPIC_LABELS = {
    "agent_architecture": "Agent架构",
    "tool_use": "工具调用",
    "memory": "记忆管理",
    "mcp": "MCP",
    "retrieval": "检索",
    "chunking": "分块",
    "advanced_rag": "高级RAG",
    "rag_evaluation": "RAG评估",
    "langchain": "LangChain",
    "langgraph": "LangGraph",
    "java": "Java",
}


@router.get("/overview")
async def get_analytics_overview(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return aggregate interview stats: total, scores, trends."""
    # Completed interviews for this user
    result = await db.execute(
        select(Interview).where(
            Interview.user_id == user.id,
            Interview.status == "completed",
        ).order_by(Interview.started_at.asc())
    )
    interviews = result.scalars().all()

    if not interviews:
        return {
            "total_interviews": 0,
            "overall_score": None,
            "score_trend": "flat",
            "latest_score": None,
            "first_score": None,
            "weak_topics": [],
        }

    scores = [i.overall_score for i in interviews if i.overall_score is not None]
    total = len(interviews)

    # Score trend
    if len(scores) >= 2:
        delta = scores[-1] - scores[0]
        trend = "up" if delta > 0.3 else ("down" if delta < -0.3 else "flat")
    else:
        trend = "flat"

    # Weak topics: aggregate blind_spots from question_records
    blind_counts = {}
    for interview in interviews:
        records_result = await db.execute(
            select(QuestionRecord).where(QuestionRecord.interview_id == interview.id)
        )
        records = records_result.scalars().all()
        for r in records:
            for spot in (r.blind_spots or []):
                blind_counts[spot] = blind_counts.get(spot, 0) + 1

    weak_topics = sorted(blind_counts.items(), key=lambda x: -x[1])[:5]

    return {
        "total_interviews": total,
        "overall_score": round(sum(scores) / len(scores), 1) if scores else None,
        "score_trend": trend,
        "latest_score": scores[-1] if scores else None,
        "first_score": scores[0] if scores else None,
        "weak_topics": [{"topic": t, "count": c} for t, c in weak_topics],
    }


@router.get("/radar")
async def get_radar_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return radar chart data: per-topic average scores."""
    result = await db.execute(
        select(Interview).where(
            Interview.user_id == user.id,
            Interview.status == "completed",
        )
    )
    interviews = result.scalars().all()

    topic_scores = {}
    topic_counts = {}
    topic_latest = {}
    topic_first = {}

    for interview in interviews:
        records_result = await db.execute(
            select(QuestionRecord).where(QuestionRecord.interview_id == interview.id)
        )
        records = records_result.scalars().all()
        for r in records:
            if r.score is None:
                continue
            # Derive topic from question_id (e.g. "agent_001" → "agent_architecture")
            qid = r.question_id or ""
            topic = "other"
            for t in RADAR_TOPICS:
                if qid.startswith(t) or t in qid.lower():
                    topic = t
                    break
            if topic == "other" and "agent" in qid.lower():
                topic = "agent_architecture"
            elif topic == "other" and "rag" in qid.lower():
                topic = "retrieval"
            elif topic == "other" and "langgraph" in qid.lower():
                topic = "langgraph"
            elif topic == "other" and "java" in qid.lower():
                topic = "java"

            topic_scores[topic] = topic_scores.get(topic, 0) + r.score
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
            if topic not in topic_first:
                topic_first[topic] = r.score
            topic_latest[topic] = r.score

    # Build radar data
    radar = []
    for t in RADAR_TOPICS:
        avg = round(topic_scores.get(t, 0) / topic_counts.get(t, 1), 1)
        label = TOPIC_LABELS.get(t, t)
        radar.append({
            "topic": t,
            "label": label,
            "score": avg if topic_counts.get(t) else 0,
            "count": topic_counts.get(t, 0),
            "first": topic_first.get(t),
            "latest": topic_latest.get(t),
        })

    return {"radar": radar}


@router.get("/trends")
async def get_trends(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return per-topic score trends (first vs latest interview)."""
    result = await db.execute(
        select(Interview).where(
            Interview.user_id == user.id,
            Interview.status == "completed",
        ).order_by(Interview.started_at.asc())
    )
    interviews = result.scalars().all()

    if len(interviews) < 2:
        return {"trends": [], "message": "Need at least 2 interviews for trends"}

    first_iv = interviews[0]
    latest_iv = interviews[-1]

    def _topic_scores(iv):
        scores_map = {}
        # We can't easily get records without async query, so fetch them
        return scores_map  # Placeholder — this needs an async query

    # Simplified: compare overall scores per interview
    trends = []
    for iv in interviews:
        trends.append({
            "date": iv.started_at.isoformat() if iv.started_at else "",
            "score": iv.overall_score,
            "questions": iv.total_questions,
        })

    # Also compute per-topic if we have records data
    topic_deltas = []
    all_topic_first = {}
    all_topic_last = {}

    for iv in interviews:
        records_result = await db.execute(
            select(QuestionRecord).where(QuestionRecord.interview_id == iv.id)
        )
        for r in records_result.scalars().all():
            if r.score is None or not r.question_id:
                continue
            topic = "other"
            for t in RADAR_TOPICS:
                if r.question_id.startswith(t):
                    topic = t
                    break
            if iv == first_iv:
                all_topic_first[topic] = all_topic_first.get(topic, 0) + r.score
            if iv == latest_iv:
                all_topic_last[topic] = all_topic_last.get(topic, 0) + r.score

    for topic in sorted(set(list(all_topic_first.keys()) + list(all_topic_last.keys()))):
        first_avg = all_topic_first.get(topic, 0)
        last_avg = all_topic_last.get(topic, 0)
        # Normalize by count
        delta = last_avg - first_avg
        topic_deltas.append({
            "topic": topic,
            "label": TOPIC_LABELS.get(topic, topic),
            "first_score": round(first_avg, 1),
            "latest_score": round(last_avg, 1),
            "delta": round(delta, 1),
        })

    topic_deltas.sort(key=lambda x: x["delta"])

    return {"trends": trends, "topic_deltas": topic_deltas}


@router.get("/recommendations")
async def get_recommendations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI-generated study recommendations based on weak areas."""
    result = await db.execute(
        select(Interview).where(
            Interview.user_id == user.id,
            Interview.status == "completed",
        ).order_by(Interview.started_at.desc())
    )
    interviews = result.scalars().all()

    if not interviews:
        return {"recommendations": [], "message": "Complete at least one interview for recommendations"}

    # Collect blind spots across all interviews
    blind_spots_all = []
    for iv in interviews:
        records_result = await db.execute(
            select(QuestionRecord).where(QuestionRecord.interview_id == iv.id)
        )
        for r in records_result.scalars().all():
            if r.blind_spots:
                blind_spots_all.extend(r.blind_spots)
            if r.score is not None and r.score <= 2:
                blind_spots_all.append(f"low_score_{r.question_id}")

    # Count frequency
    from collections import Counter
    spot_counts = Counter(blind_spots_all)

    # Build recommendations
    recs = []
    for spot, count in spot_counts.most_common(5):
        label = spot.replace("_", " ").title()
        priority = "high" if count >= 3 else ("medium" if count >= 2 else "low")
        recs.append({
            "topic": spot,
            "label": label,
            "frequency": count,
            "priority": priority,
        })

    return {"recommendations": recs}
