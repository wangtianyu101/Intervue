"""
Standalone voice interview worker — NO Agent framework dependency.

Pipeline:
  User mic → LiveKit Room (subscribe audio track)
           → collect audio frames → WhisperLive STT
           → interview agent logic (question_engine + followup_engine)
           → Persona wrap
           → Piper TTS → publish audio track back to room → User speaker
"""

import asyncio
import logging
import time
import wave
import io
from typing import Optional

from livekit import api, rtc

from core.config import settings
from agents.states import create_initial_state
from agents.question_agent import question_engine
from agents.followup_agent import followup_engine
from voice.persona import InterviewerPersona

logger = logging.getLogger("codemock-voice-worker")


# ── Audio buffer ──────────────────────────────────────────

class AudioBuffer:
    """Collect audio frames until silence, then return as WAV bytes."""

    def __init__(self, sample_rate=16000, silence_timeout=1.5):
        self.sample_rate = sample_rate
        self.silence_timeout = silence_timeout
        self._frames: list[bytes] = []
        self._last_speech = 0.0
        self._total_samples = 0

    def push(self, frame: rtc.AudioFrame) -> Optional[bytes]:
        """Add audio frame. Returns WAV bytes if silence timeout reached."""
        raw = frame.data.tobytes() if hasattr(frame.data, 'tobytes') else bytes(frame.data)
        self._frames.append(raw)
        self._total_samples += len(raw) // 2  # 16-bit PCM

        # Detect if there's actual speech (simple energy detection)
        energy = sum(abs(int.from_bytes(raw[i:i+2], 'little', signed=True))
                     for i in range(0, min(len(raw), 2000), 2)) / 1000
        if energy > 50:  # speaking
            self._last_speech = time.time()

        # Check silence timeout
        if self._frames and time.time() - self._last_speech > self.silence_timeout:
            return self._flush()
        return None

    def _flush(self) -> Optional[bytes]:
        if not self._frames:
            return None
        wav = io.BytesIO()
        with wave.open(wav, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(b''.join(self._frames))
        self._frames = []
        self._total_samples = 0
        return wav.getvalue()


# ── STT ──────────────────────────────────────────────────

class SimpleSTT:
    """Batch-transcribe audio WAV bytes using faster-whisper."""

    def __init__(self):
        self._model = None

    def _load(self):
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel("tiny", device="cpu", compute_type="int8")
            logger.info("faster-whisper (tiny) loaded")
        except Exception as e:
            logger.warning(f"faster-whisper unavailable: {e}")

    def transcribe(self, wav_bytes: bytes) -> str:
        self._load()
        if self._model is None:
            return ""
        try:
            segments, _ = self._model.transcribe(wav_bytes, language="zh")
            text = " ".join(s.text for s in segments)
            return text.strip()
        except Exception as e:
            logger.warning(f"STT error: {e}")
            return ""


# ── TTS ──────────────────────────────────────────────────

class SimpleTTS:
    """Synthesize text to WAV bytes using Piper TTS."""

    def __init__(self):
        self._engine = None

    def _load(self):
        if self._engine is not None:
            return
        try:
            from voice.tts import TTSEngine
            self._engine = TTSEngine()
            logger.info("Piper TTS loaded")
        except Exception as e:
            logger.warning(f"Piper TTS unavailable: {e}")

    def synthesize(self, text: str) -> bytes:
        self._load()
        if self._engine is None:
            return b""
        try:
            return self._engine.synthesize(text)
        except Exception as e:
            logger.warning(f"TTS error: {e}")
            return b""


# ══════════════════════════════════════════════════════
#  Main worker
# ══════════════════════════════════════════════════════

async def run_worker():
    """Connect to LiveKit as a bot, handle voice interview flow."""

    import os
    room_name = os.environ.get("LIVEKIT_ROOM", "")
    if not room_name:
        logger.error("LIVEKIT_ROOM not set — pass the room name to join")
        return

    token = api.AccessToken(
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    ).with_identity("interviewer-bot").with_grants(
        api.VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=True)
    ).to_jwt()

    room = rtc.Room()
    stt = SimpleSTT()
    tts = SimpleTTS()
    persona = InterviewerPersona(name="Alex")
    buffer = AudioBuffer()

    # Interview state
    state = create_initial_state(
        user_id="voice_user",
        profile={"tech_stack": ["LangChain", "LangGraph", "RAG"], "years_of_exp": 3, "current_level": "mid"},
        round="round1",
    )
    audio_source: Optional[rtc.AudioSource] = None
    speaking = False

    @room.on("track_subscribed")
    def on_track(track: rtc.Track, *_args):
        nonlocal audio_source
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            logger.info(f"Subscribed to audio track: {track.sid}")
            asyncio.ensure_future(_process_audio(track))

    async def _process_audio(track: rtc.Track):
        nonlocal speaking, state, audio_source

        audio_stream = rtc.AudioStream(track)
        async for frame in audio_stream:
            wav = buffer.push(frame)
            if wav is None:
                continue
            if speaking:
                continue

            # STT
            text = stt.transcribe(wav)
            if not text or len(text) < 2:
                continue
            logger.info(f"User said: {text}")

            # Interview logic
            phase = state.get("interview_phase", "intro")
            if phase == "intro":
                response = _handle_intro(text, state)
            else:
                response = await _handle_answer(text, state)

            response = persona.wrap(response) if isinstance(response, dict) else response
            logger.info(f"AI response: {response[:80]}...")

            # TTS
            speaking = True
            audio_bytes = tts.synthesize(response)
            if audio_bytes and audio_source is None:
                audio_source = rtc.AudioSource(24000, 1)

            if audio_source and audio_bytes:
                # Create audio frame and publish
                frame = rtc.AudioFrame(
                    data=audio_bytes,
                    sample_rate=24000,
                    num_channels=1,
                    samples_per_channel=len(audio_bytes) // 2,
                )
                await audio_source.capture_frame(frame)
                room.local_participant.publish_audio(audio_source)

            await asyncio.sleep(0.5)
            speaking = False

    try:
        await room.connect(settings.livekit_url, token)
        logger.info(f"Connected to LiveKit room: {room_name}")
        await asyncio.Event().wait()  # keep running
    finally:
        await room.disconnect()


