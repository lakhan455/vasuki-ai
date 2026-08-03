from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Vasuki AI"
    app_env: str = "development"
    allowed_origins: str = "http://localhost:3000"

    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    google_gemini_api: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    openrouter_api: str | None = None
    openrouter_model: str = "openai/gpt-4.1-mini"
    mistral_ai_api: str | None = None
    mistral_model: str = "mistral-small-latest"

    tavily_api_key: str | None = None
    exa_api: str | None = None
    news_api: str | None = None

    deepai_api: str | None = None
    hugging_face_inference_api: str | None = None
    hf_image_model: str = "black-forest-labs/FLUX.1-dev"
    cloudflare_account_id: str | None = None
    cloudflare_workers_ai: str | None = None
    cloudflare_image_model: str = "@cf/black-forest-labs/flux-1-schnell"
    ocr_space_api: str | None = None

    # Backend-only Supabase credentials for verified shared knowledge.
    # Never put SUPABASE_SERVICE_ROLE_KEY in the frontend or Vercel.
    supabase_url: str | None = None
    supabase_secret_key: str | None = None
    supabase_service_role_key: str | None = None
    global_learning_enabled: bool = True
    global_memory_direct_answer_score: float = 0.58
    global_memory_max_results: int = 3
    global_memory_dynamic_ttl_days: int = 7
    global_memory_stable_ttl_days: int = 365

    # Keep individual upstream calls short so one slow free provider does not
    # block the whole request. Large answers are still supported, but the app
    # fails over instead of waiting for minutes.
    request_timeout_seconds: int = 12
    chat_timeout_seconds: int = 25
    web_search_timeout_seconds: int = 14
    total_chat_timeout_seconds: int = 55
    max_prompt_chars: int = 20000
    max_context_chars: int = 45000
    max_single_message_chars: int = 35000
    context_reserve_chars: int = 7000
    max_output_tokens: int = 5000
    max_continuations: int = 0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def origins(self) -> list[str]:
        return [
            item.strip()
            for item in self.allowed_origins.split(",")
            if item.strip()
        ]

    @property
    def global_learning_configured(self) -> bool:
        return bool(
            self.global_learning_enabled
            and self.supabase_url
            and (self.supabase_secret_key or self.supabase_service_role_key)
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
