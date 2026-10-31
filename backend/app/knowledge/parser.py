from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

from pptx import Presentation


MODULES = ("嵌入式开发", "Web开发", "Android开发", "虚拟仿真")
PARSER_VERSION = 3


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


MONOSPACED_FONTS = ("consolas", "courier", "cascadia", "lucida console", "menlo", "monaco")

_PYTHON_LINE_PATTERNS = (
    re.compile(r"^\s*@\w[\w.]*(?:\(.*\))?\s*$"),
    re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+\w+"),
    re.compile(r"^\s*(?:try|except|finally|else|elif|if|for|while|with)\b.*:?\s*$"),
    re.compile(r"^\s*(?:return|raise|pass|break|continue|import|from)\b"),
    re.compile(r"^\s*(?:global|nonlocal|assert|del)\b"),
    re.compile(r"^\s*[\w.]+(?:\[[^\]]+\])?\s*=(?!=)"),
    re.compile(r"^\s*[\w.]+\s*\("),
)
_HTML_LINE_PATTERN = re.compile(r"^\s*(?:<!doctype\b|</?[a-z][^>]*>|/?[a-z][\w-]*\s*>|\{%.*%\}|\{\{.*\}\})", re.IGNORECASE)


def _indent_braced_code(lines: list[str]) -> list[str]:
    """Apply simple structural indentation to legacy JSON/CSS lines with no spaces."""
    if any(line[:1].isspace() for line in lines if line.strip()):
        return lines
    depth = 0
    result = []
    for line in lines:
        value = line.strip()
        if not value:
            result.append("")
            continue
        if value.startswith("}") or value.startswith("]"):
            depth = max(0, depth - 1)
        result.append("    " * depth + value)
        opens = value.count("{") + value.count("[")
        closes = value.count("}") + value.count("]")
        depth = max(0, depth + opens - closes)
    return result


