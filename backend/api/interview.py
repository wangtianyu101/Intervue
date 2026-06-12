import os
import tempfile
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from core.database import get_db
from core.dependencies import get_current_user
from models import User, Interview, Profile, QuestionRecord
from schemas.interview import InterviewStart, InterviewOut, QuestionRecordOut, AnswerSubmit
from agents.question_agent import question_engine
from agents.followup_agent import followup_engine
from agents.evaluate_agent import evaluate_agent
from services.interview_service import session_manager

logger = logging.getLogger("codemock")

router = APIRouter(prefix="/api/interviews", tags=["interviews"])


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
        question_id=None,  # seed data uses semantic IDs, not UUIDs
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
        except ImportError as e:
            logger.error(f"STT import failed: {e}")
            raise HTTPException(status_code=500, detail="STT engine not available")
        except Exception as e:
            logger.error(f"STT failed: {e}")
            text = ""

        return {"text": text.strip()}
    finally:
        os.unlink(tmp_path)


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
    try:
        from livekit import api
        token = api.AccessToken(
            api_key=settings.livekit_api_key or "devkey",
            api_secret=settings.livekit_api_secret or "devsecret",
        ).with_identity(data.participant_name).with_name(
            data.participant_name
        ).with_grants(
            api.VideoGrants(room_join=True, room=data.room_name)
        ).to_jwt()
        return {"token": token}
    except ImportError:
        return {"token": "dev_token_placeholder"}
