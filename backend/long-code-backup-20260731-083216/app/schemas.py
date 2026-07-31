from typing import Literal
from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=20000)


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=50)
    provider: Literal["auto", "groq", "gemini", "openrouter", "mistral"] = "auto"
    use_web: bool = False


class ChatResponse(BaseModel):
    answer: str
    provider: str
    sources: list[dict] = []


class ResearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    max_results: int = Field(default=5, ge=1, le=10)


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    provider: Literal["auto", "deepai", "huggingface", "cloudflare"] = "auto"
