from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")


class Settings:
    def __init__(self) -> None:
        self.root = ROOT
        self.course_zip = Path(os.getenv("COURSE_ZIP", str(ROOT / "knowledge_base" / "course_materials_latest.zip")))
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./database/assistant.db")
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
        self.vector_path = ROOT / "knowledge_base" / "indexes"
        self.slide_visual_path = ROOT / "knowledge_base" / "processed" / "slide_images"
        self.chat_upload_path = ROOT / "uploads" / "chat"
        self.material_upload_path = ROOT / "uploads" / "materials"
        self.submission_path = ROOT / "uploads" / "submissions"
        self.frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
        self.backend_port = int(os.getenv("BACKEND_PORT", "8001"))
        self.teacher_access_code = os.getenv("TEACHER_ACCESS_CODE", "").strip()
        self.media_signing_key = os.getenv("MEDIA_SIGNING_KEY", "").strip()
        self.qwen_api_key = os.getenv("QWEN_API_KEY", "").strip()
        self.qwen_base_url = os.getenv(
            "QWEN_BASE_URL", "https://cn-beijing.maas.qianwenaiapi.com/compatible-mode/v1"
        ).strip()
        self.qwen_model = os.getenv("QWEN_MODEL", "qwen3.8-flash").strip()
    @property
    def model_provider(self) -> str:
        return "qwen"

    @property
    def model_api_key(self) -> str:
        return self.qwen_api_key

    @property
    def model_base_url(self) -> str:
        return self.qwen_base_url

    @property
    def model_name(self) -> str:
        return self.qwen_model

    @property
    def model_label(self) -> str:
        return f"通义千问 {self.model_name}"

    @property
    def thinking_options(self) -> dict:
        return {"enable_thinking": True}


settings = Settings()
