from fastapi import APIRouter, Request

from cohort_registry import DEFAULT_COHORT_SLUG, list_cohorts
from kpredict_access import has_kpredict_access, kpredict_root


router = APIRouter()


@router.get("/api/cohorts")
def get_cohorts(request: Request):
    kpredict_available = kpredict_root() is not None and has_kpredict_access(request)
    cohorts = []
    for cohort in list_cohorts():
        item = cohort.public_dict()
        if cohort.slug == "kpredict":
            item["data_available"] = kpredict_available
            item["unavailable_reason"] = None if kpredict_available else cohort.unavailable_reason
        cohorts.append(item)
    return {
        "default_cohort": DEFAULT_COHORT_SLUG,
        "cohorts": cohorts,
    }
