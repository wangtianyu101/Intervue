"""TurnManager — manages real-time conversation turns and interrupt handling.

State machine:
  LISTENING → (user silence > 800ms) → THINKING → (first chunk ready) → SPEAKING
  SPEAKING → (user speech detected) → LISTENING (interrupt!)
  THINKING → (user speech detected) → LISTENING (cancel generation)
"""

import time
import logging
from enum import Enum
from typing import Optional, Callable, Awaitable

logger = logging.getLogger("codemock-turn")

class TurnState(Enum):
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"

class TurnManager:
    """Manages conversational turn-taking with interrupt support."""

    def __init__(self, silence_ms: int = 800, min_speech_ms: int = 500):
        self.state = TurnState.LISTENING
        self.silence_threshold = silence_ms / 1000.0
        self.min_speech_duration = min_speech_ms / 1000.0

        self._user_speech_start = 0.0
        self._user_speech_end = 0.0
        self._user_is_speaking = False
        self._ai_speech_start = 0.0
        self._total_turns = 0

        self.on_interrupt: Optional[Callable[[], Awaitable[None]]] = None
        self.on_turn_ready: Optional[Callable[[], Awaitable[None]]] = None

    def user_speech_started(self) -> Optional[str]:
        """VAD detected user speech start. Returns 'interrupt' or 'cancel' or None."""
        self._user_speech_start = time.time()
        self._user_is_speaking = True

        if self.state == TurnState.SPEAKING:
            duration = time.time() - self._ai_speech_start
            logger.info(f"INTERRUPT — user spoke after {duration:.1f}s of AI speech")
            self.state = TurnState.LISTENING
            self._total_turns += 1
            return "interrupt"

        if self.state == TurnState.THINKING:
            logger.info("CANCEL — user spoke during AI thinking")
            self.state = TurnState.LISTENING
            return "cancel"

        return None

    def user_speech_ended(self) -> Optional[str]:
        """VAD detected user stopped speaking. Returns 'turn_ready' or None."""
        self._user_speech_end = time.time()
        self._user_is_speaking = False
        duration = self._user_speech_end - self._user_speech_start

        if self.state == TurnState.LISTENING and duration >= self.min_speech_duration:
            self.state = TurnState.THINKING
            self._total_turns += 1
            logger.info(f"TURN_READY — user spoke for {duration:.1f}s, turn #{self._total_turns}")
            return "turn_ready"
        return None

    def ai_started_speaking(self):
        self._ai_speech_start = time.time()
        self.state = TurnState.SPEAKING
        logger.debug("AI started speaking")

    def ai_stopped_speaking(self):
        self.state = TurnState.LISTENING
        logger.debug("AI stopped speaking → listening")

    @property
    def is_ai_speaking(self) -> bool:
        return self.state == TurnState.SPEAKING

    @property
    def is_listening(self) -> bool:
        return self.state == TurnState.LISTENING

    @property
    def is_thinking(self) -> bool:
        return self.state == TurnState.THINKING
