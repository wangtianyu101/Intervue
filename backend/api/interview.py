import os
import subprocess
import tempfile
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from core.config import settings
from core.database import get_db
from core.dependencies import get_current_user
from models import User, Interview, Profile, QuestionRecord
from schemas.interview import InterviewStart, InterviewOut, QuestionRecordOut, AnswerSubmit
from agents.question_agent import question_engine
from agents.followup_agent import followup_engine
from agents.evaluate_agent import evaluate_agent
from services.interview_service import session_manager
from agents.states import create_initial_state

logger = logging.getLogger("codemock")

router = APIRouter(prefix="/api/interviews", tags=["interviews"])

# Tracks LiveKit voice worker processes by interview_id. Populated by
# _start_voice_worker (called when a client uses the LiveKit path), drained by
# _stop_voice_worker (called from /complete). The WebSocket path doesn't spawn
# workers, so the dict stays empty for WS-only users.
_livekit_workers: dict[str, "subprocess.Popen"] = {}


def _start_voice_worker(interview_id: str):
    """Spawn voice worker process for the given interview room (fire-and-forget)."""
    import sys
    env = {
        **os.environ,
        "LIVEKIT_ROOM": f"interview-{interview_id}",
        "LIVEKIT_URL": settings.livekit_url,
        "LIVEKIT_API_KEY": settings.livekit_api_key,
        "LIVEKIT_API_SECRET": settings.livekit_api_secret,
        "PYTHONPATH": os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    }
    logfile = open(f"/tmp/voice-worker-{interview_id[:8]}.log", "a")
    proc = subprocess.Popen(
        [sys.executable, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "voice", "interview_room.py")],
        env=env,
        stdout=logfile,
        stderr=logfile,
    )
    _livekit_workers[interview_id] = proc


def _stop_voice_worker(interview_id: str) -> bool:
    """Kill the LiveKit worker for an interview, if one is running.

    Returns True if a process was found and signaled, False otherwise.
    Idempotent — safe to call multiple times.
    """
    proc = _livekit_workers.pop(interview_id, None)
    if proc is None:
        return False
    try:
        proc.terminate()
        try:
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2.0)
    except Exception as e:
        logger.warning(f"kill voice worker {interview_id} failed: {e}")
    return True


def _search_clause(q: str):
    """Build a SQLAlchemy WHERE expression for the search filter.

    Matches if ANY of:
      - any QuestionRecord.question_text LIKE %q%
      - any QuestionRecord.user_answer LIKE %q%
      - Interview.round LIKE %q%
      - Interview.style LIKE %q%

    `%` and `_` in `q` are escaped so users can search for literal
    patterns. Empty `q` returns None (caller should skip the filter).
    """
    from sqlalchemy import literal
    if not q:
        return None
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    like = f"%{escaped}%"
    record_match_subq = (
        select(QuestionRecord.interview_id)
        .where(QuestionRecord.question_text.like(literal(like), escape="\\"))
        .union(
            select(QuestionRecord.interview_id).where(
                QuestionRecord.user_answer.like(literal(like), escape="\\"),
            )
        )
    )
    return (
        Interview.id.in_(record_match_subq)
        | Interview.round.like(literal(like), escape="\\")
        | Interview.style.like(literal(like), escape="\\")
    )