def infer_code_language(lines: list[str]) -> str | None:
    """Return a language only when several consecutive lines strongly look like code."""
    values = [line.strip() for line in lines if line.strip()]
    if len(values) < 2:
        return None

    json_keys = sum(bool(re.match(r"^['\"][^'\"]+['\"]\s*:", line)) for line in values)
    if values[0].startswith(("{", "[")) and json_keys >= 2 and sum(x.count("{") + x.count("[") for x in values) >= 2:
        return "json"

    html_count = sum(bool(_HTML_LINE_PATTERN.match(line)) for line in values)
    html_anchor = any(re.match(r"^(?:<!doctype\b|<html\b|<script\b|</script\s*>|<body\b|</body\s*>)", line, re.IGNORECASE) for line in values)
    if html_count >= 4 and html_count / len(values) >= 0.42 or html_count >= 2 and html_anchor:
        return "html"

    java_count = sum(bool(re.search(r"\b(?:public\s+class|public\s+static\s+void\s+main|System\.out|import\s+java\.)", line)) for line in values)
    if java_count >= 2:
        return "java"

    js_patterns = (
        r"\b(?:const|let|var|function|fetch|document|window|async|await|console)\b",
        r"=>|\.then\s*\(|\.catch\s*\(|\.addEventListener\s*\(|\bsetInterval\s*\(|\bsetTimeout\s*\(",
        r"\.(?:classList|querySelector|getElementById|textContent|innerHTML|destroy)\b",
        r"\bnew\s+(?:Chart|Promise|Map|Set)\s*\(",
    )
    js_count = sum(any(re.search(pattern, line) for pattern in js_patterns) for line in values)
    js_statement_count = sum(bool(re.search(r"(?:;|\{\s*$|\}\s*;?$)", line)) for line in values)
    if (js_count >= 2 and js_count / len(values) >= 0.12) or (js_count >= 1 and js_statement_count >= 3):
        return "javascript"

    # Class/id selectors and actual element selectors distinguish CSS rules from
    # JavaScript object literals such as `options: {}` or `x: {}`.
    css_selectors = sum(bool(re.match(
        r"^(?:[.#][\w-]+(?:[.#][\w-]+)*|\*|(?:html|body|:root|div|span|main|nav|header|footer|h[1-6]|a|button|input|form|table|thead|tbody|tr|td|th|canvas))\s*(?:[,:{]|$)",
        line, re.IGNORECASE,
    )) for line in values)
    css_declarations = sum(bool(re.search(r"(?:^|[{;]\s*)[\w-]+\s*:\s*[^:;{}]+;?", line)) for line in values)
    if css_selectors >= 2 and css_declarations >= 3 and sum("{" in line for line in values) >= 2:
        return "css"

    python_count = sum(any(pattern.match(line) for pattern in _PYTHON_LINE_PATTERNS) for line in values)
    python_anchors = sum(bool(re.match(r"^(?:@\w|(?:async\s+)?(?:def|class)\s+|(?:try|except|finally)\b)", line)) for line in values)
    python_blocks = sum(bool(re.match(r"^(?:if|elif|else|for|while|try|except|finally|with)\b.*:\s*$", line)) for line in values)
    import_count = sum(bool(re.match(r"^(?:from|import)\s+", line)) for line in values)
    assignment_pattern = re.compile(r"^[A-Za-z_]\w*(?:\[[^\]]+\]|\.\w+)?\s*=(?!=)")
    assignment_count = sum(bool(assignment_pattern.match(line)) for line in values)
    python_dict = any(re.match(r"^[A-Za-z_]\w*\s*=\s*[\[{]", line) for line in values) and any(
        ":" in line or line.startswith("**") for line in values
    )
    python_assignments = sum(bool(assignment_pattern.match(line)) for line in values)
    python_exec_sql = any(re.search(r"\b\w+\.execute\s*\(", line) for line in values) and any(
        re.search(r"\b(?:SELECT|CREATE\s+TABLE|INSERT\s+INTO|UPDATE)\b", line, re.IGNORECASE)
        for line in values
    )
    if len(values) == 2 and python_assignments == 2:
        return "python"
    if python_count >= 3 and (python_anchors >= 2 or python_blocks >= 2 or import_count >= 3
                              or python_dict or assignment_count >= 3
                              or python_blocks >= 1 and python_count >= 4
                              or python_exec_sql or python_count >= 6 and python_count / len(values) >= 0.25):
        return "python"
    if python_dict or python_exec_sql:
        return "python"

    if re.match(r"^(?:GET|POST|PUT|PATCH|DELETE)\s+https?://", values[0], re.IGNORECASE) and any(
        re.match(r"^[A-Za-z-]+:\s*", line) for line in values[1:]
    ):
        return "http"

    shell_commands = {
        "cd", "mkdir", "rmdir", "dir", "ls", "python", "python3", "pip", "pip3", "source", "export",
        "set", "npm", "git", "curl", "copy", "copy-item", "activate", r".venv\scripts\activate.ps1",
    }
    shell_count = sum(
        bool(re.match(r"^\s*#(?:\s|!)", line)) or line.split(maxsplit=1)[0].lower() in shell_commands
        for line in values
    )
    if shell_count >= 3 and shell_count / len(values) >= 0.62:
        return "bash"

    sql_count = sum(bool(re.search(r"\b(?:SELECT|CREATE\s+TABLE|INSERT\s+INTO|UPDATE\s+\w+|DELETE\s+FROM|ORDER\s+BY)\b", line, re.IGNORECASE)) for line in values)
    if sql_count >= 2:
        return "sql"

    c_anchors = sum(bool(re.match(r"^\s*(?:#(?:include|define|ifdef|ifndef|endif|if|else|pragma)|(?:int|void|char|float|double|uint\w+_t)\s+\w+)", line)) for line in values)
    c_lines = sum(bool(re.search(r"[;{}]\s*$", line)) for line in values)
    c_macros = sum(bool(re.match(r"^\s*#(?:include|define|ifdef|ifndef|endif|if|else|pragma)\b", line)) for line in values)
    c_calls = sum(bool(re.match(r"^\s*[A-Za-z_]\w*(?:\s*->\s*\w+|\s*\.\s*\w+)?\s*\([^;]*\)\s*;?\s*$", line)) for line in values)
    if c_anchors >= 1 and (c_lines >= 3 or c_macros >= 3 or c_macros >= 1 and c_calls >= 2):
        return "cpp"
    return None


