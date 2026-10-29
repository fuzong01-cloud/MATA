"""Task and rubric catalog extracted from the two teacher-provided guidance manuals."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Document, Slide


TASK_HEADING = re.compile(r"^\s*任务\s*(?:[一二三四五六七八九十百]+|\d+)\s*[:：、\s]+\S.+$")
MANUALS = {
    180: ("Web开发", "WEB开发模块指导手册.docx"),
    181: ("嵌入式开发", "指导手册书(嵌入式、虚拟仿真、APP).docx"),
}


def _manual_lines(db: Session, document_id: int) -> list[str]:
    return [line.strip() for slide in db.scalars(
        select(Slide).where(Slide.document_id == document_id).order_by(Slide.slide_number)
    ) for line in (slide.text or "").splitlines() if line.strip()]


def _extract_range(lines: list[str], start: int, end: int, prefix: str,
                   module: str, source: str, serial_offset: int = 0) -> list[dict]:
    end = min(end, len(lines))
    headers = [i for i in range(start, end) if TASK_HEADING.match(lines[i])]
    found = []
    for number, begin in enumerate(headers, serial_offset + 1):
        stop = headers[number - serial_offset] if number - serial_offset < len(headers) else end
        # The extraction ranges deliberately exclude the table of contents and code appendices.
        section = "\n".join(lines[begin:stop])
        title = lines[begin].strip().strip("【】`*")
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
            "source": source, "description": description[:9000],
            "rubric": rubric[:5000], "scoring_rubric": scoring_rubric[:5000],
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
