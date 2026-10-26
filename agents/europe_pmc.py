from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests

from reference_utils import (
    GENE_IDENTITY_POLICY_VERSION,
    ReferenceMetadataExtractor,
    gene_identity_profile,
    has_zero_citation_count,
    infer_phenotypes_from_text,
    paper_gene_identity_is_valid,
    parse_metadata_list,
)
from text_utils import emit_progress, unique_preserving_order

logger = logging.getLogger(__name__)

EUROPE_PMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUROPE_PMC_DEFAULT_LIMIT = 25


class EuropePMCAgent:
    """Public Europe PMC REST search with a small provider-local cache."""

    source_name = "europe_pmc"
    display_name = "Europe PMC"

    def __init__(
        self,
        cache_dir: Path | None = None,
        metadata_extractor: ReferenceMetadataExtractor | None = None,
        timeout: float = 20.0,
    ):
        self.cache_dir = cache_dir
        self.metadata_extractor = metadata_extractor
        self.timeout = timeout
        self._request_lock = threading.Lock()

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower() or "general"

    def _cache_path(self, gene: str, phenotype: str | None) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"{self._slug(gene)}_{self._slug(phenotype or 'general')}_epmc.json"

    @staticmethod
    def _read_json(path: Path | None) -> dict[str, Any]:
        if path is None or not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _write_json(path: Path | None, payload: dict[str, Any]) -> None:
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _publication_id(record: dict[str, Any]) -> str:
        pmid = str(record.get("pmid") or "").strip()
        if pmid:
            return f"PMID:{pmid}"
        pmcid = str(record.get("pmcid") or "").strip()
        if pmcid:
            return f"PMCID:{pmcid}"
        doi = str(record.get("doi") or "").strip()
        if doi:
            return f"DOI:{doi.lower()}"
        source = str(record.get("source") or "EPMC").strip()
        identifier = str(record.get("id") or "").strip()
        return f"{source}:{identifier}" if identifier else ""

    @staticmethod
    def _search_query(gene: str, phenotype: str | None) -> str:
        profile = gene_identity_profile(gene)
        identity_terms = [profile.get("symbol") or gene]
        identity_terms.extend(
            term for term in [profile.get("name"), *(profile.get("aliases") or [])]
            if term
        )
        identity = " OR ".join(
            f'TITLE_ABS:"{str(term).replace(chr(34), "")}"' for term in identity_terms
        )
        query = f"({identity})"
        if phenotype:
            safe_phenotype = str(phenotype).replace('"', "").strip()
            query += f' AND TITLE_ABS:"{safe_phenotype}"'
        # The shared eligibility policy rejects uncited records. Asking Europe
        # PMC for its citation-ranked results avoids spending the fallback page
        # on newly deposited zero-citation records.
        return f"{query} sort_cited:y"

    @classmethod
    def _normalize_result(cls, row: dict[str, Any]) -> dict[str, Any]:
        source = str(row.get("source") or "MED").strip()
        identifier = str(row.get("id") or row.get("pmid") or row.get("pmcid") or "").strip()
        journal_info = row.get("journalInfo") if isinstance(row.get("journalInfo"), dict) else {}
        journal_record = (
            journal_info.get("journal")
            if isinstance(journal_info.get("journal"), dict)
            else {}
        )
        journal = str(
            row.get("journalTitle")
            or journal_record.get("title")
            or journal_record.get("medlineAbbreviation")
            or ""
        ).strip()
        year = row.get("pubYear") or journal_info.get("yearOfPublication")
        pmid = str(row.get("pmid") or "").strip() or None
        pmcid = str(row.get("pmcid") or "").strip() or None
        provider_url = f"https://europepmc.org/article/{source}/{identifier}" if identifier else ""
        if pmcid:
            preferred_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
        elif pmid:
            preferred_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        else:
            preferred_url = provider_url
        normalized = {
            "publication_id": cls._publication_id(row),
            "paperId": cls._publication_id(row),  # compatibility with existing response clients
            "pmid": pmid,
            "pmcid": pmcid,
            "doi": str(row.get("doi") or "").strip() or None,
            "title": str(row.get("title") or "").strip(),
            "year": year,
            "abstract": str(row.get("abstractText") or "").strip(),
            "journal": journal,
            "citationCount": row.get("citedByCount"),
            "authors": str(row.get("authorString") or "").strip(),
            "url": preferred_url,
            "provider_url": provider_url,
        }
        return normalized

    def find_cached_paper(
        self,
        paper_id: str,
        genes: list[str] | tuple[str, ...],
    ) -> dict[str, Any] | None:
        """Find one paper in provider caches without making a network request."""
        if self.cache_dir is None:
            return None
        wanted = str(paper_id or "").strip()
        if not wanted:
            return None
        preferred_paths: list[Path] = []
        for gene in genes:
            preferred_paths.extend(self.cache_dir.glob(f"{self._slug(gene)}_*_epmc.json"))
        all_paths = self.cache_dir.glob("*_epmc.json")
        seen_paths: set[Path] = set()
        wanted_folded = wanted.casefold()
        for path in [*preferred_paths, *all_paths]:
            if path in seen_paths:
                continue
            seen_paths.add(path)
            payload = self._read_json(path)
            for paper in payload.get("data", []):
                if not isinstance(paper, dict):
                    continue
                pmid = str(paper.get("pmid") or "").strip()
                pmcid = str(paper.get("pmcid") or "").strip()
                doi = str(paper.get("doi") or "").strip()
                identifiers = {
                    self._publication_id(paper),
                    str(paper.get("paperId") or "").strip(),
                    pmid,
                    f"PMID:{pmid}" if pmid else "",
                    pmcid,
                    f"PMCID:{pmcid}" if pmcid else "",
                    doi,
                    f"DOI:{doi}" if doi else "",
                }
                if wanted_folded in {value.casefold() for value in identifiers if value}:
                    return paper
        return None

    def cached_query_succeeded(self, gene: str, phenotype: str | None) -> bool:
        return self._read_json(self._cache_path(gene, phenotype)).get("fetch_ok") is True

    def cached_papers(self, gene: str, phenotype: str | None = None) -> list[dict[str, Any]]:
        payload = self._read_json(self._cache_path(gene, phenotype))
        return [row for row in payload.get("data", []) if isinstance(row, dict)]

    def cached_for_gene(
        self,
        gene: str,
        limit: int = EUROPE_PMC_DEFAULT_LIMIT,
        phenotype: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[dict[str, Any]]:
        path = self._cache_path(gene, phenotype)
        cached = self._read_json(path)
        if cached.get("fetch_ok") is True:
            return [row for row in cached.get("data", []) if isinstance(row, dict)]

        query = self._search_query(gene, phenotype)
        emit_progress(progress_callback, f'Sending query to Europe PMC: "{query}" (public API)')
        try:
            with self._request_lock:
                response = requests.get(
                    EUROPE_PMC_SEARCH_URL,
                    params={
                        "query": query,
                        "resultType": "core",
                        "format": "json",
                        "pageSize": max(1, min(int(limit), 100)),
                    },
                    timeout=self.timeout,
                )
            response.raise_for_status()
            rows = response.json().get("resultList", {}).get("result", [])
            papers = [self._normalize_result(row) for row in rows if isinstance(row, dict)]
            papers = [paper for paper in papers if paper.get("publication_id")]
            if self.metadata_extractor and papers:
                papers, _ = self.metadata_extractor.enrich_papers(papers, seed_gene=gene)
            else:
                papers, _ = ReferenceMetadataExtractor(use_llm=False).enrich_papers(
                    papers, seed_gene=gene
                )
            payload = {
                "source": self.source_name,
                "gene": gene,
                "phenotype": phenotype,
                "query": query,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "fetch_ok": True,
                "pagination_complete": True,
                "raw_examined": len(rows),
                "eligible_count": sum(paper_gene_identity_is_valid(p, gene) for p in papers),
                "data": papers,
            }
            self._write_json(path, payload)
            emit_progress(progress_callback, f'Europe PMC returned {len(papers)} papers for "{query}"')
            return papers
        except (requests.RequestException, ValueError, TypeError) as exc:
            logger.warning("[EUROPE_PMC] Search failed for query=%r: %s", query, exc)
            emit_progress(progress_callback, f'Europe PMC search was unavailable for "{query}"')
            return []

    def papers_to_docs(
        self,
        gene: str,
        papers: list[dict[str, Any]],
        pool_type: str = "general",
        phenotype: str | None = None,
    ) -> list[dict[str, Any]]:
        if self.metadata_extractor:
            papers, _ = self.metadata_extractor.enrich_papers(papers, seed_gene=gene)
        else:
            papers, _ = ReferenceMetadataExtractor(use_llm=False).enrich_papers(
                papers, seed_gene=gene
            )
        phenotype_slug = self._slug(phenotype or "general")
        docs: list[dict[str, Any]] = []
        for paper in papers:
            publication_id = self._publication_id(paper)
            title = str(paper.get("title") or "").strip()
            abstract = str(paper.get("abstract") or "").strip()
            if not publication_id or not abstract or has_zero_citation_count(paper):
                continue
            if not paper_gene_identity_is_valid(paper, gene):
                continue
            text = f"{title}\n\n{abstract}"
            phenotypes = parse_metadata_list(paper.get("extracted_phenotypes")) or infer_phenotypes_from_text(text)
            genes = parse_metadata_list(paper.get("extracted_genes"))
            stable_slug = self._slug(publication_id)
            docs.append({
                "id": f"literature::europe_pmc::{pool_type}::{phenotype_slug}::{gene}::{stable_slug}",
                "text": text,
                "meta": {
                    "source": self.source_name,
                    "publication_id": publication_id,
                    "paperId": publication_id,
                    "pmid": paper.get("pmid"),
                    "pmcid": paper.get("pmcid"),
                    "doi": paper.get("doi"),
                    "gene": gene,
                    "pool_type": pool_type,
                    "phenotype": phenotype,
                    "title": title,
                    "url": paper.get("url") or "",
                    "provider_url": paper.get("provider_url") or "",
                    "journal": paper.get("journal") or "",
                    "citationCount": paper.get("citationCount"),
                    "year": paper.get("year"),
                    "authors": paper.get("authors") or "",
                    "extracted_genes": ", ".join(unique_preserving_order(genes)) or None,
                    "extracted_phenotypes": ", ".join(unique_preserving_order(phenotypes)) or None,
                    "gene_identity_validated": True,
                    "gene_identity_method": paper.get("gene_identity_method") or "validated",
                    "gene_identity_policy_version": GENE_IDENTITY_POLICY_VERSION,
                    "search_query": self._search_query(gene, phenotype),
                },
            })
        return docs