def restore_python_indentation(lines: list[str]) -> list[str]:
    """Infer only Python suite indentation when legacy export removed all leading spaces."""
    if any(line[:1].isspace() for line in lines if line.strip()):
        return lines

    output: list[str] = []
    suites: list[tuple[str, int]] = []
    indent = 0
    for raw in lines:
        line = raw.strip()
        if not line:
            output.append("")
            continue

        clause = re.match(r"^(except\b|finally\b|elif\b|else\s*:)", line)
        if clause:
            kind = "try" if line.startswith(("except", "finally")) else "branch"
            while suites and suites[-1][0] not in ({"try"} if kind == "try" else {"if", "branch"}):
                suites.pop()
            if suites:
                _, indent = suites.pop()
            else:
                indent = max(0, indent - 4)
        elif re.search(r"\b\w+\.close\s*\(", line) and any(kind == "try" for kind, _ in suites):
            # Common resource cleanup marks the end of an inner loop before the
            # enclosing try block's return/cleanup statements.
            while suites and suites[-1][0] in {"for", "while", "if", "with"}:
                suites.pop()
            try_suite = next((level for kind, level in reversed(suites) if kind == "try"), None)
            indent = (try_suite + 4) if try_suite is not None else indent

        output.append(" " * indent + line)
        header = re.match(r"^(?:async\s+)?(def|class|try|for|while|if|elif|else|with)\b.*:\s*$", line)
        if header:
            kind = header.group(1)
            suites.append((kind, indent))
            indent += 4
        elif clause and clause.group(1).startswith(("except", "finally")):
            suites.append(("try", indent))
            indent += 4
    return output


def restore_legacy_slash_code(value: str) -> str:
    """Restore only strongly recognizable legacy `` / ``-joined code runs.

    Older DOCX imports flattened table-cell paragraphs with this separator. A slash
    is treated as a line break only when the complete run has multiple code cues;
    ordinary prose, URLs, paths, and arithmetic expressions remain untouched.
    """
    output: list[str] = []
    in_fence = False
    fence_language = ""
    for line in value.splitlines():
        fence = re.match(r"^\s*```\s*([\w+-]*)", line)
        if fence:
            in_fence = not in_fence
            fence_language = fence.group(1).casefold() if in_fence else ""
            output.append(line)
            continue

        # Legacy records can split code across paragraph boundaries. Restore
        # clear separators inside existing fences without nesting new fences.
        parts = [part.strip() for part in re.split(r"\s+/\s+", line)]
        if in_fence:
            code_fence_languages = {
                "python", "py", "javascript", "js", "css", "html", "xml", "json", "bash", "sh", "sql", "cpp", "c", "java"
            }
            js_statements = all(re.match(r"^(?:[A-Za-z_$][\w.$]*\s*\(|(?:if|else|return|const|let|var|function)\b|[{}]+|//)", part) for part in parts)
            if len(parts) >= 2 and fence_language in code_fence_languages and (
                len(parts) >= 3 or infer_code_language(parts) or fence_language in {"javascript", "js"} and js_statements
            ):
                output.extend(parts)
            else:
                output.append(line)
            continue

        language = infer_code_language(parts)
        if language:
            if language == "python":
                parts = restore_python_indentation(parts)
            elif language in {"json", "css"}:
                parts = _indent_braced_code(parts)
            output.append(f"```{language}\n" + "\n".join(parts) + "\n```")
        else:
            output.append(line)
    return "\n".join(output)


def _is_monospace(name: str | None) -> bool:
    return bool(name and any(font in name.casefold() for font in MONOSPACED_FONTS))


def _plain_markdown_text(value: str) -> str:
    """Keep plain-text source literal when it could be parsed as a Markdown heading."""
    return re.sub(r"^(\s*)(#{1,6})(?=\s)", r"\1\\\2", value)


def _code_paragraph(paragraph) -> tuple[bool, str]:
    runs = [run for run in paragraph.runs if run.text.strip()]
    style_name = getattr(getattr(paragraph, "style", None), "name", "") or ""
    is_code = "code" in style_name.casefold() or "程序代码" in style_name
    is_code = is_code or bool(runs) and all(_is_monospace(run.font.name) for run in runs)
    # Paragraph.text preserves embedded hard breaks and leading spaces in PowerPoint.
    value = paragraph.text.replace("\u00a0", " ").replace("\u200b", "")
    return is_code, value if is_code else normalize_text(value)


