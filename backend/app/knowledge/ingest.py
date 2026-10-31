from __future__ import annotations

import hashlib
import re
import zipfile
from collections import Counter
from pathlib import PurePosixPath

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import Document, Slide, SlideVisual
from app.knowledge.parser import PARSER_VERSION, iter_ppt_entries, module_for_name, parse_presentation, split_slide
from app.knowledge.vector import collection, embed_texts


def zip_digest(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def current_stats(db: Session) -> dict:
    documents = db.scalar(select(func.count(Document.id))) or 0
    slides = db.scalar(select(func.count(Slide.id))) or 0
    blank = db.scalar(select(func.count(Slide.id)).where(Slide.status == "blank")) or 0
    errors = db.scalar(select(func.count(Slide.id)).where(Slide.status == "error")) or 0
    partial = db.scalar(select(func.count(Slide.id)).where(Slide.status == "partial")) or 0
    visual_pages = db.scalar(select(func.count(SlideVisual.id))) or 0
    ppt_documents = db.scalar(select(func.count(Document.id)).where(Document.source_type == "pptx")) or 0
    ppt_pages = db.scalar(select(func.coalesce(func.sum(Document.slide_count), 0)).where(
        Document.source_type == "pptx")) or 0
    return {
        "documents": documents,
        "slides": slides,
        "blank_slides": blank,
        "partial_slides": partial,
        "error_slides": errors,
        "indexed_chunks": collection().count() if documents else 0,
        "visual_pages": visual_pages,
        "ppt_documents": ppt_documents,
        "ppt_pages": ppt_pages,
    }


def import_course_zip(db: Session, force: bool = False) -> dict:
    path = settings.course_zip
    if not path.is_file():
        raise FileNotFoundError(f"课程资料 ZIP 不存在：{path}")
    digest = zip_digest(path)
    existing = db.scalars(select(Document).where(Document.source_type == "pptx")).all()
    vector_collection = collection()
    all_vector_ids = vector_collection.get(include=[])["ids"]
    old_prefixes = tuple(f"d{document.id}-" for document in existing)
    old_ids = [item for item in all_vector_ids if item.startswith(old_prefixes)] if old_prefixes else []
    if not force and existing and all(document.zip_sha256 == digest and
                                      document.parser_version >= PARSER_VERSION for document in existing) and old_ids:
        return {"status": "unchanged", **current_stats(db), "file_errors": []}

    prepared = []
    file_errors = []
    try:
        with zipfile.ZipFile(path) as archive:
            for info, data, read_error in iter_ppt_entries(archive):
                filename = PurePosixPath(info.filename).name
                if read_error:
                    file_errors.append({"filename": filename, "error": read_error})
                    continue
                try:
                    slides = parse_presentation(data)
                except Exception as exc:
                    file_errors.append({"filename": filename, "error": str(exc)[:400]})
                    continue
                prepared.append((info.filename, filename, module_for_name(info.filename), slides))
    except zipfile.BadZipFile as exc:
        raise ValueError("课程 ZIP 文件已损坏，无法导入") from exc
    if not prepared:
        raise ValueError("ZIP 中没有可读取的 PPTX 文件")

    if old_ids:
        for start in range(0, len(old_ids), 500):
            vector_collection.delete(ids=old_ids[start:start + 500])
    # Replace only the ZIP PPT set. Uploaded PDF/Word materials keep their rows and vectors.
    old_document_ids = [document.id for document in existing]
    if old_document_ids:
        old_slide_ids = select(Slide.id).where(Slide.document_id.in_(old_document_ids))
        db.execute(delete(SlideVisual).where(SlideVisual.slide_id.in_(old_slide_ids)))
        db.execute(delete(Slide).where(Slide.document_id.in_(old_document_ids)))
        db.execute(delete(Document).where(Document.id.in_(old_document_ids)))
    db.flush()

    ids, texts, metadatas = [], [], []
    for entry, filename, module, slides in prepared:
        document = Document(
            filename=filename,
            module=module,
            zip_entry=entry,
            zip_sha256=digest,
            source_type="pptx",
            parser_version=PARSER_VERSION,
            slide_count=len(slides),
        )
        db.add(document)
        db.flush()
        for slide in slides:
            db.add(Slide(
                document_id=document.id,
                slide_number=slide.number,
                text=slide.text,
                status=slide.status,
                error=slide.error,
            ))
            for index, chunk in enumerate(split_slide(slide.text)):
                task_match = re.search(r"\d{1,2}月\d{1,2}日\s*任务\s*\d*", chunk)
                ids.append(f"d{document.id}-s{slide.number}-c{index}")
                texts.append(chunk)
                metadatas.append({
                    "document_id": document.id,
                    "filename": filename,
                    "module": module,
                    "slide_number": slide.number,
                    "unit_label": "页",
                    "source_type": "pptx",
                    "material_category": "任务说明与实操脚本" if "任务布置" in entry else "课程课件",
                    "lesson_label": task_match.group(0).replace(" ", "") if task_match else None,
                    "source_path": entry,
                    "version": digest[:12],
                })

    try:
        for start in range(0, len(ids), 64):
            end = start + 64
            batch_texts = texts[start:end]
            vector_collection.upsert(
                ids=ids[start:end],
                documents=batch_texts,
                embeddings=embed_texts(batch_texts),
                metadatas=metadatas[start:end],
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    stats = current_stats(db)
    stats["status"] = "imported"
    stats["file_errors"] = file_errors
    stats["modules"] = dict(Counter(module for _, _, module, _ in prepared))
    return stats
