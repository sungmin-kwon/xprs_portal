from fastapi import APIRouter

from config import PHENOTYPE_LABELS_KO
from schemas import PhenotypeConfigResponse

router = APIRouter()


@router.get("/api/phenotype_config", response_model=PhenotypeConfigResponse)
def get_phenotype_config():
    return {"ko_labels": PHENOTYPE_LABELS_KO}