def _format_paragraphs(paragraphs, heading_level: int | None = None) -> list[str]:
    """Render source paragraphs as conservative Markdown, fencing only styled code."""
    output: list[str] = []
    code_lines: list[str] = []

    def flush_code() -> None:
        if code_lines:
            output.append("```\n" + "\n".join(code_lines).rstrip("\n") + "\n```")
            code_lines.clear()

    for paragraph in paragraphs:
        is_code, value = _code_paragraph(paragraph)
        if not value.strip():
            if is_code:
                code_lines.append(value)
            else:
                flush_code()
            continue
        if is_code:
            code_lines.append(value.rstrip("\r\n"))
            continue
        flush_code()
        level = heading_level(paragraph) if callable(heading_level) else heading_level
        if level:
            output.append(f"{'#' * max(1, min(level, 6))} {value.strip()}")
        else:
            output.append(_paragraph_list_marker(paragraph) + _plain_markdown_text(value))
    flush_code()
    return output


def _paragraph_heading_level(paragraph) -> int | None:
    style_name = getattr(getattr(paragraph, "style", None), "name", "") or ""
    match = re.search(r"(?:heading|标题)\s*([1-6])", style_name, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _paragraph_list_marker(paragraph) -> str:
    properties = getattr(getattr(paragraph, "_p", None), "pPr", None)
    if properties is None:
        return ""
    namespace = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    if properties.find(f"{namespace}buNone") is not None:
        return ""
    level = min(max(int(getattr(paragraph, "level", 0) or 0), 0), 6)
    if properties.find(f"{namespace}buAutoNum") is not None:
        return "  " * level + "1. "
    if properties.find(f"{namespace}buChar") is not None:
        return "  " * level + "- "
    return ""


def shape_text(shape) -> list[str]:
    parts: list[str] = []
    if getattr(shape, "has_text_frame", False):
        is_title = False
        if getattr(shape, "is_placeholder", False):
            try:
                is_title = shape.placeholder_format.type in (1, 3)  # TITLE / CENTER_TITLE
            except (AttributeError, ValueError):
                pass
        parts.extend(_format_paragraphs(
            shape.text_frame.paragraphs,
            _paragraph_heading_level if not is_title else 1,
        ))
    if getattr(shape, "has_table", False):
        rows = [[normalize_text(cell.text).replace("|", "\\|") for cell in row.cells]
                for row in shape.table.rows]
        rows = [row for row in rows if any(row)]
        if rows:
            parts.append("| " + " | ".join(rows[0]) + " |")
            parts.append("| " + " | ".join("---" for _ in rows[0]) + " |")
            parts.extend("| " + " | ".join(row) + " |" for row in rows[1:])
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
        text = "\n\n".join(line for line in lines if line.strip()).strip()
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

    fenced_blocks = list(re.finditer(r"(?ms)^```[^\n]*\n.*?^```\s*$", text))
    if fenced_blocks:
        # Keep explicit source-code blocks intact for both reading and retrieval;
        # apply the usual overlap only to surrounding prose.
        chunks: list[str] = []
        cursor = 0
        for block in fenced_blocks:
            if block.start() > cursor:
                chunks.extend(_split_plain(text[cursor:block.start()], max_chars, overlap))
            chunks.append(block.group().strip("\n"))
            cursor = block.end()
        if cursor < len(text):
            chunks.extend(_split_plain(text[cursor:], max_chars, overlap))
        return [chunk for chunk in chunks if chunk.strip()]
    return _split_plain(text, max_chars, overlap)


def _split_plain(text: str, max_chars: int, overlap: int) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            boundary = text.rfind("\n", start + max_chars // 2, end)
            if boundary > start:
                end = boundary
        # Avoid trimming code indentation at chunk boundaries. A chunk may still split a
        # code block when a single paragraph exceeds the limit, but its text is intact.
        chunks.append(text[start:end].strip("\n"))
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return [chunk for chunk in chunks if chunk]
