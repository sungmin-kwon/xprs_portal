from __future__ import annotations

from typing import Any, Callable, Protocol


class LiteratureSource(Protocol):
    """Common boundary for publication-search providers.

    Provider caches remain separate, while documents produced here share the
    same Chroma schema. This keeps upstream API behavior out of vector-store
    and answer-generation code.
    """

    source_name: str
    display_name: str

    def cached_query_succeeded(self, gene: str, phenotype: str | None) -> bool: ...

    def cached_papers(
        self,
        gene: str,
        phenotype: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def cached_for_gene(
        self,
        gene: str,
        limit: int,
        phenotype: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> list[dict[str, Any]]: ...

    def papers_to_docs(
        self,
        gene: str,
        papers: list[dict[str, Any]],
        pool_type: str = "general",
        phenotype: str | None = None,
    ) -> list[dict[str, Any]]: ...
