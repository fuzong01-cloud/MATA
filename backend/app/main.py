from __future__ import annotations

import io
import json
import base64
import binascii
import zipfile
import re
import uuid
import hmac
import hashlib
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pypdf import PdfReader
from sqlalchemy import delete as sql_delete, desc, func, select
from sqlalchemy.orm import Session

from app.agents.llm import (generate_assignment_grade, generate_assignment_guidance,
                             generate_code_review, generate_general_answer, generate_grounded_answer,
                             generate_learning_summary, GroundingValidationError, score_items_percent,
                             is_visual_question, synthesize_grounded_answers)
from app.agents.offline import (
    AgentResult,
    analyze_code_locally,
    detect_code_language,
    is_ambiguous_wiring_question,
    is_curriculum_overview_question,
    plan_agents,
    respond_offline,
    respond_course_overview,
    respond_smalltalk,
    retrieval_query,
)
from app.api.schemas import (AssignmentGradeRequest, AssignmentTutorRequest, CodeRequest,
                             LearningSummaryRequest, QuestionRequest, SearchRequest,
                             SubmissionAttachment, StudentProfileRequest, TeacherReviewRequest,
                             TeacherSubmissionReviewRequest)
from app.core.config import settings
from app.database.models import (AssignmentSubmission, CodeReview, Conversation, Document, DocumentAsset,
                                 LearningSummary, MaterialRevision, Slide, SlideVisual, StudentProfile)
from app.database.session import get_db, init_db
from app.knowledge.ingest import current_stats, import_course_zip
from app.knowledge.assignments import assignment_catalog, get_assignment
from app.knowledge.uploaded_documents import import_uploaded_document
from app.knowledge.vector import collection
from app.knowledge.parser import MODULES
from app.knowledge.search import search_course, search_course_overview
from app.knowledge.visual_ingest import import_slide_visuals


IMAGE_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def _require_teacher(x_teacher_code: str | None = Header(default=None)) -> None:
    if not settings.teacher_access_code:
        raise HTTPException(status_code=503, detail="教师访问码尚未配置，请在 .env 中设置 TEACHER_ACCESS_CODE")
    if not x_teacher_code or not hmac.compare_digest(x_teacher_code, settings.teacher_access_code):
        raise HTTPException(status_code=403, detail="教师访问码无效")


def _student_key(x_student_key: str | None = Header(default=None)) -> str:
    try:
        return str(uuid.UUID(x_student_key or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="学生身份标识无效") from exc


def _assert_student_key(provided: str | None, actual: str) -> None:
    if provided != actual:
        raise HTTPException(status_code=403, detail="学生身份与当前浏览器不一致")


def _submission_score(item: AssignmentSubmission) -> float:
    return item.teacher_final_score if item.teacher_review_status == "approved" and item.teacher_final_score is not None else item.total_score


def _decode_chat_image(data_url: str | None) -> tuple[str, bytes] | None:
    if not data_url:
        return None
    match = re.fullmatch(r"data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)", data_url)
    if not match:
        raise HTTPException(status_code=400, detail="图片只支持 PNG、JPEG 或 WebP")
    try:
        data = base64.b64decode(match.group(2), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="图片数据无效") from exc
    mime = match.group(1)
    valid = ((mime == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n")) or
             (mime == "image/jpeg" and data.startswith(b"\xff\xd8\xff")) or
             (mime == "image/webp" and data.startswith(b"RIFF") and data[8:12] == b"WEBP"))
    if not valid or not data or len(data) > 5_000_000:
        raise HTTPException(status_code=400, detail="图片格式不符或超过 5 MB")
    return mime, data


def _chat_image_url(item: Conversation) -> str | None:
    if not item.image_path or not item.student_key or not settings.media_signing_key:
        return None
    signature = hmac.new(settings.media_signing_key.encode(),
                         f"{item.id}:{item.student_key}".encode(), hashlib.sha256).hexdigest()
    return f"/api/conversations/{item.id}/image?token={signature}"


def _saved_image_data_url(item: Conversation) -> str | None:
    if not item.image_path:
        return None
    path = (settings.root / item.image_path).resolve()
    if not path.is_relative_to(settings.chat_upload_path.resolve()) or not path.is_file():
        return None
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}.get(path.suffix.lower())
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}" if mime else None


def _public_answer(answer: str) -> str:
    """Hide provider names and remove provider-specific boilerplate in saved conversations."""
    answer = re.sub(
        r"\s*（本轮使用\s*[^）]+?\s*通用知识回答，未找到足够相关的课程\s*PPT\s*依据。）\s*$",
        "", answer, flags=re.IGNORECASE,
    )
    return re.sub(r"(?:Qwen|通义千问)", "AI 模型", answer, flags=re.IGNORECASE)


def _public_trace(trace: list[str]) -> list[str]:
    return [re.sub(r"(?:Qwen(?:3\.8-Flash)?|通义千问)", "AI 模型", step, flags=re.IGNORECASE)
            for step in trace]


def _asks_general_concept(question: str) -> bool:
    if re.search(r"课件|PPT|教材|手册|资料(?:中|里)|老师(?:说|要求)", question, re.IGNORECASE):
        return False
    return bool(re.search(r"全称|缩写|英文名|是什么意思|什么是|为什么|作用|用途|原理|区别", question))


def _grounded_answer_lacks_answer(answer: str) -> bool:
    return bool(re.search(r"未说明|未提供|未涉及|未提到|没有说明|没有提供|没有涉及|没有提到", answer))


COURSE_TOPIC_PATTERN = re.compile(
    r"物联网|课程|课件|PPT|实训|实验|作业|任务|验收|评分|代码|程序|编程|报错|"
    r"传感器|采集|单片机|嵌入式|串口|接线|电路|开发|数据库|接口|云平台|服务器|"
    r"网络|通信|协议|寄存器|仿真|登录|表单|部署|网页|前端|后端|"
    r"Python|Flask|Android|Web|Java|C\+\+|HTML|CSS|JavaScript|SQLite|SQL|"
    r"ESP\d+|STM32|ADAM|Modbus|RTU|CRC|RS-?485|GPIO|HTTP|API|TCP|UDP|MQTT|"
    r"Arduino|Linux|Git|IDE|PLC",
    re.IGNORECASE,
)


def _is_course_question(question: str, has_image: bool, previous: list[Conversation]) -> bool:
    if COURSE_TOPIC_PATTERN.search(question):
        return True
    if has_image and not re.search(r"旅游|证件|购物|天气|娱乐|美食|明星|机场", question):
        return True
    is_followup = bool(re.search(r"这个|那个|它|上面|刚才|继续|接着|第二个|还有呢|呢[？?]?$", question))
    return is_followup and any(COURSE_TOPIC_PATTERN.search(turn.question) for turn in previous)


def _conversation_context(db: Session, session_id: str, student_key: str) -> list[Conversation]:
    return db.scalars(select(Conversation).where(Conversation.session_id == session_id,
                                                 Conversation.student_key == student_key)
                      .order_by(desc(Conversation.id)).limit(8)).all()[::-1]


def _clarification_choice(question: str, previous: list[Conversation]) -> dict | None:
    """Resolve an ordinal or equipment name against the last clarification's cited candidates."""
    if not previous:
        return None
    clarification = previous[-1]
    if clarification.status != "needs_clarification" and not clarification.status.endswith("_general"):
        return None
    try:
        candidates = json.loads(clarification.evidence_json)
    except (TypeError, json.JSONDecodeError):
        return None
    normalized = question.lower().strip()
    ordinal = re.search(r"(?:第\s*)?(\d+|一|二|两|三|四|五)\s*(?:个|条|项|张|页)?", normalized)
    if ordinal and len(normalized) <= 12:
        number = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5}.get(ordinal.group(1))
        number = int(ordinal.group(1)) if ordinal.group(1).isdigit() else number
        if number and 1 <= number <= len(candidates):
            return candidates[number - 1]
    tokens = set(re.findall(r"[a-z]+\s*-?\s*\d+|[a-z]{2,}|[\u4e00-\u9fff]{2,}", normalized))
    stop = {"这个", "那个", "我要", "第二", "第一个", "设备", "怎么", "如何", "接线"}
    tokens -= stop
    matches = []
    for item in candidates:
        source = f"{item.get('filename', '')} {item.get('excerpt', '')}".lower()
        score = sum(token.replace(" ", "") in source.replace(" ", "") for token in tokens)
        if score:
            matches.append((score, item))
    matches.sort(key=lambda result: result[0], reverse=True)
    if matches and (len(matches) == 1 or matches[0][0] > matches[1][0]):
        return matches[0][1]
    return None


