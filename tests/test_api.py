from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database.models import Base
from app.database.session import get_db
from app.main import app
from app.core.config import settings


STUDENT_KEY = "00000000-0000-4000-8000-000000000001"


def student_client() -> TestClient:
    client = TestClient(app)
    client.headers.update({"X-Student-Key": STUDENT_KEY})
    return client


def student_question(question: str, module: str | None = None) -> dict:
    return {"question": question, "module": module, "student_key": STUDENT_KEY}


def test_chat_records_only_used_evidence(monkeypatch):
    monkeypatch.setattr(settings, "qwen_api_key", "")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    def temporary_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = temporary_db
    monkeypatch.setattr("app.main.search_course", lambda *_args: [{
        "chunk_id": "test", "document_id": 1, "filename": "测试.pptx", "module": "Web开发",
        "slide_number": 3, "excerpt": "Flask 登录表单的 name 属性必须与 request.form 的字段一致。",
        "score": 0.81, "download_url": "/api/materials/1/download",
    }])
    try:
        client = student_client()
        response = client.post("/api/chat", json=student_question("Flask 登录表单字段如何对应？", "Web开发"))
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "offline_evidence"
        assert payload["agent"] == "experiment_guide"
        assert payload["evidence"][0]["slide_number"] == 3
        history = client.get("/api/conversations").json()
        assert len(history) == 1
        assert history[0]["trace"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_chat_uses_model_with_sufficient_slide_evidence(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    def temporary_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = temporary_db
    monkeypatch.setattr(settings, "qwen_api_key", "test-only")
    evidence = [{
        "chunk_id": "test", "document_id": 1, "filename": "课程.pptx", "module": "Web开发",
        "slide_number": 3, "excerpt": "Flask 表单字段应与 request.form 的字段一致。",
        "score": 0.82, "download_url": "/api/materials/1/download",
    }]
    monkeypatch.setattr("app.main.search_course", lambda *_args: evidence)
    calls = []

    def fake_generate(question, module, sources, *_args, **_kwargs):
        calls.append((question, module, sources))
        return "课件要求字段名保持一致。[1]"

    monkeypatch.setattr("app.main.generate_grounded_answer", fake_generate)
    try:
        client = student_client()
        response = client.post("/api/chat", json=student_question("Flask 表单字段如何对应？", "Web开发"))
        assert response.status_code == 200
        assert response.json()["mode"] == "model_grounded"
        assert response.json()["status"] == "answered_with_model"
        assert response.json()["evidence"][0]["slide_number"] == 3
        assert len(calls) == 1
        assert client.get("/api/conversations").json()[0]["mode"] == "model_grounded"

        monkeypatch.setattr("app.main.search_course", lambda *_args: [])
        monkeypatch.setattr("app.main.generate_general_answer", lambda *_args, **_kwargs: "这是通用分析。")
        response = client.post("/api/chat", json=student_question("课件没有的问题？"))
        assert response.json()["status"] == "answered_with_model_general"
        assert len(calls) == 1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_chat_falls_back_when_model_fails(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    def temporary_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = temporary_db
    monkeypatch.setattr(settings, "qwen_api_key", "test-only")
    monkeypatch.setattr("app.main.search_course", lambda *_args: [{
        "chunk_id": "test", "document_id": 1, "filename": "课程.pptx", "module": "Web开发",
        "slide_number": 3, "excerpt": "Flask 表单字段应与 request.form 的字段一致。",
        "score": 0.82, "download_url": "/api/materials/1/download",
    }])

    def fake_failure(*_args):
        raise RuntimeError("provider failure")

    monkeypatch.setattr("app.main.generate_grounded_answer", fake_failure)
    try:
        client = student_client()
        response = client.post("/api/chat", json=student_question("Flask 表单字段如何对应？"))
        assert response.status_code == 200
        assert response.json()["mode"] == "offline_fallback"
        assert response.json()["status"] == "answered_offline_fallback"
        assert response.json()["evidence"]
        assert "provider failure" not in str(response.json())
        assert client.get("/api/conversations").json()[0]["mode"] == "offline_fallback"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_code_endpoint_reports_syntax_error():
    client = student_client()
    response = client.post("/api/code/analyze", json={"language": "python", "code": "def f(: pass", "student_key": STUDENT_KEY})
    assert response.status_code == 200
    assert response.json()["status"] == "syntax_error"
