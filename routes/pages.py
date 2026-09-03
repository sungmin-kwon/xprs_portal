from fastapi import APIRouter
from fastapi.responses import FileResponse

from config import STATIC_DIR

router = APIRouter()


@router.get("/")
def home():
    return FileResponse(STATIC_DIR / "home.html")


@router.get("/dashboard")
def dashboard():
    return FileResponse(STATIC_DIR / "dashboard.html")


@router.get("/about")
def about():
    return FileResponse(STATIC_DIR / "about.html")


@router.get("/favicon.ico")
def favicon():
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")
