"""Replace the indexed course corpus from COURSE_MATERIALS_DIR.

PPTX files are archived in knowledge_base/course_materials_latest.zip so the
existing download and visual-index features continue to work. DOCX files are
stored as supplemental course documents and indexed in SQLite/Chroma.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import uuid
import zipfile
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
SOURCE = Path(os.getenv("COURSE_MATERIALS_DIR", str(ROOT / "course_materials")))
PPT_ROOT = SOURCE / "课件PPT"
ARCHIVE = ROOT / "knowledge_base" / "course_materials_latest.zip"
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import delete, select  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.database.models import Document, Slide, SlideVisual  # noqa: E402
from app.database.session import SessionLocal, init_db  # noqa: E402
from app.knowledge.ingest import import_course_zip  # noqa: E402
from app.knowledge.parser import split_slide  # noqa: E402
from app.knowledge.uploaded_documents import _word_segments  # noqa: E402
from app.knowledge.vector import collection, embed_texts  # noqa: E402


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def docx_module(relative: Path) -> str:
    path = relative.as_posix().casefold()
    name = relative.name.casefold()
    if "app模块" in path or "应用端" in name or "android" in name:
        return "Android开发"
    if "web开发" in path or "web开发" in name:
        return "Web开发"
    if "虚拟仿真" in path or "虚拟仿真" in name:
        return "虚拟仿真"
    if "成绩" in name or "综合实训课程" in name:
        return "通用课程资料"
    return "嵌入式开发"


def material_category(relative: Path) -> str:
    path = relative.as_posix()
    name = relative.name
    if "知识题库" in path:
        return "习题与题库"
    if "指导手册" in path:
        return "指导手册"
    if "实操" in path or "任务" in name or "任务" in path:
        return "任务说明与实操脚本"
    if "模板" in name or "报告模板" in path:
        return "报告模板"
    if "成绩" in name:
        return "评分标准"
    if "理论课" in path or "理论" in path:
        return "课程讲义"
    return "课程补充资料"


def lesson_label(relative: Path) -> str | None:
    text = relative.as_posix()
    patterns = (
        (r"第\s*(\d+)\s*节", lambda m: f"第{int(m.group(1))}节"),
        (r"(\d+)\s*实操", lambda m: f"实操{int(m.group(1))}"),
        (r"农林物联网系统综合实训\s*-\s*(\d+)", lambda m: f"第{int(m.group(1))}讲"),
        (r"第([一二三四五六七八九十]+)节", lambda m: f"第{m.group(1)}节"),
    )
    for pattern, render in patterns:
        match = re.search(pattern, text)
        if match:
            return render(match)
    return None


def build_ppt_archive() -> dict:
    if not PPT_ROOT.is_dir():
        raise FileNotFoundError(f"课件目录不存在：{PPT_ROOT}")
    files = sorted(PPT_ROOT.rglob("*.pptx"))
    # The revised deck supersedes its old same-numbered version.
    revised = {p.parent / (p.stem.removesuffix("改") + p.suffix)
               for p in files if p.stem.endswith("改")}
    files = [p for p in files if p not in revised]
    task_deck = SOURCE / "任务.pptx"
    if task_deck.is_file():
        files.append(task_deck)
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for path in files:
            relative = (Path("通用课程资料") / "课程任务布置.pptx").as_posix() if path == task_deck else path.relative_to(PPT_ROOT).as_posix()
            archive.write(path, relative)
    return {"pptx_files": len(files), "task_deck_included": task_deck.is_file(),
            "replaced_revisions": [p.name for p in sorted(revised)]}


def import_docx_corpus(db) -> dict:
    docx_files = sorted(SOURCE.rglob("*.docx"))
    prefix = "course_materials/"
    old_documents = db.scalars(select(Document).where(Document.zip_entry.like(f"{prefix}%"))).all()
    old_ids = [doc.id for doc in old_documents]
    old_storage_paths = [settings.root / doc.storage_path for doc in old_documents if doc.storage_path]
    vector = collection()
    old_vector_ids = [item for item in vector.get(include=[])["ids"]
                      if any(item.startswith(f"d{doc_id}-") for doc_id in old_ids)]
    if old_vector_ids:
        vector.delete(ids=old_vector_ids)
    if old_ids:
        slide_ids = select(Slide.id).where(Slide.document_id.in_(old_ids))
        db.execute(delete(SlideVisual).where(SlideVisual.slide_id.in_(slide_ids)))
        db.execute(delete(Slide).where(Slide.document_id.in_(old_ids)))
        db.execute(delete(Document).where(Document.id.in_(old_ids)))
        db.commit()
        for stored_path in old_storage_paths:
            resolved = stored_path.resolve()
            if resolved.is_relative_to(settings.material_upload_path.resolve()):
                resolved.unlink(missing_ok=True)

    settings.material_upload_path.mkdir(parents=True, exist_ok=True)
    imported, errors = [], []
    for path in docx_files:
        relative = path.relative_to(SOURCE)
        try:
            data = path.read_bytes()
            units = _word_segments(data)
            module = docx_module(relative)
            category = material_category(relative)
            lesson = lesson_label(relative)
            document = Document(
                filename=path.name, module=module,
                zip_entry=prefix + relative.as_posix(), zip_sha256=sha256(data),
                source_type="docx", slide_count=len(units),
            )
            stored = settings.material_upload_path / f"{uuid.uuid4().hex}.docx"
            shutil.copyfile(path, stored)
            document.storage_path = stored.relative_to(settings.root).as_posix()
            db.add(document)
            db.flush()
            ids, texts, metadatas = [], [], []
            for unit in units:
                db.add(Slide(document_id=document.id, slide_number=unit.number,
                             text=unit.text, status=unit.status, error=unit.error))
                for index, chunk in enumerate(split_slide(unit.text)):
                    ids.append(f"d{document.id}-s{unit.number}-c{index}")
                    texts.append(chunk)
                    metadatas.append({"document_id": document.id, "filename": path.name,
                                      "module": module, "slide_number": unit.number,
                                      "unit_label": "片段", "source_type": "docx",
                                      "material_category": category,
                                      "lesson_label": lesson,
                                      "source_path": relative.as_posix()})
            for start in range(0, len(ids), 64):
                end = start + 64
                vector.upsert(ids=ids[start:end], documents=texts[start:end],
                              embeddings=embed_texts(texts[start:end]),
                              metadatas=metadatas[start:end])
            db.commit()
            imported.append({"path": relative.as_posix(), "module": module,
                             "segments": len(units), "chunks": len(ids)})
        except Exception as exc:
            db.rollback()
            errors.append({"path": relative.as_posix(), "error": str(exc)[:400]})
    return {"docx_imported": len(imported), "docx_errors": errors,
            "docx_segments": sum(item["segments"] for item in imported),
            "docx_chunks": sum(item["chunks"] for item in imported)}


def main() -> None:
    if not SOURCE.is_dir():
        raise FileNotFoundError(f"资料目录不存在：{SOURCE}")
    zip_stats = build_ppt_archive()
    # Point the existing import and visual-index routes at the revised corpus.
    env_path = ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    course_line = f"COURSE_ZIP={ARCHIVE.as_posix()}"
    replaced = False
    for index, line in enumerate(lines):
        if line.startswith("COURSE_ZIP="):
            lines[index] = course_line
            replaced = True
            break
    if not replaced:
        lines.append(course_line)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Settings was loaded before .env was updated, so point this process at the archive.
    settings.course_zip = ARCHIVE
    init_db()
    with SessionLocal() as db:
        ppt_stats = import_course_zip(db, force=True)
        docx_stats = import_docx_corpus(db)
    print(json.dumps({"archive": str(ARCHIVE), **zip_stats, "ppt": ppt_stats, **docx_stats},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
