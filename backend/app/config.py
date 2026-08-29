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

    # VASUKI_V42_DUAL_PROVIDER_START
    # Backend-only OpenCode Zen gateway. Keep the API key out of frontend/Vercel.
    # The default uses a Zen model documented on /chat/completions.
    # For a stronger paid coding model after enabling Zen billing, set:
    # OPENCODE_ZEN_MODEL=kimi-k2.7-code
    opencode_zen_api_key: str | None = None
    opencode_zen_base_url: str = "https://opencode.ai/zen/v1"
    opencode_zen_model: str = "north-mini-code-free"
    opencode_zen_timeout_seconds: float = 45.0

    # OpenRouter chat already uses OPENROUTER_API above.
    # Image generation is opt-in because it can consume OpenRouter credits.
    openrouter_image_enabled: bool = False
    openrouter_image_model: str = ""
    # VASUKI_V42_DUAL_PROVIDER_END

    # VASUKI_V44_ZAI_GLM_CODING_START
    # Backend-only Z.AI GLM Coding Plan provider.
    # Coding Plan keys must use the dedicated coding endpoint.
    zai_api_key: str | None = None
    zai_coding_base_url: str = "https://api.z.ai/api/coding/paas/v4"
    zai_model: str = "glm-4.7"
    zai_timeout_seconds: float = 45.0
    # VASUKI_V44_ZAI_GLM_CODING_END

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

    # VASUKI_V41_LIVE_WEATHER_TOOL_START
    # Backend-only WeatherAPI credentials. Never expose this key in Vercel/frontend.
    weatherapi_key: str | None = None
    weatherapi_base_url: str = "https://api.weatherapi.com/v1"
    weatherapi_timeout_seconds: float = 9.0
    # VASUKI_V41_LIVE_WEATHER_TOOL_END

    # Backend-only Supabase credentials.
    # Never put a service-role/secret key in the frontend or Vercel.
    supabase_url: str | None = None
    supabase_secret_key: str | None = None
    supabase_service_role_key: str | None = None

    # Vasuki Pro / owner access. Secrets stay only on Render.
    vasuki_owner_emails: str = ""
    puter_free_for_all: bool = True
    puter_image_daily_limit: int = 50
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

    # VASUKI_V17_MISSION_CONTROL_START
    v17_max_concurrent_builds: int = 2
    v17_job_ttl_seconds: int = 3600

    # V17.1 build-only provider recovery. These settings do not change
    # normal chat routing.
    v17_provider_retry_rounds: int = 2
    v17_provider_attempt_timeout_seconds: int = 38
    v17_provider_transient_cooldown_seconds: int = 4
    v17_provider_quota_cooldown_seconds: int = 75
    # VASUKI_V17_MISSION_CONTROL_END

    # VASUKI_V18_LIVING_MIND_START
    v18_living_mind_enabled: bool = True
    v18_reflection_enabled: bool = True
    v18_goal_memory_limit: int = 12
    v18_experience_memory_limit: int = 8

    # V18.1 normal-chat provider recovery. Used only when normal shared
    # cooldown/health filtering leaves zero candidates.
    v18_chat_provider_recovery_enabled: bool = True
    v18_chat_recovery_max_attempts: int = 5
    v18_chat_recovery_first_token_seconds: float = 4.5
    # VASUKI_V18_LIVING_MIND_END

    # VASUKI_V16_AUTONOMOUS_BUILDER_START
    # V16 generates a compact manifest first and then source in small batches.
    # This avoids large single-JSON truncation failures.
    v16_max_project_files: int = 24
    v16_generation_batch_size: int = 3
    v16_generation_concurrency: int = 2
    v16_repair_attempts: int = 2

    # Restricted Docker validation is used only when Docker already exists on
    # the host. V16 never pulls images implicitly and never enables network in
    # its validation containers.
    v16_docker_sandbox_enabled: bool = True

    # Optional deployment integrations. Core V16 coding does not require them.
    # Keep these backend-only.
    v16_netlify_token: str | None = None
    v16_netlify_site_id: str | None = None
    v16_vercel_deploy_hook_url: str = ""
    # VASUKI_V16_AUTONOMOUS_BUILDER_END
    global_learning_enabled: bool = True
    global_memory_direct_answer_score: float = 0.58
    global_memory_max_results: int = 3
    global_memory_dynamic_ttl_days: int = 7
    global_memory_stable_ttl_days: int = 365

    request_timeout_seconds: int = 12
    chat_timeout_seconds: int = 25
    fast_provider_timeout_seconds: int = 4
    first_token_timeout_seconds: float = 1.6
    large_provider_timeout_seconds: int = 45

    # VASUKI_V46_ADAPTIVE_SPEED_START
    # In-memory latency learning. No extra provider calls and no DB writes.
    v46_adaptive_speed_enabled: bool = True
    v46_adaptive_min_samples: int = 2
    v46_simple_first_token_timeout_seconds: float = 1.25
    v46_code_first_token_timeout_seconds: float = 2.2
    v46_large_first_token_timeout_seconds: float = 3.0
    # VASUKI_V46_ADAPTIVE_SPEED_END

    # VASUKI_V47_SELF_HEALING_ROUTER_START
    # V47 learns real runtime speed/reliability, persists sampled signals in
    # the existing v11_provider_quality table, and opens task-specific circuits
    # around repeatedly failing providers. No new database migration is needed.
    v47_reliability_router_enabled: bool = True
    v47_persistent_learning_enabled: bool = True
    v47_adaptive_min_samples: int = 2
    v47_persist_every_n_successes: int = 3
    v47_persist_timeout_seconds: float = 1.2
    v47_restore_timeout_seconds: float = 4.0
    v47_circuit_failure_threshold: int = 2
    v47_circuit_base_cooldown_seconds: float = 45.0
    v47_circuit_max_cooldown_seconds: float = 900.0
    v47_first_token_timeout_floor_seconds: float = 1.0
    v47_simple_first_token_timeout_max_seconds: float = 3.5
    v47_code_first_token_timeout_max_seconds: float = 5.5
    v47_large_first_token_timeout_max_seconds: float = 7.0
    # VASUKI_V47_SELF_HEALING_ROUTER_END
    # VASUKI_V49_CONTINUOUS_LIVE_KNOWLEDGE_START
    # Budget-aware background freshness collector. Reuses existing web research
    # credentials and existing verified Supabase global knowledge.
    v49_live_knowledge_enabled: bool = True
    v49_refresh_interval_seconds: int = 7200
    v49_startup_delay_seconds: int = 20
    v49_topics_per_cycle: int = 2
    v49_search_results_per_topic: int = 10
    v49_min_sources: int = 2
    v49_topic_timeout_seconds: float = 120.0
    v49_default_topics_enabled: bool = True

    # VASUKI_V49_1_AUTHORITATIVE_CURRENT_FACTS_START
    # Current officeholder snapshots are accepted only when every requested
    # entity is independently supported by current evidence.
    v49_1_authoritative_current_facts_enabled: bool = True
    v49_1_cm_snapshot_max_age_hours: float = 6.0
    v49_1_cm_min_confidence: float = 0.84
    v49_1_cm_batch_size: int = 4
    # LLM is only a last-resort CM adjudicator after source checks.\n    v49_1_llm_fallback_enabled: bool = True\n    # VASUKI_V49_1_AUTHORITATIVE_CURRENT_FACTS_END
    # VASUKI_V49_CONTINUOUS_LIVE_KNOWLEDGE_END

    rate_limit_per_minute: int = 60
    daily_message_limit: int = 0
    error_alert_webhook_url: str | None = None
    error_alert_min_interval_seconds: int = 300
    provider_timeout_seconds: int = 14
    provider_cooldown_seconds: int = 120
    max_provider_attempts: int = 7
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
