"""题库 service (Phase 1b-1 · 学习复习模块 4 tab · /learn 路由对应)。

职责:
- 题目查询 (种子题 + 用户题 + tag)
- 用户题 CRUD
- tag 管理 (系统 + 用户自定义)
- 用户题内联笔记

注意:
- 种子题 (Question) 只读, 来自 backend/seed_data/*.json
- 用户题 (UserQuestion) 可 CRUD
- 题库列表用 Redis cache (key: question_list:{filter_hash}), 5min TTL
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import cache
from models import (
    BookmarkCollection,
    Question,
    QuestionAnswerLog,
    QuestionProgress,
    QuestionTag,
    QuestionTagMap,
    UserQuestion,
    UserQuestionNote,
)

log = logging.getLogger("codemock.question_bank")

QUESTION_LIST_TTL = 300  # 5 min


# ════════════════════════════════════════════════════════════
#  题目查询 (种子题 + 用户题合并视图)
# ════════════════════════════════════════════════════════════


def _filter_cache_key(user_id: str, filters: dict, page: int, size: int) -> str:
    """生成 question list cache key (基于 user_id + filter hash)。"""
    payload = json.dumps({"u": user_id, "f": filters, "p": page, "s": size}, sort_keys=True)
    h = hashlib.md5(payload.encode()).hexdigest()[:16]
    return f"question_list:{h}"


async def list_questions(
    db: AsyncSession,
    user_id: str,
    *,
    topic: Optional[str] = None,
    difficulty: Optional[int] = None,
    source: Optional[str] = None,
    bookmarked: Optional[bool] = None,
    q: Optional[str] = None,
    sort: str = "id",
    page: int = 1,
    size: int = 20,
) -> dict:
    """列表查询: 合并 seed (Question) + user (UserQuestion) + tag 过滤。

    Returns:
        {
            "items": [QuestionListItem dict],
            "total": int,
            "page": int,
            "size": int,
        }
    """
    filters = {
        "topic": topic, "difficulty": difficulty, "source": source,
        "bookmarked": bookmarked, "q": q, "sort": sort,
    }
    cache_key = _filter_cache_key(user_id, filters, page, size)

    # 1) cache 读
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached

    # 2) seed 题
    seed_q = select(Question)
    if topic:
        seed_q = seed_q.where(Question.topic == topic)
    if difficulty:
        seed_q = seed_q.where(Question.difficulty == difficulty)
    if q:
        seed_q = seed_q.where(Question.question_text.contains(q))

    # 3) 用户题
    user_q = select(UserQuestion).where(UserQuestion.user_id == user_id)
    if topic:
        user_q = user_q.where(UserQuestion.topic == topic)
    if difficulty:
        user_q = user_q.where(UserQuestion.difficulty == difficulty)
    if q:
        user_q = user_q.where(UserQuestion.question_text.contains(q))

    # 4) 进度 (bookmarked 过滤需要 join progress)
    progress_q = select(QuestionProgress).where(
        QuestionProgress.user_id == user_id
    )
    if bookmarked is not None:
        progress_q = progress_q.where(QuestionProgress.bookmarked == bookmarked)
    progress_map = {
        p.question_id: p for p in (await db.execute(progress_q)).scalars().all()
    }

    seed_rows = (await db.execute(seed_q)).scalars().all()
    user_rows = (await db.execute(user_q)).scalars().all()

    # 5) 合并 + 装 view dict
    items = []
    for q_row in seed_rows:
        p = progress_map.get(q_row.id)
        if bookmarked is True and not (p and p.bookmarked):
            continue
        items.append(_seed_to_item(q_row, p))
    for u_row in user_rows:
        p = progress_map.get(u_row.id)
        if bookmarked is True and not (p and p.bookmarked):
            continue
        items.append(_user_question_to_item(u_row, p))

    # 6) sort + paginate
    items = _sort_items(items, sort)
    total = len(items)
    start = (page - 1) * size
    page_items = items[start:start + size]

    result = {"items": page_items, "total": total, "page": page, "size": size}
    await cache.set(cache_key, result, ttl=QUESTION_LIST_TTL)
    return result


def _seed_to_item(q: Question, p: Optional[QuestionProgress]) -> dict:
    return {
        "id": q.id,
        "topic": q.topic,
        "sub_topic": q.sub_topic,
        "difficulty": q.difficulty,
        "question_text": q.question_text,
        "source": "seed",
        "progress": _progress_to_dict(p) if p else None,
    }


def _user_question_to_item(u: UserQuestion, p: Optional[QuestionProgress]) -> dict:
    return {
        "id": u.id,
        "topic": u.topic or "",
        "sub_topic": u.sub_topic or "",
        "difficulty": u.difficulty,
        "question_text": u.question_text,
        "source": u.source,
        "progress": _progress_to_dict(p) if p else None,
    }


def _progress_to_dict(p: QuestionProgress) -> dict:
    return {
        "id": p.id,
        "status": p.status,
        "practice_count": p.practice_count,
        "correct_count": p.correct_count,
        "bookmarked": p.bookmarked,
        "ease_factor": p.ease_factor,
        "interval_days": p.interval_days,
        "next_review_at": p.next_review_at.isoformat() if p.next_review_at else None,
        "last_practiced_at": p.last_practiced_at.isoformat() if p.last_practiced_at else None,
    }


def _sort_items(items: list[dict], sort: str) -> list[dict]:
    if sort == "difficulty":
        items.sort(key=lambda x: x.get("difficulty") or 0, reverse=True)
    elif sort == "last_practiced":
        items.sort(key=lambda x: (x.get("progress") or {}).get("last_practiced_at") or "", reverse=True)
    elif sort == "random":
        import random
        random.shuffle(items)
    else:  # "id" default
        items.sort(key=lambda x: x.get("id") or "")
    return items


async def get_question_detail(
    db: AsyncSession, user_id: str, qid: str
) -> Optional[dict]:
    """取单题详情 (从 seed 或 user 表)。

    Returns None if not found.
    """
    q_row = await db.get(Question, qid)
    if q_row is not None:
        progress = (await db.execute(
            select(QuestionProgress).where(
                QuestionProgress.user_id == user_id,
                QuestionProgress.question_id == qid,
            )
        )).scalar_one_or_none()
        return {
            "id": q_row.id,
            "topic": q_row.topic,
            "sub_topic": q_row.sub_topic,
            "difficulty": q_row.difficulty,
            "question_text": q_row.question_text,
            "answer_key_points": q_row.answer_key_points or [],
            "followup_tree": q_row.followup_tree or {},
            "source": "seed",
            "tags": await _get_tags_for_question(db, qid),
            "progress": _progress_to_dict(progress) if progress else None,
            "note": await _get_user_note(db, user_id, qid),
        }

    # 尝试 user_questions (UUID 格式)
    if len(qid) == 36:  # UUID 长度
        u_row = await db.get(UserQuestion, qid)
        if u_row is not None and u_row.user_id == user_id:
            progress = (await db.execute(
                select(QuestionProgress).where(
                    QuestionProgress.user_id == user_id,
                    QuestionProgress.question_id == qid,
                )
            )).scalar_one_or_none()
            return {
                "id": u_row.id,
                "topic": u_row.topic or "",
                "sub_topic": u_row.sub_topic or "",
                "difficulty": u_row.difficulty,
                "question_text": u_row.question_text,
                "answer_key_points": [u_row.answer] if u_row.answer else [],
                "followup_tree": {},
                "source": u_row.source,
                "tags": u_row.tags or [],
                "progress": _progress_to_dict(progress) if progress else None,
                "note": None,
            }

    return None


# ════════════════════════════════════════════════════════════
#  用户题 CRUD
# ════════════════════════════════════════════════════════════


async def create_user_question(
    db: AsyncSession, user_id: str, data: dict
) -> UserQuestion:
    """创建用户题 (来源 = user_note / news / interview)。"""
    uq = UserQuestion(
        user_id=user_id,
        question_text=data["question_text"],
        answer=data.get("answer"),
        topic=data.get("topic"),
        sub_topic=data.get("sub_topic"),
        difficulty=data.get("difficulty", 3),
        tags=data.get("tags", []),
        source=data.get("source", "user_note"),
    )
    db.add(uq)
    await db.commit()
    await db.refresh(uq)
    await _invalidate_user_list_cache(user_id)
    return uq


async def update_user_question(
    db: AsyncSession, user_id: str, qid: str, data: dict
) -> Optional[UserQuestion]:
    uq = await db.get(UserQuestion, qid)
    if uq is None or uq.user_id != user_id:
        return None
    for field in ["question_text", "answer", "topic", "sub_topic", "difficulty", "tags"]:
        if field in data:
            setattr(uq, field, data[field])
    await db.commit()
    await db.refresh(uq)
    await _invalidate_user_list_cache(user_id)
    return uq


async def delete_user_question(
    db: AsyncSession, user_id: str, qid: str
) -> bool:
    uq = await db.get(UserQuestion, qid)
    if uq is None or uq.user_id != user_id:
        return False
    await db.delete(uq)
    await db.commit()
    await _invalidate_user_list_cache(user_id)
    return True


async def _invalidate_user_list_cache(user_id: str):
    """所有该 user 的 question_list cache 都失效。pattern 删除。"""
    await cache.delete_pattern(f"question_list:*")  # 简化: 全局失效
    # 注: 精确实现应按 user_id 隔离 key (key 内含 user_id hash)


# ════════════════════════════════════════════════════════════
#  Tag 管理
# ════════════════════════════════════════════════════════════


async def list_tags(
    db: AsyncSession, user_id: Optional[str] = None, include_system: bool = True
) -> list[dict]:
    """列 tag (默认包含系统标签 + 当前用户自定义)。"""
    q = select(QuestionTag)
    if include_system and user_id:
        q = q.where(or_(QuestionTag.is_system == True, QuestionTag.user_id == user_id))  # noqa: E712
    elif user_id:
        q = q.where(QuestionTag.user_id == user_id)
    elif include_system:
        q = q.where(QuestionTag.is_system == True)  # noqa: E712
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "color": t.color,
            "is_system": t.is_system,
            "user_id": t.user_id,
        }
        for t in rows
    ]


async def create_tag(
    db: AsyncSession, user_id: str, name: str, color: Optional[str] = None, is_system: bool = False
) -> QuestionTag:
    t = QuestionTag(
        name=name, color=color, is_system=is_system, user_id=None if is_system else user_id,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


async def add_tag_to_question(
    db: AsyncSession, question_id: str, tag_id: str
) -> bool:
    """加 tag 到 question (幂等)。"""
    exists = (await db.execute(
        select(QuestionTagMap).where(
            QuestionTagMap.question_id == question_id,
            QuestionTagMap.tag_id == tag_id,
        )
    )).scalar_one_or_none()
    if exists:
        return True
    db.add(QuestionTagMap(question_id=question_id, tag_id=tag_id))
    await db.commit()
    return True


async def remove_tag_from_question(
    db: AsyncSession, question_id: str, tag_id: str
) -> bool:
    m = (await db.execute(
        select(QuestionTagMap).where(
            QuestionTagMap.question_id == question_id,
            QuestionTagMap.tag_id == tag_id,
        )
    )).scalar_one_or_none()
    if m is None:
        return False
    await db.delete(m)
    await db.commit()
    return True


async def _get_tags_for_question(db: AsyncSession, question_id: str) -> list[str]:
    """取 question 关联的所有 tag name 列表。"""
    rows = (await db.execute(
        select(QuestionTag.name)
        .join(QuestionTagMap, QuestionTagMap.tag_id == QuestionTag.id)
        .where(QuestionTagMap.question_id == question_id)
    )).scalars().all()
    return list(rows)


# ════════════════════════════════════════════════════════════
#  用户题内联笔记
# ════════════════════════════════════════════════════════════


async def get_user_note(
    db: AsyncSession, user_id: str, question_id: str
) -> Optional[dict]:
    n = (await db.execute(
        select(UserQuestionNote).where(
            UserQuestionNote.user_id == user_id,
            UserQuestionNote.question_id == question_id,
        )
    )).scalar_one_or_none()
    if n is None:
        return None
    return {
        "id": n.id,
        "content_md": n.content_md,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }


async def upsert_user_note(
    db: AsyncSession, user_id: str, question_id: str, content_md: str
) -> UserQuestionNote:
    n = (await db.execute(
        select(UserQuestionNote).where(
            UserQuestionNote.user_id == user_id,
            UserQuestionNote.question_id == question_id,
        )
    )).scalar_one_or_none()
    if n is None:
        n = UserQuestionNote(
            user_id=user_id, question_id=question_id, content_md=content_md,
        )
        db.add(n)
    else:
        n.content_md = content_md
        n.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(n)
    return n


async def _get_user_note(db: AsyncSession, user_id: str, question_id: str) -> Optional[dict]:
    return await get_user_note(db, user_id, question_id)