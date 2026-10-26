from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

from config import PLOTS_DIR
from disease_registry import enabled_disease_config
from plot_data import write_plotdata_files
from reference_utils import extract_journal_name, split_reference_genes
from runtime_agents import get_europe_pmc_agent, get_rag_agent, get_s2_agent
from schemas import PlotsRequest
from cohort_registry import get_cohort_config
from kpredict_access import require_kpredict_access
from kpredict_data import available_diseases, density_data, manhattan_data

router = APIRouter()


def disease_plot_dir(disease: str) -> Path:
    return PLOTS_DIR / disease


def plotdata_paths(pid: str, disease: str) -> dict[str, Path]:
    base = disease_plot_dir(disease)
    return {
        "manhattan": base / f"{pid}_manhattan.json",
        "density": base / f"{pid}_density.json",
    }


def generate_plotdata(pid: str, disease: str) -> None:
    try:
        write_plotdata_files(pid, disease_plot_dir(disease), disease=disease)
    except Exception as e:
        logging.error("Python plotdata generation failed for %s/%s: %s", disease, pid, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Python plotdata generation failed: {e}")


@router.post("/api/plotdata")
def plotdata_post(req: PlotsRequest, request: Request) -> dict:
    pid = req.individual_id
    try:
        cohort = get_cohort_config(req.cohort)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if cohort.slug == "kpredict":
        root = require_kpredict_access(request)
        if req.disease not in available_diseases(root):
            raise HTTPException(status_code=404, detail="Disease data not found")
        try:
            return {
                "individual_id": pid,
                "disease": req.disease,
                "cohort": cohort.slug,
                "generated": False,
                "manhattan": manhattan_data(root, req.disease, pid),
                "density": density_data(root, req.disease, pid),
                "manhattan_url": None,
                "density_url": None,
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
    try:
        disease = enabled_disease_config(req.disease).slug
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    paths = plotdata_paths(pid, disease)

    missing = [k for k, p in paths.items() if not p.exists()]
    generated = False

    if missing:
        generate_plotdata(pid, disease)
        generated = True

    still_missing = [k for k, p in paths.items() if not p.exists()]
    if still_missing:
        logging.error("Python plot generation finished but plotdata missing: %s", still_missing)
        raise HTTPException(status_code=500, detail=f"Plotdata missing after Python generation: {still_missing}")

    try:
        with open(paths["manhattan"], "r", encoding="utf-8") as f:
            manhattan = json.load(f)
        with open(paths["density"], "r", encoding="utf-8") as f:
            density = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read plotdata JSON: {e}")

    return {
        "individual_id": pid,
        "disease": disease,
        "generated": generated,
        "manhattan": manhattan,
        "density": density,
        "manhattan_url": f"/static/plots/{disease}/{pid}_manhattan.json?v={int(paths['manhattan'].stat().st_mtime)}",
        "density_url": f"/static/plots/{disease}/{pid}_density.json?v={int(paths['density'].stat().st_mtime)}",
    }


@router.get("/api/paper")
def get_paper(paper_id: str = Query(...), gene: str = Query(...)):
    if paper_id.startswith("local:"):
        raise HTTPException(status_code=404, detail="Local reference notes are not available in the paper viewer")

    genes = split_reference_genes(gene) or [gene]
    indexed_paper = get_rag_agent().find_indexed_paper(paper_id, genes)
    if indexed_paper is not None:
        return indexed_paper

    europe_pmc_agent = get_europe_pmc_agent()
    europe_pmc_paper = europe_pmc_agent.find_cached_paper(paper_id, genes)
    if europe_pmc_paper is not None:
        return {
            "paperId": europe_pmc_paper.get("publication_id") or paper_id,
            "title": europe_pmc_paper.get("title"),
            "year": europe_pmc_paper.get("year"),
            "authors": europe_pmc_paper.get("authors") or "",
            "journal": europe_pmc_paper.get("journal") or None,
            "citationCount": europe_pmc_paper.get("citationCount"),
            "abstract": europe_pmc_paper.get("abstract"),
            "url": europe_pmc_paper.get("url") or "",
            "pmid": europe_pmc_paper.get("pmid"),
            "pmcid": europe_pmc_paper.get("pmcid"),
            "doi": europe_pmc_paper.get("doi"),
            "openAccessPdf": {},
        }
    s2_paper = get_s2_agent().find_cached_paper(paper_id, genes)
    if s2_paper is not None:
        external_ids = (
            s2_paper.get("externalIds")
            if isinstance(s2_paper.get("externalIds"), dict)
            else {}
        )
        url = s2_paper.get("url") or ""
        return {
            "paperId": s2_paper.get("paperId") or paper_id,
            "title": s2_paper.get("title"),
            "year": s2_paper.get("year"),
            "authors": s2_paper.get("authors", []),
            "journal": extract_journal_name(s2_paper) or None,
            "citationCount": s2_paper.get("citationCount"),
            "abstract": s2_paper.get("abstract"),
            "url": url or f"https://www.semanticscholar.org/paper/{paper_id}",
            "pmid": str(external_ids.get("PubMed") or s2_paper.get("pmid") or "").strip() or None,
            "pmcid": str(external_ids.get("PubMedCentral") or s2_paper.get("pmcid") or "").strip() or None,
            "doi": str(external_ids.get("DOI") or s2_paper.get("doi") or "").strip() or None,
            "openAccessPdf": s2_paper.get("openAccessPdf", {}),
        }

    raise HTTPException(status_code=404, detail="Paper not found in cache")
