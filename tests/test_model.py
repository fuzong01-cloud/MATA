from types import SimpleNamespace

import pytest

from app.agents import llm
from app.core.config import settings


EVIDENCE = [{
    "filename": "Web课程.pptx", "module": "Web开发", "slide_number": 12,
    "excerpt": "登录表单的 name 字段必须对应 request.form 中的键。",
}]


def test_model_stream_uses_slide_text_and_only_final_content(monkeypatch):
    monkeypatch.setattr(settings, "qwen_api_key", "test-only")
    calls = []

    class FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            calls.append(kwargs)
            return iter([
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None, reasoning_content="内部思考"))]),
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="字段应匹配 [1]"))]),
            ])

        def close(self):
            pass

    monkeypatch.setattr(llm, "create_model_client", FakeClient)
    answer = llm.generate_grounded_answer("登录表单字段？", "Web开发", EVIDENCE)
    assert answer == "字段应匹配 [1]"
    assert "Web课程.pptx" in calls[0]["messages"][1]["content"]
    assert "第 12 页" in calls[0]["messages"][1]["content"]
    assert calls[0]["stream"] is True
    assert calls[0]["extra_body"] == {"enable_thinking": True}
    assert "temperature" not in calls[0]


def test_model_rejects_uncited_or_invalid_citations(monkeypatch):
    monkeypatch.setattr(settings, "qwen_api_key", "test-only")

    class FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **_kwargs):
            return iter([SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="未提供的来源 [2]"))])])

        def close(self):
            pass

    monkeypatch.setattr(llm, "create_model_client", FakeClient)
    with pytest.raises(ValueError, match="有效的课件引用"):
        llm.generate_grounded_answer("登录表单字段？", "Web开发", EVIDENCE)
