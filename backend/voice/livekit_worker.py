"""LiveKit Agent Worker — V2: real-time phone-call interview with TurnManager + Persona.

Audio flow:
  User mic → LiveKit Server → Silero VAD → TurnManager
  → Streaming STT (WhisperLive) → LangGraph Agent → Persona wrap
  → Piper TTS (sentence streaming) → LiveKit Server → User speaker
"""

import asyncio
import logging
import re
from typing import AsyncIterable, Optional

from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli
from livekit.agents.llm import ChatContext, ChatMessage
from livekit.agents.voice import VoicePipelineAgent
from livekit.plugins import silero

from core.config import settings
from agents.states import create_initial_state
from agents.question_agent import question_engine
from agents.followup_agent import followup_engine
from voice.turn_manager import TurnManager
from voice.persona import InterviewerPersona

logger = logging.getLogger("codemock-voice")


# ── STT Adapter ──────────────────────────────────────────────

class LocalSTT:
    """LiveKit STT adapter: WhisperLive streaming with SimpleSTT fallback."""

    def __init__(self):
        self._whisper_client = None
        self._simple_stt = None

    async def _ensure_whisper(self):
        if self._whisper_client is not None: return
        try:
            from voice.stt import WhisperLiveClient
            self._whisper_client = WhisperLiveClient()
            await self._whisper_client.connect()
            logger.info("WhisperLive STT connected")
        except Exception as e:
            logger.warning(f"WhisperLive unavailable ({e}), using SimpleSTT")
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
        try:
            return self._simple_stt.transcribe_bytes(audio) or ""
        except Exception as e:
            logger.warning(f"STT error: {e}")
            return ""

    async def aclose(self):
        if self._whisper_client:
            try: await self._whisper_client.close()
            except Exception: pass


# ── Streaming TTS Adapter ────────────────────────────────────

class StreamingLocalTTS:
    """TTS adapter: sentence-by-sentence streaming for low latency.

    Splits text at punctuation, synthesizes each sentence separately.
    First sentence latency ~300ms (vs ~3s for whole-text).
    """

    def __init__(self):
        self._engine = None
        self._sample_rate = 22050

    def _ensure_engine(self):
        if self._engine is not None: return
        try:
            from voice.tts import TTSEngine
            self._engine = TTSEngine()
            self._sample_rate = 22050
            logger.info("Piper TTS loaded (streaming mode)")
        except Exception as e:
            logger.warning(f"TTS unavailable: {e}")
            self._engine = None

    def synthesize(self, *, text: str) -> bytes:
        """Synthesize entire text (fallback for single sentences)."""
        self._ensure_engine()
        if self._engine is None: return b""
        try: return self._engine.synthesize(text)
        except Exception as e:
            logger.warning(f"TTS error: {e}")
            return b""

    async def synthesize_stream(self, text: str) -> AsyncIterable[bytes]:
        """Yield audio frames sentence by sentence."""
        self._ensure_engine()
        if self._engine is None: return

        # Split into sentences
        sentences = re.split(r'(?<=[。！？.!?\n])\s*', text)
        for sentence in sentences:
            s = sentence.strip()
            if not s: continue
            try:
                audio = self._engine.synthesize(s)
                if audio:
                    yield audio
            except Exception as e:
                logger.warning(f"TTS sentence error: {e}")


# ═══════════════════════════════════════════════════════════════
# V2: Real-time Interview Agent
# ═══════════════════════════════════════════════════════════════

