"""Import configured course PPT ZIP into the local database and vector index."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database.session import SessionLocal, init_db  # noqa: E402
from app.knowledge.ingest import import_course_zip  # noqa: E402


def main() -> None:
    init_db()
    with SessionLocal() as db:
        result = import_course_zip(db, force="--force" in sys.argv)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
