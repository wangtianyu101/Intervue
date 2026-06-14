"""LiveKit Agent Worker — V2: real-time phone-call interview.

Audio flow:
  User mic → LiveKit → Silero VAD → Streaming STT
  → Agent logic → Persona wrap → Piper TTS → User speaker

Uses livekit-agents v1.6+ Agent class (VoicePipelineAgent was removed).
"""

import asyncio
import logging
import re
from typing import AsyncIterable, Optional

from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli
from livekit.agents.llm import ChatContext, ChatMessage
from livekit.agents.voice import Agent
from livekit.plugins import silero

from core.config import settings
from agents.states import create_initial_state
from agents.question_agent import question_engine
from agents.followup_agent import followup_engine
from voice.turn_manager import TurnManager
from voice.persona import InterviewerPersona

logger = logging.getLogger("codemock-voice")


# ── STT ────────────────────────────────────────────────────

class LocalSTT:
    def __init__(self):
        self._whisper_client = None
        self._simple_stt = None

    async def _ensure_whisper(self):
        if self._whisper_client is not None: return
        try:
            from voice.stt import WhisperLiveClient
            self._whisper_client = WhisperLiveClient()
            await self._whisper_client.connect()
            logger.info("WhisperLive connected")
        except Exception as e:
            logger.warning(f"WhisperLive unavailable: {e}")
            self._whisper_client = None

    async def recognize(self, *, audio: bytes) -> str:
        if not audio or len(audio) < 160: return ""
        if self._whisper_client:
            try:
                await self._whisper_client.send_audio(audio)
                return await self._whisper_client.receive_transcript() or ""
            except Exception: pass
        if self._simple_stt is None:
            from voice.stt import SimpleSTT
            self._simple_stt = SimpleSTT()
        try: return self._simple_stt.transcribe_bytes(audio) or ""
        except Exception as e:
            logger.warning(f"STT error: {e}")
            return ""

    async def aclose(self):
        if self._whisper_client:
            try: await self._whisper_client.close()
            except Exception: pass


# ── TTS ────────────────────────────────────────────────────

class LocalTTS:
    def __init__(self):
        self._engine = None

    def _ensure(self):
        if self._engine is not None: return
        try:
            from voice.tts import TTSEngine
            self._engine = TTSEngine()
            logger.info("Piper TTS loaded")
        except Exception as e:
            logger.warning(f"TTS unavailable: {e}")
            self._engine = None

    def synthesize(self, *, text: str) -> bytes:
        self._ensure()
        if self._engine is None: return b""
        try: return self._engine.synthesize(text)
        except Exception as e:
            logger.warning(f"TTS error: {e}")
            return b""


# ═══════════════════════════════════════════════════════════
# Interview Agent
# ═══════════════════════════════════════════════════════════

class InterviewAgentV2(Agent):
    """V2: Full-duplex interview with turn management and persona."""

    def __init__(self, ctx: JobContext):
        super().__init__(
            vad=silero.VAD.load(),
            stt=LocalSTT(),
            tts=LocalTTS(),
        )
        self.ctx = ctx
        self.turn = TurnManager()
        self.persona = InterviewerPersona(name="Alex")
        self.state = None
        self.profile = {
            "tech_stack": ["LangChain", "LangGraph", "RAG"],
            "years_of_exp": 3,
            "current_level": "mid",
        }
        self._done = asyncio.Event()

    async def on_enter(self):
        await self.ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
        self.state = create_initial_state(
            user_id="voice_user", profile=self.profile, round="round1",
        )
        greeting = self.persona.greeting(self.profile["tech_stack"])
        self.turn.ai_started_speaking()
        await self.say(greeting, allow_interruptions=True)
        self.turn.ai_stopped_speaking()

    async def on_user_message(self, text: str):
        """Handle transcribed user speech."""
        if not text.strip(): return

        phase = self.state.get("interview_phase", "intro") if self.state else "intro"
        response = await (self._handle_intro(text) if phase == "intro" else self._handle_answer(text))

        self.turn.ai_started_speaking()
        await self.say(response, allow_interruptions=True)
        self.turn.ai_stopped_speaking()

    async def _handle_intro(self, text: str) -> str:
        keywords = ["langchain","langgraph","rag","python","go","java","react","vue","k8s","docker","agent","llm","spring"]
        found = [t for t in keywords if t.lower() in text.lower()]
        if found: self.profile["tech_stack"] = list(set(found))
        next_q = question_engine.select_next_question(
            round="round1", profile=self.profile, questions_asked=[], blind_spots=[])
        if next_q:
            self.state["current_question"] = next_q
            self.state["current_question_id"] = next_q["id"]
            self.state["interview_phase"] = "questioning"
            return self.persona.wrap({"action":"next_question","question_text":next_q["question_text"]})
        return "请简单说一下你对 Agent 架构的理解？"

    async def _handle_answer(self, text: str) -> str:
        self.state["user_answer"] = text
        q = self.state.get("current_question", {})
        result = await followup_engine.determine_action(
            question=q, user_answer=text,
            current_depth=self.state.get("current_depth",0),
            followup_count=self.state.get("followup_count",0), max_depth=4)
        action = result.get("action","next_question")

        if action == "skip_and_record":
            self.state["blind_spots"] = self.state.get("blind_spots",[]) + [result.get("blind_spot","")]
            nq = question_engine.select_next_question(
                round=self.state.get("round","round1"), profile=self.profile,
                questions_asked=self.state.get("questions_asked",[]),
                blind_spots=self.state.get("blind_spots",[]))
            if nq:
                self.state["current_question"] = nq; self.state["current_question_id"] = nq["id"]
                self.state["current_depth"] = 0; self.state["followup_count"] = 0
                return self.persona.wrap({"action":"next_question","question_text":nq["question_text"]})
            self.state["interview_phase"] = "done"; return self.persona.closing()
        elif action in ("followup","probe","give_hint","degrade"):
            self.state["current_depth"] = self.state.get("current_depth",0) + 1
            self.state["followup_count"] = self.state.get("followup_count",0) + 1
            return self.persona.wrap({"action":"probe","followup_text":result.get("followup_text","能再详细说说吗？")})
        else:
            nq = question_engine.select_next_question(
                round=self.state.get("round","round1"), profile=self.profile,
                questions_asked=self.state.get("questions_asked",[]),
                blind_spots=self.state.get("blind_spots",[]))
            if nq:
                self.state["current_question"] = nq; self.state["current_question_id"] = nq["id"]
                self.state["current_depth"] = 0; self.state["followup_count"] = 0
                return self.persona.wrap({"action":"next_question","question_text":nq["question_text"]})
            self.state["interview_phase"] = "done"; return self.persona.closing()


def entrypoint(ctx: JobContext):
    agent = InterviewAgentV2(ctx)
    agent.start(ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
