from fastapi import FastAPI

from . import (
    admin_documents,
    chat,
    cohorts,
    diseases,
    evaluation,
    health,
    pages,
    individuals,
    kpredict,
    models,
    phenotype,
    plots,
    reports,
    sessions,
    summary,
    tasks,
)


def register_routes(app: FastAPI) -> None:
    app.include_router(pages.router)
    app.include_router(admin_documents.router)
    app.include_router(cohorts.router)
    app.include_router(diseases.router)
    app.include_router(evaluation.router)
    app.include_router(individuals.router)
    app.include_router(kpredict.router)
    app.include_router(models.router)
    app.include_router(phenotype.router)
    app.include_router(health.router)
    app.include_router(summary.router)
    app.include_router(chat.router)
    app.include_router(tasks.router)
    app.include_router(sessions.router)
    app.include_router(reports.router)
    app.include_router(plots.router)
