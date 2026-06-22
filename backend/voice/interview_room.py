"""
Standalone voice interview worker — no Agent framework.

Pipeline (each step logged):
  1. LiveKit Room: subscribe to user audio track
  2. AudioBuffer: collect frames until silence → WAV bytes
  3. STT: SimpleSTT (reuse existing faster-whisper with cache)
  4. Interview Agent: question_engine + followup_engine
  5. Persona: wrap agent output in interviewer style
  6. TTS: Piper TTS → WAV bytes
  7. LiveKit Room: publish audio frame back to user
"""

import asyncio
import logging
import sys
import time
import wave
import io
import os
from typing import Optional
from datetime import datetime

from livekit import api, rtc

from core.config import settings
from agents.states import create_initial_state
from agents.question_agent import question_engine
from agents.followup_agent import followup_engine
from voice.persona import InterviewerPersona
from voice.stt import SimpleSTT

# ══════════════════════════════════════════════════════════
#  Logging system — trace every pipeline step
# ══════════════════════════════════════════════════════════

PIPELINE_LOG = logging.getLogger("voice.pipeline")
AUDIO_LOG = logging.getLogger("voice.audio")
STT_LOG = logging.getLogger("voice.stt")
TTS_LOG = logging.getLogger("voice.tts")
AGENT_LOG = logging.getLogger("voice.agent")


