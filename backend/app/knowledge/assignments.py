"""Task and rubric catalog extracted from the two teacher-provided guidance manuals."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Document, Slide
from app.knowledge.parser import restore_legacy_slash_code


TASK_HEADING = re.compile(r"^\s*(?:#{1,6}\s*)?任务\s*(?:[一二三四五六七八九十百]+|\d+)\s*[:：、\s]+\S.+$")
MANUALS = {
    180: ("Web开发", "WEB开发模块指导手册.docx"),
    181: ("嵌入式开发", "指导手册书(嵌入式、虚拟仿真、APP).docx"),
}


_C_CODE_LINE = re.compile(
    r"^\s*(?:#(?:include|define|ifdef|ifndef|endif|if|else|pragma)\b.*|"
    r"//.*|/\*.*|\*/|(?:extern\s+|static\s+|const\s+|volatile\s+)*(?:void|int|char|float|double|uint\w+_t|GPIO_\w+|RCC_\w+)\s+[*\w]+\s*(?:\[[^\]]*\]\s*)?(?:[=;(,\[]|$).*|"
    r"(?:if|else|for|while|switch|case|default|return|break|continue)\b.*|"
    r"[A-Za-z_]\w*(?:\s*\[[^\]]+\])?\s*(?:=|\+=|-=)\s*.+;\s*(?://.*)?$|"
    r"[A-Za-z_]\w*(?:\s*\[[^\]]+\])?\s*(?:\+\+|--)\s*;?\s*(?://.*)?$|"
    r"[A-Za-z_]\w*\s*,\s*\\?\s*$|"
    r"[A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)+\\?\s*$|"
    r"[A-Za-z_]\w*(?:\s*->\s*\w+|\s*\.\s*\w+)?\s*\([^;]*\)\s*;?\s*(?://.*)?$|"
    r"[{}]\s*;?\s*$)",
    re.IGNORECASE,
)
_JS_CODE_LINE = re.compile(
    r"^\s*(?://|(?:async\s+)?function\b|(?:const|let|var)\s+[\w$]+|"
    r"(?:if|else|for|while|switch|return|try|catch)\b|"
    r"(?:fetch|console|document|window|[A-Za-z_$][\w$]*)\s*(?:\.|\()|"
    r"[{}]\s*;?\s*$|[\w$.[\]'\"()+\-*/?:, ]+;\s*$)"
)
_CSS_CODE_LINE = re.compile(
    r"^\s*(?:[.#][\w-]+(?:[.#][\w-]+)*|(?:html|body|:root|div|span|main|nav|header|footer|h[1-6]|a|button|input|form|table|thead|tbody|tr|td|th|canvas)|\*|\})\s*(?:\{|,|$)|"
    r"^\s*[\w-]+\s*:\s*[^:;{}]+;?\s*$"
)


def _is_embedded_code_line(line: str, previous: str = "") -> bool:
    if _C_CODE_LINE.match(line):
        return True
    if re.match(r"^\s*[A-Za-z_]\w*\s*\([^)]*\)\s*;\s*(?://.*)?$", line):
        return True
    if re.match(r"^\s*[A-Za-z_]\w*(?:\s*\[[^\]]+\])?\s*=\s*.+(?:;|//.*)$", line):
        return True
    if re.match(r"^\s*[A-Za-z_]\w*(?:\s*\[[^\]]+\])?\s*(?:\+\+|--)\s*;?\s*(?://.*)?$", line):
        return True
    if previous.rstrip().endswith(("\\", ",")) and re.match(r"^\s*[A-Za-z_]\w*", line):
        return True
    return bool(re.match(r"^\s*(?:STM32_|GPIO_|RCC_|HAL_|TIM\d|LCD_|IIC\d?_?|NVIC_|Buzzer_|delay_ms|SMGSONGXIAN)\w*\s*\(", line))


def _split_joined_embedded_statements(value: str) -> str:
    """Restore semicolon boundaries in unmistakably flattened C call sequences."""
    output = []
    for line in value.splitlines():
        if not re.match(r"^\s*(?:STM32_|HAL_|GPIO_|RCC_|TIM\d|LCD_|IIC\d?_?|NVIC_|Buzzer_)\w*\s*\(", line) or line.count(";") < 2:
            output.append(line)
            continue
        pieces: list[str] = []
        start = depth = 0
        quote = ""
        escaped = False
        for index, char in enumerate(line):
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = ""
                continue
            if char in {"'", '"'}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth = max(0, depth - 1)
            elif char == ";" and depth == 0:
                pieces.append(line[start:index + 1].strip())
                start = index + 1
        if line[start:].strip():
            pieces.append(line[start:].strip())
        output.extend(pieces if len(pieces) >= 2 else [line])
    return "\n".join(output)


def _strip_legacy_c_fences(lines: list[str]) -> list[str]:
    """Remove stale fences around C examples so their boundaries can be rebuilt."""
    output = lines[:]
    open_index: int | None = None

    def is_c_region(start: int, end: int) -> bool:
        body = [line for line in lines[start:end] if line.strip()]
        candidates = [line for line in body if _C_CODE_LINE.match(line)]
        anchors = sum(bool(re.match(r"^\s*(?:#(?:include|define)|(?:void|int|char|uint\w+_t)\b)", line, re.IGNORECASE)) for line in body)
        return len(candidates) >= 3 and anchors >= 1 and len(candidates) / len(body) >= 0.5

    for index, line in enumerate(lines):
        if not re.match(r"^\s*```", line):
            continue
        if open_index is None:
            open_index = index
            continue
        if is_c_region(open_index + 1, index):
            output[open_index] = ""
            output[index] = ""
        open_index = None

    if open_index is not None and is_c_region(open_index + 1, len(lines)):
        output[open_index] = ""
    return output


def _fence_unmarked_code(value: str, *, embedded: bool = False) -> str:
    """Fence obvious legacy code runs whose DOCX font metadata was lost."""
    lines = value.splitlines()
    output: list[str] = []
    index = 0
    in_fence = False
    while index < len(lines):
        line = lines[index]
        if re.match(r"^\s*```", line):
            in_fence = not in_fence
            output.append(line)
            index += 1
            continue
        if not in_fence and re.match(r"^\s*(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=.+;\s*$", line):
            output.extend(["```javascript", line, "```"])
            index += 1
            continue
        matcher = _C_CODE_LINE if embedded else None
        is_code = _is_embedded_code_line(line) if embedded else bool(_JS_CODE_LINE.match(line) or _CSS_CODE_LINE.match(line))
        if in_fence or not is_code:
            output.append(line)
            index += 1
            continue

        language = "c" if embedded else "javascript" if _JS_CODE_LINE.match(line) else "css"
        matcher = _C_CODE_LINE if language == "c" else _JS_CODE_LINE if language == "javascript" else _CSS_CODE_LINE
        end = index + 1
        while end < len(lines) and not re.match(r"^\s*```", lines[end]):
            previous = lines[end - 1] if end > index else ""
            next_is_code = _is_embedded_code_line(lines[end], previous) if embedded else bool(matcher.match(lines[end]))
            if next_is_code:
                end += 1
                continue
            if not lines[end].strip() and end + 1 < len(lines) and matcher.match(lines[end + 1]):
                end += 1
                continue
            break
        run = lines[index:end]
        code_lines = sum(bool(re.search(r"[;{}]\s*$", item)) or bool(re.match(r"^\s*#", item)) or item.lstrip().startswith(("//", "/*", "*")) for item in run if item.strip())
        nonempty_lines = sum(bool(item.strip()) for item in run)
        min_lines = 1 if embedded else 3
        if embedded or nonempty_lines >= min_lines and code_lines / nonempty_lines >= 0.55:
            output.extend([f"```{language}", *run, "```"])
        else:
            output.extend(run)
        index = end
    return "\n".join(output)


def _merge_split_code_fences(value: str) -> str:
    """Join legacy fences that split a single code statement at a paragraph slash."""
    lines = value.splitlines()
    output: list[str] = []
    index = 0
    in_fence = False
    while index < len(lines):
        line = lines[index]
        if line.strip() == "```" and in_fence and index + 1 < len(lines):
            opening = re.match(r"^\s*```([\w+-]*)\s*$", lines[index + 1])
            previous = next((item for item in reversed(output) if item.strip()), "")
            continuation = previous.strip() in {"<", "</"} or bool(re.search(r"(?:\s/|[,([{])\s*$", previous))
            if opening and continuation:
                # The slash is the old DOCX paragraph separator, not source code.
                output[-1] = re.sub(r"\s+/\s*$", "", output[-1])
                following = lines[index + 2] if index + 2 < len(lines) else ""
                if output[-1].strip() in {"<", "</"} and re.match(r"^\s*[A-Za-z][\w-]*>", following):
                    output[-1] += following.strip()
                    index += 3
                    continue
                index += 2  # keep the existing block open; discard both markers
                if re.match(r"^\s*/\s+[^/]", lines[index] if index < len(lines) else ""):
                    lines[index] = re.sub(r"^\s*/\s+", "", lines[index])
                continue
        if re.match(r"^\s*```", line):
            in_fence = not in_fence
        output.append(line)
        index += 1
    cleaned: list[str] = []
    in_fence = False
    first_content = False
    for line in output:
        if re.match(r"^\s*```", line):
            in_fence = not in_fence
            first_content = in_fence
            cleaned.append(line)
            continue
        if in_fence:
            if first_content and re.match(r"^\s*/\s+[^/]", line):
                line = re.sub(r"^\s*/\s+", "", line)
            line = re.sub(r"\s+/\s*$", "", line)
            if line.strip():
                first_content = False
        cleaned.append(line)
    return "\n".join(cleaned)


def _format_pipe_tables(value: str) -> str:
    """Turn contiguous legacy pipe-delimited rows into actual Markdown tables."""
    output: list[str] = []
    lines = value.splitlines()
    index = 0
    in_fence = False
    while index < len(lines):
        line = lines[index]
        if re.match(r"^\s*```", line):
            in_fence = not in_fence
            output.append(line)
            index += 1
            continue
        if in_fence or line.count("|") < 1:
            output.append(line)
            index += 1
            continue
        end = index + 1
        while end < len(lines) and lines[end].count("|") >= 1 and not re.match(r"^\s*```", lines[end]):
            end += 1
        rows = [item.strip().strip("|").split("|") for item in lines[index:end]]
        rows = [[cell.strip() for cell in row] for row in rows]
        width = max(map(len, rows))
        rows = [row + [""] * (width - len(row)) for row in rows]
        if len(rows) >= 2:
            output.append("| " + " | ".join(rows[0]) + " |")
            if all(re.fullmatch(r":?-{3,}:?", cell) for cell in rows[1]):
                output.append("| " + " | ".join(rows[1]) + " |")
                output.extend("| " + " | ".join(row) + " |" for row in rows[2:])
            else:
                output.append("| " + " | ".join("---" for _ in range(width)) + " |")
                output.extend("| " + " | ".join(row) + " |" for row in rows[1:])
        else:
            output.append(line)
        index = end
    return "\n".join(output)


def _format_task_content(value: str, module: str = "") -> str:
    embedded = module == "嵌入式开发"
    if embedded:
        # Legacy embedded manual fences are often inserted in the middle of a C
        # macro continuation or loop. Rebuild code boundaries from the C lines so
        # one stray marker cannot turn the rest of the task into raw prose.
        value = "\n".join(line for line in value.splitlines() if not re.match(r"^\s*```", line))
        # This heading and function signature were concatenated in the legacy
        # manual record; the final i is the parameter name, not part of void.
        value = value.replace("形参 ivoid SMGSONGXIAN", "形参 i\nvoid SMGSONGXIAN")
        value = _split_joined_embedded_statements(value)
    else:
        value = "\n".join(_strip_legacy_c_fences(value.splitlines()))
    # `_manual_lines` already restored slash-joined code at source paragraph
    # boundaries. Re-running that transformation after dropping stale fences
    # would recreate partial and unbalanced C blocks.
    if not embedded:
        value = restore_legacy_slash_code(value)
        value = _merge_split_code_fences(value)
        value = re.sub(r"(?m)^(token\s*=\s*\{\}\s*#.*)$", r"```python\n\1\n```", value)
    value = _fence_unmarked_code(value, embedded=embedded)
    return _format_pipe_tables(value)


def _manual_lines(db: Session, document_id: int) -> list[str]:
    lines = []
    chunks = [slide.text or "" for slide in db.scalars(
        select(Slide).where(Slide.document_id == document_id).order_by(Slide.slide_number)
    )]
    for index in range(1, len(chunks)):
        first_line, separator, rest = chunks[index].partition("\n")
        previous = chunks[index - 1]
        # The legacy indexer sometimes cut a code token in half exactly at a
        # slide boundary. Repair that source boundary before interpreting /.
        if (re.search(r"[A-Za-z_][\w-]*[_-][\w-]*$", previous)
                and re.match(r"^[a-z][\w-]*\s*[:(;=]", first_line)):
            chunks[index - 1] += first_line
            chunks[index] = rest if separator else ""
    for chunk in chunks:
        # Existing course-manual records were imported by a legacy DOCX table
        # extractor that joined code paragraphs with " / ". Repair only complete,
        # high-confidence code runs before task sections are assembled.
        restored = restore_legacy_slash_code(chunk)
        chunk_lines = [line.rstrip() for line in restored.splitlines()]
        lines.extend(chunk_lines)
    return lines


def _extract_range(lines: list[str], start: int, end: int, prefix: str,
                   module: str, source: str, serial_offset: int = 0) -> list[dict]:
    end = min(end, len(lines))
    headers = [i for i in range(start, end) if TASK_HEADING.match(lines[i])]
    found = []
    for number, begin in enumerate(headers, serial_offset + 1):
        stop = headers[number - serial_offset] if number - serial_offset < len(headers) else end
        # The extraction ranges deliberately exclude the table of contents and code appendices.
        section = "\n".join(lines[begin:stop])
        title = re.sub(r"^\s*#{1,6}\s*", "", lines[begin]).strip().strip("【】`*")
        rubric_index = next((i for i, line in enumerate(lines[begin:stop])
                             if "任务考核点" in line or "评分标准" in line), None)
        rubric = "\n".join(lines[begin + rubric_index:stop]) if rubric_index is not None else ""
        excluded_rubric_terms = ("环境搭建", "虚拟环境创建", "IDE 安装", "IDE安装", "依赖安装", "项目目录结构")
        scoring_rubric = "\n".join(line for line in rubric.splitlines()
                                   if not any(term in line for term in excluded_rubric_terms))
        description = "\n".join(lines[begin:begin + rubric_index]) if rubric_index is not None else section
        task_id = f"{prefix}-{number}"
        found.append({
            "id": task_id, "module": module, "title": title,
            "source": source, "description": _format_task_content(description, module),
            "rubric": _format_task_content(rubric, module), "scoring_rubric": _format_task_content(scoring_rubric, module),
            "rubric_available": bool(rubric),
            "rubric_note": "" if rubric else "指导手册未列出分项分值；AI 将按任务要求和提交证据给出预评，结果需教师确认。",
        })
    return found


def assignment_catalog(db: Session) -> list[dict]:
    web_doc = db.scalar(select(Document).where(Document.filename == "WEB开发模块指导手册.docx"))
    guide_doc = db.scalar(select(Document).where(
        Document.filename == "指导手册书(嵌入式、虚拟仿真、APP).docx"))
    if not web_doc or not guide_doc:
        return []
    web = _manual_lines(db, web_doc.id)
    guide = _manual_lines(db, guide_doc.id)

    items = []
    # The Web manual contains the four-project track followed by a seven-task UI/API track.
    first_web_group = next((i for i, line in enumerate(web)
                            if line.startswith("任务二：实时数据监控与设备控制")), len(web))
    second_web_group = next((i for i, line in enumerate(web)
                             if line.startswith("任务一 用户登录界面设计")), len(web))
    items += _extract_range(web, 0, second_web_group, "web-project", "Web开发", web_doc.filename)
    items += _extract_range(web, second_web_group, len(web), "web-ui", "Web开发", web_doc.filename)

    # The embedded manual repeats its task headings in the table of contents, with
    # page numbers appended (for example "...照明灯6"). Start at the body heading.
    embedded_start = next((i for i, line in enumerate(guide)
                           if line.startswith("任务一 继电器控制风扇和照明灯")
                           and not re.search(r"\d+$", line)), None)
    if embedded_start is None:
        embedded_start = next((i for i, line in enumerate(guide)
                               if line.startswith("任务一 继电器控制风扇和照明灯")), 0)
    code_appendix = next((i for i, line in enumerate(guide[embedded_start:], embedded_start)
                          if line.startswith("附录2")), len(guide))
    simulation_start = next((i for i in range(code_appendix, len(guide))
                             if guide[i].startswith("任务一：农业气象站仿真系统")), len(guide))
    app_start = next((i for i in range(simulation_start, len(guide))
                      if guide[i].startswith("任务一 APP登录界面设计与实现")), len(guide))
    items += _extract_range(guide, embedded_start, code_appendix, "embedded", "嵌入式开发", guide_doc.filename)
    items += _extract_range(guide, simulation_start, app_start, "simulation", "虚拟仿真", guide_doc.filename)
    items += _extract_range(guide, app_start, len(guide), "android-app", "Android开发", guide_doc.filename)
    return items


def get_assignment(db: Session, task_id: str) -> dict | None:
    return next((item for item in assignment_catalog(db) if item["id"] == task_id), None)
