from functools import lru_cache
import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

# Per-generation-model ExplanationAgent cache. The model set is bounded by the
# allowlist (config.GENERATION_MODEL_IDS), so we never evict. A lock gives
# double-checked locking so concurrent first-hits on the same model build once.
_expl_agent_cache: dict[tuple[str, str, str, str], Any] = {}
_expl_agent_lock = threading.Lock()


def _build_reference_metadata_extractor(default_provider: str):
    """Build the optional reference extractor and its dedicated LLM agent."""
    from llm_utils import build_llm_agent, build_llm_client
    from reference_utils import ReferenceMetadataExtractor

    provider = os.getenv("REFERENCE_EXTRACTION_PROVIDER", default_provider).lower()
    client, default_model = build_llm_client(provider)
    model = os.getenv("REFERENCE_EXTRACTION_MODEL") or default_model
    raw_enabled = os.getenv("ENABLE_LLM_REFERENCE_EXTRACTION")
    enabled = (
        bool(os.getenv("REFERENCE_EXTRACTION_PROVIDER") or os.getenv("REFERENCE_EXTRACTION_MODEL"))
        if raw_enabled is None
        else raw_enabled.lower() in {"1", "true", "yes", "on"}
    )
    timeout = int(os.getenv("REFERENCE_EXTRACTION_TIMEOUT", "30"))
    batch_size = int(os.getenv("REFERENCE_EXTRACTION_BATCH_SIZE", "10"))
    llm = build_llm_agent(provider, client=client, model=model)
    extractor = ReferenceMetadataExtractor(
        llm_chat=lambda messages, request_timeout: llm.chat(
            messages,
            timeout=request_timeout,
        ),
        timeout=timeout,
        use_llm=enabled,
        batch_size=batch_size,
        label=f"{provider}:{model}",
    )
    logger.info(
        "[INIT] Reference extraction: enabled=%s provider=%s model=%s timeout=%ss batch_size=%s mode=llm_only",
        enabled,
        provider,
        model,
        timeout,
        batch_size,
    )
    return extractor, llm