class InterviewAgentV2(VoicePipelineAgent):
    """V2: Phone-call interview with turn management, persona, and streaming TTS."""

    def __init__(self, ctx: JobContext):
        stt = LocalSTT()
        tts = StreamingLocalTTS()

        super().__init__(
            vad=silero.VAD.load(
                min_speech_duration=0.3,
                min_silence_duration=0.8,
            ),
            stt=stt,
            tts=tts,
            chat_ctx=ChatContext(),
            allow_interruptions=True,
        )
        self.ctx = ctx
        self.turn = TurnManager(silence_ms=800)
        self.persona = InterviewerPersona(name="Alex")
        self.interview_state = None
        self.profile = {
            "tech_stack": ["LangChain", "LangGraph", "RAG"],
            "years_of_exp": 3,
            "current_level": "mid",
            "target_companies": [],
        }
        self._streaming_tts = tts

    async def on_enter(self):
        """User joined — greet and start."""
        await self.ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

        self.interview_state = create_initial_state(
            user_id="voice_user",
            profile=self.profile,
            round="round1",
        )

        greeting = self.persona.greeting(self.profile["tech_stack"])
        self.turn.ai_started_speaking()
        await self.say(greeting)
        self.turn.ai_stopped_speaking()

    async def on_user_speech_started(self):
        """VAD detects user talking."""
        action = self.turn.user_speech_started()
        if action == "interrupt":
            logger.info("AI interrupted — stopping speech")
        elif action == "cancel":
            logger.info("AI generation cancelled")

    async def on_user_speech_ended(self) -> Optional[str]:
        """VAD detects user finished — return AI reply."""
        action = self.turn.user_speech_ended()
        if action != "turn_ready":
            return None

        # Get STT transcription (already in the pipeline)
        # The user's text will come through on_user_message
        return None  # Let VoicePipelineAgent handle the STT→Agent→TTS pipeline

    async def on_user_message(self, text: str):
        """Handle transcribed user speech — core interview logic."""
        if not text.strip():
            return

        phase = (self.interview_state.get("interview_phase", "intro")
                 if self.interview_state else "intro")

        if phase == "intro":
            response = await self._handle_intro(text)
        elif phase in ("questioning", "following_up"):
            response = await self._handle_answer(text)
        else:
            response = "请简单介绍一下你自己。"

        self.turn.ai_started_speaking()
        await self.say(response)
        self.turn.ai_stopped_speaking()

    async def _handle_intro(self, text: str) -> str:
        """Extract profile from self-intro, then ask first question."""
        tech_keywords = [
            "langchain", "langgraph", "rag", "python", "go", "java",
            "react", "vue", "k8s", "docker", "agent", "llm", "spring"
        ]
        found = [t for t in tech_keywords if t.lower() in text.lower()]
        if found:
            self.profile["tech_stack"] = list(set(found))
            self.interview_state["profile"] = self.profile

        next_q = question_engine.select_next_question(
            round="round1", profile=self.profile,
            questions_asked=[], blind_spots=[],
        )
        if next_q:
            self.interview_state["current_question"] = next_q
            self.interview_state["current_question_id"] = next_q["id"]
            self.interview_state["interview_phase"] = "questioning"
            return self.persona.wrap({
                "action": "next_question",
                "question_text": next_q["question_text"],
            })
        return self.persona.wrap({
            "action": "next_question",
            "question_text": "请简单说一下你对 Agent 架构的理解？",
        })

    async def _handle_answer(self, text: str) -> str:
        """Process interview answer through followup engine, wrap in persona."""
        self.interview_state["user_answer"] = text
        question = self.interview_state.get("current_question", {})

        result = await followup_engine.determine_action(
            question=question, user_answer=text,
            current_depth=self.interview_state.get("current_depth", 0),
            followup_count=self.interview_state.get("followup_count", 0),
            max_depth=4,
        )
        action = result.get("action", "next_question")

        if action == "skip_and_record":
            self.interview_state["blind_spots"] = (
                self.interview_state.get("blind_spots", []) +
                [result.get("blind_spot", "")]
            )
            next_q = question_engine.select_next_question(
                round=self.interview_state.get("round", "round1"),
                profile=self.profile,
                questions_asked=self.interview_state.get("questions_asked", []),
                blind_spots=self.interview_state.get("blind_spots", []),
            )
            if next_q:
                self.interview_state["current_question"] = next_q
                self.interview_state["current_question_id"] = next_q["id"]
                self.interview_state["current_depth"] = 0
                self.interview_state["followup_count"] = 0
                return self.persona.wrap({
                    "action": "next_question",
                    "question_text": next_q["question_text"],
                })
            self.interview_state["interview_phase"] = "done"
            return self.persona.closing()

        elif action in ("followup", "probe", "give_hint", "degrade"):
            self.interview_state["current_depth"] = (
                self.interview_state.get("current_depth", 0) + 1
            )
            self.interview_state["followup_count"] = (
                self.interview_state.get("followup_count", 0) + 1
            )
            return self.persona.wrap({
                "action": "probe",
                "followup_text": result.get("followup_text", "能再详细说说吗？"),
            })

        else:  # next_question
            next_q = question_engine.select_next_question(
                round=self.interview_state.get("round", "round1"),
                profile=self.profile,
                questions_asked=self.interview_state.get("questions_asked", []),
                blind_spots=self.interview_state.get("blind_spots", []),
            )
            if next_q:
                self.interview_state["current_question"] = next_q
                self.interview_state["current_question_id"] = next_q["id"]
                self.interview_state["current_depth"] = 0
                self.interview_state["followup_count"] = 0
                return self.persona.wrap({
                    "action": "next_question",
                    "question_text": next_q["question_text"],
                })
            self.interview_state["interview_phase"] = "done"
            return self.persona.closing()


# ── Entry Point ──────────────────────────────────────────────

def entrypoint(ctx: JobContext):
    agent = InterviewAgentV2(ctx)
    agent.start(ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
