from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.database.models import Base


def _database_url() -> str:
    url = settings.database_url
    if url.startswith("sqlite:///./"):
        path = settings.root / url.removeprefix("sqlite:///./")
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path.as_posix()}"
    return url


engine = create_engine(_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
    for table_name in ("conversations", "code_reviews", "assignment_submissions", "learning_summaries"):
        table_columns = {column["name"] for column in inspect(engine).get_columns(table_name)}
        if "student_key" not in table_columns:
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN student_key VARCHAR(64)"))
                connection.execute(text(f"CREATE INDEX ix_{table_name}_student_key ON {table_name} (student_key)"))
    document_columns = {column["name"] for column in inspect(engine).get_columns("documents")}
    if "source_type" not in document_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE documents ADD COLUMN source_type VARCHAR(16) NOT NULL DEFAULT 'pptx'"))
    if "storage_path" not in document_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE documents ADD COLUMN storage_path TEXT"))
    if "parser_version" not in document_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE documents ADD COLUMN parser_version INTEGER NOT NULL DEFAULT 1"))
    # Add session grouping to existing SQLite/MySQL databases without requiring a reset.
    columns = {column["name"] for column in inspect(engine).get_columns("conversations")}
    if "session_id" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN session_id VARCHAR(64)"))
            connection.execute(text(
                "CREATE INDEX ix_conversations_session_id ON conversations (session_id)"
            ))
    if "image_path" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN image_path TEXT"))
    if "mode" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN mode VARCHAR(32)"))
    if "review_status" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN review_status VARCHAR(24) NOT NULL DEFAULT 'pending'"))
    if "review_note" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE conversations ADD COLUMN review_note TEXT"))
    code_review_columns = {column["name"] for column in inspect(engine).get_columns("code_reviews")}
    if "code" not in code_review_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE code_reviews ADD COLUMN code TEXT NOT NULL DEFAULT ''"))
    if "module" not in code_review_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE code_reviews ADD COLUMN module VARCHAR(32)"))
    submission_columns = {column["name"] for column in inspect(engine).get_columns("assignment_submissions")}
    submission_migrations = {
        "teacher_review_status": "VARCHAR(24) NOT NULL DEFAULT 'pending'",
        "teacher_review_note": "TEXT",
        "teacher_final_score": "FLOAT",
        "teacher_reviewed_at": "DATETIME",
    }
    with engine.begin() as connection:
        for name, definition in submission_migrations.items():
            if name not in submission_columns:
                connection.execute(text(f"ALTER TABLE assignment_submissions ADD COLUMN {name} {definition}"))


def get_db():
    with SessionLocal() as session:
        yield session