def _handle_intro(text: str, state: dict) -> dict:
    keywords = ["langchain", "langgraph", "rag", "python", "go", "java", "k8s", "docker", "agent"]
    found = [t for t in keywords if t.lower() in text.lower()]
    if found:
        state["profile"]["tech_stack"] = list(set(found))

    next_q = question_engine.select_next_question(
        round="round1", profile=state["profile"], questions_asked=[], blind_spots=[])
    if next_q:
        state["current_question"] = next_q
        state["current_question_id"] = next_q["id"]
        state["interview_phase"] = "questioning"
        return {"action": "next_question", "question_text": next_q["question_text"]}
    return {"action": "next_question", "question_text": "请简单说一下你对 AI Agent 架构的理解？"}


async def _handle_answer(text: str, state: dict) -> dict:
    state["user_answer"] = text
    q = state.get("current_question", {})
    result = await followup_engine.determine_action(
        question=q, user_answer=text,
        current_depth=state.get("current_depth", 0),
        followup_count=state.get("followup_count", 0),
        max_depth=4,
    )
    action = result.get("action", "next_question")

    if action == "skip_and_record":
        state["blind_spots"] = state.get("blind_spots", []) + [result.get("blind_spot", "")]
        nq = question_engine.select_next_question(
            round=state.get("round", "round1"), profile=state["profile"],
            questions_asked=state.get("questions_asked", []),
            blind_spots=state.get("blind_spots", []))
        if nq:
            state["current_question"] = nq
            state["current_question_id"] = nq["id"]
            return {"action": "next_question", "question_text": nq["question_text"]}
        state["interview_phase"] = "done"
        return {"action": "done", "question_text": "面试结束，感谢你的时间！"}
    elif action in ("followup", "probe", "give_hint", "degrade"):
        return {"action": "probe", "followup_text": result.get("followup_text", "能再详细说说吗？")}
    else:
        nq = question_engine.select_next_question(
            round=state.get("round", "round1"), profile=state["profile"],
            questions_asked=state.get("questions_asked", []),
            blind_spots=state.get("blind_spots", []))
        if nq:
            state["current_question"] = nq
            return {"action": "next_question", "question_text": nq["question_text"]}
        state["interview_phase"] = "done"
        return {"action": "done", "question_text": "面试结束！"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())
