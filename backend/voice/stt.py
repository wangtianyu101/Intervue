"""Speech-to-Text: faster-whisper (local, offline) + WhisperLive streaming.

Priority: faster-whisper for batch transcription (works everywhere, no network needed).
WhisperLive is optional for real-time streaming mode.
"""

from __future__ import annotations

import os
import json
import subprocess
import tempfile
import logging
from pathlib import Path

from core.config import settings

logger = logging.getLogger("codemock.stt")

# HuggingFace mirror for China
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

MODEL_DIR = Path(settings.upload_dir) / "whisper_models"
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "tiny")  # tiny=75MB, base=145MB, small=480MB


class SimpleSTT:
    """Local offline STT using faster-whisper."""

    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def warm_up(self):
        """Pre-load the model. Call on startup to avoid first-request timeout."""
        self._load_model()

    def _load_model(self):
        if self._model is not None:
            return
        import whisper
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Loading whisper model '{MODEL_SIZE}' (openai-whisper)...")
        self._model = whisper.load_model(MODEL_SIZE)
        logger.info("whisper model ready")

    def transcribe_file(self, audio_path: str, language: str = "zh") -> str:
        """Transcribe an audio file. Supports any format ffmpeg can read (webm, wav, mp4, etc)."""
        self._load_model()

        # Convert to 16kHz mono WAV if needed (whisper works best with this)
        wav_path = None
        try:
            if not audio_path.endswith(".wav"):
                wav_path = audio_path + ".16k.wav"
                subprocess.run([
                    "ffmpeg", "-y", "-i", audio_path,
                    "-ar", "16000", "-ac", "1",
                    "-sample_fmt", "s16",
                    wav_path,
                ], capture_output=True, timeout=30)
                audio_path = wav_path

            result = self._model.transcribe(
                audio_path,
                language=language,
                beam_size=5,
            )
            # openai-whisper returns dict with 'text' key
            text = result.get("text", "").strip()
            if text:
                logger.info(f"STT result: {text[:80]}...")
            return text
        except Exception as e:
            logger.error(f"STT transcribe failed: {e}")
            return ""
        finally:
            if wav_path and os.path.exists(wav_path):
                os.unlink(wav_path)

    def transcribe_bytes(self, audio_bytes: bytes, language: str = "zh") -> str:
        """Transcribe raw audio bytes."""
        suffix = ".webm"
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            with open(path, "wb") as f:
                f.write(audio_bytes)
            return self.transcribe_file(path, language=language)
        finally:
            if os.path.exists(path):
                os.unlink(path)


class DashScopeSTT:
    """Alibaba Bailian Qwen3-ASR cloud API — 10h free, ¥0.00022/s after.

    More accurate than local whisper for Chinese, works perfectly in China.
    """

    def __init__(self, api_key: str | None = None):
        import dashscope
        self.api_key = api_key or settings.dashscope_api_key
        dashscope.api_key = self.api_key

    def transcribe_file(self, audio_path: str, language: str = "zh") -> str:
        """Transcribe via Qwen3-ASR-Flash MultiModalConversation API."""
        if not self.api_key:
            return SimpleSTT().transcribe_file(audio_path)

        try:
            from dashscope import MultiModalConversation

            response = MultiModalConversation.call(
                model="qwen3-asr-flash",
                api_key=self.api_key,
                messages=[{
                    "role": "user",
                    "content": [{"audio": audio_path}],
                }],
            )

            if response.output and response.output.choices:
                msg = response.output.choices[0].message
                if msg and msg.content:
                    for part in msg.content if isinstance(msg.content, list) else [msg.content]:
                        if isinstance(part, dict) and part.get("text"):
                            text = part["text"]
                            if text.strip():
                                logger.info(f"DashScope: {text.strip()[:80]}...")
                                return text.strip()

            logger.warning(f"DashScope: no text")
            return SimpleSTT().transcribe_file(audio_path)
        except Exception as e:
            logger.error(f"DashScope failed: {e}")
            return SimpleSTT().transcribe_file(audio_path)


class WhisperLiveClient:
    """Connects to WhisperLive server for real-time streaming transcription."""

    def __init__(self, url: str | None = None):
        self.url = url or settings.whisper_live_url
        self._ws = None

    async def connect(self):
        import websockets
        self._ws = await websockets.connect(self.url)

    async def send_audio(self, audio_bytes: bytes):
        if not self._ws:
            raise RuntimeError("Not connected. Call connect() first.")
        await self._ws.send(audio_bytes)

    async def receive_transcript(self) -> str:
        if not self._ws:
            raise RuntimeError("Not connected. Call connect() first.")
        msg = await self._ws.recv()
        data = json.loads(msg)
        return data.get("text", data.get("partial", ""))

    async def close(self):
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.close()