@lru_cache(maxsize=1)
def get_runtime_agents() -> dict[str, Any]:
    from agents.conversation import ConversationAgent
    from agents.evidence_assembly import EvidenceAssemblyAgent
    from agents.europe_pmc import EuropePMCAgent
    from agents.explanation import ExplanationAgent
    from agents.gene_importance import GeneImportanceAgent
    from agents.literature_enrichment import LiteratureEnrichmentQueue
    from agents.open_targets import OpenTargetsAgent
    from agents.query_analysis import QueryAnalysisAgent
    from agents.rag import CHROMA_COLLECTION, EMB_MODEL_NAME, RAGAgent
    from agents.semantic_scholar import SemanticScholarAgent
    from config import (
        CHROMA_DIR,
        EUROPE_PMC_CACHE_DIR,
        GENE_IMPORTANCE_CSV,
        OT_MERGED_CSV,
        RERANKER_BATCH_SIZE,
        RERANKER_ENABLED,
        RERANKER_MAX_LENGTH,
        RERANKER_MODEL,
        S2_CACHE_DIR,
    )
    from llm_utils import LLM_PROVIDER, build_llm_agent, build_llm_client

    client, llm_model = build_llm_client(LLM_PROVIDER)
    llm_agent = build_llm_agent(LLM_PROVIDER, client=client, model=llm_model)
    metadata_extractor, reference_extractor_llm = (
        _build_reference_metadata_extractor(LLM_PROVIDER)
    )

    rag_agent = RAGAgent(
        emb_model_name=EMB_MODEL_NAME,
        chroma_dir=str(CHROMA_DIR),
        collection_name=CHROMA_COLLECTION,
        reranker_model_name=RERANKER_MODEL,
        reranker_enabled=RERANKER_ENABLED,
        reranker_batch_size=RERANKER_BATCH_SIZE,
        reranker_max_length=RERANKER_MAX_LENGTH,
    )
    ot_agent = OpenTargetsAgent(merged_csv=str(OT_MERGED_CSV))
    s2_agent = SemanticScholarAgent(
        api_key=os.getenv("S2_API_KEY"),
        cache_dir=S2_CACHE_DIR,
        metadata_extractor=metadata_extractor,
    )
    europe_pmc_agent = EuropePMCAgent(
        cache_dir=EUROPE_PMC_CACHE_DIR,
        metadata_extractor=metadata_extractor,
    )
    enrichment_queue = LiteratureEnrichmentQueue(
        s2_agent=s2_agent,
        rag_agent=rag_agent,
    )
    gene_agent = GeneImportanceAgent(csv_path=str(GENE_IMPORTANCE_CSV))
    evidence_agent = EvidenceAssemblyAgent(
        rag_agent=rag_agent,
        ot_agent=ot_agent,
        s2_agent=s2_agent,
        europe_pmc_agent=europe_pmc_agent,
        enrichment_queue=enrichment_queue,
    )
    query_agent = QueryAnalysisAgent(llm=llm_agent)
    conversation_agent = ConversationAgent(llm=llm_agent)
    expl_agent = ExplanationAgent(
        llm=llm_agent,
        gene_agent=gene_agent,
        evidence_agent=evidence_agent,
        ot_agent=ot_agent,
        query_agent=query_agent,
        conversation_agent=conversation_agent,
    )

    return {
        "client": client,
        "llm_model": llm_model,
        "rag_agent": rag_agent,
        "ot_agent": ot_agent,
        "s2_agent": s2_agent,
        "europe_pmc_agent": europe_pmc_agent,
        "enrichment_queue": enrichment_queue,
        "gene_agent": gene_agent,
        "evidence_agent": evidence_agent,
        "llm_agent": llm_agent,
        "reference_extractor_llm": reference_extractor_llm,
        "query_agent": query_agent,
        "conversation_agent": conversation_agent,
        "expl_agent": expl_agent,
    }


def _build_llm_bound_agents(
    bundle: dict[str, Any],
    model: str,
    *,
    privacy_mode: str | None = None,
):
    """Build the lightweight agents that must share one selected model."""
    from agents.conversation import ConversationAgent
    from agents.query_analysis import QueryAnalysisAgent
    from llm_utils import LLM_PROVIDER, build_llm_agent

    llm = build_llm_agent(
        LLM_PROVIDER,
        client=bundle["client"],
        model=model,
        privacy_mode=privacy_mode,
    )
    return llm, QueryAnalysisAgent(llm=llm), ConversationAgent(llm=llm)


def _build_expl_agent_for_model(bundle: dict[str, Any], model: str):
    """Build a model-specific explanation agent around shared heavy resources."""
    from agents.explanation import ExplanationAgent

    llm, query_agent, conversation_agent = _build_llm_bound_agents(bundle, model)
    return ExplanationAgent(
        llm=llm,
        gene_agent=bundle["gene_agent"],
        evidence_agent=bundle["evidence_agent"],
        ot_agent=bundle["ot_agent"],
        query_agent=query_agent,
        conversation_agent=conversation_agent,
    )