def _recent_model_history(previous: list[Conversation]) -> list[dict[str, str]]:
    return [{"role": role, "content": content}
            for item in previous[-4:]
            for role, content in (("user", item.question), ("assistant", item.answer))]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="物联网综合实训课程多智能体协同助教系统", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-Student-Key", "X-Teacher-Code"],
)


@app.get("/api/status")
def status(db: Session = Depends(get_db)):
    model_configured = bool(settings.model_api_key)
    knowledge = current_stats(db)
    if model_configured and knowledge["visual_pages"]:
        message = f"AI 助教已就绪，已建立 {knowledge['visual_pages']} 页图像索引；视觉类问题可结合页面图像和课件文字回答。"
    elif model_configured:
        message = "AI 助教已就绪：优先依据课程资料回答，资料不足时会结合通用知识继续分析。"
    else:
        message = "当前使用本地课程资料检索；配置模型 API 后可启用 AI 问答。"
    return {
        "mode": "llm_rag_ready" if model_configured else "offline_evidence",
        "model_configured": model_configured,
        "message": message,
        "modules": MODULES,
        "knowledge": knowledge,
    }


@app.get("/api/student/profile")
def student_profile(student_key: str = Depends(_student_key), db: Session = Depends(get_db)):
    profile = db.get(StudentProfile, student_key)
    return {"student_key": student_key, "name": profile.name if profile else "",
            "student_number": profile.student_number if profile else "",
            "class_name": profile.class_name if profile else "", "registered": bool(profile)}


@app.put("/api/student/profile")
def save_student_profile(payload: StudentProfileRequest, student_key: str = Depends(_student_key),
                         db: Session = Depends(get_db)):
    name, class_name = payload.name.strip(), payload.class_name.strip()
    if not name or not class_name:
        raise HTTPException(status_code=400, detail="请填写姓名和班级")
    profile = db.get(StudentProfile, student_key)
    if profile is None:
        profile = StudentProfile(student_key=student_key, name=name, class_name=class_name)
        db.add(profile)
    else:
        profile.name, profile.class_name = name, class_name
    profile.student_number = payload.student_number.strip()
    db.commit()
    return {"student_key": student_key, "name": profile.name,
            "student_number": profile.student_number, "class_name": profile.class_name,
            "registered": True}


@app.get("/api/student/progress")
def student_progress(student_key: str = Depends(_student_key), db: Session = Depends(get_db)):
    questions = db.scalars(select(Conversation).where(Conversation.student_key == student_key)).all()
    reviews = db.scalars(select(CodeReview).where(CodeReview.student_key == student_key)).all()
    summaries = db.scalars(select(LearningSummary).where(LearningSummary.student_key == student_key)).all()
    submissions = db.scalars(select(AssignmentSubmission).where(
        AssignmentSubmission.student_key == student_key).order_by(desc(AssignmentSubmission.id))).all()
    latest = {}
    for item in submissions:
        latest.setdefault(item.assignment_id, item)
    module_activity = defaultdict(lambda: {"questions": 0, "code_reviews": 0, "submitted_tasks": 0})
    for item in questions:
        module_activity[item.module or "未指定模块"]["questions"] += 1
    for item in reviews:
        module_activity[item.module or "未指定模块"]["code_reviews"] += 1
    for item in latest.values():
        module_activity[item.module]["submitted_tasks"] += 1
    tasks = [{"assignment_id": item.assignment_id, "title": item.assignment_title,
              "module": item.module, "score": _submission_score(item),
              "teacher_review_status": item.teacher_review_status,
              "submitted_at": item.created_at.isoformat()}
             for item in latest.values()]
    return {"totals": {"questions": len(questions), "code_reviews": len(reviews),
                       "learning_summaries": len(summaries), "submitted_tasks": len(tasks)},
            "modules": [{"name": name, **value} for name, value in sorted(module_activity.items())],
            "tasks": tasks}


@app.get("/api/assignments")
def assignments(module: str | None = None, db: Session = Depends(get_db)):
    items = assignment_catalog(db)
    if module and module in MODULES:
        items = [item for item in items if item["module"] == module]
    return {"items": [{**item, "description": item["description"][:1800],
                        "rubric": item["rubric"][:1800]} for item in items],
            "total": len(items), "modules": MODULES}


@app.get("/api/assignments/{assignment_id}")
def assignment_detail(assignment_id: str, db: Session = Depends(get_db)):
    item = get_assignment(db, assignment_id)
    if not item:
        raise HTTPException(status_code=404, detail="未找到该指导手册任务")
    return item


def _read_submission_attachment(filename: str, encoded: str):
    safe_name = Path(filename.replace("\\", "/")).name[:255]
    extension = Path(safe_name).suffix.lower()
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail=f"附件 {safe_name} 编码无效") from exc
    if not raw or len(raw) > 10_000_000:
        raise HTTPException(status_code=400, detail=f"附件 {safe_name} 为空或超过 10 MB")
    image_types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    if extension in image_types:
        mime = image_types[extension]
        if not _decode_chat_image(f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"):
            raise HTTPException(status_code=400, detail=f"附件 {safe_name} 图片数据无效")
        return safe_name, raw, "", f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
    try:
        if extension in {".txt", ".py", ".c", ".h", ".cpp", ".hpp", ".java", ".js", ".html", ".css", ".json", ".xml", ".md", ".ino", ".sql"}:
            text = raw.decode("utf-8-sig")
        elif extension == ".docx":
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if "word/document.xml" not in archive.namelist() or archive.getinfo("word/document.xml").file_size > 10_000_000:
                    raise ValueError("Word 正文无效或过大")
                root = __import__("xml.etree.ElementTree", fromlist=["ElementTree"]).fromstring(archive.read("word/document.xml"))
            text = "\n".join("".join(node.text or "" for node in p.iter() if node.tag.endswith("}t"))
                              for p in root.iter() if p.tag.endswith("}p"))
        elif extension == ".pdf":
            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted or len(reader.pages) > 150:
                raise ValueError("PDF 加密或超过 150 页")
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        elif extension == ".zip":
            snippets = []
            text_extensions = {".txt", ".py", ".c", ".h", ".cpp", ".hpp", ".java", ".js", ".html", ".css", ".json", ".xml", ".md", ".ino", ".sql"}
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                for item in archive.infolist():
                    if item.is_dir() or Path(item.filename).suffix.lower() not in text_extensions:
                        continue
                    if item.file_size > 250_000 or len(snippets) >= 40:
                        continue
                    try:
                        snippets.append(f"### {item.filename}\n{archive.read(item).decode('utf-8-sig', errors='replace')[:12000]}")
                    except (KeyError, OSError):
                        continue
            text = "\n\n".join(snippets)
        else:
            raise HTTPException(status_code=400, detail=f"附件 {safe_name} 暂不支持；可提交 DOCX、PDF、ZIP、代码文件或图片")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"附件 {safe_name} 解析失败：{str(exc)[:160]}") from exc
    if not text.strip():
        raise HTTPException(status_code=400, detail=f"附件 {safe_name} 未提取到可评分的文本内容")
    return safe_name, raw, text[:80000], None


@app.post("/api/assignments/{assignment_id}/questions")
def assignment_question(assignment_id: str, request: AssignmentTutorRequest,
                        db: Session = Depends(get_db)):
    assignment = get_assignment(db, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="未找到该指导手册任务")
    try:
        answer = generate_assignment_guidance(
            assignment, request.question,
            [{"role": turn.role, "content": turn.content} for turn in request.history[-8:]],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"作业答疑暂不可用：{str(exc)[:200]}") from exc
    return {"answer": answer}


