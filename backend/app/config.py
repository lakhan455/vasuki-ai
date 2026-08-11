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

    # Vasuki Pro / owner access. Secrets stay only on Render.
    vasuki_owner_emails: str = ""
    puter_free_for_all: bool = True
    puter_image_daily_limit: int = 100
    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None
    razorpay_plan_amount_paise: int = 9900
    razorpay_plan_days: int = 30

    # VASUKI_V10_OMNI_BRAIN_START
    # Optional OmniRoute sidecar. Secrets stay backend-only.
    omniroute_enabled: bool = False
    omniroute_base_url: str = ""
    omniroute_api_key: str | None = None
    omniroute_timeout_seconds: int = 65
    omniroute_compression: str = "default"
    omniroute_budget_usd: float = 0.0
    omniroute_budget_fallback: str = "cheapest"
    omniroute_knowledge_enabled: bool = True
    omniroute_search_enabled: bool = False
    omniroute_image_enabled: bool = False
    omniroute_image_model: str = ""
    omniroute_embedding_enabled: bool = False
    omniroute_embedding_model: str = ""
    # VASUKI_V10_OMNI_BRAIN_END


    # VASUKI_V11_ALL_IN_ONE_START
    v11_eval_concurrency: int = 3
    v11_research_max_subquestions: int = 6
    v11_canary_percent: int = 5
    v11_abuse_requests_per_minute: int = 120

    v11_scheduler_enabled: bool = True
    v11_scheduler_poll_seconds: int = 60

    v11_auto_rollback_enabled: bool = False
    v11_rollback_min_samples: int = 50
    v11_rollback_error_pct: float = 12.0
    v11_rollback_webhook_url: str = ""

    v11_mcp_enabled: bool = False
    v11_a2a_enabled: bool = False

    # Backend-only GitHub token. Use the least privilege needed.
    v11_github_token: str | None = None

    # Optional OpenAI-compatible video provider.
    v11_video_api_base_url: str = ""
    v11_video_api_key: str | None = None
    v11_video_model: str = "auto"

    # Optional OpenAI-compatible server TTS/STT. Browser voice works without these.
    v11_tts_api_base_url: str = ""
    v11_tts_api_key: str | None = None
    v11_tts_model: str = "tts-1"
    v11_stt_api_base_url: str = ""
    v11_stt_api_key: str | None = None
    v11_stt_model: str = "whisper-1"
    # VASUKI_V11_ALL_IN_ONE_END

    global_learning_enabled: bool = True
    global_memory_direct_answer_score: float = 0.58
    global_memory_max_results: int = 3
    global_memory_dynamic_ttl_days: int = 7
    global_memory_stable_ttl_days: int = 365

    request_timeout_seconds: int = 12
    chat_timeout_seconds: int = 25
    fast_provider_timeout_seconds: int = 7
    first_token_timeout_seconds: int = 4
    large_provider_timeout_seconds: int = 45
    rate_limit_per_minute: int = 15
    daily_message_limit: int = 250
    error_alert_webhook_url: str | None = None
    error_alert_min_interval_seconds: int = 300
    provider_timeout_seconds: int = 14
    provider_cooldown_seconds: int = 120
    max_provider_attempts: int = 3
    response_cache_enabled: bool = True
    response_cache_ttl_seconds: int = 900
    web_cache_current_ttl_seconds: int = 60
    web_cache_stable_ttl_seconds: int = 600
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
    max_continuations: int = 2

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
