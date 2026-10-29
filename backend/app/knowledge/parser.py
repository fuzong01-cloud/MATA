from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from pptx import Presentation


MODULES = ("嵌入式开发", "Web开发", "Android开发", "虚拟仿真")


@dataclass(frozen=True)
class ParsedSlide:
    number: int
    text: str
    status: str
    error: str | None = None


def module_for_name(filename: str) -> str:
    path_parts = PurePosixPath(filename.replace("\\", "/")).parts
    parent_names = {part.casefold() for part in path_parts[:-1]}
    if "通用课程资料" in parent_names:
        return "通用课程资料"
    if "app开发" in parent_names:
        return "Android开发"
    if "web开发" in parent_names:
        return "Web开发"
    if "虚拟仿真" in parent_names:
        return "虚拟仿真"
    if "嵌入式开发" in parent_names:
        return "嵌入式开发"
    if re.match(r"^第\d+节", filename):
        return "Android开发"
    if re.match(r"^(?:\d+第|第\d+节)", filename) and any(x in filename.casefold() for x in ("flask", "web", "sql", "数据库")):
        return "Web开发"
    if filename.startswith(("1第一节", "2 左侧栏", "3 登录", "4 历史")):
        return "Web开发"
    if filename.startswith("农林物联网系统综合实训 - "):
        return "嵌入式开发"
    if "仿真" in filename or "传感器-" in filename:
        return "虚拟仿真"
    return "未分类"


def normalize_text(value: str) -> str:
    value = value.replace("\u00a0", " ").replace("\u200b", "")
    return re.sub(r"[ \t]+", " ", value).strip()


def shape_text(shape) -> list[str]:
    parts: list[str] = []
    if getattr(shape, "has_text_frame", False):
        for paragraph in shape.text_frame.paragraphs:
            line = normalize_text(paragraph.text)
            if line:
                parts.append(line)
    if getattr(shape, "has_table", False):
        for row in shape.table.rows:
            line = " | ".join(normalize_text(cell.text) for cell in row.cells)
            if line.strip(" |"):
                parts.append(line)
    if getattr(shape, "shape_type", None) == 6:  # group shape
        for child in shape.shapes:
            parts.extend(shape_text(child))
    return parts


def parse_presentation(data: bytes) -> list[ParsedSlide]:
    presentation = Presentation(io.BytesIO(data))
    slides: list[ParsedSlide] = []
    for number, slide in enumerate(presentation.slides, start=1):
        lines: list[str] = []
        errors: list[str] = []
        for shape in slide.shapes:
            try:
                lines.extend(shape_text(shape))
            except Exception as exc:  # preserve other shapes on the same slide
                errors.append(str(exc)[:120])
        text = "\n".join(lines).strip()
        status = "partial" if text and errors else "text" if text else "error" if errors else "blank"
        slides.append(ParsedSlide(number, text, status, "; ".join(errors)[:400] or None))
    return slides


def iter_ppt_entries(archive: zipfile.ZipFile):
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        if info.is_dir() or path.suffix.lower() != ".pptx":
            continue
        if info.file_size > 40_000_000:
            yield info, None, "文件超过 40 MB 限制"
            continue
        try:
            yield info, archive.read(info), None
        except Exception as exc:
            yield info, None, str(exc)[:400]


def split_slide(text: str, max_chars: int = 900, overlap: int = 120) -> list[str]:
    if not text.strip():
        return []
    if len(text) <= max_chars:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            boundary = text.rfind("\n", start + max_chars // 2, end)
            if boundary > start:
                end = boundary
        chunks.append(text[start:end].strip())
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return [chunk for chunk in chunks if chunk]
