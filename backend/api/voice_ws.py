"""
WebSocket 语音面试端点（薄壳）

工作流:
    1. 客户端 connect ws://.../ws/voice/{interview_id}?token=<jwt>
    2. 服务端 verify token (decode_token) + verify interview ownership
    3. 客户端发送 {type: "audio", data: <b64>, format: "webm"}
    4. 客户端发送 {type: "stop"}
    5. 服务端:
        a. POST /api/interviews/transcribe → text
        b. POST /api/interviews/voice/respond → response text
        c. ASRTTSService.synthesize(response) → mp3 bytes
    6. 服务端回 {type: transcript} → {type: response} → {type: audio} → {type: done}

设计原则: WS 不直接操作 InterviewSessionManager，状态机只由
backend/api/interview.py:/voice/respond 推进 — WS 是流式上传/下载壳。

关闭码:
    4401 — token 无效
    4403 — token 与 interview 的 user_id 不匹配
    4404 — interview 不存在
    1011 — 服务端内部错误
"""

import asyncio
import base64
import json
import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from core.database import async_session
from core.dependencies import decode_token
from models import Interview
from services.asr_tts import get_asr_tts_service

logger = logging.getLogger("codemock.voice_ws")

router = APIRouter()

# 内部 HTTP base — WS 进程要么跟 REST 同进程（默认）要么显式 INTERNAL_API_URL 覆盖
INTERNAL_API_URL = os.environ.get("INTERNAL_API_URL", "http://localhost:8000")

# per-interview 串行化 stop 处理 — 避免 "stop in flight 时收到新 audio/stop" 写竞态
_session_locks: dict[str, asyncio.Lock] = {}
_session_locks_guard = asyncio.Lock()


async def _get_session_lock(interview_id: str) -> asyncio.Lock:
    async with _session_locks_guard:
        lock = _session_locks.get(interview_id)
        if lock is None:
            lock = asyncio.Lock()
            _session_locks[interview_id] = lock
        return lock


async def _verify_ownership(interview_id: str, token_payload: dict) -> Optional[str]:
    """Check that the interview belongs to the JWT subject. Returns error close code or None."""
    user_id = token_payload.get("sub")
    if not user_id:
        return "4401"
    async with async_session() as db:
        result = await db.execute(select(Interview).where(Interview.id == interview_id))
        interview = result.scalar_one_or_none()
        if interview is None:
            return "4404"
        if interview.user_id != user_id:
            return "4403"
    return None


async def _call_transcribe(audio_bytes: bytes, fmt: str, token: str) -> str:
    """POST audio to /api/interviews/transcribe, return text.

    Note: the form field MUST be named "file" — the endpoint binds it as
        file: UploadFile = File(...)
    and FastAPI returns 422 otherwise. (Earlier this was mismatched as "audio"
    and the resulting 422 surfaced to users as a generic "语音识别失败".)
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{INTERNAL_API_URL}/api/interviews/transcribe",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (f"chunk.{fmt}", audio_bytes, f"audio/{fmt}")},
        )
    r.raise_for_status()
    return r.json().get("text", "").strip()


async def _call_voice_respond(interview_id: str, user_answer: str, token: str) -> str:
    """POST to /api/interviews/voice/respond, return response text."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{INTERNAL_API_URL}/api/interviews/voice/respond",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"interview_id": interview_id, "user_answer": user_answer},
        )
    r.raise_for_status()
    return r.json().get("response", "").strip()


