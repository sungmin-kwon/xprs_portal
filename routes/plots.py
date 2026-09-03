from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from config import PLOTS_DIR
from disease_registry import enabled_disease_config
from plot_data import write_plotdata_files
from reference_utils import extract_journal_name
from runtime_agents import get_s2_agent
from s2_helpers import get_s2_cache_paths, split_reference_genes
from schemas import PlotsRequest

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
def plotdata_post(req: PlotsRequest) -> dict:
    pid = req.individual_id
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

    s2_agent = get_s2_agent()
    genes = split_reference_genes(gene) or [gene]
    cache_files: list[Path] = []
    for gene_symbol in genes:
        for path in get_s2_cache_paths(gene_symbol):
            if path not in cache_files:
                cache_files.append(path)

    if not cache_files:
        logging.warning("No cache files found for gene reference %s. Rebuilding known pools.", gene)
        for gene_symbol in genes:
            try:
                s2_agent.cached_for_gene(gene_symbol, limit=50)
                s2_agent.cached_for_gene(gene_symbol, limit=15, phenotype="breast cancer")
            except Exception as e:
                logging.error("Failed to rebuild S2 caches for gene %s: %s", gene_symbol, e)
        for gene_symbol in genes:
            for path in get_s2_cache_paths(gene_symbol):
                if path not in cache_files:
                    cache_files.append(path)

    if not cache_files:
        raise HTTPException(status_code=404, detail=f"No cache for gene {gene}")

    for cache_file in cache_files:
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:
            logging.error("Failed to read cache file %s: %s", cache_file, e)
            continue

        for p in payload.get("data", []):
            stored_id = p.get("paperId")
            url = p.get("url") or ""
            is_match = (stored_id == paper_id) or (paper_id in url)

            if is_match:
                return {
                    "paperId": stored_id or paper_id,
                    "title": p.get("title"),
                    "year": p.get("year"),
                    "authors": p.get("authors", []),
                    "journal": extract_journal_name(p) or None,
                    "citationCount": p.get("citationCount"),
                    "abstract": p.get("abstract"),
                    "url": url or f"https://www.semanticscholar.org/paper/{paper_id}",
                    "openAccessPdf": p.get("openAccessPdf", {}),
                }

    raise HTTPException(status_code=404, detail="Paper not found in cache")