@router.get("")
async def list_interviews(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status: str = "",
    topic: str = "",
    favorites: bool = False,
    q: str = "",
    page: int = 1,
    size: int = 20,
):
    """List user's interviews with optional filters and pagination.

    `favorites=true` returns only bookmarked interviews (independent of
    status). Soft-deleted interviews (deleted_at IS NOT NULL) are always
    excluded. `q` does a case-insensitive LIKE across question text, user
    answers, round, and style. Empty `q` skips the search filter entirely.
    """
    base = [
        Interview.user_id == user.id,
        Interview.deleted_at.is_(None),
    ]

    query = select(Interview).where(*base)
    count_q = select(func.count()).select_from(Interview).where(*base)
    if status:
        query = query.where(Interview.status == status)
        count_q = count_q.where(Interview.status == status)
    if favorites:
        query = query.where(Interview.is_favorite.is_(True))
        count_q = count_q.where(Interview.is_favorite.is_(True))
    search = _search_clause(q)
    if search is not None:
        query = query.where(search)
        count_q = count_q.where(search)

    query = query.order_by(Interview.started_at.desc()).offset((page - 1) * size).limit(size)

    result = await db.execute(query)
    interviews = result.scalars().all()
    total = (await db.execute(count_q)).scalar() or 0

    items = []
    for iv in interviews:
        items.append({
            "id": iv.id,
            "round": iv.round,
            "style": iv.style,
            "status": iv.status,
            "total_questions": iv.total_questions,
            "overall_score": iv.overall_score,
            "is_favorite": iv.is_favorite,
            "started_at": iv.started_at.isoformat() if iv.started_at else None,
            "ended_at": iv.ended_at.isoformat() if iv.ended_at else None,
        })

    return {"items": items, "total": total, "page": page, "size": size}


@router.post("/{interview_id}/favorite")
async def toggle_favorite(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle the is_favorite flag. Returns the new value.

    Note: this endpoint does NOT filter deleted_at in the WHERE clause,
    because the soft-delete state carries its own semantic — 410 Gone —
    distinct from 404. Other action endpoints (next-question, complete,
    voice/respond) filter deleted rows and return 404 to make "deleted"
    indistinguishable from "never existed", which is the safer default
    for write paths.
    """
    result = await db.execute(
        select(Interview).where(Interview.id == str(interview_id))
    )
    interview = result.scalar_one_or_none()
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    if interview.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your interview")
    if interview.deleted_at is not None:
        raise HTTPException(status_code=410, detail="Interview was deleted")

    interview.is_favorite = not bool(interview.is_favorite)
    await db.commit()
    await db.refresh(interview)

    return {
        "interview_id": str(interview.id),
        "is_favorite": interview.is_favorite,
    }


@router.delete("/{interview_id}")
async def soft_delete_interview(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete: set deleted_at, keep the row for audit / undo.

    Idempotent — re-deleting an already-deleted interview is a no-op (200
    with already_deleted=True) rather than a 404, so client retries don't
    surface confusing errors. Like /favorite, this endpoint does NOT
    filter deleted_at in the WHERE clause so the idempotency check works.
    """
    from datetime import datetime, timezone
    result = await db.execute(
        select(Interview).where(Interview.id == str(interview_id))
    )
    interview = result.scalar_one_or_none()
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    if interview.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your interview")

    was_already = interview.deleted_at is not None
    if not was_already:
        interview.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(interview)

    return {
        "interview_id": str(interview.id),
        "deleted": True,
        "already_deleted": was_already,
        "deleted_at": interview.deleted_at.isoformat() if interview.deleted_at else None,
    }


@router.post("", response_model=InterviewOut)
async def start_interview(
    data: InterviewStart,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Profile).where(Profile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=400, detail="Profile not found")

    # Dedup: if this user already has an in_progress interview for the same
    # (round, style), return it instead of creating a new one. Prevents the
    # double/triple POST pattern from React StrictMode + double-mount + room
    # page ignoring the `?id=` query param.
    existing = await db.execute(
        select(Interview)
        .where(
            Interview.user_id == user.id,
            Interview.round == data.round,
            Interview.style == data.style,
            Interview.status == "in_progress",
            Interview.deleted_at.is_(None),
        )
        .order_by(Interview.started_at.desc())
        .limit(1)
    )
    existing_iv = existing.scalar_one_or_none()
    if existing_iv is not None:
        return existing_iv

    interview = Interview(
        user_id=user.id,
        profile_id=profile.id,
        round=data.round,
        style=data.style,
        status="in_progress",
    )
    db.add(interview)
    await db.commit()
    await db.refresh(interview)

    # Create LangGraph-backed interview session tied to this interview
    profile_dict = {
        "tech_stack": profile.tech_stack if profile else [],
        "years_of_exp": profile.years_of_exp if profile else 0,
        "current_level": profile.current_level if profile else "mid",
    }
    sid = session_manager.create_session(
        user_id=user.id,
        profile=profile_dict,
        round=data.round,
        style=data.style,
        session_id=str(interview.id),
    )
    # Persist initial state to DB
    try:
        await session_manager.save_state(sid, db)
    except Exception:
        pass  # best-effort: session still works in memory

    # Start voice worker for this room (fire-and-forget)
    try:
        _start_voice_worker(str(interview.id))
    except Exception:
        pass

    return interview


@router.get("/{interview_id}", response_model=InterviewOut)
async def get_interview(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Interview).where(
            Interview.id == str(interview_id),
            Interview.user_id == user.id,
            Interview.deleted_at.is_(None),
        )
    )
    interview = result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    return interview


