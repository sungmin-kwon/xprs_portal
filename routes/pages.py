from fastapi import APIRouter
from fastapi.responses import FileResponse

from config import STATIC_DIR

router = APIRouter()

PAGE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}


@router.get("/")
def home():
    return FileResponse(STATIC_DIR / "home.html", headers=PAGE_HEADERS)


@router.get("/dashboard")
def dashboard():
    return FileResponse(STATIC_DIR / "dashboard.html", headers=PAGE_HEADERS)


@router.get("/about")
def about():
    return FileResponse(STATIC_DIR / "about.html", headers=PAGE_HEADERS)


@router.get("/cohort-analysis")
def cohort_analysis_page():
    return FileResponse(STATIC_DIR / "cohort_analysis.html", headers=PAGE_HEADERS)


@router.get("/favicon.ico")
def favicon():
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")
