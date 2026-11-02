from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    individual_id: str
    query: str
    disease: str = "breast_cancer"
    cohort: str = "1000_genomes"
    session_id: str | None = None
    language: str | None = "en"
    model: str | None = None  # OpenRouter generation model id; None -> default


class ReferenceItem(BaseModel):
    n: int
    title: str | None = None
    gene: str | None = None
    phenotype: str | None = None
    journal: str | None = None
    citationCount: int | None = None
    source: str | None = None
    paperId: str | None = None
    url: str | None = None


class ChatResponse(BaseModel):
    answer: str
    answer_id: str | None = None
    session_id: str | None = None
    references: list[ReferenceItem] = []


class SummaryRequest(BaseModel):
    individual_id: str
    disease: str = "breast_cancer"
    cohort: str = "1000_genomes"
    # Number of genes selected from each contribution direction.
    gene_count: int = Field(default=5, ge=1, le=5)
    language: str | None = "en"
    model: str | None = None  # OpenRouter generation model id; None -> default


class SummaryResponse(BaseModel):
    summary: str
    simple_summary: str
    detailed_summary: str
    references: list[ReferenceItem] = []
    session_id: str | None = None
    report_ready: bool = False


class SummaryPreviewResponse(BaseModel):
    genes: list[str]
    gene_count: int


class PhenotypeConfigResponse(BaseModel):
    ko_labels: dict[str, str]


class SemanticScholarHealthResponse(BaseModel):
    status: str
    query: str | None = None
    api_key_present: bool
    api_key_status: str
    public_fallback_enabled: bool
    public_fallback_active: bool
    effective_mode: str
    last_mode: str | None = None
    last_status_code: int | None = None
    last_error: str | None = None
    public_min_interval_seconds: float | None = None
    api_key_check: str | None = None
    api_key_status_code: int | None = None
    public_check: str | None = None
    public_status_code: int | None = None
    hit_count: int | None = None


class PlotsRequest(BaseModel):
    individual_id: str
    disease: str = "breast_cancer"
    cohort: str = "1000_genomes"


class DiseaseRiskOverviewRequest(BaseModel):
    individual_id: str
    cohort: str = "1000_genomes"


class TaskStartResponse(BaseModel):
    task_id: str


class ReportPdfRequest(BaseModel):
    session_id: str
    individual_id: str
    disease: str = "breast_cancer"
    language: str | None = None
    density_image_data: str | None = None
    manhattan_image_data: str | None = None
