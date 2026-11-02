import json
import logging
import re
import threading
from typing import Any, Callable

from config import PHENOTYPE_ALIASES
from phenotype_utils import infer_phenotypes_from_text, normalize_phenotype_values
from text_utils import unique_preserving_order

logger = logging.getLogger(__name__)


# Increment this whenever the rules that decide whether an acronym denotes the
# intended gene change. The version is stored in both the JSON cache and Chroma
# metadata so old lexical-only matches cannot silently remain citable.
GENE_IDENTITY_POLICY_VERSION = 2
GENE_SEARCH_STRATEGY_VERSION = 2

# Short symbols are particularly prone to acronym collisions. A small curated
# identity record improves both search precision and deterministic validation;
# other short symbols are sent through the semantic identity check below.
GENE_IDENTITY_OVERRIDES: dict[str, dict[str, Any]] = {
    "GML": {
        "name": "glycosylphosphatidylinositol anchored molecule like",
        "aliases": ["LY6DL", "GPI-anchored molecule-like protein"],
    },
}


def _extract_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except Exception:
        return {}


def _normalize_gene_symbol(value: str) -> str:
    token = (value or "").strip()
    if not token:
        return ""
    token = token.upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9-]{1,19}", token):
        return ""
    return token


def gene_identity_profile(gene: str) -> dict[str, Any]:
    symbol = _normalize_gene_symbol(gene)
    override = GENE_IDENTITY_OVERRIDES.get(symbol, {})
    return {
        "symbol": symbol,
        "name": str(override.get("name") or "").strip(),
        "aliases": [
            str(alias).strip()
            for alias in override.get("aliases", [])
            if str(alias).strip()
        ],
        "requires_semantic_validation": bool(symbol and len(symbol) <= 3),
    }


def gene_search_query(gene: str, phenotype: str | None = None) -> str:
    """Build a plain-text Semantic Scholar query with gene-sense context."""
    profile = gene_identity_profile(gene)
    terms = [profile["symbol"] or str(gene).strip()]
    if profile["name"]:
        terms.append(profile["name"])
        terms.extend(profile["aliases"][:1])
    elif profile["requires_semantic_validation"]:
        terms.extend(["human gene", "genomics"])
    if phenotype:
        terms.append(str(phenotype).strip())
    return " ".join(term for term in terms if term).strip()


def gene_search_strategies(
    gene: str,
    phenotype: str | None = None,
) -> list[dict[str, str]]:
    """Return ordered, deduplicated Semantic Scholar recall strategies.

    The first query remains the most identity-specific query used for an
    interactive cache miss. Later strategies are consumed incrementally by
    rescue/background pagination. Broad acronym searches are safe to include
    here because every returned paper must still pass the independent gene
    identity gate before it can enter RAG or the reference list.
    """
    profile = gene_identity_profile(gene)
    symbol = profile["symbol"] or str(gene).strip()
    canonical_phenotype = str(phenotype or "").strip().lower()
    candidates: list[tuple[str, str]] = [
        ("identity", gene_search_query(gene, phenotype)),
    ]

    if canonical_phenotype:
        # Disease names have common alternatives in the literature (for
        # example T2D and type II diabetes). Use at most two to bound upstream
        # traffic; the eligible-document target usually stops the sweep sooner.
        aliases = PHENOTYPE_ALIASES.get(canonical_phenotype, [])[:2]
        identity_terms = [symbol]
        if profile["name"]:
            identity_terms.append(profile["name"])
            identity_terms.extend(profile["aliases"][:1])
        elif profile["requires_semantic_validation"]:
            identity_terms.extend(["human gene", "genomics"])
        for index, alias in enumerate(aliases, start=1):
            candidates.append((f"phenotype_alias_{index}", " ".join([
                *identity_terms,
                str(alias).strip(),
            ])))

    if profile["requires_semantic_validation"]:
        suffix = canonical_phenotype
        candidates.extend([
            ("symbol_gene", " ".join(term for term in [symbol, "gene", suffix] if term)),
            ("symbol_recall", " ".join(term for term in [symbol, suffix] if term)),
        ])

    seen: set[str] = set()
    strategies: list[dict[str, str]] = []
    for name, query in candidates:
        normalized = " ".join(str(query).split()).strip()
        if not normalized or normalized.casefold() in seen:
            continue
        seen.add(normalized.casefold())
        strategies.append({"name": name, "query": normalized})
    return strategies


