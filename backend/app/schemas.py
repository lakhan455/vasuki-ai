from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=120000)


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=100)
    provider: Literal[
        "auto",
        "groq",
        "sambanova",
        "cerebras",
        "gemini",
        "openrouter",
        "mistral",
    ] = "auto"
    use_web: bool = False
    use_memory: bool = True
    use_documents: bool = False
    document_ids: list[str] = Field(default_factory=list, max_length=50)


class ChatResponse(BaseModel):
    answer: str
    provider: str
    sources: list[dict] = Field(default_factory=list)
    context_trimmed: bool = False
    original_context_chars: int = 0
    used_context_chars: int = 0


class ResearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=5000)
    max_results: int = Field(default=5, ge=1, le=30)


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=5000)
    provider: Literal["auto", "deepai", "huggingface", "cloudflare"] = "auto"


class MemoryCreateRequest(BaseModel):
    memory_text: str = Field(min_length=3, max_length=600)
    category: str = Field(default="preference", min_length=1, max_length=40)


class MemorySettingsRequest(BaseModel):
    enabled: bool
