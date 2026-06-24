"""QA 服务 (Phase 1b-4 · /qa 路由对应)。

设计:
- 每个 QASession 是针对某道题的多轮对话
- LLM 用 DeepSeek V3 (通过 ChatOpenAI), prompt 注入题目上下文
- 历史消息存为 JSON (items 字段), 不分表 (避免小数据膨胀)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from models import QASession, Question, UserQuestion

log = logging.getLogger("codemock.qa")


# ════════════════════════════════════════════════════════════
#  LLM client (singleton, 懒初始化)
# ════════════════════════════════════════════════════════════

_llm: Optional[ChatOpenAI] = None


def _get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=0.3,
        )
    return _llm


# ════════════════════════════════════════════════════════════
#  QASession CRUD
# ════════════════════════════════════════════════════════════


async def list_qa_sessions(
    db: AsyncSession, user_id: str, limit: int = 50
) -> dict:
    rows = (await db.execute(
        select(QASession).where(QASession.user_id == user_id)
        .order_by(QASession.created_at.desc()).limit(limit)
    )).scalars().all()
    return {
        "items": [
            {
                "id": s.id,
                "question_id": s.question_id,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "message_count": len(s.messages or []),
            }
            for s in rows
        ]
    }


async def get_qa_session(
    db: AsyncSession, user_id: str, session_id: str
) -> Optional[QASession]:
    s = await db.get(QASession, session_id)
    if s is None or s.user_id != user_id:
        return None
    return s


async def create_qa_session(
    db: AsyncSession, user_id: str, question_id: str
) -> QASession:
    s = QASession(
        user_id=user_id,
        question_id=question_id,
        messages=[],
        created_at=datetime.now(timezone.utc),
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def delete_qa_session(
    db: AsyncSession, user_id: str, session_id: str
) -> bool:
    s = await db.get(QASession, session_id)
    if s is None or s.user_id != user_id:
        return False
    await db.delete(s)
    await db.commit()
    return True


# ════════════════════════════════════════════════════════════
#  Chat (LLM 调用核心)
# ════════════════════════════════════════════════════════════


def _build_system_prompt(question_text: str, key_points: list, source: str = "seed") -> str:
    """构造 system prompt, 注入题目上下文。"""
    kp = "\n".join(f"- {p}" for p in (key_points or []))
    return f"""你是一位资深技术面试官，正在和候选人讨论一道题目。

## 题目
{question_text}

## 参考答案要点
{kp if kp else '(无标准答案, 由你根据经验给出)'}

## 你的角色
- 候选人会向你提问关于这道题的任何疑问 (概念、实现、追问、举一反三 等)
- 你应该像 1v1 模拟面试官一样回答：直接、准确、有深度
- 不要复述题目，直接答疑问
- 如果候选人回答了某个要点, 你应该追问深挖

## 输出格式
- 用 Markdown, 必要时用代码块
- 中文回答
- 单次回答控制在 200-400 字, 除非候选人明确要详细
"""


async def _get_question_context(db: AsyncSession, question_id: str) -> Optional[dict]:
    """取题目上下文 (text + key_points)。"""
    q_row = await db.get(Question, question_id)
    if q_row is not None:
        return {
            "text": q_row.question_text,
            "key_points": q_row.answer_key_points or [],
        }
    u_row = await db.get(UserQuestion, question_id)
    if u_row is not None:
        return {
            "text": u_row.question_text,
            "key_points": [u_row.answer] if u_row.answer else [],
        }
    return None


async def chat_qa(
    db: AsyncSession,
    user_id: str,
    question_id: str,
    message: str,
    session_id: Optional[str] = None,
) -> dict:
    """用户向 LLM 提问关于 question_id 的问题。

    - session_id 为空 → 新建 session
    - 否则追加消息并调 LLM

    Returns:
        {"session_id": str, "reply": str, "messages": [...]}
    """
    # 1) 取题目上下文
    ctx = await _get_question_context(db, question_id)
    if ctx is None:
        return {
            "session_id": None,
            "reply": "题目不存在或已被删除",
            "messages": [],
        }

    # 2) 取/创建 session
    if session_id:
        s = await db.get(QASession, session_id)
        if s is None or s.user_id != user_id:
            return {
                "session_id": None,
                "reply": "Session 不存在或无权限",
                "messages": [],
            }
    else:
        s = await create_qa_session(db, user_id, question_id)

    # 3) 追加 user message
    messages = list(s.messages or [])
    messages.append({
        "role": "user",
        "content": message,
        "ts": datetime.now(timezone.utc).isoformat(),
    })

    # 4) 构造 LLM messages
    sys_prompt = _build_system_prompt(ctx["text"], ctx["key_points"])
    llm_messages = [SystemMessage(content=sys_prompt)]
    # 历史消息 (最近 10 轮)
    for m in messages[-20:]:
        if m["role"] == "user":
            llm_messages.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            from langchain_core.messages import AIMessage
            llm_messages.append(AIMessage(content=m["content"]))

    # 5) 调 LLM
    try:
        resp = await _get_llm().ainvoke(llm_messages)
        reply = resp.content if hasattr(resp, "content") else str(resp)
    except Exception as e:
        log.warning(f"QA LLM call failed: {e}")
        reply = f"⚠️ LLM 调用失败 ({type(e).__name__}): {str(e)[:200]}"

    # 6) 追加 assistant message
    messages.append({
        "role": "assistant",
        "content": reply,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    s.messages = messages
    await db.commit()
    await db.refresh(s)

    return {
        "session_id": s.id,
        "reply": reply,
        "messages": messages,
    }