def _build_kpredict_expl_agent(
    bundle: dict[str, Any],
    model: str,
    disease: str,
    data_root,
):
    from agents.evidence_assembly import EvidenceAssemblyAgent
    from agents.explanation import ExplanationAgent
    from agents.gene_importance import KPredictGeneImportanceAgent
    from disease_registry import get_disease_config
    from kpredict_data import risk_profile

    disease_config = get_disease_config(disease)
    llm, query_agent, conversation_agent = _build_llm_bound_agents(
        bundle,
        model,
        privacy_mode="kpredict",
    )
    # The current Open Targets extract is breast-carcinoma-specific. Do not
    # present it as evidence for another disease.
    ot_agent = bundle["ot_agent"] if disease_config.slug == "breast_cancer" else None
    evidence_agent = EvidenceAssemblyAgent(
        rag_agent=bundle["rag_agent"],
        ot_agent=ot_agent,
        s2_agent=bundle["s2_agent"],
        europe_pmc_agent=bundle["europe_pmc_agent"],
        primary_phenotype=disease_config.primary_phenotype,
        enrichment_queue=bundle["enrichment_queue"],
    )
    gene_agent = KPredictGeneImportanceAgent(data_root, disease_config.slug)
    return ExplanationAgent(
        llm=llm,
        gene_agent=gene_agent,
        evidence_agent=evidence_agent,
        ot_agent=ot_agent,
        query_agent=query_agent,
        conversation_agent=conversation_agent,
        primary_phenotype=disease_config.primary_phenotype,
        disease_display_name=disease_config.display_name,
        risk_profile_provider=lambda pid: risk_profile(data_root, disease_config.slug, pid),
        minimize_sensitive_context=True,
    )


def get_expl_agent(
    model: str | None = None,
    *,
    cohort: str = "1000_genomes",
    disease: str = "breast_cancer",
    data_root=None,
):
    """Return an ExplanationAgent for the requested generation model.

    The configured default resolves to a concrete model before choosing the
    pre-warmed shared agent. This prevents an environment/config mismatch from
    silently running a different model than the one selected in the UI.
    """
    from config import DEFAULT_GENERATION_MODEL

    bundle = get_runtime_agents()
    requested_model = model or DEFAULT_GENERATION_MODEL
    if cohort == "kpredict":
        if data_root is None:
            from kpredict_access import kpredict_root

            data_root = kpredict_root()
        if data_root is None:
            raise ValueError("K-PREDICT data are not configured")
        cache_key = (requested_model, cohort, disease, str(data_root))
        cached = _expl_agent_cache.get(cache_key)
        if cached is not None:
            return cached
        with _expl_agent_lock:
            cached = _expl_agent_cache.get(cache_key)
            if cached is None:
                cached = _build_kpredict_expl_agent(
                    bundle,
                    requested_model,
                    disease,
                    data_root,
                )
                _expl_agent_cache[cache_key] = cached
            return cached

    if requested_model == bundle["llm_model"]:
        return bundle["expl_agent"]

    cache_key = (requested_model, cohort, disease, "")
    cached = _expl_agent_cache.get(cache_key)
    if cached is not None:
        return cached
    with _expl_agent_lock:
        cached = _expl_agent_cache.get(cache_key)
        if cached is None:
            cached = _build_expl_agent_for_model(bundle, requested_model)
            _expl_agent_cache[cache_key] = cached
        return cached


def get_s2_agent():
    return get_runtime_agents()["s2_agent"]


def get_europe_pmc_agent():
    return get_runtime_agents()["europe_pmc_agent"]


def get_rag_agent():
    return get_runtime_agents()["rag_agent"]


def get_retrieval_admin_status() -> dict[str, Any]:
    """Return safe, non-probing retrieval state for the protected admin page."""
    bundle = get_runtime_agents()
    evidence_agents = [bundle["evidence_agent"]]
    with _expl_agent_lock:
        evidence_agents.extend(
            agent.evidence_agent
            for agent in _expl_agent_cache.values()
            if getattr(agent, "evidence_agent", None) is not None
        )
    seen: set[int] = set()
    runtime = []
    for agent in evidence_agents:
        if id(agent) in seen:
            continue
        seen.add(id(agent))
        if hasattr(agent, "get_runtime_status"):
            runtime.append(agent.get_runtime_status())
    return {
        "semantic_scholar": bundle["s2_agent"].get_health_status(),
        "queue": bundle["enrichment_queue"].get_status(),
        "runtime_cooldowns": runtime,
    }
