from __future__ import annotations

from pathlib import Path

from config import S2_CACHE_DIR


def get_s2_cache_path(gene: str) -> Path:
    safe_gene = "".join(x for x in gene if x.isalnum())
    return S2_CACHE_DIR / f"{safe_gene}_s2.json"


def get_s2_cache_paths(gene: str) -> list[Path]:
    safe_gene = "".join(x for x in gene if x.isalnum())
    candidates = sorted(S2_CACHE_DIR.glob(f"{safe_gene}*_s2.json"))
    legacy = get_s2_cache_path(gene)
    if legacy.exists() and legacy not in candidates:
        candidates.append(legacy)
    return candidates


def split_reference_genes(gene_text: str) -> list[str]:
    genes = [
        token.strip()
        for token in (gene_text or "").split(",")
        if token.strip()
    ]
    deduped: list[str] = []
    seen: set[str] = set()
    for gene in genes:
        key = gene.upper()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(gene)
    return deduped
