import re

from fastapi import APIRouter
from fastapi import HTTPException, Request
from fastapi.responses import Response

from disease_registry import enabled_disease_config, get_disease_config
from kpredict_access import require_kpredict_access
from pdf_report import build_pdf_report
from schemas import ReportPdfRequest
from session_logs import load_session_log_by_id

router = APIRouter()


def _model_filename_tag(model: str | None) -> str:
    """Filesystem-safe suffix from a model id, e.g. 'openai/gpt-5.4' -> '_openai-gpt-5.4'."""
    if not model:
        return ""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", model).strip("-")
    return f"_{safe}" if safe else ""


@router.post("/api/report/pdf")
def export_pdf_report(req: ReportPdfRequest, request: Request):
    session = load_session_log_by_id(req.session_id, individual_id=req.individual_id)
    if session.get("cohort") == "kpredict":
        require_kpredict_access(request)
    try:
        disease_config = (
            get_disease_config(req.disease)
            if session.get("cohort") == "kpredict"
            else enabled_disease_config(req.disease)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    pdf_bytes = build_pdf_report(
        session=session,
        density_image_data=req.density_image_data,
        manhattan_image_data=req.manhattan_image_data,
    )
    model_tag = _model_filename_tag(session.get("generation_model"))
    filename = f"xprs_report_{disease_config.slug}_{req.individual_id}{model_tag}.pdf"
    # The report is already fully materialized in memory. Returning it as a
    # regular response gives the browser a Content-Length and avoids an
    # unnecessary chunked streaming boundary during the download.
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
