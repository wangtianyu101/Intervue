"""
阿里云 ASR + TTS 服务封装（dashscope 1.20+）

依赖:
    pip install dashscope>=1.20.0

环境变量:
    DASHSCOPE_API_KEY - 阿里云 API Key (https://dashscope.console.aliyun.com/)

API 参考:
    ASR: dashscope.MultiModalConversation.call(model="qwen3-asr-flash", ...)
    TTS: dashscope.audio.tts_v2.SpeechSynthesizer(model="cosyvoice-v1", voice="longxiaochun").call(text)
"""

import os
import tempfile
import logging
from typing import Optional

from core.config import settings

logger = logging.getLogger("codemock.asr_tts")


class ASRTTSService:
    """阿里云 ASR + TTS 服务（dashscope 1.20+）"""

    def __init__(self, api_key: Optional[str] = None):
        try:
            import dashscope
        except ImportError:
            logger.warning("dashscope not installed, ASR/TTS will not work")
            self.dashscope = None
            self._available = False
            return

        self.dashscope = dashscope
        dashscope.api_key = api_key or settings.dashscope_api_key
        if not dashscope.api_key:
            logger.warning("dashscope_api_key not set, ASR/TTS will not work")
        self._available = bool(dashscope.api_key)

    @property
    def available(self) -> bool:
        return self._available

    async def recognize(self, audio_bytes: bytes, format: str = "wav") -> str:
        """语音转文字（qwen3-asr-flash）

        Args:
            audio_bytes: 音频数据
            format: 音频格式 (wav, mp3, webm 等)

        Returns:
            识别的文字
        """
        if not self.available:
            logger.error("ASR not available (no API key or dashscope not installed)")
            return ""

        try:
            from dashscope import MultiModalConversation

            # 写入临时文件
            with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as f:
                f.write(audio_bytes)
                audio_path = f.name

            try:
                response = MultiModalConversation.call(
                    model="qwen3-asr-flash",
                    messages=[{
                        "role": "user",
                        "content": [{"audio": audio_path}]
                    }]
                )

                if response.output and response.output.choices:
                    message = response.output.choices[0].message
                    if message and message.content:
                        for part in message.content if isinstance(message.content, list) else [message.content]:
                            if isinstance(part, dict) and part.get("text"):
                                text = part["text"].strip()
                                if text:
                                    logger.info(f"ASR result: {text[:50]}...")
                                    return text

                logger.warning("ASR returned empty result")
                return ""

            finally:
                os.unlink(audio_path)

        except Exception as e:
            logger.error(f"ASR failed: {e}")
            return ""

    async def synthesize(self, text: str, voice: str = "longxiaochun") -> bytes:
        """文字转语音（dashscope.audio.tts_v2.SpeechSynthesizer）

        Args:
            text: 要转换的文字
            voice: 音色名称 (默认 longxiaochun — 中文女声)

        Returns:
            MP3 音频数据
        """
        if not self.available:
            logger.error("TTS not available (no API key or dashscope not installed)")
            return b""

        try:
            from dashscope.audio.tts_v2 import SpeechSynthesizer

            syn = SpeechSynthesizer(model="cosyvoice-v1", voice=voice)
            audio_bytes = syn.call(text)
            if audio_bytes:
                logger.info(f"TTS synthesized {len(audio_bytes)} bytes")
                return bytes(audio_bytes)
            logger.warning("TTS returned empty result")
            return b""

        except Exception as e:
            logger.error(f"TTS failed: {e}")
            return b""


# 全局单例
_asr_tts_service: Optional[ASRTTSService] = None


def get_asr_tts_service() -> ASRTTSService:
    """获取 ASR/TTS 服务单例"""
    global _asr_tts_service
    if _asr_tts_service is None:
        _asr_tts_service = ASRTTSService()
    return _asr_tts_service


# 兼容旧代码
async def recognize_audio(audio_bytes: bytes) -> str:
    """快捷函数：语音转文字"""
    service = get_asr_tts_service()
    return await service.recognize(audio_bytes)


async def synthesize_speech(text: str) -> bytes:
    """快捷函数：文字转语音"""
    service = get_asr_tts_service()
    return await service.synthesize(text)
