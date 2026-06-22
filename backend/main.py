import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.auth import router as auth_router
from api.profile import router as profile_router
from api.interview import router as interview_router
from api.report import router as report_router
from api.dashboard import router as dashboard_router
from api.analytics import router as analytics_router
from api.knowledge import router as knowledge_router
from api.news import router as news_router
from api.voice_ws import router as voice_ws_router

logger = logging.getLogger("codemock")

app = FastAPI(title="CodeMock", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(profile_router)
app.include_router(interview_router)
app.include_router(report_router)
app.include_router(dashboard_router)
app.include_router(analytics_router)
app.include_router(knowledge_router)
app.include_router(news_router)
app.include_router(voice_ws_router)


@app.on_event("startup")
async def on_startup():
    try:
        from core.database import init_db
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database unavailable, running without persistence: {e}")

    # Pre-warm STT model so first request doesn't time out
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _warm_stt)
    except Exception as e:
        logger.warning(f"STT pre-warm skipped: {e}")


def _warm_stt():
    from voice.stt import SimpleSTT
    stt = SimpleSTT()
    stt.warm_up()


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "codemock"}