def _identity_name_is_present(text: str, profile: dict[str, Any]) -> bool:
    haystack = (text or "").casefold()
    identity_terms = [profile.get("name") or "", *(profile.get("aliases") or [])]
    return any(
        len(str(term).strip()) >= 4 and str(term).strip().casefold() in haystack
        for term in identity_terms
    )


def paper_gene_identity_is_valid(record: dict[str, Any], gene: str) -> bool:
    try:
        policy_version = int(record.get("gene_identity_policy_version") or 0)
    except (TypeError, ValueError):
        policy_version = 0
    if policy_version != GENE_IDENTITY_POLICY_VERSION:
        return False
    if record.get("gene_identity_validated") is not True:
        return False
    target = _normalize_gene_symbol(gene)
    extracted = {
        _normalize_gene_symbol(value)
        for value in parse_metadata_list(record.get("extracted_genes"))
    }
    return bool(target and target in extracted)


class ReferenceMetadataExtractor:
    def __init__(
        self,
        llm_chat: Callable[[list[dict[str, str]], int], str] | None = None,
        timeout: int = 45,
        use_llm: bool = False,
        batch_size: int = 10,
        label: str = "extractor",
    ):
        self.llm_chat = llm_chat
        self.timeout = timeout
        self.use_llm = use_llm
        self.batch_size = max(1, int(batch_size or 10))
        self._llm_temporarily_disabled = False
        self._llm_lock = threading.Lock()
        self.label = label

    @staticmethod
    def _compact_abstract(text: str, max_chars: int = 2400) -> str:
        raw = (text or "").strip()
        if len(raw) <= max_chars:
            return raw
        trimmed = raw[:max_chars].rsplit(" ", 1)[0].strip()
        return f"{trimmed} ..."

    @staticmethod
    def _normalize_llm_batch_payload(parsed: Any) -> list[dict[str, Any]]:
        if isinstance(parsed, dict):
            items = parsed.get("items")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        return []

    def _extract_entities_batch_with_llm(
        self,
        batch: list[dict[str, Any]],
        *,
        seed_gene: str | None = None,
    ) -> dict[str, dict[str, list[str]]]:
        if not self.llm_chat or not batch:
            return {}

        seed_profile = gene_identity_profile(seed_gene or "")
        compact_items = []
        for item in batch:
            compact_items.append(
                {
                    "paper_id": item["paper_id"],
                    "title": item.get("title") or "",
                    "abstract": self._compact_abstract(item.get("abstract") or ""),
                    "seed_gene": seed_gene or "",
                    "seed_gene_full_name": seed_profile.get("name") or "",
                    "seed_gene_aliases": seed_profile.get("aliases") or [],
                }
            )

        logger.info(
            '[REF_EXTRACT] provider=%s batch_size=%d seed_gene="%s" starting batch entity extraction',
            self.label,
            len(batch),
            seed_gene or "",
        )
        with self._llm_lock:
            raw = self.llm_chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "You extract biomedical entities from paper titles and abstracts. "
                            "Return JSON only. The JSON must have an 'items' array. "
                            "Each item must contain paper_id, genes, and phenotypes. "
                            "genes must be gene symbols explicitly mentioned in the text. "
                            "The seed symbol may be an ambiguous acronym. Include the seed gene in genes only when "
                            "the text uses that symbol, its full name, or an alias to denote the intended human gene "
                            "or its gene product. Do not count unrelated expansions such as a method, chemical, "
                            "organization, lesion, material, or statistical model that happens to use the same acronym. "
                            "phenotypes must be disease or phenotype names explicitly mentioned or clearly denoted in the text. "
                            "Do not infer diseases that are not stated. "
                            "Do not include generic words like cancer, disease, tumor, neoplasm, or disorder by themselves."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Return JSON like "
                            "{\"items\": [{\"paper_id\": \"...\", \"genes\": [...], \"phenotypes\": [...]}]}.\n\n"
                            f"{json.dumps(compact_items, ensure_ascii=False)}"
                        ),
                    },
                ],
                self.timeout,
            )
        parsed = _extract_json_object(raw)
        normalized_items = self._normalize_llm_batch_payload(parsed)
        logger.info(
            "[REF_EXTRACT] provider=%s parsed %d entity payload items from batch",
            self.label,
            len(normalized_items),
        )
        out: dict[str, dict[str, list[str]]] = {}
        for item in normalized_items:
            paper_id = str(item.get("paper_id") or "").strip()
            if not paper_id:
                continue
            genes = [
                normalized
                for value in item.get("genes", [])
                if isinstance(value, str)
                for normalized in [_normalize_gene_symbol(value)]
                if normalized
            ]
            phenotypes = [
                value.strip().lower()
                for value in item.get("phenotypes", [])
                if isinstance(value, str) and value.strip()
            ]
            out[paper_id] = {
                "genes": unique_preserving_order(genes),
                "phenotypes": normalize_phenotype_values(phenotypes),
            }
        if out:
            for item in batch:
                paper_id = item.get("paper_id")
                if not paper_id or paper_id not in out:
                    continue
                title = (item.get("title") or "").strip()
                logger.info(
                    '[REF_EXTRACT] paperId=%s title="%s" genes=%s phenotypes=%s',
                    paper_id,
                    title,
                    out[paper_id]["genes"],
                    out[paper_id]["phenotypes"],
                )
        else:
            logger.info(
                "[REF_EXTRACT] provider=%s batch returned no usable extracted entities",
                self.label,
            )
        return out

    def extract_entities(
        self,
        *,
        title: str,
        abstract: str,
        seed_gene: str | None = None,
    ) -> dict[str, list[str]]:
        text = "\n".join(part for part in [title, abstract] if part).strip()
        if not self.use_llm or not self.llm_chat or not text:
            return {"genes": [], "phenotypes": []}

        try:
            raw = self.llm_chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "You extract biomedical entities from paper titles and abstracts. "
                            "Return JSON only with keys genes and phenotypes. "
                            "genes must be gene symbols explicitly mentioned in the text. "
                            "phenotypes must be disease or phenotype names explicitly mentioned or clearly denoted in the text. "
                            "Do not infer diseases that are not stated. "
                            "Do not include generic words like cancer, disease, tumor, neoplasm, or disorder by themselves."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Seed gene: {seed_gene or 'None'}\n"
                            f"Title: {title or ''}\n"
                            f"Abstract: {abstract or ''}\n\n"
                            "Return JSON like {\"genes\": [...], \"phenotypes\": [...]}."
                        ),
                    },
                ],
                self.timeout,
            )
            parsed = _extract_json_object(raw)
            llm_genes = [
                normalized
                for item in parsed.get("genes", [])
                if isinstance(item, str)
                for normalized in [_normalize_gene_symbol(item)]
                if normalized
            ]
            llm_phenotypes = normalize_phenotype_values([
                item.strip().lower()
                for item in parsed.get("phenotypes", [])
                if isinstance(item, str) and item.strip()
            ])
            return {
                "genes": unique_preserving_order(llm_genes),
                "phenotypes": llm_phenotypes,
            }
        except Exception:
            return {"genes": [], "phenotypes": []}

    def enrich_papers(
        self,
        papers: list[dict[str, Any]],
        *,
        seed_gene: str | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        changed = False
        pending_batch: list[dict[str, Any]] = []
        pending_index_by_id: dict[str, int] = {}
        seed_profile = gene_identity_profile(seed_gene or "")
        normalized_seed_gene = seed_profile.get("symbol") or ""

        for idx, paper in enumerate(papers):
            paper_id = extract_s2_paper_id(paper)
            if not paper_id:
                continue
            try:
                existing_policy_version = int(
                    paper.get("gene_identity_policy_version") or 0
                )
            except (TypeError, ValueError):
                existing_policy_version = 0
            if (
                paper.get("entity_extraction_complete") is True
                and existing_policy_version == GENE_IDENTITY_POLICY_VERSION
            ):
                continue

            title = paper.get("title", "")
            abstract = paper.get("abstract", "")
            text = "\n".join(part for part in [title, abstract] if part).strip()

            heuristic_genes: list[str] = []
            identity_method = ""
            symbol_is_present = bool(
                seed_gene and text_mentions_gene(text, seed_gene)
            )
            identity_name_is_present = bool(
                seed_gene and _identity_name_is_present(text, seed_profile)
            )
            requires_semantic_validation = bool(
                seed_profile.get("requires_semantic_validation")
            )
            if seed_gene and normalized_seed_gene:
                if identity_name_is_present:
                    heuristic_genes = [normalized_seed_gene]
                    identity_method = "official_name_or_alias"
                elif symbol_is_present and not requires_semantic_validation:
                    heuristic_genes = [normalized_seed_gene]
                    identity_method = "unambiguous_symbol"

            heuristic_phenotypes = infer_phenotypes_from_text(text)

            paper["extracted_genes"] = heuristic_genes
            paper["extracted_phenotypes"] = heuristic_phenotypes
            paper["gene_identity_policy_version"] = GENE_IDENTITY_POLICY_VERSION
            paper["gene_identity_validated"] = bool(heuristic_genes)
            paper["gene_identity_method"] = identity_method or "rejected"
            paper["entity_extraction_complete"] = False
            changed = True

            # A result with neither the symbol nor an official identity term
            # cannot refer to the requested gene and does not need an LLM call.
            if seed_gene and not symbol_is_present and not identity_name_is_present:
                paper["entity_extraction_complete"] = True
                logger.info(
                    '[REF_EXTRACT] skipped non-matching paperId=%s for seed_gene="%s"',
                    paper_id,
                    seed_gene,
                )
                continue

            # An official name/alias or a longer unambiguous symbol is enough
            # for deterministic identity validation.
            if heuristic_genes or heuristic_phenotypes:
                if heuristic_genes:
                    paper["entity_extraction_complete"] = True
                    logger.info(
                        '[REF_EXTRACT] heuristic paperId=%s title="%s" genes=%s phenotypes=%s identity=%s',
                        paper_id,
                        (title or "").strip(),
                        heuristic_genes,
                        heuristic_phenotypes,
                        identity_method,
                    )
                    continue

            # Short symbols such as GML require semantic disambiguation when
            # only the acronym itself appears.
            if symbol_is_present and self.use_llm and self.llm_chat:
                pending_batch.append(
                    {
                        "paper_id": paper_id,
                        "title": title,
                        "abstract": abstract,
                    }
                )
                pending_index_by_id[paper_id] = idx
            else:
                paper["entity_extraction_complete"] = True

        if self.use_llm and not self._llm_temporarily_disabled and self.llm_chat and pending_batch:
            logger.info(
                '[REF_EXTRACT] provider=%s scheduling %d papers for LLM extraction (seed_gene="%s")',
                self.label,
                len(pending_batch),
                seed_gene or "",
            )
            for start in range(0, len(pending_batch), self.batch_size):
                batch = pending_batch[start : start + self.batch_size]
                batch_succeeded = True
                try:
                    llm_results = self._extract_entities_batch_with_llm(batch, seed_gene=seed_gene)
                except Exception as e:
                    logger.warning(
                        "[REF_EXTRACT] disabling LLM extraction for the rest of this run after batch failure: %s",
                        e,
                    )
                    self._llm_temporarily_disabled = True
                    llm_results = {}
                    batch_succeeded = False
                for paper_id, entities in llm_results.items():
                    idx = pending_index_by_id.get(paper_id)
                    if idx is None:
                        continue
                    paper = papers[idx]
                    llm_genes = unique_preserving_order(entities.get("genes", []))
                    llm_phenotypes = normalize_phenotype_values(entities.get("phenotypes", []))
                    if llm_genes != parse_metadata_list(paper.get("extracted_genes")) or llm_phenotypes != parse_metadata_list(paper.get("extracted_phenotypes")):
                        paper["extracted_genes"] = llm_genes
                        paper["extracted_phenotypes"] = llm_phenotypes
                        changed = True
                    seed_confirmed = bool(
                        normalized_seed_gene
                        and normalized_seed_gene in {
                            _normalize_gene_symbol(value) for value in llm_genes
                        }
                    )
                    paper["gene_identity_policy_version"] = GENE_IDENTITY_POLICY_VERSION
                    paper["gene_identity_validated"] = seed_confirmed
                    paper["gene_identity_method"] = (
                        "semantic_validation" if seed_confirmed else "semantic_rejection"
                    )
                    logger.info(
                        '[REF_EXTRACT] merged paperId=%s title="%s" genes=%s phenotypes=%s identity=%s',
                        paper_id,
                        (paper.get("title") or "").strip(),
                        paper.get("extracted_genes"),
                        paper.get("extracted_phenotypes"),
                        paper.get("gene_identity_method"),
                    )
                if batch_succeeded:
                    for item in batch:
                        paper_id = item.get("paper_id")
                        idx = pending_index_by_id.get(paper_id)
                        if idx is not None:
                            papers[idx]["entity_extraction_complete"] = True
                            changed = True

        elif self.use_llm and not pending_batch:
            logger.info(
                '[REF_EXTRACT] provider=%s no papers required LLM extraction for seed_gene="%s"',
                self.label,
                seed_gene or "",
            )

        return papers, changed


def extract_publication_id(record: dict[str, Any]) -> str:
    """Return a stable, provider-neutral publication identifier."""
    pid = str(
        record.get("publication_id")
        or record.get("paperId")
        or record.get("paper_id")
        or ""
    ).strip()
    if pid:
        return pid

    pmid = str(record.get("pmid") or "").strip()
    if pmid:
        return f"PMID:{pmid}"
    pmcid = str(record.get("pmcid") or "").strip()
    if pmcid:
        return f"PMCID:{pmcid}"
    doi = str(record.get("doi") or "").strip()
    if doi:
        return f"DOI:{doi.lower()}"

    url = (record.get("url") or "").strip()
    match = re.search(r"semanticscholar\.org/paper/([0-9a-fA-F]{40})", url)
    if match:
        return match.group(1)

    return ""


def extract_s2_paper_id(record: dict[str, Any]) -> str:
    """Backward-compatible alias for callers not yet renamed."""
    return extract_publication_id(record)


def split_reference_genes(gene_text: str) -> list[str]:
    """Split a merged reference gene label while preserving display order."""
    genes: list[str] = []
    seen: set[str] = set()
    for token in (gene_text or "").split(","):
        gene = token.strip()
        key = gene.upper()
        if not gene or key in seen:
            continue
        seen.add(key)
        genes.append(gene)
    return genes


def publication_dedup_key(record: dict[str, Any]) -> str:
    """Return a provider-neutral key when shared identifiers are available."""
    external_ids = (
        record.get("externalIds")
        if isinstance(record.get("externalIds"), dict)
        else {}
    )
    pmid = str(record.get("pmid") or external_ids.get("PubMed") or "").strip()
    if pmid:
        return f"PMID:{pmid}"
    pmcid = str(
        record.get("pmcid") or external_ids.get("PubMedCentral") or ""
    ).strip().upper()
    if pmcid:
        return f"PMCID:{pmcid}"
    doi = str(record.get("doi") or external_ids.get("DOI") or "").strip().lower()
    if doi:
        return f"DOI:{doi}"
    return extract_publication_id(record)


def extract_journal_name(record: dict[str, Any]) -> str:
    journal = record.get("journal")
    if isinstance(journal, dict):
        name = (journal.get("name") or "").strip()
        if name:
            return name
    if isinstance(journal, str) and journal.strip():
        return journal.strip()

    publication_venue = record.get("publicationVenue")
    if isinstance(publication_venue, dict):
        name = (publication_venue.get("name") or "").strip()
        if name:
            return name

    venue = record.get("venue")
    if isinstance(venue, str) and venue.strip():
        return venue.strip()

    return ""


def normalize_citations(text: str) -> str:
    """Normalize citation bracket styles and split grouped citations into [n][m] form."""

    text = re.sub(r"【\s*(\d+(?:\s*[,，\-–]\s*\d+)*)\s*】", r"[\1]", text)
    text = re.sub(r"［\s*(\d+(?:\s*[,，\-–]\s*\d+)*)\s*］", r"[\1]", text)
    text = re.sub(r"〔\s*(\d+(?:\s*[,，\-–]\s*\d+)*)\s*〕", r"[\1]", text)
    text = re.sub(
        r"\[(\d+)\s*[;|/]\s*OT:\s*([A-Za-z0-9._-]+)\]",
        r"[\1][OT: \2]",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\[OT:\s*([A-Za-z0-9._-]+)\s*[;|/]\s*(\d+)\]",
        r"[OT: \1][\2]",
        text,
        flags=re.IGNORECASE,
    )

    def repl(match: re.Match) -> str:
        inner = match.group(1).strip()
        if not re.fullmatch(r"[0-9,，\s\-–]+", inner):
            return match.group(0)

        nums: list[int] = []
        for token in re.split(r"\s*[,，]\s*", inner):
            token = token.strip()
            if not token:
                continue

            range_match = re.fullmatch(r"(\d+)\s*[\-–]\s*(\d+)", token)
            if range_match:
                a = int(range_match.group(1))
                b = int(range_match.group(2))
                if a <= b and (b - a) <= 50:
                    nums.extend(range(a, b + 1))
                else:
                    nums.extend([a, b])
                continue

            if token.isdigit():
                nums.append(int(token))

        seen: set[int] = set()
        ordered = [x for x in nums if not (x in seen or seen.add(x))]
        return "".join(f"[{x}]" for x in ordered) if ordered else match.group(0)

    return re.sub(r"\[([0-9,\s\-–]+)\]", repl, text)


def text_mentions_gene(text: str, gene: str) -> bool:
    gene_symbol = (gene or "").strip()
    if not gene_symbol:
        return False
    return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(gene_symbol)}(?![A-Za-z0-9])", text or "", flags=re.IGNORECASE))


