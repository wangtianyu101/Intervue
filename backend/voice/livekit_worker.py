"""LiveKit Voice Agent — Local STT/TTS + DeepSeek LLM interviewer."""

import logging
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli
from livekit.agents.voice import Agent
from livekit.plugins import silero, openai

from core.config import settings

logger = logging.getLogger("codemock-voice")

INTERVIEWER_PROMPT = """你是 Alex，一位专业友好的 AI 技术面试官。

面试规则：
1. 先向候选人打招呼，请他们简单介绍自己的技术栈和经验
2. 根据介绍选方向提问：AI Agent架构(ReAct/Tool Use/Memory/MCP)、RAG、LangGraph、Java后端
3. 每次只问一个问题，候选人的回答会通过语音转文字传给你
4. 根据回答质量：好→深入追问；一般→引导补充；不会→给提示或换方向
5. 8题左右结束，给简短反馈
6. 保持专业友好的语气，像真实面试对话

现在开始——先打招呼，请候选人做自我介绍。"""


async def entrypoint(ctx: JobContext):
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info(f"Voice room joined: {ctx.room.name}")

    agent = Agent(
        instructions=INTERVIEWER_PROMPT,
        vad=silero.VAD.load(),
        stt=openai.STT(
            model="whisper-1",
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        ),
        llm=openai.LLM(
            model="deepseek-chat",
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        ),
        tts=openai.TTS(
            model="tts-1",
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        ),
    )

    agent.start(ctx.room)
    logger.info("Agent started — awaiting participant")

    await ctx.wait_for_participant()
    await agent.on_enter()
    logger.info("Interview begun")

    await ctx.done.wait()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