@app.post("/api/assignments/{assignment_id}/grade")
def grade_assignment(assignment_id: str, request: AssignmentGradeRequest,
                     db: Session = Depends(get_db), student_key: str = Depends(_student_key)):
    _assert_student_key(request.student_key, student_key)
    assignment = get_assignment(db, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="未找到该指导手册任务")
    if not request.work_text.strip() and not request.work_files:
        raise HTTPException(status_code=400, detail="请提交作品、代码或验收证据")
    if not request.report_text.strip() and not request.report_files:
        raise HTTPException(status_code=400, detail="请同时提交实验报告，课程总评中报告占 30%")

    total_bytes = 0
    work_parts, report_parts, images, stored_files, attachment_names = [], [], [], [], []
    for group, attachments, label in (("work", request.work_files, "作品"),
                                      ("report", request.report_files, "报告")):
        for item in attachments:
            name, raw, extracted, image_url = _read_submission_attachment(item.filename, item.data_base64)
            total_bytes += len(raw)
            if total_bytes > 30_000_000:
                raise HTTPException(status_code=400, detail="本次提交附件总量不得超过 30 MB")
            attachment_names.append(f"{label}：{name}")
            stored_files.append((group, name, raw))
            if extracted:
                (work_parts if group == "work" else report_parts).append(f"【附件：{name}】\n{extracted}")
            if image_url:
                images.append(image_url)
    work = "\n\n".join([request.work_text.strip(), *work_parts]).strip()
    report = "\n\n".join([request.report_text.strip(), *report_parts]).strip()
    try:
        raw_result = generate_assignment_grade(assignment, work, report, attachment_names, images)
        match = re.search(r"\{[\s\S]*\}", raw_result)
        if not match:
            raise ValueError("模型返回内容不是可解析的评分 JSON")
        result = json.loads(match.group(0))
        excluded_terms = ("环境搭建", "虚拟环境", "IDE安装", "IDE 安装", "依赖安装", "依赖配置", "项目目录", "目录结构", "软件安装")
        reviewed_items = []
        for item in result.get("acceptance_items", []):
            if not isinstance(item, dict):
                continue
            criterion = str(item.get("criterion", ""))
            if any(term in criterion for term in excluded_terms):
                continue
            reviewed_items.append(item)
        result["acceptance_items"] = reviewed_items
        acceptance = score_items_percent(reviewed_items, "现场验收")
        report_score = score_items_percent(result.get("report_items"), "实验报告")
        for field in ("issues", "next_steps"):
            if isinstance(result.get(field), list):
                result[field] = [item for item in result[field] if not any(term in str(item) for term in excluded_terms)]
        result["acceptance_score"] = round(acceptance, 2)
        result["report_score"] = round(report_score, 2)
        result["total_score"] = round(acceptance * 0.7 + report_score * 0.3, 2)
        result["policy_version"] = "code_function_focus_v2"
        result["scoring_policy_note"] = "现场验收按代码实现和功能完整度评分；环境搭建、软件安装、依赖配置不计分。"
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI 验收评分失败：{str(exc)[:220]}") from exc

    settings.submission_path.mkdir(parents=True, exist_ok=True)
    submission_dir = settings.submission_path / uuid.uuid4().hex
    submission_dir.mkdir(parents=True, exist_ok=False)
    attachment_records = []
    for group, name, raw in stored_files:
        saved_name = f"{uuid.uuid4().hex}_{name}"
        (submission_dir / saved_name).write_bytes(raw)
        attachment_records.append({"group": group, "filename": name,
                                   "path": (submission_dir / saved_name).relative_to(settings.root).as_posix()})
    record = AssignmentSubmission(
        session_id=request.session_id, student_key=request.student_key,
        assignment_id=assignment_id,
        assignment_title=assignment["title"], module=assignment["module"],
        work_text=request.work_text.strip(), report_text=request.report_text.strip(),
        attachments_json=json.dumps(attachment_records, ensure_ascii=False),
        acceptance_score=result["acceptance_score"], report_score=result["report_score"],
        total_score=result["total_score"], evaluation_json=json.dumps(result, ensure_ascii=False),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {**result, "submission_id": record.id, "assignment_id": assignment_id,
            "created_at": record.created_at.isoformat(), "attachments": [
                {"group": item["group"], "filename": item["filename"]} for item in attachment_records]}


@app.get("/api/assignments/{assignment_id}/submissions")
def assignment_submissions(assignment_id: str, session_id: str | None = None, db: Session = Depends(get_db),
                           student_key: str = Depends(_student_key)):
    records = db.scalars(select(AssignmentSubmission).where(
        AssignmentSubmission.assignment_id == assignment_id,
        AssignmentSubmission.student_key == student_key,
    ).order_by(desc(AssignmentSubmission.id)).limit(10)).all()
    return [{"submission_id": item.id, "assignment_id": item.assignment_id,
             "assignment_title": item.assignment_title, "module": item.module,
             "acceptance_score": item.acceptance_score, "report_score": item.report_score,
             "total_score": item.total_score, "evaluation": json.loads(item.evaluation_json),
             "teacher_review_status": item.teacher_review_status,
             "teacher_review_note": item.teacher_review_note,
             "teacher_final_score": item.teacher_final_score,
             "created_at": item.created_at.isoformat(),
             "attachments": [{"index": index, "group": attachment["group"],
                              "filename": attachment["filename"]}
                             for index, attachment in enumerate(json.loads(item.attachments_json))]} for item in records]


def _owned_submission(db: Session, assignment_id: str, submission_id: int,
                      student_key: str) -> AssignmentSubmission:
    record = db.get(AssignmentSubmission, submission_id)
    if not record or record.assignment_id != assignment_id or record.student_key != student_key:
        raise HTTPException(status_code=404, detail="未找到本会话中的提交记录")
    return record


def _submission_attachment_path(path_value: str) -> Path:
    path = (settings.root / path_value).resolve()
    if not path.is_relative_to(settings.submission_path.resolve()):
        raise HTTPException(status_code=400, detail="提交附件路径无效")
    return path


def _remove_submission_files(record: AssignmentSubmission) -> None:
    for attachment in json.loads(record.attachments_json):
        path = _submission_attachment_path(attachment["path"])
        path.unlink(missing_ok=True)
        if path.parent != settings.submission_path.resolve():
            try:
                path.parent.rmdir()
            except OSError:
                pass


@app.get("/api/assignments/{assignment_id}/submissions/{submission_id}")
def assignment_submission_detail(assignment_id: str, submission_id: int, session_id: str | None = None,
                                 db: Session = Depends(get_db),
                                 student_key: str = Depends(_student_key)):
    record = _owned_submission(db, assignment_id, submission_id, student_key)
    return {"submission_id": record.id, "work_text": record.work_text,
            "report_text": record.report_text,
            "teacher_review_status": record.teacher_review_status,
            "teacher_review_note": record.teacher_review_note,
            "teacher_final_score": record.teacher_final_score,
            "attachments": [{"index": index, "group": item["group"], "filename": item["filename"]}
                            for index, item in enumerate(json.loads(record.attachments_json))]}


@app.put("/api/assignments/{assignment_id}/submissions/{submission_id}")
def revise_assignment_submission(assignment_id: str, submission_id: int,
                                 request: AssignmentGradeRequest,
                                 db: Session = Depends(get_db),
                                 student_key: str = Depends(_student_key)):
    _assert_student_key(request.student_key, student_key)
    record = _owned_submission(db, assignment_id, submission_id, student_key)
    prior_attachments = json.loads(record.attachments_json)
    retained_work, retained_report = [], []
    for index in dict.fromkeys(request.retain_attachment_indexes):
        if index < 0 or index >= len(prior_attachments):
            raise HTTPException(status_code=400, detail="保留附件编号无效")
        item = prior_attachments[index]
        path = _submission_attachment_path(item["path"])
        if not path.is_file():
            raise HTTPException(status_code=400, detail=f"原附件 {item['filename']} 已丢失")
        packed = SubmissionAttachment(filename=item["filename"],
                                      data_base64=base64.b64encode(path.read_bytes()).decode("ascii"))
        (retained_work if item["group"] == "work" else retained_report).append(packed)
    if len(retained_work) + len(request.work_files) > 8 or len(retained_report) + len(request.report_files) > 4:
        raise HTTPException(status_code=400, detail="修订后的附件数量超过限制")
    revised_request = AssignmentGradeRequest(
        session_id=request.session_id, student_key=record.student_key or request.student_key,
        work_text=request.work_text,
        report_text=request.report_text,
        work_files=[*retained_work, *request.work_files],
        report_files=[*retained_report, *request.report_files],
    )
    result = grade_assignment(assignment_id, revised_request, db, student_key)
    db.delete(record)
    db.commit()
    _remove_submission_files(record)
    return {**result, "revised_from": submission_id}


@app.delete("/api/assignments/{assignment_id}/submissions/{submission_id}")
def delete_assignment_submission(assignment_id: str, submission_id: int, session_id: str | None = None,
                                 db: Session = Depends(get_db),
                                 student_key: str = Depends(_student_key)):
    record = _owned_submission(db, assignment_id, submission_id, student_key)
    db.delete(record)
    db.commit()
    _remove_submission_files(record)
    return {"deleted": True, "submission_id": submission_id}


@app.post("/api/assignments/{assignment_id}/submissions/{submission_id}/regrade")
def regrade_assignment(assignment_id: str, submission_id: int, session_id: str | None = None,
                       db: Session = Depends(get_db), student_key: str = Depends(_student_key)):
    record = db.get(AssignmentSubmission, submission_id)
    if not record or record.assignment_id != assignment_id or record.student_key != student_key:
        raise HTTPException(status_code=404, detail="未找到本会话中的提交记录")
    work_files, report_files = [], []
    for attachment in json.loads(record.attachments_json):
        path = _submission_attachment_path(attachment["path"])
        if not path.is_file():
            continue
        packed = SubmissionAttachment(filename=attachment["filename"],
                                      data_base64=base64.b64encode(path.read_bytes()).decode("ascii"))
        (work_files if attachment["group"] == "work" else report_files).append(packed)
    request = AssignmentGradeRequest(session_id=record.session_id, student_key=record.student_key,
                                     work_text=record.work_text, report_text=record.report_text,
                                     work_files=work_files, report_files=report_files)
    return grade_assignment(assignment_id, request, db, student_key)


@app.post("/api/materials/import", dependencies=[Depends(_require_teacher)])
def import_materials(force: bool = False, db: Session = Depends(get_db)):
    try:
        return import_course_zip(db, force=force)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/knowledge/visuals/import", dependencies=[Depends(_require_teacher)])
def import_visuals(db: Session = Depends(get_db)):
    try:
        return import_slide_visuals(db)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/materials")
def materials(db: Session = Depends(get_db)):
    documents = db.scalars(select(Document).order_by(Document.module, Document.filename)).all()
    return [{
        "id": item.id, "filename": item.filename, "module": item.module,
        "slide_count": item.slide_count, "source_type": item.source_type,
        "version": item.zip_sha256[:12], "created_at": item.created_at.isoformat(),
        "unit_label": "片段" if item.source_type == "docx" else "页",
    } for item in documents]


@app.get("/api/materials/{document_id}/assets/{asset_id}")
def material_asset(document_id: int, asset_id: int, db: Session = Depends(get_db)):
    asset = db.scalar(select(DocumentAsset).where(
        DocumentAsset.id == asset_id, DocumentAsset.document_id == document_id))
    if asset is None:
        raise HTTPException(status_code=404, detail="课程资料图片不存在")
    image_path = (settings.root / asset.storage_path).resolve()
    if not image_path.is_relative_to(settings.material_upload_path.resolve()) or not image_path.is_file():
        raise HTTPException(status_code=404, detail="课程资料图片文件不存在")
    return FileResponse(image_path, media_type=asset.mime_type,
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=86400, immutable"})


@app.post("/api/materials/upload", dependencies=[Depends(_require_teacher)])
async def upload_material(request: Request, filename: str, module: str, ocr: bool = False,
                          db: Session = Depends(get_db)):
    if module not in MODULES:
        raise HTTPException(status_code=400, detail="请选择有效的课程模块")
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > 20_000_000:
        raise HTTPException(status_code=413, detail="资料超过 20 MB")
    data = await request.body()
    try:
        safe_name = filename.replace("\\", "/").split("/")[-1].strip()
        old_documents = db.scalars(select(Document).where(
            Document.filename == safe_name, Document.module == module,
            Document.source_type == Path(safe_name).suffix.lower().lstrip("."))).all()
        result = import_uploaded_document(db, filename, module, data, ocr=ocr)
        new_document = db.get(Document, result["document_id"])
        for old in old_documents:
            if old.id != result["document_id"]:
                old_id, old_digest = old.id, old.zip_sha256
                delete_uploaded_material(old_id, db)
                if old_digest != new_document.zip_sha256:
                    db.add(MaterialRevision(filename=safe_name, module=module,
                                            source_type=Path(safe_name).suffix.lower().lstrip("."),
                                            old_version=old_digest,
                                            new_version=new_document.zip_sha256))
                    db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="资料解析或索引失败，请检查文件格式") from exc


@app.delete("/api/materials/{document_id}", dependencies=[Depends(_require_teacher)])
def delete_uploaded_material(document_id: int, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="资料不存在")
    if document.source_type == "pptx":
        raise HTTPException(status_code=400, detail="ZIP 课件请通过重新导入管理")
    ids = [item for item in collection().get(include=[])["ids"]
           if item.startswith(f"d{document.id}-")]
    asset_paths = [(settings.root / item.storage_path).resolve() for item in db.scalars(
        select(DocumentAsset).where(DocumentAsset.document_id == document.id)).all()]
    storage_path = (settings.root / document.storage_path).resolve() if document.storage_path else None
    slide_ids = select(Slide.id).where(Slide.document_id == document.id)
    db.execute(sql_delete(SlideVisual).where(SlideVisual.slide_id.in_(slide_ids)))
    db.execute(sql_delete(Slide).where(Slide.document_id == document.id))
    db.execute(sql_delete(DocumentAsset).where(DocumentAsset.document_id == document.id))
    db.delete(document)
    db.commit()
    for start in range(0, len(ids), 500):
        collection().delete(ids=ids[start:start + 500])
    if storage_path and storage_path.is_relative_to(settings.material_upload_path.resolve()):
        storage_path.unlink(missing_ok=True)
    for asset_path in asset_paths:
        if asset_path.is_relative_to(settings.material_upload_path.resolve()):
            asset_path.unlink(missing_ok=True)
    return {"deleted": True, "document_id": document_id}


@app.get("/api/teacher/overview", dependencies=[Depends(_require_teacher)])
def teacher_overview(db: Session = Depends(get_db)):
    documents = db.scalars(select(Document).order_by(Document.module, Document.filename)).all()
    questions = db.scalars(select(Conversation).order_by(desc(Conversation.id)).limit(40)).all()
    module_counts = {}
    for item in documents:
        current = module_counts.setdefault(item.module, {"documents": 0, "slides": 0})
        current["documents"] += 1
        current["slides"] += item.slide_count
    return {
        "totals": {
            "documents": len(documents),
            "slides": sum(item.slide_count for item in documents),
            "visual_pages": current_stats(db)["visual_pages"],
            "questions": db.scalar(select(func.count(Conversation.id))) or 0,
            "code_reviews": db.scalar(select(func.count(CodeReview.id))) or 0,
            "learning_summaries": db.scalar(select(func.count(LearningSummary.id))) or 0,
            "pending_reviews": db.scalar(select(func.count(Conversation.id)).where(
                Conversation.review_status == "pending")) or 0,
        },
        "modules": module_counts,
        "materials": [{"id": item.id, "filename": item.filename, "module": item.module,
                       "slide_count": item.slide_count, "source_type": item.source_type,
                       "version": item.zip_sha256[:12], "created_at": item.created_at.isoformat(),
                       "unit_label": "片段" if item.source_type == "docx" else "页"}
                      for item in documents],
        "questions": [{"id": item.id, "session_id": item.session_id,
                       "question": item.question, "answer": _public_answer(item.answer),
                       "module": item.module, "status": item.status,
                       "review_status": item.review_status, "review_note": item.review_note,
                       "created_at": item.created_at.isoformat(),
                       "evidence": json.loads(item.evidence_json)} for item in questions],
        "material_revisions": [{"id": item.id, "filename": item.filename,
                                "module": item.module, "old_version": item.old_version[:12],
                                "new_version": item.new_version[:12],
                                "replaced_at": item.replaced_at.isoformat()}
                               for item in db.scalars(select(MaterialRevision).order_by(
                                   desc(MaterialRevision.id)).limit(30)).all()],
    }


@app.get("/api/teacher/analytics", dependencies=[Depends(_require_teacher)])
def teacher_analytics(class_name: str | None = None, module: str | None = None,
                      from_date: date | None = None, to_date: date | None = None,
                      db: Session = Depends(get_db)):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
    if module and module not in MODULES:
        raise HTTPException(status_code=400, detail="课程模块无效")
    profiles = {item.student_key: item for item in db.scalars(select(StudentProfile)).all()}
    class_names = sorted({item.class_name for item in profiles.values()})
    profile_class = lambda key: profiles[key].class_name if key in profiles else "未登记"
    def selected(item, item_module: str | None = None) -> bool:
        day = item.created_at.date()
        return ((not class_name or profile_class(item.student_key) == class_name)
                and (not module or item_module == module)
                and (not from_date or day >= from_date)
                and (not to_date or day <= to_date))

    conversations = [item for item in db.scalars(select(Conversation)).all()
                     if selected(item, item.module)]
    reviews = [item for item in db.scalars(select(CodeReview)).all()
               if selected(item, item.module)]
    submissions = [item for item in db.scalars(select(AssignmentSubmission)).all()
                   if selected(item, item.module)]
    summaries = [item for item in db.scalars(select(LearningSummary)).all()
                 if selected(item)]
    activity = [("questions", item, item.module or "未指定") for item in conversations]
    activity += [("code_reviews", item, item.module or "未指定模块") for item in reviews]
    activity += [("submissions", item, item.module) for item in submissions]
    activity += [("learning_summaries", item, "学习回顾") for item in summaries]
    classes: dict[str, dict] = defaultdict(lambda: {
        "participants": set(), "questions": 0, "code_reviews": 0,
        "submissions": 0, "learning_summaries": 0})
    modules: dict[str, dict] = defaultdict(lambda: {
        "questions": 0, "code_reviews": 0, "submissions": 0, "learning_summaries": 0})
    timeline: dict[str, dict] = defaultdict(lambda: {
        "questions": 0, "code_reviews": 0, "submissions": 0, "learning_summaries": 0})
    participants = set()
    for kind, item, item_module in activity:
        participant = item.student_key or f"legacy:{item.session_id}"
        participants.add(participant)
        class_row = classes[profile_class(item.student_key)]
        class_row["participants"].add(participant)
        class_row[kind] += 1
        modules[item_module][kind] += 1
        timeline[item.created_at.date().isoformat()][kind] += 1
    student_rows: dict[str, dict] = {}
    visible_student_keys = ({key for key in participants if not key.startswith("legacy:")}
                            | {key for key, profile in profiles.items()
                               if not class_name or profile.class_name == class_name})
    for key in visible_student_keys:
        profile = profiles.get(key)
        student_rows[key] = {
            "name": profile.name if profile else "未登记",
            "student_number": profile.student_number if profile else "",
            "class_name": profile.class_name if profile else "未登记",
            "questions": 0, "code_reviews": 0, "submissions": 0,
            "learning_summaries": 0, "assignment_count": 0, "average_score": None,
        }
    student_assignments: dict[str, dict[str, AssignmentSubmission]] = defaultdict(dict)
    for kind, item, _ in activity:
        if item.student_key in student_rows:
            student_rows[item.student_key][kind] += 1
        if kind == "submissions" and item.student_key:
            current = student_assignments[item.student_key].get(item.assignment_id)
            if current is None or item.id > current.id:
                student_assignments[item.student_key][item.assignment_id] = item
    for key, row in student_rows.items():
        latest = list(student_assignments[key].values())
        row["assignment_count"] = len(latest)
        row["average_score"] = round(sum(_submission_score(item) for item in latest) / len(latest), 1) if latest else None
    average_score = round(sum(_submission_score(item) for item in submissions) / len(submissions), 1) if submissions else None
    common_issues = Counter()
    for item in reviews:
        if item.local_status == "syntax_error":
            common_issues["Python 语法错误"] += 1
    for item in submissions:
        try:
            issues = json.loads(item.evaluation_json).get("issues", [])
        except (TypeError, json.JSONDecodeError):
            issues = []
        for issue in issues[:5]:
            label = re.sub(r"\s+", " ", str(issue)).strip()[:100]
            if label:
                common_issues[label] += 1
    return {
        "filters": {"classes": class_names, "modules": MODULES},
        "summary": {"registered_students": len([item for item in profiles.values()
                                                    if not class_name or item.class_name == class_name]),
                    "active_participants": len(participants), "questions": len(conversations),
                    "code_reviews": len(reviews), "submissions": len(submissions),
                    "learning_summaries": len(summaries), "average_score": average_score,
                    "pending_reviews": sum(item.review_status == "pending" for item in conversations)},
        "classes": [{"name": name, **{k: len(v) if k == "participants" else v
                                      for k, v in row.items()}}
                    for name, row in sorted(classes.items())],
        "modules": [{"name": name, **row} for name, row in sorted(modules.items())],
        "timeline": [{"date": day, **row} for day, row in sorted(timeline.items())],
        "students": sorted(student_rows.values(), key=lambda item: (item["class_name"], item["name"])),
        "common_issues": [{"issue": issue, "count": count}
                          for issue, count in common_issues.most_common(10)],
        "recent_submissions": [{"id": item.id, "assignment_title": item.assignment_title,
                                "module": item.module, "class_name": profile_class(item.student_key),
                                "student_name": profiles[item.student_key].name if item.student_key in profiles else "未登记",
                                "total_score": item.total_score,
                                "teacher_review_status": item.teacher_review_status,
                                "teacher_final_score": item.teacher_final_score,
                                "created_at": item.created_at.isoformat()}
                               for item in sorted(submissions, key=lambda row: row.id, reverse=True)[:20]],
    }


@app.post("/api/teacher/reviews/{conversation_id}", dependencies=[Depends(_require_teacher)])
def review_answer(conversation_id: int, request: TeacherReviewRequest,
                  db: Session = Depends(get_db)):
    record = db.get(Conversation, conversation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="问答记录不存在")
    record.review_status = request.status
    record.review_note = request.note.strip() if request.note else None
    db.commit()
    return {"id": record.id, "review_status": record.review_status,
            "review_note": record.review_note}


@app.get("/api/teacher/submissions/{submission_id}", dependencies=[Depends(_require_teacher)])
def teacher_submission_detail(submission_id: int, db: Session = Depends(get_db)):
    record = db.get(AssignmentSubmission, submission_id)
    if record is None:
        raise HTTPException(status_code=404, detail="提交记录不存在")
    return {"id": record.id, "assignment_title": record.assignment_title,
            "module": record.module, "work_text": record.work_text,
            "report_text": record.report_text, "evaluation": json.loads(record.evaluation_json),
            "attachments": [{"index": index, "group": item["group"], "filename": item["filename"]}
                            for index, item in enumerate(json.loads(record.attachments_json))],
            "teacher_review_status": record.teacher_review_status,
            "teacher_review_note": record.teacher_review_note,
            "teacher_final_score": record.teacher_final_score,
            "teacher_reviewed_at": record.teacher_reviewed_at.isoformat() if record.teacher_reviewed_at else None}


@app.post("/api/teacher/submissions/{submission_id}/review", dependencies=[Depends(_require_teacher)])
def review_submission(submission_id: int, payload: TeacherSubmissionReviewRequest,
                      db: Session = Depends(get_db)):
    record = db.get(AssignmentSubmission, submission_id)
    if record is None:
        raise HTTPException(status_code=404, detail="提交记录不存在")
    if payload.final_score is not None and payload.status != "approved":
        raise HTTPException(status_code=400, detail="只有确认通过时才能填写最终分数")
    record.teacher_review_status = payload.status
    record.teacher_review_note = payload.note.strip() if payload.note else None
    record.teacher_final_score = payload.final_score if payload.status == "approved" else None
    record.teacher_reviewed_at = datetime.now(timezone.utc) if payload.status != "pending" else None
    db.commit()
    return {"id": record.id, "teacher_review_status": record.teacher_review_status,
            "teacher_review_note": record.teacher_review_note,
            "teacher_final_score": record.teacher_final_score,
            "teacher_reviewed_at": record.teacher_reviewed_at.isoformat() if record.teacher_reviewed_at else None}


@app.get("/api/submission-files/{submission_id}/{attachment_index}")
def download_submission_file(submission_id: int, attachment_index: int,
                             x_student_key: str | None = Header(default=None),
                             x_teacher_code: str | None = Header(default=None),
                             db: Session = Depends(get_db)):
    record = db.get(AssignmentSubmission, submission_id)
    if record is None:
        raise HTTPException(status_code=404, detail="提交记录不存在")
    is_teacher = (bool(settings.teacher_access_code) and bool(x_teacher_code) and
                  hmac.compare_digest(x_teacher_code, settings.teacher_access_code))
    is_owner = bool(x_student_key) and record.student_key == x_student_key
    if not (is_teacher or is_owner):
        raise HTTPException(status_code=403, detail="无权查看该附件")
    attachments = json.loads(record.attachments_json)
    if attachment_index < 0 or attachment_index >= len(attachments):
        raise HTTPException(status_code=404, detail="附件不存在")
    item = attachments[attachment_index]
    path = _submission_attachment_path(item["path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="附件文件不存在")
    return FileResponse(path, filename=item["filename"], media_type="application/octet-stream")


@app.get("/api/materials/{document_id}/slides/{slide_number}")
def slide_detail(document_id: int, slide_number: int, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="课件不存在")
    slide = db.scalar(select(Slide).where(Slide.document_id == document_id, Slide.slide_number == slide_number))
    if slide is None:
        raise HTTPException(status_code=404, detail="该页不存在")
    visual = db.scalar(select(SlideVisual).where(SlideVisual.slide_id == slide.id))
    image_path = settings.root / visual.image_path if visual else None
    return {"document_id": document_id, "filename": document.filename, "module": document.module,
            "slide_number": slide_number, "unit_label": "片段" if document.source_type == "docx" else "页",
            "source_type": document.source_type,
            "text": slide.text, "status": slide.status, "error": slide.error,
            "image_url": f"/api/materials/{document_id}/slides/{slide_number}/image"
            if image_path and image_path.is_file() else None}


@app.get("/api/materials/{document_id}/slides/{slide_number}/image")
def slide_image(document_id: int, slide_number: int, db: Session = Depends(get_db)):
    slide = db.scalar(select(Slide).where(Slide.document_id == document_id, Slide.slide_number == slide_number))
    if slide is None:
        raise HTTPException(status_code=404, detail="该页不存在")
    visual = db.scalar(select(SlideVisual).where(SlideVisual.slide_id == slide.id))
    if visual is None:
        raise HTTPException(status_code=404, detail="该页尚未建立图像索引")
    image_path = (settings.root / visual.image_path).resolve()
    if not image_path.is_relative_to(settings.slide_visual_path.resolve()) or not image_path.is_file():
        raise HTTPException(status_code=404, detail="页面图像文件不存在")
    return FileResponse(image_path, media_type=visual.mime_type,
                        filename=f"slide-{slide_number:04d}.png")


@app.get("/api/materials/{document_id}/download")
def download_material(document_id: int, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="课件不存在")
    if document.source_type in {"pdf", "docx"}:
        storage_path = (settings.root / document.storage_path).resolve() if document.storage_path else None
        if not storage_path or not storage_path.is_relative_to(settings.material_upload_path.resolve()) or not storage_path.is_file():
            raise HTTPException(status_code=404, detail="原始资料文件不存在")
        mime = "application/pdf" if document.source_type == "pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return FileResponse(storage_path, media_type=mime, filename=document.filename)
    if not settings.course_zip.is_file():
        raise HTTPException(status_code=404, detail="原始 ZIP 文件已移动")
    try:
        with zipfile.ZipFile(settings.course_zip) as archive:
            data = archive.read(document.zip_entry)
    except (KeyError, zipfile.BadZipFile) as exc:
        raise HTTPException(status_code=404, detail="原始 PPT 文件不可读取") from exc
    return StreamingResponse(io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                             headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(document.filename)}"})


@app.post("/api/knowledge/search")
def search(request: SearchRequest):
    return {"results": search_course(request.question, request.module, request.top_k), "mode": "offline_evidence"}


@app.post("/api/chat")
def chat(request: QuestionRequest, db: Session = Depends(get_db),
         student_key: str = Depends(_student_key)):
    _assert_student_key(request.student_key, student_key)
    uploaded_image = _decode_chat_image(request.image_data_url)
    session_id = request.session_id or str(uuid.uuid4())
    previous = _conversation_context(db, session_id, student_key)
    model_image_data_url = request.image_data_url if uploaded_image else None
    reused_previous_image = False
    if not model_image_data_url and previous and (
        is_visual_question(request.question) or any(term in request.question for term in ("这张", "刚才", "上图"))
    ):
        for turn in reversed(previous):
            model_image_data_url = _saved_image_data_url(turn)
            if model_image_data_url:
                reused_previous_image = True
                break
    smalltalk = respond_smalltalk(request.question)
    off_topic = smalltalk is None and not _is_course_question(
        request.question, bool(model_image_data_url), previous)
    selected_candidate = None if smalltalk or off_topic else _clarification_choice(request.question, previous)
    previous_question = previous[-1].question if previous else ""
    effective_question = request.question
    if smalltalk:
        effective_question = request.question
    elif selected_candidate:
        effective_question = (f"{previous_question} {selected_candidate.get('filename', '')} "
                              f"第{selected_candidate.get('slide_number', '')}"
                              f"{selected_candidate.get('unit_label', '页')} {request.question}")
    elif previous and (any(
        term in request.question for term in ("这个", "那个", "它", "上面", "继续", "接着", "刚才")
    ) or (len(request.question.strip()) <= 12 and not re.search(
        r"什么是|为什么|如何|怎么|哪些|是否|区别", request.question
    ))):
        # Carry the student's topic forward, not the previous retrieval result:
        # an irrelevant candidate page must never become the next query's topic.
        effective_question = f"{previous_question} {request.question}"

    curriculum_overview = is_curriculum_overview_question(request.question, request.module)
    query = retrieval_query(effective_question, request.module)
    try:
        if smalltalk or off_topic:
            evidence = []
        elif curriculum_overview:
            evidence = search_course_overview(query, MODULES)
        else:
            evidence = [item for item in search_course(query, request.module, 5) if item["score"] >= 0.50]
    except Exception:
        # A retrieval/index issue should still produce a useful, honest assistant reply.
        evidence = []
    if selected_candidate:
        key = (selected_candidate.get("document_id"), selected_candidate.get("slide_number"))
        if not any((item.get("document_id"), item.get("slide_number")) == key for item in evidence):
            evidence.insert(0, selected_candidate)
        evidence = evidence[:5]
    # Short follow-ups need the earlier topic to find fresh slide evidence.
    # A previous answer itself is never inserted as evidence.
    evidence = [dict(item) for item in evidence]
    visual_inputs = []
    for source_index, item in enumerate(evidence, 1):
        visual = db.scalar(select(SlideVisual).join(Slide, Slide.id == SlideVisual.slide_id).where(
            Slide.document_id == item["document_id"], Slide.slide_number == item["slide_number"]))
        image_path = (settings.root / visual.image_path).resolve() if visual else None
        item["has_visual"] = bool(image_path and image_path.is_relative_to(settings.slide_visual_path.resolve())
                                  and image_path.is_file())
        item["slide_image_url"] = (f"/api/materials/{item['document_id']}/slides/"
                                   f"{item['slide_number']}/image") if item["has_visual"] else None
        if (is_visual_question(effective_question) and not is_ambiguous_wiring_question(effective_question)
                and item["has_visual"] and len(visual_inputs) < 2):
            visual_inputs.append({
                "source_index": source_index,
                "data_url": "data:image/png;base64," + base64.b64encode(image_path.read_bytes()).decode("ascii"),
            })
    smalltalk_handled = smalltalk is not None and not model_image_data_url
    result = (AgentResult("course_qa",
                          "我是《物联网综合实训课程》的助教，主要回答课程知识、实验、代码和任务问题。"
                          "这个问题不在课程范围内；你可以换一个课程相关问题继续问我。",
                          "out_of_scope", ["识别为课程范围之外的问题"]) if off_topic else
              (smalltalk if smalltalk_handled else None) or
              (respond_course_overview(evidence, MODULES) if curriculum_overview
               else respond_offline(effective_question, evidence)))
    if (not off_topic and not smalltalk_handled and settings.model_api_key and _asks_general_concept(request.question)
            and re.search(r"全称|缩写|英文名", request.question)):
        fallback = result.answer
        if "rtu" in request.question.lower():
            fallback = ("RTU 的全称是 Remote Terminal Unit（远程终端单元）。"
                        "这是通用协议知识；本轮课件片段没有写出该英文全称。")
        result = AgentResult(result.agent, fallback, "insufficient_evidence",
                             result.trace + ["缩写全称问题交由 AI 通用知识回答"])
    if model_image_data_url and not settings.model_api_key:
        result = AgentResult(result.agent, result.answer + "\n\n当前未配置图像分析模型，无法识别你上传的图片。",
                             result.status, result.trace + ["图像分析未启用"])
    mode = ("out_of_scope" if result.status == "out_of_scope" else
            "general_knowledge" if result.status == "answered_basic" else
            "general" if result.status == "answered_general" else
            "clarification" if result.status == "needs_clarification" else "offline_evidence")
    general_fallback_attempted = False
    if result.status == "answered_from_slides" and settings.model_api_key:
        try:
            plan = plan_agents(request.question)
            if model_image_data_url and len(plan) > 1:
                # Keep the student's picture with the specialist answering this turn.
                plan = ["experiment_guide"]
            image_trace = (["沿用本对话前一轮上传的现场图片"] if reused_previous_image else
                           ["读取学生上传的现场图片"] if uploaded_image else [])
            trace = result.trace + image_trace + ["任务调度：" + "、".join(
                "课程问答 Agent" if role == "course_qa" else "实验指导 Agent" for role in plan)]
            if len(plan) == 2:
                drafts = {}
                for role in plan:
                    role_visuals = visual_inputs if role == "experiment_guide" else []
                    try:
                        drafts[role] = generate_grounded_answer(
                            request.question, request.module, evidence, role_visuals,
                            _recent_model_history(previous), role=role,
                        )
                        trace.append(("课程问答 Agent" if role == "course_qa" else "实验指导 Agent")
                                     + " 已依据课件形成带引用的分析")
                    except Exception:
                        trace.append(("课程问答 Agent" if role == "course_qa" else "实验指导 Agent")
                                     + " 本轮未成功")
                if len(drafts) == 2:
                    try:
                        generated = synthesize_grounded_answers(effective_question, evidence, drafts)
                        trace.append("结果校验与整合模块核对原始课件和引用后生成答复")
                        result = AgentResult("collaborative", generated, "answered_with_collaboration", trace)
                        mode = "multi_agent"
                    except Exception:
                        trace.append("整合校验未通过，采用已核对引用的课程问答结果")
                        result = AgentResult("course_qa", drafts["course_qa"], "answered_with_model", trace)
                        mode = "model_grounded"
                elif drafts:
                    role, draft = next(iter(drafts.items()))
                    trace.append("另一角色未完成，本轮采用已形成的课件回答")
                    result = AgentResult(role, draft, "answered_with_model", trace)
                    mode = "model_grounded"
                else:
                    raise RuntimeError("各专门 Agent 均未生成可用回答")
            else:
                role = plan[0]
                generated = generate_grounded_answer(
                    request.question, request.module, evidence, visual_inputs,
                    _recent_model_history(previous), role=role,
                    user_image=model_image_data_url,
                    curriculum_overview=curriculum_overview,
                    curriculum_modules=MODULES if curriculum_overview else None,
                )
                trace.append(("实验指导 Agent" if role == "experiment_guide" else "课程问答 Agent")
                             + " 根据课件生成带编号引用的回答")
                result = AgentResult(role, generated,
                                     "answered_with_vision" if visual_inputs or model_image_data_url else "answered_with_model", trace)
                mode = "model_multimodal" if visual_inputs or model_image_data_url else "model_grounded"
        except GroundingValidationError:
            result = AgentResult(result.agent, result.answer, "answered_offline_fallback",
                                 result.trace + ["AI 答复未通过引用或模块覆盖校验，已回退到本地课件整理"])
            mode = "offline_fallback"
        except Exception:
            # Do not expose SDK exceptions: provider error text can include sensitive request details.
            result = AgentResult(result.agent, result.answer, "answered_offline_fallback",
                                 result.trace + ["AI 调用未成功，已回退到本地资料整理"])
            mode = "offline_fallback"
    elif (not smalltalk_handled and not curriculum_overview and settings.model_api_key and result.status in {
        "answered_general", "answered_basic", "insufficient_evidence", "needs_clarification",
    }):
        general_fallback_attempted = True
        try:
            generated = generate_general_answer(
                request.question, _recent_model_history(previous), evidence,
                user_image=model_image_data_url,
            )
            result = AgentResult(
                result.agent,
                generated,
                "answered_with_model_general",
                result.trace + ["课程资料依据不足，使用 AI 通用知识补充分析"],
            )
            mode = "model_multimodal" if model_image_data_url else "model_general"
        except Exception:
            fallback = result.answer
            result = AgentResult(
                result.agent,
                fallback + "\n\n（AI 暂时无法连接，以上为本地回复。）",
                "answered_offline_fallback",
                result.trace + ["AI 调用未成功，已回退到本地回复"],
            )
            mode = "offline_fallback"
    if (settings.model_api_key and _asks_general_concept(request.question)
            and result.status in {"answered_with_model", "answered_with_vision", "answered_with_collaboration"}
            and _grounded_answer_lacks_answer(result.answer)):
        try:
            generated = generate_general_answer(
                request.question, _recent_model_history(previous), evidence,
                user_image=model_image_data_url,
            )
            result = AgentResult(result.agent, generated, "answered_with_model_general",
                                 result.trace + ["课件未覆盖问题要点，使用 AI 通用知识补充回答"])
            mode = "model_multimodal" if model_image_data_url else "model_general"
            general_fallback_attempted = True
        except Exception:
            result = AgentResult(result.agent, result.answer, result.status,
                                 result.trace + ["通用知识补充暂不可用，保留课件回答"])
    used_evidence = evidence if result.status in {
        "answered_from_slides", "answered_with_model", "answered_with_vision", "answered_offline_fallback",
        "needs_clarification", "answered_with_model_general", "answered_with_collaboration",
    } else []
    if result.status == "answered_with_model_general" or (
        general_fallback_attempted and result.status == "answered_offline_fallback"
    ):
        used_evidence = [dict(item, candidate_only=True) for item in used_evidence]
    elif model_image_data_url and result.status == "answered_with_vision" and not re.search(
        r"\[\d+\]", result.answer
    ):
        used_evidence = [dict(item, candidate_only=True) for item in used_evidence]
    result = AgentResult(result.agent, _public_answer(result.answer), result.status,
                         _public_trace(result.trace))
    image_path = None
    if uploaded_image:
        mime, data = uploaded_image
        settings.chat_upload_path.mkdir(parents=True, exist_ok=True)
        image_file = settings.chat_upload_path / f"{uuid.uuid4().hex}.{IMAGE_TYPES[mime]}"
        image_file.write_bytes(data)
        image_path = image_file.relative_to(settings.root).as_posix()
    record = Conversation(
        session_id=session_id, student_key=request.student_key,
        question=request.question, module=request.module, answer=result.answer,
        agent=result.agent, status=result.status, mode=mode,
        evidence_json=json.dumps(used_evidence, ensure_ascii=False),
        trace_json=json.dumps(result.trace, ensure_ascii=False),
        image_path=image_path,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id, "session_id": session_id, "question": request.question,
            "answer": result.answer, "agent": result.agent,
            "status": result.status, "trace": result.trace, "evidence": used_evidence,
            "mode": mode, "image_url": _chat_image_url(record),
            "review_status": record.review_status, "review_note": record.review_note}


@app.post("/api/code/analyze")
def analyze_code(request: CodeRequest, db: Session = Depends(get_db),
                 student_key: str = Depends(_student_key)):
    _assert_student_key(request.student_key, student_key)
    uploaded_image = _decode_chat_image(request.image_data_url)
    model_image_data_url = request.image_data_url if uploaded_image else None
    session_id = request.session_id or str(uuid.uuid4())
    previous = db.scalars(select(CodeReview).where(CodeReview.session_id == session_id,
                                                  CodeReview.student_key == student_key)
                          .order_by(desc(CodeReview.id)).limit(8)).all()
    effective_code = request.code.strip() or (previous[0].code if previous else "")
    if not effective_code and not model_image_data_url:
        raise HTTPException(status_code=400, detail="请先粘贴代码，或在已有代码分析对话中继续追问")
    effective_code = effective_code or "（代码或报错截图，待视觉分析）"
    language = (detect_code_language(effective_code, request.filename)
                if request.language == "auto" and request.code.strip()
                else previous[0].language if request.language == "auto" and previous
                else "python" if request.language == "auto" else request.language)
    turn_question = (request.context or "").strip() or "请分析这段代码"
    local = (analyze_code_locally(language, effective_code)
             if request.code.strip() or (previous and previous[0].code.strip())
             else {"language": language, "status": "image_only",
                   "summary": "本轮未提供文本代码，先根据图片内容进行视觉分析。",
                   "issues": [], "agent": "code_analysis"})
    trace = ["代码分析 Agent 已完成本地检查" if language == "python"
             else "代码分析 Agent 已识别语言；本地未运行编译器"]
    evidence = []
    if request.context:
        try:
            evidence = [item for item in search_course(
                f"{language} {request.context}", request.module, 3) if item["score"] >= 0.55]
        except Exception:
            trace.append("课程资料检索暂不可用")
    analysis = None
    mode = "local"
    if settings.model_api_key:
        try:
            analysis = _public_answer(generate_code_review(
                language, effective_code, turn_question, local, evidence,
                conversation_history=[{
                    "question": item.context or "请分析这段代码",
                    "summary": item.summary,
                    "analysis": item.analysis or "",
                    "code": item.code if item.code and item.code != effective_code else "",
                } for item in reversed(previous)],
                user_image=model_image_data_url))
            citations = {int(number) for number in re.findall(r"\[(\d+)\]", analysis)}
            if any(number < 1 or number > len(evidence) for number in citations):
                analysis = re.sub(r"\[(\d+)\]", "", analysis)
                citations = set()
            evidence = [dict(item, source_index=index) for index, item in enumerate(evidence, 1)
                        if index in citations]
            trace.append("代码分析 Agent 已生成逐行静态建议")
            mode = "ai_static"
        except Exception:
            trace.append("AI 静态分析暂不可用，保留本地检查结果")
            evidence = []
    record = CodeReview(session_id=session_id, student_key=request.student_key,
                        language=language, module=request.module,
                        context=turn_question, code=effective_code,
                        local_status=local["status"], summary=local["summary"], analysis=analysis)
    db.add(record)
    db.commit()
    db.refresh(record)
    return {**local, "id": record.id, "session_id": session_id, "module": request.module,
            "context": turn_question,
            "analysis": analysis, "mode": mode, "evidence": evidence, "trace": trace,
            "image_data_url": model_image_data_url,
            "created_at": record.created_at.isoformat()}


@app.get("/api/code/reviews")
def code_reviews(session_id: str, db: Session = Depends(get_db),
                 student_key: str = Depends(_student_key)):
    records = db.scalars(select(CodeReview).where(CodeReview.session_id == session_id,
                                                  CodeReview.student_key == student_key)
                         .order_by(desc(CodeReview.id)).limit(30)).all()
    return [{"id": item.id, "session_id": item.session_id, "language": item.language,
             "module": item.module,
             "context": item.context, "code": item.code, "status": item.local_status,
             "issues": analyze_code_locally(item.language, item.code)["issues"] if item.code else [],
             "structure": analyze_code_locally(item.language, item.code).get("structure") if item.code else None,
             "summary": item.summary, "analysis": _public_answer(item.analysis) if item.analysis else None,
             "mode": "ai_static" if item.analysis else "local",
             "created_at": item.created_at.isoformat()} for item in records]


@app.post("/api/learning/summary")
def create_learning_summary(request: LearningSummaryRequest, db: Session = Depends(get_db),
                            student_key: str = Depends(_student_key)):
    _assert_student_key(request.student_key, student_key)
    turns = db.scalars(select(Conversation).where(Conversation.session_id == request.session_id,
                                                  Conversation.student_key == student_key)
                       .order_by(desc(Conversation.id)).limit(20)).all()[::-1]
    reviews = db.scalars(select(CodeReview).where(CodeReview.session_id == request.session_id,
                                                  CodeReview.student_key == student_key)
                         .order_by(desc(CodeReview.id)).limit(10)).all()[::-1]
    if not turns and not reviews:
        raise HTTPException(status_code=400, detail="这段对话还没有学习记录")
    turn_data = [{"module": item.module, "question": item.question, "answer": item.answer,
                  "status": item.status} for item in turns]
    review_data = [{"language": item.language, "module": item.module, "context": item.context,
                    "summary": item.summary} for item in reviews]
    if settings.model_api_key:
        try:
            content = _public_answer(generate_learning_summary(turn_data, review_data))
            if re.search(r"(?:评分|得分|成绩)\s*[:：]?\s*\d+|\b\d{1,3}\s*分(?!钟)", content):
                raise ValueError("过程性回顾不应输出成绩")
            mode = "ai_formative"
        except Exception:
            content = None
    else:
        content = None
    if content is None:
        modules = sorted({item.module for item in turns if item.module})
        content = (f"本段记录包含 {len(turns)} 次提问、{len(reviews)} 次代码检查。"
                   + (f"涉及模块：{'、'.join(modules)}。" if modules else "尚未指定课程模块。")
                   + "\n\n目前只能汇总学习过程，无法据此判断知识掌握程度。建议回看课件依据，并补充实验结果或报错继续讨论。")
        mode = "local_formative"
    record = LearningSummary(session_id=request.session_id,
                             student_key=request.student_key, content=content)
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id, "session_id": request.session_id, "content": content,
            "mode": mode, "created_at": record.created_at.isoformat(),
            "turn_count": len(turns), "code_review_count": len(reviews)}


@app.get("/api/learning/summaries/{session_id}")
def learning_summaries(session_id: str, db: Session = Depends(get_db),
                       student_key: str = Depends(_student_key)):
    records = db.scalars(select(LearningSummary).where(LearningSummary.session_id == session_id,
                                                        LearningSummary.student_key == student_key)
                         .order_by(desc(LearningSummary.id)).limit(10)).all()
    return [{"id": item.id, "session_id": item.session_id, "content": _public_answer(item.content),
             "created_at": item.created_at.isoformat()} for item in records]


@app.get("/api/conversations")
def conversations(limit: int = 20, session_id: str | None = None,
                  db: Session = Depends(get_db), student_key: str = Depends(_student_key)):
    limit = min(max(limit, 1), 100)
    statement = select(Conversation).where(Conversation.student_key == student_key)
    if session_id:
        if session_id.startswith("legacy-") and session_id[7:].isdigit():
            statement = statement.where(Conversation.id == int(session_id[7:]),
                                       Conversation.session_id.is_(None))
        else:
            statement = statement.where(Conversation.session_id == session_id)
    records = db.scalars(statement.order_by(desc(Conversation.id)).limit(limit)).all()
    records.reverse()
    return [{"id": item.id, "question": item.question, "module": item.module,
             "session_id": item.session_id,
            "answer": _public_answer(item.answer), "agent": item.agent, "status": item.status,
            "mode": item.mode or ("general" if item.status == "answered_general" else
                     "multi_agent" if item.status == "answered_with_collaboration" else
                     ("model_multimodal" if item.image_path else "model_general")
                     if item.status == "answered_with_model_general" else
                     "clarification" if item.status == "needs_clarification" else
                     "model_multimodal" if item.status == "answered_with_vision" else
                     "model_grounded" if item.status == "answered_with_model" else
                     "offline_fallback" if item.status == "answered_offline_fallback" else "offline_evidence"),
             "evidence": json.loads(item.evidence_json), "trace": _public_trace(json.loads(item.trace_json)),
             "image_url": _chat_image_url(item),
             "review_status": item.review_status, "review_note": item.review_note,
             "created_at": item.created_at.isoformat()} for item in records]


@app.get("/api/conversations/{conversation_id}/image")
def conversation_image(conversation_id: int, token: str, db: Session = Depends(get_db)):
    record = db.get(Conversation, conversation_id)
    if not record or not record.image_path or not record.student_key or not settings.media_signing_key:
        raise HTTPException(status_code=404, detail="图片不存在")
    expected = hmac.new(settings.media_signing_key.encode(),
                        f"{record.id}:{record.student_key}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, token):
        raise HTTPException(status_code=403, detail="图片访问链接无效")
    image_path = (settings.root / record.image_path).resolve()
    if not image_path.is_relative_to(settings.chat_upload_path.resolve()) or not image_path.is_file():
        raise HTTPException(status_code=404, detail="图片文件不存在")
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}.get(image_path.suffix.lower())
    if not mime:
        raise HTTPException(status_code=404, detail="图片类型无效")
    return FileResponse(image_path, media_type=mime)


@app.get("/api/conversations/sessions")
def conversation_sessions(db: Session = Depends(get_db),
                          student_key: str = Depends(_student_key)):
    records = db.scalars(select(Conversation).where(Conversation.student_key == student_key)
                         .order_by(desc(Conversation.id))).all()
    sessions = {}
    for item in records:
        key = item.session_id or f"legacy-{item.id}"
        if key not in sessions:
            sessions[key] = {
                "session_id": key, "title": item.question[:80], "last_question": item.question,
                "updated_at": item.created_at.isoformat(), "count": 0, "kind": "chat",
            }
        sessions[key]["title"] = item.question[:80]
        sessions[key]["count"] += 1
    reviews = db.scalars(select(CodeReview).where(CodeReview.student_key == student_key)
                         .order_by(desc(CodeReview.id))).all()
    for item in reviews:
        if item.session_id not in sessions:
            sessions[item.session_id] = {
                "session_id": item.session_id, "title": f"代码分析 · {item.language}",
                "last_question": item.context or "代码检查", "updated_at": item.created_at.isoformat(),
                "count": 0, "kind": "code",
            }
        sessions[item.session_id]["count"] += 1
    return sorted(sessions.values(), key=lambda item: item["updated_at"], reverse=True)


@app.delete("/api/conversations/{session_id}")
def delete_conversation(session_id: str, db: Session = Depends(get_db),
                        student_key: str = Depends(_student_key)):
    if session_id.startswith("legacy-") and session_id[7:].isdigit():
        records = db.scalars(select(Conversation).where(Conversation.id == int(session_id[7:]),
                                                   Conversation.session_id.is_(None),
                                                   Conversation.student_key == student_key)).all()
        statement = sql_delete(Conversation).where(Conversation.id == int(session_id[7:]),
                                                   Conversation.session_id.is_(None),
                                                   Conversation.student_key == student_key)
    else:
        records = db.scalars(select(Conversation).where(Conversation.session_id == session_id,
                                                         Conversation.student_key == student_key)).all()
        statement = sql_delete(Conversation).where(Conversation.session_id == session_id,
                                                   Conversation.student_key == student_key)
    result = db.execute(statement)
    removed = result.rowcount or 0
    if not session_id.startswith("legacy-"):
        removed += db.execute(sql_delete(CodeReview).where(CodeReview.session_id == session_id,
                                                           CodeReview.student_key == student_key)).rowcount or 0
        removed += db.execute(sql_delete(LearningSummary).where(LearningSummary.session_id == session_id,
                                                                 LearningSummary.student_key == student_key)).rowcount or 0
    if not removed:
        db.rollback()
        raise HTTPException(status_code=404, detail="对话不存在或已删除")
    db.commit()
    for record in records:
        if record.image_path:
            image_path = (settings.root / record.image_path).resolve()
            if image_path.is_relative_to(settings.chat_upload_path.resolve()):
                image_path.unlink(missing_ok=True)
    return {"deleted": True, "session_id": session_id}