def text_has_usable_abstract(text: str) -> bool:
    body = (text or "").split("\n\n", 1)
    if len(body) < 2:
        return False
    return bool(body[1].strip())


def parse_metadata_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def has_zero_citation_count(record: dict[str, Any]) -> bool:
    value = record.get("citationCount")
    if value is None or value == "":
        return False
    try:
        return int(value) == 0
    except (TypeError, ValueError):
        return False


NON_ARTICLE_NOTICE_RE = re.compile(
    r"^\s*(correction|erratum|retraction|expression\s+of\s+concern)\s*:",
    flags=re.IGNORECASE,
)


def is_non_article_notice_title(title: str) -> bool:
    return bool(NON_ARTICLE_NOTICE_RE.search(title or ""))


def literature_paper_is_eligible(record: dict[str, Any], gene: str) -> bool:
    """Apply the complete cache-to-Chroma publication eligibility policy."""
    return bool(
        extract_publication_id(record)
        and str(record.get("abstract") or "").strip()
        and not has_zero_citation_count(record)
        and not is_non_article_notice_title(str(record.get("title") or ""))
        and paper_gene_identity_is_valid(record, gene)
    )


def build_reference_hit(
    text: str,
    meta: dict[str, Any] | None,
    *,
    gene: str,
) -> tuple[str, dict[str, Any]] | None:
    meta = meta or {}
    if not text_has_usable_abstract(text):
        return None
    if (meta.get("source") or "").strip().lower() in {"semanticscholar", "europe_pmc"} and not paper_gene_identity_is_valid(meta, gene):
        return None
    if has_zero_citation_count(meta):
        return None

    title = (meta.get("title") or "").strip() or "Untitled"
    inferred_phenotypes = parse_metadata_list(meta.get("extracted_phenotypes")) or infer_phenotypes_from_text(
        "\n".join(part for part in [title, text] if part)
    )

    return text, {
        "title": title,
        "paperId": extract_publication_id(meta) or None,
        "publicationId": extract_publication_id(meta) or None,
        "source": (meta.get("source") or "unknown").strip(),
        "gene": gene,
        "url": (meta.get("url") or "").strip(),
        "pmid": (meta.get("pmid") or "").strip() or None,
        "pmcid": (meta.get("pmcid") or "").strip() or None,
        "doi": (meta.get("doi") or "").strip() or None,
        "phenotype": ", ".join(inferred_phenotypes)
        or (meta.get("phenotype") or "").strip()
        or None,
        "inferred_phenotypes": inferred_phenotypes,
        "journal": (meta.get("journal") or "").strip() or None,
        "year": meta.get("year"),
        "authors": meta.get("authors") or None,
        "citationCount": meta.get("citationCount"),
    }


