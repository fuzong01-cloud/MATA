"""Render current course slides to local page images and associate them with the KB."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database.session import SessionLocal, init_db  # noqa: E402
from app.knowledge.visual_ingest import import_slide_visuals  # noqa: E402


def main() -> None:
    init_db()
    with SessionLocal() as db:
        result = import_slide_visuals(db)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
