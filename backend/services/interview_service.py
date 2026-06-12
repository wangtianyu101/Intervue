"""Interview Session Manager — wraps LangGraph state graph for REST API use.

Session state is stored in memory for fast access and persisted to the
interviews.state_snapshot column for durability across restarts.

Persistence flow:
  - After each state mutation (next-question, answer), the API handler
    calls save_state() to write the snapshot to MySQL.
  - On _get_session() miss, restore_from_db() rebuilds the in-memory session
    from the saved snapshot.
"""

import json
import logging
from typing import Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Interview

from agents.states import InterviewState, create_initial_state
from agents.question_agent import question_engine
from agents.followup_agent import followup_engine
from agents.evaluate_agent import evaluate_agent
from agents.interview_graph import build_interview_graph

logger = logging.getLogger("codemock")


class InterviewSessionManager:
    """Manages interview sessions backed by the LangGraph state graph.

    Each session maintains a compiled graph instance with MemorySaver checkpointing.
    State is mirrored to interviews.state_snapshot for persistence.
    """

    def __init__(self):
        self._sessions: dict[str, dict] = {}

    # ── Public API ──────────────────────────────────────────────

    def create_session(
        self,
        user_id: str,
        profile: dict,
        round: str = "round1",
        style: str = "standard",
        session_id: str | None = None,
    ) -> str:
        """Create a new interview session and return its session ID."""
        if session_id is None:
            session_id = str(uuid4())

        initial_state = create_initial_state(
            user_id=user_id,
            profile=profile,
            round=round,
            style=style,
        )

        graph = build_interview_graph()
        config = {"configurable": {"thread_id": session_id}}

        self._sessions[session_id] = {
            "graph": graph,
            "config": config,
            "state": dict(initial_state),
        }

        logger.info(f"Created interview session {session_id} for user {user_id}")
        return session_id

    def get_next_question(self, session_id: str) -> Optional[dict]:
        """Get the next question for the session using the question engine.

        Returns None if no more questions are available.
        """
        session = self._get_session(session_id)
        state = session["state"]

        next_q = question_engine.select_next_question(
            round=state["round"],
            profile=state["profile"],
            questions_asked=state.get("questions_asked", []),
            blind_spots=state.get("blind_spots", []),
            current_topic=state.get("current_topic"),
        )

        if not next_q:
            state["interview_phase"] = "done"
            state["should_end"] = True
            return None

        # Update state with selected question
        state["current_question_id"] = next_q["id"]
        state["current_question"] = next_q
        state["current_topic"] = next_q.get("topic", "")
        state["current_depth"] = 0
        state["followup_count"] = 0
        state["interview_phase"] = "questioning"

        asked_ids = state.get("questions_asked", [])
        if next_q["id"] not in asked_ids:
            state["questions_asked"] = asked_ids + [next_q["id"]]

        return next_q

    async def process_answer(self, session_id: str, user_answer: str) -> dict:
        """Process a user answer through the followup and evaluation engines.

        Returns a dict with: action, followup_text, has_followup, score, feedback, blind_spots.
        """
        session = self._get_session(session_id)
        state = session["state"]

        state["user_answer"] = user_answer

        current_question = state.get("current_question", {})

        # Run through followup engine
        followup_result = await followup_engine.determine_action(
            question=current_question,
            user_answer=user_answer,
            current_depth=state.get("current_depth", 0),
            followup_count=state.get("followup_count", 0),
            max_depth=state.get("max_followup_depth", 4),
        )

        # Evaluate the answer
        evaluation = await evaluate_agent.evaluate_answer(
            question_text=current_question.get("question_text", ""),
            answer_key_points=current_question.get("answer_key_points", []),
            user_answer=user_answer,
            topic=current_question.get("topic", ""),
            sub_topic=current_question.get("sub_topic", ""),
        )

        action = followup_result.get("action", "next_question")

        # Update state based on action
        if action == "skip_and_record":
            blind_spot = followup_result.get("blind_spot", "")
            if blind_spot:
                state["blind_spots"] = state.get("blind_spots", []) + [blind_spot]
            state["interview_phase"] = "questioning"

        elif action in ("followup", "probe", "give_hint", "degrade"):
            state["current_depth"] = state.get("current_depth", 0) + 1
            state["followup_count"] = state.get("followup_count", 0) + 1
            state["interview_phase"] = "following_up"

        else:
            state["interview_phase"] = "questioning"

        return {
            "action": action,
            "followup_text": followup_result.get("followup_text", ""),
            "has_followup": action in ("followup", "probe", "give_hint", "degrade"),
            "score": evaluation.get("score", 3),
            "feedback": evaluation.get("feedback", ""),
            "blind_spots": evaluation.get("blind_spots", []),
        }

    def get_state(self, session_id: str) -> dict:
        """Get current interview state."""
        session = self._get_session(session_id)
        return dict(session["state"])

    def is_complete(self, session_id: str) -> bool:
        """Check if the interview is complete."""
        session = self._get_session(session_id)
        return session["state"].get("interview_phase") == "done"

    # ── Persistence ─────────────────────────────────────────────

    async def save_state(self, session_id: str, db: AsyncSession) -> None:
        """Persist current session state to the interviews row."""
        if session_id not in self._sessions:
            return
        state = self._sessions[session_id]["state"]
        result = await db.execute(
            select(Interview).where(Interview.id == session_id)
        )
        interview = result.scalar_one_or_none()
        if interview is not None:
            # Serialize state, excluding non-JSON-safe objects (graph, complex types)
            clean = _serializable_state(state)
            interview.state_snapshot = clean
            await db.commit()
            logger.debug(f"Saved state snapshot for session {session_id}")

    async def restore_from_db(self, session_id: str, db: AsyncSession) -> bool:
        """Try to restore a session from the database. Returns True on success."""
        result = await db.execute(
            select(Interview).where(Interview.id == session_id)
        )
        interview = result.scalar_one_or_none()
        if interview is None or not interview.state_snapshot:
            return False

        snapshot = interview.state_snapshot
        if not snapshot or not isinstance(snapshot, dict):
            return False

        # Rebuild session from snapshot, with fresh graph
        restored_state = dict(snapshot)
        graph = build_interview_graph()
        config = {"configurable": {"thread_id": session_id}}

        self._sessions[session_id] = {
            "graph": graph,
            "config": config,
            "state": restored_state,
        }
        logger.info(f"Restored session {session_id} from database snapshot")
        return True

    # ── Internals ───────────────────────────────────────────────

    def _get_session(self, session_id: str) -> dict:
        """Get or raise for a session. Use _get_or_restore for DB-backed lookup."""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not found")
        return self._sessions[session_id]


def _serializable_state(state: dict) -> dict:
    """Return a JSON-serializable shallow copy of the state dict.

    Strips non-serializable values (e.g. PIL images, file handles) which
    should never appear in InterviewState but are guarded against.
    """
    clean = {}
    for key, value in state.items():
        try:
            json.dumps(value)
            clean[key] = value
        except (TypeError, ValueError):
            # Skip non-serializable values — they will be regenerated
            logger.debug(f"Skipping non-serializable state key: {key}")
    return clean


# Singleton
session_manager = InterviewSessionManager()
