import io
import zipfile
from PIL import Image

from app.knowledge import uploaded_documents


def _docx_bytes(document_xml: str, styles_xml: str = "", numbering_xml: str = "") -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
        if styles_xml:
            archive.writestr("word/styles.xml", styles_xml)
        if numbering_xml:
            archive.writestr("word/numbering.xml", numbering_xml)
    return stream.getvalue()


def test_docx_extraction_keeps_headings_code_and_lists_without_slash_joining():
    document = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
      <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Flask 项目搭建</w:t></w:r></w:p>
      <w:p><w:r><w:t>步骤 1：创建项目目录</w:t></w:r></w:p>
      <w:p><w:r><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/></w:rPr><w:t xml:space="preserve">mkdir demog3</w:t></w:r></w:p>
      <w:p><w:r><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/></w:rPr><w:t xml:space="preserve">cd demog3</w:t></w:r></w:p>
      <w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>安装 Flask</w:t></w:r></w:p>
      <w:tbl><w:tr><w:tc><w:p><w:r><w:t>操作</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>说明</w:t></w:r></w:p></w:tc></w:tr>
        <w:tr><w:tc><w:p><w:r><w:t>创建目录</w:t></w:r></w:p><w:p><w:r><w:t>进入项目</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>C:\\work\\demo</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
      <w:sectPr/></w:body></w:document>'''
    styles = '''<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="Heading 1"/></w:style></w:styles>'''
    numbering = '''<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/></w:lvl></w:abstractNum>
      <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num></w:numbering>'''

    segments = uploaded_documents._word_segments(_docx_bytes(document, styles, numbering))
    text = "\n\n".join(segment.text for segment in segments)
    assert "# Flask 项目搭建" in text
    assert "```" in text
    assert "mkdir demog3\ncd demog3" in text
    assert "    mkdir" not in text  # the source did not indent this shell command
    assert "1. 安装 Flask" in text
    assert "| 操作 | 说明 |" in text
    assert "创建目录；进入项目" in text
    assert "C:\\\\work" in text or "C:\\work" in text
    assert " / 进入项目" not in text


def test_pdf_extraction_requests_layout_mode(monkeypatch):
    calls = []

    class Page:
        def extract_text(self, **kwargs):
            calls.append(kwargs)
            return "mkdir demo\n    python -m venv .venv"

    class Reader:
        is_encrypted = False
        pages = [Page()]

        def __init__(self, _stream):
            pass

    monkeypatch.setattr(uploaded_documents, "PdfReader", Reader)
    page = uploaded_documents._pdf_pages(b"pdf")[0]
    assert calls == [{"extraction_mode": "layout"}]
    assert "    python -m venv .venv" in page.text


def test_pdf_font_metadata_restores_heading_and_code_fences():
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Flask Project Setup", fontname="hebo", fontsize=20)
    page.insert_text((72, 110), "def main():", fontname="cour")
    page.insert_text((72, 124), "    # keep the comment", fontname="cour")
    page.insert_text((72, 138), "    return 4 / 2", fontname="cour")
    raw = document.tobytes()
    document.close()

    page_text = uploaded_documents._pdf_pages(raw)[0].text
    assert page_text.startswith("# Flask Project Setup") or page_text.startswith("## Flask Project Setup")
    assert "```" in page_text
    assert "    # keep the comment" in page_text
    assert "4 / 2" in page_text


def test_docx_inline_images_keep_a_safe_asset_reference():
    document = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
      xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>
      <w:p><w:r><w:t>接线图：</w:t></w:r><w:r><w:drawing><a:graphic><a:graphicData><a:blip r:embed="rId1"/></a:graphicData></a:graphic></w:drawing></w:r></w:p>
      <w:sectPr/></w:body></w:document>'''
    relations = '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Id="rId1" Target="media/image1.png" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"/>
      </Relationships>'''
    stream = io.BytesIO()
    Image.new("RGB", (2, 2), (15, 119, 116)).save(stream, format="PNG")
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("word/document.xml", document)
        archive.writestr("word/_rels/document.xml.rels", relations)
        archive.writestr("word/media/image1.png", stream.getvalue())

    text = "\n".join(segment.text for segment in uploaded_documents._word_segments(package.getvalue()))
    media = uploaded_documents._word_media(package.getvalue())
    assert "![课程配图](asset:rId1)" in text
    assert set(media) == {"rId1"}
    assert media["rId1"][0] == "image/png"


def test_docx_code_paragraphs_inside_table_keep_newlines_and_become_code_block():
    code_lines = [
        "@app.route('/sensor_historical_data')",
        "def sensor_historical_data():",
        "    try:",
        "        conn = sqlite3.connect('sensor_data.db')",
        "        rows = conn.cursor().fetchall()",
        "        return render_template('history.html', records=rows)",
    ]
    paragraphs = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in code_lines)
    document = f'''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
      <w:tbl><w:tr><w:tc>{paragraphs}</w:tc></w:tr></w:tbl>
      <w:sectPr/></w:body></w:document>'''

    text = "\n\n".join(segment.text for segment in uploaded_documents._word_segments(_docx_bytes(document)))
    assert "```python" in text
    assert "def sensor_historical_data():\n    try:\n        conn =" in text
    assert "| @app.route" not in text
