from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.routes.pages import router as pages_router
from app.database import SessionLocal
from app.services.ui_data import ensure_demo_data


APP_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with SessionLocal() as db:
        ensure_demo_data(db)
    yield


app = FastAPI(
    title="WKUCourseKit",
    description="Python-first syllabus and materials organizer for WKU / Kean students.",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
app.include_router(pages_router)