@router.websocket("/ws/voice/{interview_id}")
async def voice_websocket(
    websocket: WebSocket,
    interview_id: str,
    token: str = Query(..., description="JWT for the user owning the interview"),
):
    """Real-time voice interview endpoint.

    Protocol — server → client messages:
      {type: "processing", message: "..."}
      {type: "transcript", text, is_final: true}
      {type: "response", text}
      {type: "audio", data: <base64 mp3>}
      {type: "done"}
      {type: "error", message}
    """
    # ── Auth: before accept, so a bad token never opens a session ──
    payload = decode_token(token)
    if payload is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid token")
        return

    err = await _verify_ownership(interview_id, payload)
    if err == "4401":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="missing sub")
        return
    if err == "4403":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="not your interview")
        return
    if err == "4404":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="interview not found")
        return

    await websocket.accept()
    logger.info(f"WS connected: interview={interview_id} user={payload.get('sub')}")

    audio_chunks = bytearray()
    audio_format = "webm"
    asr_tts = get_asr_tts_service()
    lock = await _get_session_lock(interview_id)
    processing = False

    async def _send(msg: dict) -> None:
        try:
            await websocket.send_json(msg)
        except Exception as e:
            logger.debug(f"WS send failed: {e}")

    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await _send({"type": "error", "message": "invalid JSON"})
                continue

            kind = msg.get("type")

            if kind == "ping":
                await _send({"type": "pong"})
                continue

            if kind == "audio":
                # Drop new audio while a turn is being processed — the client's stop
                # message is the boundary that flushes the buffer. If we accepted audio
                # in-flight, two stop messages would race on the same bytearray.
                if processing:
                    logger.warning("audio received while processing — dropping")
                    continue
                b64 = msg.get("data", "")
                if not b64:
                    continue
                try:
                    audio_chunks.extend(base64.b64decode(b64))
                except Exception as e:
                    logger.error(f"bad b64 in audio: {e}")
                    await _send({"type": "error", "message": "bad audio encoding"})
                    continue
                audio_format = msg.get("format", audio_format)
                continue

            if kind == "stop":
                if processing:
                    logger.warning("stop received while processing — dropping")
                    continue
                if not audio_chunks:
                    await _send({"type": "error", "message": "no audio captured"})
                    continue

                async with lock:
                    processing = True
                    try:
                        audio_data = bytes(audio_chunks)
                        audio_chunks.clear()
                        # snapshot the format before yielding to the event loop
                        fmt = audio_format

                        await _send({"type": "processing", "message": "正在识别..."})

                        # 1) STT
                        try:
                            text = await _call_transcribe(audio_data, fmt, token)
                        except httpx.HTTPStatusError as e:
                            logger.error(
                                f"transcribe HTTP {e.response.status_code}: "
                                f"{e.response.text[:200]}"
                            )
                            await _send({
                                "type": "error",
                                "message": f"语音识别失败 (HTTP {e.response.status_code})",
                            })
                            continue
                        except Exception as e:
                            logger.error(f"transcribe failed: {type(e).__name__}: {e}")
                            await _send({"type": "error", "message": "语音识别失败"})
                            continue

                        if not text:
                            await _send({"type": "error", "message": "未识别到语音内容"})
                            await _send({"type": "done"})
                            continue

                        await _send({"type": "transcript", "text": text, "is_final": True})

                        # 2) Agent
                        try:
                            response_text = await _call_voice_respond(interview_id, text, token)
                        except Exception as e:
                            logger.error(f"voice/respond failed: {e}")
                            await _send({"type": "error", "message": "面试官无响应"})
                            continue

                        if not response_text:
                            await _send({"type": "done"})
                            continue

                        await _send({"type": "response", "text": response_text})

                        # 3) TTS
                        audio_bytes = await asr_tts.synthesize(response_text)
                        if audio_bytes:
                            await _send({
                                "type": "audio",
                                "data": base64.b64encode(audio_bytes).decode(),
                            })

                        await _send({"type": "done"})
                    finally:
                        processing = False
                continue

            # unknown
            await _send({"type": "error", "message": f"unknown type: {kind}"})

    except WebSocketDisconnect:
        logger.info(f"WS disconnected: interview={interview_id}")
    except Exception as e:
        logger.error(f"WS fatal: {e}", exc_info=True)
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
    finally:
        logger.info(f"WS closed: interview={interview_id}")
        # free lock for this interview
        async with _session_locks_guard:
            _session_locks.pop(interview_id, None)
