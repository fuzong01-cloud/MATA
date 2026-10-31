from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    zip_entry: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    zip_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False, default="pptx")
    parser_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    storage_path: Mapped[str | None] = mapped_column(Text)
    slide_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    slides: Mapped[list[Slide]] = relationship(back_populates="document", cascade="all, delete-orphan")
    assets: Mapped[list[DocumentAsset]] = relationship(back_populates="document", cascade="all, delete-orphan")


class DocumentAsset(Base):
    __tablename__ = "document_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_key: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(32), nullable=False)
    document: Mapped[Document] = relationship(back_populates="assets")


class MaterialRevision(Base):
    __tablename__ = "material_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    old_version: Mapped[str] = mapped_column(String(64), nullable=False)
    new_version: Mapped[str] = mapped_column(String(64), nullable=False)
    replaced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Slide(Base):
    __tablename__ = "slides"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    slide_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    document: Mapped[Document] = relationship(back_populates="slides")


class SlideVisual(Base):
    __tablename__ = "slide_visuals"
    __table_args__ = (UniqueConstraint("slide_id", name="uq_slide_visuals_slide_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slide_id: Mapped[int] = mapped_column(ForeignKey("slides.id", ondelete="CASCADE"), nullable=False, index=True)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=1280)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=720)
    mime_type: Mapped[str] = mapped_column(String(32), nullable=False, default="image/png")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    student_key: Mapped[str | None] = mapped_column(String(64), index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    module: Mapped[str | None] = mapped_column(String(32))
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    agent: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str | None] = mapped_column(String(32))
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    trace_json: Mapped[str] = mapped_column(Text, nullable=False)
    image_path: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    review_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CodeReview(Base):
    __tablename__ = "code_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    student_key: Mapped[str | None] = mapped_column(String(64), index=True)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    module: Mapped[str | None] = mapped_column(String(32))
    context: Mapped[str | None] = mapped_column(Text)
    code: Mapped[str] = mapped_column(Text, default="", nullable=False)
    local_status: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    analysis: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AssignmentSubmission(Base):
    __tablename__ = "assignment_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    student_key: Mapped[str | None] = mapped_column(String(64), index=True)
    assignment_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    assignment_title: Mapped[str] = mapped_column(String(255), nullable=False)
    module: Mapped[str] = mapped_column(String(32), nullable=False)
    work_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    report_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    attachments_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    acceptance_score: Mapped[float] = mapped_column(Float, nullable=False)
    report_score: Mapped[float] = mapped_column(Float, nullable=False)
    total_score: Mapped[float] = mapped_column(Float, nullable=False)
    evaluation_json: Mapped[str] = mapped_column(Text, nullable=False)
    assignment_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    assignment_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    revised_from_id: Mapped[int | None] = mapped_column(Integer)
    student_hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    teacher_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    teacher_review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    teacher_review_note: Mapped[str | None] = mapped_column(Text)
    teacher_final_score: Mapped[float | None] = mapped_column(Float)
    teacher_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AssignmentVersion(Base):
    __tablename__ = "assignment_versions"
    __table_args__ = (UniqueConstraint("assignment_id", "version", name="uq_assignment_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    scoring_rubric: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AssignmentReviewEvent(Base):
    __tablename__ = "assignment_review_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("assignment_submissions.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    final_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LearningSummary(Base):
    __tablename__ = "learning_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    student_key: Mapped[str | None] = mapped_column(String(64), index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    student_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    student_number: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    class_name: Mapped[str] = mapped_column(String(80), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
