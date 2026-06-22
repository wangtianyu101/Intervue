from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "mysql+aiomysql://codemock:codemock@localhost:3306/codemock"

    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:8000/api/auth/github/callback"

    # JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7  # 7 days

    # LLM (MiniMax — OpenAI-compatible API)
    llm_api_key: str = "sk-cp-KnpGSzglSReB2B4lmaCjfVrwbDUF9pRNH7JwSah7giN_7lGf2yz5HikQMvsEVWmbYArUjgNCGtmiTRWtE0HgtObeRJo9Z-55EPp3C529thv5T4FrhCykXHg"
    llm_base_url: str = "https://api.minimax.chat/v1"
    llm_model: str = "MiniMax-Text-01"

    # DashScope (Alibaba ASR)
    dashscope_api_key: str = ""

    # WhisperLive
    whisper_live_url: str = "ws://localhost:9090"

    # LiveKit
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = ""
    livekit_api_secret: str = ""

    # Upload
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = 10

    class Config:
        env_file = (".env", ".env.local")


settings = Settings()