@router.get("/{interview_id}/records", response_model=list[QuestionRecordOut])
async def get_question_records(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(QuestionRecord).where(QuestionRecord.interview_id == str(interview_id))
    )
    records = result.scalars().all()
    return records


@router.post("/{interview_id}/next-question")
async def get_next_question(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the next question using the Agent question engine."""
    interview_result = await db.execute(
        select(Interview).where(
            Interview.id == str(interview_id),
            Interview.user_id == user.id,
            Interview.deleted_at.is_(None),
        )
    )
    interview = interview_result.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    # Get profile for context (used in fallback session creation)
    profile_result = await db.execute(
        select(Profile).where(Profile.user_id == user.id)
    )
    profile = profile_result.scalar_one_or_none()

    # Use session manager (LangGraph-backed) to select next question
    sid = str(interview_id)
    try:
        next_q = session_manager.get_next_question(sid)
    except ValueError:
        # Session not found — try DB restore, then recreate
        restored = await session_manager.restore_from_db(sid, db)
        if restored:
            next_q = session_manager.get_next_question(sid)
        else:
            profile_dict = {
                "tech_stack": profile.tech_stack if profile else [],
                "years_of_exp": profile.years_of_exp if profile else 0,
                "current_level": profile.current_level if profile else "mid",
            }
            session_manager.create_session(
                user_id=user.id,
                profile=profile_dict,
                round=interview.round,
                style=interview.style,
                session_id=sid,
            )
            next_q = session_manager.get_next_question(sid)

    if not next_q:
        # Mark interview as complete
        interview.status = "completed"
        await db.commit()
        raise HTTPException(status_code=404, detail="No more questions available")

    # Persist state after question selection
    try:
        await session_manager.save_state(sid, db)
    except Exception:
        pass

    question_text = next_q["question_text"]

    record = QuestionRecord(
        interview_id=str(interview_id),
        question_id=next_q.get("id"),  # semantic ID like "agent_001" — not a UUID
        question_text=question_text,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    state = session_manager.get_state(str(interview_id))
    asked_count = len(state.get("questions_asked", []))

    return {
        "record_id": str(record.id),
        "question_id": next_q["id"],
        "question_text": question_text,
        "topic": next_q.get("topic", ""),
        "sub_topic": next_q.get("sub_topic", ""),
        "followup_tree": next_q.get("followup_tree", {}),
        "asked_count": asked_count,
    }


@router.post("/{interview_id}/complete")
async def complete_interview(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """User-initiated end of interview. Idempotent — already-completed returns 200.

    Differs from the auto-complete path inside /next-question (which fires when
    the question pool is exhausted): this is called from the UI when the user
    clicks "结束面试" before running out of questions.
    """
    from datetime import datetime, timezone

    result = await db.execute(
        select(Interview).where(
            Interview.id == str(interview_id),
            Interview.deleted_at.is_(None),
        )
    )
    interview = result.scalar_one_or_none()
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    if interview.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your interview")

    was_already = interview.status == "completed"
    if not was_already:
        interview.status = "completed"
        interview.ended_at = datetime.now(timezone.utc)

        # ── Compute overall_score from QuestionRecord.score average ──
        # Replaces the stub of "always 3". Only counts scored records
        # (intro phase doesn't produce a QuestionRecord; skip_and_record
        # follows the same /voice/respond path so it does).
        score_q = await db.execute(
            select(func.avg(QuestionRecord.score)).where(
                QuestionRecord.interview_id == str(interview_id),
                QuestionRecord.score.is_not(None),
            )
        )
        avg = score_q.scalar()
        if avg is not None:
            interview.overall_score = round(float(avg), 2)

        # ── Compute total_questions: distinct non-null question_ids ──
        # Single source of truth: the records we already persisted. Counts
        # distinct questions (a Q with N followups = 1, not N+1). NULL
        # question_id is excluded — those are edge-case records created
        # before a real question was selected.
        count_q = await db.execute(
            select(func.count(func.distinct(QuestionRecord.question_id))).where(
                QuestionRecord.interview_id == str(interview_id),
                QuestionRecord.question_id.is_not(None),
            )
        )
        total = count_q.scalar() or 0
        if total > 0:
            interview.total_questions = total

        await db.commit()
        await db.refresh(interview)

        # Best-effort: kill the LiveKit worker if one was started for this
        # interview. The WS path doesn't spawn one, so this is a no-op for
        # WS users. We don't fail /complete on cleanup errors.
        try:
            _stop_voice_worker(str(interview_id))
        except Exception as e:
            logger.warning(f"stop_voice_worker failed for {interview_id}: {e}")

    return {
        "status": "completed",
        "already_completed": was_already,
        "interview_id": str(interview.id),
        "ended_at": interview.ended_at.isoformat() if interview.ended_at else None,
        "overall_score": interview.overall_score,
        "total_questions": interview.total_questions,
    }


@router.post("/records/{record_id}/answer")
async def submit_answer(
    record_id: UUID,
    data: AnswerSubmit,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit answer. Agent evaluates it and determines followup or next question."""
    result = await db.execute(
        select(QuestionRecord).where(QuestionRecord.id == str(record_id))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    # Save the answer
    record.user_answer = data.user_answer
    record.time_spent = data.time_spent

    # Get interview_id from the record for session lookup
    interview_id = record.interview_id

    # Process answer through session manager (LangGraph-backed)
    try:
        processed = await session_manager.process_answer(interview_id, data.user_answer)
    except ValueError:
        # Session not found — try DB restore, then fall back to direct agent calls
        restored = await session_manager.restore_from_db(interview_id, db)
        if restored:
            processed = await session_manager.process_answer(interview_id, data.user_answer)
        else:
            from services.seed_service import get_question_by_id
            question_data = get_question_by_id(str(record.question_id)) if record.question_id else None
            if not question_data:
                question_data = {
                    "id": str(record.question_id) if record.question_id else "seed_fallback",
                    "question_text": record.question_text,
                    "topic": "",
                    "sub_topic": "",
                    "answer_key_points": [],
                    "followup_tree": {},
                }

            followup_result = await followup_engine.determine_action(
                question=question_data,
                user_answer=data.user_answer,
                current_depth=0,
                followup_count=0,
                max_depth=4,
            )

            evaluation = await evaluate_agent.evaluate_answer(
                question_text=record.question_text,
                answer_key_points=question_data.get("answer_key_points", []),
                user_answer=data.user_answer,
                topic=question_data.get("topic", ""),
                sub_topic=question_data.get("sub_topic", ""),
            )

            processed = {
                "score": evaluation.get("score", 3),
                "feedback": evaluation.get("feedback", ""),
                "blind_spots": evaluation.get("blind_spots", []),
                "action": followup_result.get("action", "next_question"),
                "followup_text": followup_result.get("followup_text", ""),
                "has_followup": followup_result.get("action") in ("followup", "probe", "give_hint", "degrade"),
            }

    # Persist session state after answer processing
    try:
        await session_manager.save_state(interview_id, db)
    except Exception:
        pass

    # Update record with evaluation
    record.score = processed.get("score", 3)
    record.blind_spots = processed.get("blind_spots", [])

    await db.commit()

    return {
        "status": "ok",
        "record_id": str(record_id),
        "score": processed.get("score", 3),
        "feedback": processed.get("feedback", ""),
        "blind_spots": processed.get("blind_spots", []),
        "action": processed.get("action", "next_question"),
        "followup_text": processed.get("followup_text", ""),
        "has_followup": processed.get("has_followup", False),
    }


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Transcribe uploaded audio (webm/wav) to text using local Whisper."""
    ct = file.content_type or ""
    if ct and not ct.startswith("audio/"):
        raise HTTPException(status_code=400, detail=f"Not an audio file: {ct}")

    suffix = ".webm"
    if file.filename and file.filename.endswith(".wav"):
        suffix = ".wav"
    elif file.content_type == "audio/wav":
        suffix = ".wav"

    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)

        try:
            from voice.stt import DashScopeSTT
            stt = DashScopeSTT()
            text = stt.transcribe_file(tmp_path)
        except ImportError:
            try:
                from voice.stt import SimpleSTT
                text = SimpleSTT().transcribe_file(tmp_path)
            except ImportError as e:
                logger.error(f"STT import failed: {e}")
                raise HTTPException(status_code=500, detail="STT engine not available")
        except Exception as e:
            logger.error(f"STT failed: {e}")
            text = ""

        return {"text": text.strip()}
    finally:
        os.unlink(tmp_path)


class VoiceRespondRequest(BaseModel):
    interview_id: str
    user_answer: str


@router.post("/voice/respond")
async def voice_respond(
    data: VoiceRespondRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Browser SpeechRecognition → backend interview agent → text response."""
    from voice.persona import InterviewerPersona
    persona = InterviewerPersona(name="Alex")

    # Try session manager first for stateful interview
    try:
        state = session_manager.get_state(data.interview_id)
        phase = state.get("interview_phase", "intro")
    except Exception:
        phase = "intro"
        state = create_initial_state(
            user_id=user.id,
            profile={"tech_stack": ["LangChain", "LangGraph", "RAG"], "years_of_exp": 3, "current_level": "mid"},
            round="round1",
        )

    if phase == "intro":
        keywords = ["langchain","langgraph","rag","python","go","java","k8s","docker","agent","llm","spring","react","vue"]
        found = [t for t in keywords if t.lower() in data.user_answer.lower()]
        if found:
            state["profile"]["tech_stack"] = list(set(found))
        next_q = question_engine.select_next_question(
            round="round1", profile=state["profile"], questions_asked=[], blind_spots=[])
        if next_q:
            # Transition intro → questioning. Without these two writes (and the
            # matching session_manager.set_state below) every subsequent call
            # would loop back through the intro branch — never producing
            # followups or persisting QuestionRecord rows.
            state["current_question"] = next_q
            state["current_question_id"] = next_q.get("id")
            state["interview_phase"] = "questioning"
            session_manager.set_state(data.interview_id, state)
            response = persona.wrap({"action": "next_question", "question_text": next_q["question_text"]})
        else:
            response = persona.wrap({"action": "next_question", "question_text": "请简单说一下你对 AI Agent 架构的理解？"})
    else:
        state["user_answer"] = data.user_answer
        q = state.get("current_question", {})
        result = await followup_engine.determine_action(
            question=q, user_answer=data.user_answer,
            current_depth=state.get("current_depth", 0),
            followup_count=state.get("followup_count", 0), max_depth=4)
        action = result.get("action", "next_question")
        if action == "skip_and_record":
            nq = question_engine.select_next_question(
                round=state.get("round", "round1"), profile=state["profile"],
                questions_asked=state.get("questions_asked", []), blind_spots=state.get("blind_spots", []))
            response = persona.wrap({"action": "next_question", "question_text": nq["question_text"] if nq else "好的，我们继续。"})
        elif action in ("followup", "probe", "give_hint", "degrade"):
            response = persona.wrap({"action": "probe", "followup_text": result.get("followup_text", "能再详细说说吗？")})
        else:
            nq = question_engine.select_next_question(
                round=state.get("round", "round1"), profile=state["profile"],
                questions_asked=state.get("questions_asked", []), blind_spots=state.get("blind_spots", []))
            response = persona.wrap({"action": "next_question", "question_text": nq["question_text"] if nq else "面试结束！"})

        # ── Persist: find/create QuestionRecord, save answer + evaluation ──
        # Until now the WS path threw the answer away. Mirror what
        # /records/{id}/answer does on the HTTP path: write the user text,
        # run the evaluator, store score/blind_spots so the report + history
        # pages can show real data.
        try:
            question_id = str(q.get("id", "")) or None
            question_text = q.get("question_text", "") or ""

            # Find an existing record for this question (idempotent on retries)
            existing = None
            if question_id:
                qr = await db.execute(
                    select(QuestionRecord).where(
                        QuestionRecord.interview_id == data.interview_id,
                        QuestionRecord.question_id == question_id,
                    )
                )
                existing = qr.scalar_one_or_none()

            if existing is None:
                existing = QuestionRecord(
                    interview_id=data.interview_id,
                    question_id=question_id,
                    question_text=question_text,
                )
                db.add(existing)

            existing.user_answer = data.user_answer

            # Evaluate — only on the first answer for a question to avoid
            # re-scoring the same text every followup turn.
            if existing.score is None:
                evaluation = await evaluate_agent.evaluate_answer(
                    question_text=question_text,
                    answer_key_points=q.get("answer_key_points", []),
                    user_answer=data.user_answer,
                    topic=q.get("topic", ""),
                    sub_topic=q.get("sub_topic", ""),
                )
                existing.score = evaluation.get("score", 3)
                existing.blind_spots = evaluation.get("blind_spots", [])

            await db.commit()
        except Exception as e:
            # Persistence failure shouldn't break the live interview — just log
            logger.warning(f"voice_respond persist failed: {e}")
            await db.rollback()

        # Write the in-memory state back — `get_state` returned a shallow
        # copy, so the followup_agent-induced mutations (blind_spots,
        # current_depth, followup_count) would otherwise be discarded.
        # session_manager.set_state is the only safe write-back path.
        try:
            session_manager.set_state(data.interview_id, state)
        except Exception as e:
            logger.warning(f"voice_respond set_state failed: {e}")

    return {"response": response}


class LiveKitTokenRequest(BaseModel):
    room_name: str
    participant_name: str


@router.post("/livekit-token")
async def get_livekit_token(
    data: LiveKitTokenRequest,
    user: User = Depends(get_current_user),
):
    """Generate a LiveKit access token for joining a voice room."""
    from core.config import settings
    import time
    from jose import jwt

    api_key = settings.livekit_api_key or "devkey"
    api_secret = settings.livekit_api_secret or "devsecret"

    now = int(time.time())
    payload = {
        "iss": api_key,
        "sub": data.participant_name,
        "nbf": now,
        "exp": now + 3600 * 6,  # 6 hours
        "room": data.room_name,
        "name": data.participant_name,
        "video": {"roomJoin": True, "room": data.room_name, "canPublish": True, "canSubscribe": True},
    }
    token = jwt.encode(payload, api_secret, algorithm="HS256")
    return {"token": token}
