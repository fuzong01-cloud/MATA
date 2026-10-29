from openai import OpenAI

from app.core.config import settings


def create_model_client() -> OpenAI:
    if not settings.model_api_key:
        raise ValueError("模型 API 尚未配置")
    return OpenAI(
        api_key=settings.model_api_key,
        base_url=settings.model_base_url,
        timeout=90.0,
        max_retries=1,
    )