def process_reference_hits(
    txt_list: list[str],
    meta_list: list[dict[str, Any] | None],
    *,
    gene: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    out_chunks: list[str] = []
    out_refs: list[dict[str, Any]] = []
    for txt, meta in zip(txt_list, meta_list):
        built = build_reference_hit(txt, meta, gene=gene)
        if not built:
            continue
        chunk, ref = built
        out_chunks.append(chunk)
        out_refs.append(ref)
    return out_chunks, out_refs


def reference_identity(ref: dict[str, Any]) -> tuple[Any, ...]:
    paper_id = publication_dedup_key(ref)
    if paper_id:
        return ("paperId", paper_id)

    url = (ref.get("url") or "").strip()
    if url:
        return ("url", url)

    return (
        "meta",
        (ref.get("title") or "").strip().lower(),
        (ref.get("gene") or "").strip().upper(),
        (ref.get("source") or "").strip().upper(),
    )


def merge_references_preserve_numbers(
    existing_refs: list[dict[str, Any]] | None,
    current_refs: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], dict[int, int]]:
    merged: list[dict[str, Any]] = []
    key_to_n: dict[tuple[Any, ...], int] = {}
    used_numbers: set[int] = set()

    for ref in existing_refs or []:
        if not extract_publication_id(ref):
            continue
        ref_copy = dict(ref)
        ref_copy["paperId"] = extract_publication_id(ref_copy)
        try:
            n = int(ref_copy.get("n"))
        except (TypeError, ValueError):
            n = max(used_numbers, default=0) + 1
        if n in used_numbers:
            n = max(used_numbers, default=0) + 1
        ref_copy["n"] = n
        merged.append(ref_copy)
        key_to_n[reference_identity(ref_copy)] = n
        used_numbers.add(n)

    current_to_canonical: dict[int, int] = {}
    next_n = max(used_numbers, default=0) + 1

    for ref in sorted(current_refs or [], key=lambda x: x.get("n", 0)):
        paper_id = extract_publication_id(ref)
        if not paper_id:
            continue

        try:
            current_n = int(ref.get("n"))
        except (TypeError, ValueError):
            continue

        key = reference_identity(ref)
        canonical_n = key_to_n.get(key)
        if canonical_n is None:
            canonical_n = next_n
            next_n += 1
            ref_copy = dict(ref)
            ref_copy["n"] = canonical_n
            ref_copy["paperId"] = paper_id
            merged.append(ref_copy)
            key_to_n[key] = canonical_n
        else:
            existing_ref = next((item for item in merged if item.get("n") == canonical_n), None)
            if existing_ref is not None:
                existing_genes = split_reference_genes(str(existing_ref.get("gene") or ""))
                new_genes = split_reference_genes(str(ref.get("gene") or ""))
                merged_genes = unique_preserving_order([*existing_genes, *new_genes])
                if merged_genes:
                    existing_ref["gene"] = ", ".join(merged_genes)

                existing_phenotype = (existing_ref.get("phenotype") or "").strip()
                new_phenotype = (ref.get("phenotype") or "").strip()
                if new_phenotype and (
                    not existing_phenotype
                    or existing_phenotype.lower() == "breast cancer"
                    or len(new_phenotype) > len(existing_phenotype)
                ):
                    existing_ref["phenotype"] = new_phenotype

        current_to_canonical[current_n] = canonical_n

    merged.sort(key=lambda x: x["n"])
    return merged, current_to_canonical
