from fastapi import APIRouter

from cohort_registry import DEFAULT_COHORT_SLUG, list_cohorts


router = APIRouter()


@router.get("/api/cohorts")
def get_cohorts():
    return {
        "default_cohort": DEFAULT_COHORT_SLUG,
        "cohorts": [cohort.public_dict() for cohort in list_cohorts()],
    }
