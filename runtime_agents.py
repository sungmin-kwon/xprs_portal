from functools import lru_cache
import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

# Per-generation-model ExplanationAgent cache. The model set is bounded by the
# allowlist (config.GENERATION_MODEL_IDS), so we never evict. A lock gives
# double-checked locking so concurrent first-hits on the same model build once.
_expl_agent_cache: dict[str, Any] = {}
_expl_agent_lock = threading.Lock()


@lru_cache(maxsize=1)
def get_runtime_agents() -> dict[str, Any]:
    from agents.conversation import ConversationAgent
    from agents.evidence_assembly import EvidenceAssemblyAgent
    from agents.explanation import ExplanationAgent
    from agents.gene_importance import GeneImportanceAgent
    from agents.open_targets import OpenTargetsAgent
    from agents.query_analysis import QueryAnalysisAgent
    from agents.rag import CHROMA_COLLECTION, EMB_MODEL_NAME, RAGAgent
    from agents.semantic_scholar import SemanticScholarAgent
    from config import (
        CHROMA_DIR,
        GENE_IMPORTANCE_CSV,
        OT_MERGED_CSV,
        RERANKER_BATCH_SIZE,
        RERANKER_ENABLED,
        RERANKER_MAX_LENGTH,
        RERANKER_MODEL,
        S2_CACHE_DIR,
    )
    from llm_utils import LLM_PROVIDER, build_llm_agent, build_llm_client
    from reference_utils import ReferenceMetadataExtractor

    client, llm_model = build_llm_client(LLM_PROVIDER)
    llm_agent = build_llm_agent(LLM_PROVIDER, client=client, model=llm_model)
    reference_extraction_provider = os.getenv("REFERENCE_EXTRACTION_PROVIDER", LLM_PROVIDER).lower()
    reference_extraction_client, default_reference_extraction_model = build_llm_client(reference_extraction_provider)
    reference_extraction_model = os.getenv("REFERENCE_EXTRACTION_MODEL") or default_reference_extraction_model
    raw_enable_llm_reference_extraction = os.getenv("ENABLE_LLM_REFERENCE_EXTRACTION")
    if raw_enable_llm_reference_extraction is None:
        enable_llm_reference_extraction = bool(
            os.getenv("REFERENCE_EXTRACTION_PROVIDER") or os.getenv("REFERENCE_EXTRACTION_MODEL")
        )
    else:
        enable_llm_reference_extraction = raw_enable_llm_reference_extraction.lower() in {
            "1", "true", "yes", "on"
        }
    reference_extraction_timeout = int(os.getenv("REFERENCE_EXTRACTION_TIMEOUT", "30"))
    reference_extraction_batch_size = int(os.getenv("REFERENCE_EXTRACTION_BATCH_SIZE", "10"))
    reference_extractor_llm = build_llm_agent(
        reference_extraction_provider,
        client=reference_extraction_client,
        model=reference_extraction_model,
    )
    metadata_extractor = ReferenceMetadataExtractor(
        llm_chat=lambda messages, timeout: reference_extractor_llm.chat(messages, timeout=timeout),
        timeout=reference_extraction_timeout,
        use_llm=enable_llm_reference_extraction,
        batch_size=reference_extraction_batch_size,
        label=f"{reference_extraction_provider}:{reference_extraction_model}",
    )
    logger.info(
        "[INIT] Reference extraction: enabled=%s provider=%s model=%s timeout=%ss batch_size=%s mode=llm_only",
        enable_llm_reference_extraction,
        reference_extraction_provider,
        reference_extraction_model,
        reference_extraction_timeout,
        reference_extraction_batch_size,
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
    gene_agent = GeneImportanceAgent(csv_path=str(GENE_IMPORTANCE_CSV))
    evidence_agent = EvidenceAssemblyAgent(
        rag_agent=rag_agent,
        ot_agent=ot_agent,
        s2_agent=s2_agent,
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
        "gene_agent": gene_agent,
        "evidence_agent": evidence_agent,
        "llm_agent": llm_agent,
        "reference_extractor_llm": reference_extractor_llm,
        "query_agent": query_agent,
        "conversation_agent": conversation_agent,
        "expl_agent": expl_agent,
    }


def _build_expl_agent_for_model(bundle: dict[str, Any], model: str):
    """Build an ExplanationAgent on a specific generation model, reusing the
    shared expensive resources (client + rag/ot/gene/s2/evidence agents). Only
    the cheap LLM-bound agents are rebuilt so the whole request runs on `model`:
    query analysis and conversation-turn resolution route through their own
    agents, so those must be rebuilt too (not just expl_agent.llm)."""
    from agents.conversation import ConversationAgent
    from agents.explanation import ExplanationAgent
    from agents.query_analysis import QueryAnalysisAgent
    from llm_utils import LLM_PROVIDER, build_llm_agent

    llm = build_llm_agent(LLM_PROVIDER, client=bundle["client"], model=model)
    query_agent = QueryAnalysisAgent(llm=llm)
    conversation_agent = ConversationAgent(llm=llm)
    return ExplanationAgent(
        llm=llm,
        gene_agent=bundle["gene_agent"],
        evidence_agent=bundle["evidence_agent"],
        ot_agent=bundle["ot_agent"],
        query_agent=query_agent,
        conversation_agent=conversation_agent,
    )


def get_expl_agent(model: str | None = None):
    """Return an ExplanationAgent for the requested generation model.

    The configured default resolves to a concrete model before choosing the
    pre-warmed shared agent. This prevents an environment/config mismatch from
    silently running a different model than the one selected in the UI.
    """
    from config import DEFAULT_GENERATION_MODEL

    bundle = get_runtime_agents()
    requested_model = model or DEFAULT_GENERATION_MODEL
    if requested_model == bundle["llm_model"]:
        return bundle["expl_agent"]

    cached = _expl_agent_cache.get(requested_model)
    if cached is not None:
        return cached
    with _expl_agent_lock:
        cached = _expl_agent_cache.get(requested_model)
        if cached is None:
            cached = _build_expl_agent_for_model(bundle, requested_model)
            _expl_agent_cache[requested_model] = cached
        return cached


def get_s2_agent():
    return get_runtime_agents()["s2_agent"]


def get_rag_agent():
    return get_runtime_agents()["rag_agent"]