def _setup_logging(room_id: str):
    """Configure structured logging for voice pipeline tracing."""
    fmt = logging.Formatter(
        f'%(asctime)s [{room_id[:8]}] %(name)-16s %(levelname)-5s %(message)s',
        datefmt='%H:%M:%S',
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(fmt)

    for log in [PIPELINE_LOG, AUDIO_LOG, STT_LOG, TTS_LOG, AGENT_LOG, logging.getLogger("codemock-voice-worker")]:
        log.setLevel(logging.DEBUG)
        log.handlers = [handler]
        log.propagate = False


# ══════════════════════════════════════════════════════════
#  Audio Buffer
# ══════════════════════════════════════════════════════════

class AudioBuffer:
    """Collect audio frames, detect silence, flush as WAV."""

    def __init__(self, sample_rate=16000, silence_timeout=1.5):
        self.sample_rate = sample_rate
        self.silence_timeout = silence_timeout
        self._frames: list[bytes] = []
        self._last_speech_time = 0.0
        self._total_duration = 0.0

    def push(self, frame: rtc.AudioFrame) -> Optional[bytes]:
        raw = frame.data.tobytes() if hasattr(frame.data, 'tobytes') else bytes(frame.data)
        self._frames.append(raw)

        frame_ms = len(raw) / (self.sample_rate * 2)
        self._total_duration += frame_ms

        # Simple energy detection
        energy = sum(abs(int.from_bytes(raw[i:i + 2], 'little', signed=True))
                     for i in range(0, min(len(raw), 2000), 2)) / 1000
        if energy > 50:
            self._last_speech_time = time.time()

        # Flush on silence
        if self._frames and time.time() - self._last_speech_time > self.silence_timeout:
            wav = self._flush()
            AUDIO_LOG.debug(f"Flushed {self._total_duration:.1f}s audio ({len(self._frames)} frames)")
            return wav
        return None

    def _flush(self) -> Optional[bytes]:
        if not self._frames:
            return None
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(b''.join(self._frames))
        self._frames.clear()
        self._total_duration = 0.0
        return buf.getvalue()


# ══════════════════════════════════════════════════════════
#  Main Worker
# ══════════════════════════════════════════════════════════

async def run_worker():
    room_name = os.environ.get("LIVEKIT_ROOM", "")
    if not room_name:
        PIPELINE_LOG.error("LIVEKIT_ROOM not set — cannot start")
        return

    _setup_logging(room_name)
    PIPELINE_LOG.info(f"=== Worker starting for room: {room_name} ===")

    # ── Token ──
    token = api.AccessToken(
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    ).with_identity("interviewer-bot").with_grants(
        api.VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=True)
    ).to_jwt()
    PIPELINE_LOG.info("LiveKit token generated")

    # ── STT: macOS native speech recognition (offline, no download) ──
    stt = SimpleSTT()
    STT_LOG.info("STT engine initialized (faster-whisper)")

    # ── TTS (reuse existing TTSEngine) ──
    from voice.tts import TTSEngine
    tts_engine = TTSEngine()
    TTS_LOG.info("TTS engine initialized (Piper)")

    # ── Persona ──
    persona = InterviewerPersona(name="Alex")
    AGENT_LOG.info("Persona loaded: Alex")

    # ── Interview State ──
    state = create_initial_state(
        user_id="voice_user",
        profile={"tech_stack": ["LangChain", "LangGraph", "RAG"], "years_of_exp": 3, "current_level": "mid"},
        round="round1",
    )
    AGENT_LOG.info(f"Interview state initialized: round={state['round']}")

    # ── Connect to LiveKit ──
    room = rtc.Room()
    buffer = AudioBuffer()
    audio_source: Optional[rtc.AudioSource] = None
    speaking = asyncio.Event()

    @room.on("track_subscribed")
    def on_track(track: rtc.Track, *_args):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            AUDIO_LOG.info(f"Audio track subscribed: {track.sid}")
            asyncio.ensure_future(_process_audio(track))

    @room.on("participant_connected")
    def on_participant(participant: rtc.RemoteParticipant):
        PIPELINE_LOG.info(f"Participant joined: {participant.identity}")

    @room.on("disconnected")
    def on_disconnected():
        PIPELINE_LOG.warning("Room disconnected")

    async def _process_audio(track: rtc.Track):
        nonlocal audio_source, speaking
        AUDIO_LOG.info("Audio processing loop started")

        audio_stream = rtc.AudioStream(track)
        frame_count = 0
        async for event in audio_stream:
            frame = event.frame
            frame_count += 1

            wav = buffer.push(frame)
            if wav is None:
                continue
            if speaking.is_set():
                AUDIO_LOG.debug("Skipping — AI still speaking")
                continue

            # ═══ STEP 1: STT ═══
            t_start = time.time()
            text = stt.transcribe_bytes(wav)
            t_stt = time.time() - t_start
            STT_LOG.info(f"Transcribed ({t_stt:.1f}s): '{text[:80]}'")

            if not text or len(text.strip()) < 2:
                STT_LOG.debug("Too short — skipping")
                continue

            # ═══ STEP 2: Interview Agent ═══
            phase = state.get("interview_phase", "intro")
            AGENT_LOG.info(f"Processing user input — phase={phase}")

            if phase == "intro":
                raw_response = _handle_intro(text, state)
            else:
                raw_response = await _handle_answer(text, state)

            wrapped = persona.wrap(raw_response) if isinstance(raw_response, dict) else raw_response
            AGENT_LOG.info(f"Response: '{wrapped[:100]}'")

            # ═══ STEP 3: TTS ═══
            t_start = time.time()
            audio_bytes = tts_engine.synthesize(wrapped)
            t_tts = time.time() - t_start
            TTS_LOG.info(f"Synthesized {len(audio_bytes)} bytes ({t_tts:.1f}s)")

            if not audio_bytes:
                TTS_LOG.error("TTS produced empty audio")
                continue

            # ═══ STEP 4: Publish audio back ═══
            speaking.set()
            try:
                if audio_source is None:
                    audio_source = rtc.AudioSource(22050, 1)
                    audio_track = rtc.LocalAudioTrack.create_audio_track("response", audio_source)
                    await room.local_participant.publish_track(audio_track)
                    AUDIO_LOG.info("Audio track published")
                    await asyncio.sleep(0.5)  # Wait for track to be ready

                frame = rtc.AudioFrame(
                    data=audio_bytes,
                    sample_rate=22050,
                    num_channels=1,
                    samples_per_channel=len(audio_bytes) // 2,
                )
                await audio_source.capture_frame(frame)
                AUDIO_LOG.info(f"Audio frame sent ({len(audio_bytes)} bytes)")

                await asyncio.sleep(0.5)
            except Exception as e:
                AUDIO_LOG.error(f"Audio publish failed: {e}")
            finally:
                speaking.clear()

    # ── Connect ──
    try:
        await room.connect(settings.livekit_url, token)
        PIPELINE_LOG.info(f"Connected to LiveKit room: {room_name}")

        # Send initial greeting after connecting
        greeting = persona.wrap({"action": "next_question", "question_text": "你好！我是 Alex，一位 AI 技术面试官。请先简单介绍一下你自己，包括你熟悉的编程语言和技术栈。"})
        PIPELINE_LOG.info(f"Initial greeting: '{greeting[:60]}'")

        # TTS for greeting
        audio_bytes = tts_engine.synthesize(greeting)
        if audio_bytes:
            speaking.set()
            try:
                if audio_source is None:
                    audio_source = rtc.AudioSource(22050, 1)
                    audio_track = rtc.LocalAudioTrack.create_audio_track("greeting", audio_source)
                    await room.local_participant.publish_track(audio_track)
                    # Wait for track to be fully published
                    await asyncio.sleep(2.0)
                frame = rtc.AudioFrame(data=audio_bytes, sample_rate=22050, num_channels=1, samples_per_channel=len(audio_bytes) // 2)
                await audio_source.capture_frame(frame)
                TTS_LOG.info(f"Greeting sent ({len(audio_bytes)} bytes)")
                await asyncio.sleep(len(audio_bytes) / 22050 + 0.5)  # Wait for audio to finish
            except Exception as e:
                TTS_LOG.error(f"Greeting failed: {e}")
            finally:
                speaking.clear()

        await asyncio.Event().wait()
    except Exception as e:
        PIPELINE_LOG.error(f"Fatal: {e}", exc_info=True)
    finally:
        await room.disconnect()
        PIPELINE_LOG.info("Worker stopped")


# ══════════════════════════════════════════════════════════
#  Interview Logic
# ══════════════════════════════════════════════════════════

def _handle_intro(text: str, state: dict) -> dict:
    keywords = ["langchain", "langgraph", "rag", "python", "go", "java", "k8s", "docker", "agent", "llm", "spring"]
    found = [t for t in keywords if t.lower() in text.lower()]
    if found:
        state["profile"]["tech_stack"] = list(set(found))
        AGENT_LOG.info(f"Detected tech: {found}")

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
    asyncio.run(run_worker())
