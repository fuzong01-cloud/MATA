from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import Document, Slide, SlideVisual
from app.knowledge.ingest import zip_digest
from app.knowledge.powerpoint_render import PowerPointRenderer


def visual_page_count(db: Session) -> int:
    return db.scalar(select(func.count(SlideVisual.id))) or 0


def import_slide_visuals(db: Session) -> dict:
    archive_path = settings.course_zip
    if not archive_path.is_file():
        raise FileNotFoundError(f"课程资料 ZIP 不存在：{archive_path}")
    digest = zip_digest(archive_path)
    documents = db.scalars(select(Document).where(Document.source_type == "pptx")
                           .order_by(Document.id)).all()
    if not documents:
        raise ValueError("请先导入课程 PPT 文字资料")
    if any(document.zip_sha256 != digest for document in documents):
        raise ValueError("课程 ZIP 与当前文字知识库版本不一致，请先重新导入课程 PPT")

    page_by_entry: dict[str, dict[int, Slide]] = {}
    for document in documents:
        page_by_entry[document.zip_entry] = {
            page.slide_number: page
            for page in db.scalars(select(Slide).where(Slide.document_id == document.id)).all()
        }

    rendered_count = 0
    errors: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="course-ppt-visuals-") as temporary:
        temporary_root = Path(temporary)
        with zipfile.ZipFile(archive_path) as archive, PowerPointRenderer() as renderer:
            for document in documents:
                try:
                    entry = archive.getinfo(document.zip_entry)
                    if entry.file_size > 40_000_000:
                        errors.append({"filename": document.filename, "error": "文件超过 40 MB 限制"})
                        continue
                    source_path = temporary_root / f"{document.id}.pptx"
                    source_path.write_bytes(archive.read(entry))
                    staging = temporary_root / f"rendered-{document.id}"
                    rendered, slide_errors = renderer.render(source_path, staging)
                    errors.extend({"filename": document.filename, **item} for item in slide_errors)

                    document_key = hashlib.sha256(document.zip_entry.encode("utf-8")).hexdigest()[:12]
                    destination_dir = settings.slide_visual_path / document_key
                    destination_dir.mkdir(parents=True, exist_ok=True)
                    for page_number, staged_path in rendered.items():
                        page = page_by_entry[document.zip_entry].get(page_number)
                        if page is None:
                            errors.append({"filename": document.filename, "slide_number": page_number,
                                           "error": "该页不存在于当前文字知识库"})
                            continue
                        destination = destination_dir / f"slide-{page_number:04d}.png"
                        shutil.copyfile(staged_path, destination)
                        visual = db.scalar(select(SlideVisual).where(SlideVisual.slide_id == page.id))
                        if visual is None:
                            visual = SlideVisual(slide_id=page.id, image_path=destination.relative_to(settings.root).as_posix())
                            db.add(visual)
                        else:
                            visual.image_path = destination.relative_to(settings.root).as_posix()
                        rendered_count += 1
                except KeyError:
                    errors.append({"filename": document.filename, "error": "PPT 未包含在课程 ZIP 中"})
                except Exception as exc:
                    errors.append({"filename": document.filename, "error": str(exc)[:400]})
        db.commit()

    return {
        "status": "imported",
        "visual_pages": visual_page_count(db),
        "rendered_this_run": rendered_count,
        "file_errors": errors,
    }
