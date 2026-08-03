from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Vasuki AI"
    app_env: str = "development"
    allowed_origins: str = "http://localhost:3000"

    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_fast_model: str = "llama-3.1-8b-instant"
    sambanova_api_key: str | None = None
    sambanova_model: str = "gpt-oss-120b"
    sambanova_base_url: str = "https://api.sambanova.ai/v1"
    cerebras_api_key: str | None = None
    cerebras_model: str = "gpt-oss-120b"
    cerebras_base_url: str = "https://api.cerebras.ai/v1"
    google_gemini_api: str | None = None
    gemini_model: str = "gemini-3.6-flash"
    gemini_vision_model: str = "gemini-3.6-flash"
    gemini_image_edit_model: str = "gemini-3.1-flash-image"
    gemini_embedding_model: str = "gemini-embedding-2"
    embedding_dimensions: int = 768
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
    cloudflare_vision_model: str = "@cf/moondream/moondream3.1-9B-A2B"
    cloudflare_edit_model: str = "@cf/black-forest-labs/flux-2-klein-4b"
    ocr_space_api: str | None = None

    # Backend-only Supabase credentials.
    # Never put a service-role/secret key in the frontend or Vercel.
    supabase_url: str | None = None
    supabase_secret_key: str | None = None
    supabase_service_role_key: str | None = None
    global_learning_enabled: bool = True
    global_memory_direct_answer_score: float = 0.58
    global_memory_max_results: int = 3
    global_memory_dynamic_ttl_days: int = 7
    global_memory_stable_ttl_days: int = 365

    request_timeout_seconds: int = 12
    chat_timeout_seconds: int = 25
    fast_provider_timeout_seconds: int = 9
    provider_timeout_seconds: int = 18
    provider_cooldown_seconds: int = 120
    web_search_timeout_seconds: int = 14
    total_chat_timeout_seconds: int = 55
    image_timeout_seconds: int = 95
    total_image_timeout_seconds: int = 150
    vision_timeout_seconds: int = 120
    vision_max_file_mb: int = 15
    image_retry_attempts: int = 3
    max_prompt_chars: int = 20000
    max_context_chars: int = 45000
    max_single_message_chars: int = 35000
    context_reserve_chars: int = 7000
    max_output_tokens: int = 5000
    max_fast_output_tokens: int = 1600
    max_continuations: int = 0

    document_max_mb: int = 15
    document_max_chunks: int = 120
    document_match_count: int = 8

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
