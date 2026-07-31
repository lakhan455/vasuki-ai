from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Power Vasuki AI"
    app_env: str = "development"
    allowed_origins: str = "http://localhost:3000"

    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
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

    request_timeout_seconds: int = 60
    max_prompt_chars: int = 20000

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
