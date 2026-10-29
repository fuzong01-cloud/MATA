import io
import zipfile

from pptx import Presentation

from app.knowledge.parser import module_for_name, parse_presentation, split_slide


def test_presentation_preserves_page_numbers_and_blank_status():
    presentation = Presentation()
    first = presentation.slides.add_slide(presentation.slide_layouts[6])
    first.shapes.add_textbox(0, 0, 1000000, 1000000).text = "ADAM-4017 接线"
    presentation.slides.add_slide(presentation.slide_layouts[6])
    stream = io.BytesIO()
    presentation.save(stream)
    slides = parse_presentation(stream.getvalue())
    assert [(slide.number, slide.status) for slide in slides] == [(1, "text"), (2, "blank")]
    assert "ADAM-4017" in slides[0].text


def test_modules_and_chunk_overlap():
    assert module_for_name("第8节 SQLite 数据库表结构设计核心规范.pptx") == "Android开发"
    assert module_for_name("第11节 传感器历史数据 SQLite 持久化存储.pptx") == "Android开发"
    assert module_for_name("第一节 模拟量传感器-农业气象站.pptx") == "虚拟仿真"
    text = "课件内容" * 300
    chunks = split_slide(text, max_chars=120, overlap=20)
    assert len(chunks) > 1
    assert chunks[0][-20:] == chunks[1][:20]


def test_invalid_ppt_raises():
    try:
        parse_presentation(b"not a presentation")
    except zipfile.BadZipFile:
        pass
    else:
        raise AssertionError("damaged PPTX must be reported")
