import io
import zipfile

from pptx import Presentation

from app.knowledge.parser import module_for_name, parse_presentation, restore_legacy_slash_code, split_slide


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


def test_split_slide_keeps_fenced_code_blocks_as_atomic_chunks():
    code = "```python\n" + "    value = 1\n" * 180 + "```"
    chunks = split_slide("intro\n\n" + code + "\n\nending", max_chars=100, overlap=10)
    assert code in chunks
    assert all(chunk.count("```") % 2 == 0 for chunk in chunks)


def test_invalid_ppt_raises():
    try:
        parse_presentation(b"not a presentation")
    except zipfile.BadZipFile:
        pass
    else:
        raise AssertionError("damaged PPTX must be reported")


def test_ppt_code_font_keeps_indentation_and_fences_hash_lines():
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    box = slide.shapes.add_textbox(0, 0, 5_000_000, 1_000_000)
    box.text_frame.paragraphs[0].text = "def read_value():"
    box.text_frame.paragraphs[0].runs[0].font.name = "Consolas"
    following = box.text_frame.add_paragraph()
    following.text = "    # keep this comment"
    following.runs[0].font.name = "Consolas"
    following = box.text_frame.add_paragraph()
    following.text = "    return 4 / 2"
    following.runs[0].font.name = "Consolas"
    stream = io.BytesIO()
    presentation.save(stream)

    text = parse_presentation(stream.getvalue())[0].text
    assert "```" in text
    assert "    # keep this comment" in text
    assert "4 / 2" in text


def test_plain_ppt_hash_line_is_preserved_verbatim():
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    slide.shapes.add_textbox(0, 0, 2_000_000, 500_000).text = "#include <stdio.h>"
    stream = io.BytesIO()
    presentation.save(stream)

    text = parse_presentation(stream.getvalue())[0].text
    assert text == "#include <stdio.h>"


def test_legacy_slash_joined_python_and_jinja_code_is_restored_conservatively():
    python = "@app.route('/sensor_historical_data') / def sensor_historical_data(): / try: / conn = sqlite3.connect('sensor_data.db') / c = conn.cursor() / rows = c.fetchall() / for row in rows: / records.append(row) / conn.close() / return render_template('history.html') / except Exception as e: / return f'Error: {str(e)}'"
    html = '<!DOCTYPE html> / <html lang="zh"> / <head> / <title>History</title> / </head> / <body> / <div class="container"> / {% block content %}{% endblock %} / </body> / </html>'

    restored_python = restore_legacy_slash_code(python)
    restored_html = restore_legacy_slash_code(html)
    assert restored_python.startswith("```python\n")
    assert "def sensor_historical_data():\n    try:\n        conn =" in restored_python
    assert "        for row in rows:\n            records.append(row)\n        conn.close()\n        return render_template" in restored_python
    assert restored_html.startswith("```html\n")
    assert "<head>\n<title>History</title>" in restored_html


def test_legacy_slash_recovery_does_not_split_paths_urls_or_arithmetic():
    source = "See C:/work/demo, https://example.test/a/b and 4 / 2; then use /sensor/data."
    assert restore_legacy_slash_code(source) == source


def test_legacy_slash_recovery_recognizes_subscript_assignment_pair():
    source = "new_state = 1 if control_state.get(device, 0) == 0 else 0 / control_state[device] = new_state"
    assert restore_legacy_slash_code(source) == (
        "```python\nnew_state = 1 if control_state.get(device, 0) == 0 else 0\n"
        "control_state[device] = new_state\n```"
    )


def test_legacy_slash_recovery_covers_other_common_manual_code_languages():
    samples = {
        "json": '{ / "Status": 0, / "ResultObj": { / "AccessToken": "token" / } / }',
        "bash": "# create project / mkdir demo / cd demo / python -m venv .venv",
        "css": "body { / margin: 0; / color: #333; / } / .card { / padding: 1rem; / }",
        "javascript": "const target = document.querySelector('#app'); / target.textContent = 'ready'; / function update(value) { / return value + 1; / }",
        "html": "div> / </div> / <script> / const value = 1; / </script>",
        "http": "GET https://api.example.test/data / Content-Type: application/json / AccessToken=token",
        "python": "cols = ', '.join(keys) / c.execute(f'''CREATE TABLE IF NOT EXISTS readings / (id INTEGER PRIMARY KEY, / {cols})''')",
    }
    for language, source in samples.items():
        restored = restore_legacy_slash_code(source)
        assert restored.startswith(f"```{language}\n"), (language, restored)
        assert " / " not in restored


def test_legacy_slash_recovery_handles_javascript_and_css_tail_fragments():
    javascript = "document.getElementById('status_msg').textContent = 'network error'; / }); / } / // start timer / updateSensorData(); / setInterval(updateSensorData, 5000); / </script>"
    css = " .status-bar.warning { border-left-color: #ff9800; } / .status-bar.danger { border-left-color: #f44336; } / .chart-container-live { / position: relative; / height: 420px; / }"
    chart = "function renderChart(key) { / if (historyChart) { / historyChart.destroy(); / } / historyChart = new Chart(ctx, { ... }); / }"

    assert restore_legacy_slash_code(javascript).startswith("```javascript\n")
    assert restore_legacy_slash_code(css).startswith("```css\n")
    assert restore_legacy_slash_code(chart).startswith("```javascript\n")


def test_slash_recovery_inside_existing_fence_does_not_nest_markdown_fences():
    source = "```javascript\nupdateSensorData(); / setInterval(updateSensorData, 5000);\n```"
    restored = restore_legacy_slash_code(source)
    assert restored.count("```") == 2
    assert "updateSensorData();\nsetInterval(updateSensorData, 5000);" in restored
