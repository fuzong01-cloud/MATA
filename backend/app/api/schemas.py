from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Module = Literal["嵌入式开发", "Web开发", "Android开发", "虚拟仿真"]


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=10000)
    module: Module | None = None
    session_id: str | None = Field(default=None, min_length=1, max_length=64)
    student_key: str | None = Field(default=None, min_length=36, max_length=64)
    image_data_url: str | None = Field(default=None, max_length=7_000_000)


class SearchRequest(QuestionRequest):
    top_k: int = Field(default=5, ge=1, le=10)


class CodeRequest(BaseModel):
    language: Literal["auto", "python", "c", "cpp", "java", "javascript", "html", "css"] = "auto"
    module: Module | None = None
    filename: str | None = None
    context: str | None = Field(default=None, max_length=1000)
    session_id: str | None = Field(default=None, min_length=1, max_length=64)
    student_key: str | None = Field(default=None, min_length=36, max_length=64)
    code: str = Field(default="", max_length=20000)
    image_data_url: str | None = Field(default=None, max_length=7_000_000)


class SubmissionAttachment(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    data_base64: str = Field(min_length=1, max_length=14_000_000)


class AssignmentGradeRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    student_key: str | None = Field(default=None, min_length=36, max_length=64)
    work_text: str = Field(default="", max_length=60000)
    report_text: str = Field(default="", max_length=60000)
    work_files: list[SubmissionAttachment] = Field(default_factory=list, max_length=8)
    report_files: list[SubmissionAttachment] = Field(default_factory=list, max_length=4)
    retain_attachment_indexes: list[int] = Field(default_factory=list, max_length=12)


class AssignmentTutorTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=3000)


class AssignmentTutorRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1500)
    history: list[AssignmentTutorTurn] = Field(default_factory=list, max_length=8)


class LearningSummaryRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    student_key: str | None = Field(default=None, min_length=36, max_length=64)


class TeacherReviewRequest(BaseModel):
    status: Literal["pending", "approved", "needs_revision"]
    note: str | None = Field(default=None, max_length=2000)


class TeacherSubmissionReviewRequest(TeacherReviewRequest):
    final_score: float | None = Field(default=None, ge=0, le=100)


class StudentProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    student_number: str = Field(default="", max_length=40)
    class_name: str = Field(min_length=1, max_length=80)
