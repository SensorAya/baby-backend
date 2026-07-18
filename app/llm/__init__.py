from openai import AsyncOpenAI

from app.core.config import settings

client = AsyncOpenAI(
    api_key=settings.LLM_API_KEY,
    base_url=settings.LLM_BASE_URL,
)
