"""Run with: python backend/run.py"""

import uvicorn


if __name__ == "__main__":
    from app.core.config import settings

    uvicorn.run("app.main:app", host="127.0.0.1", port=settings.backend_port, reload=False)
