import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from text_utils import unique_preserving_order


@dataclass
class ConversationState:
    active_genes: list[str] = field(default_factory=list)
    active_phenotypes: list[str] = field(default_factory=list)
    active_intent: str | None = None
    last_user_query: str | None = None
    last_resolved_question: str | None = None

    @classmethod
    def from_session(cls, payload: dict[str, Any] | None) -> "ConversationState":
        payload = payload or {}
        return cls(
            active_genes=list(payload.get("active_genes") or []),
            active_phenotypes=list(payload.get("active_phenotypes") or []),
            active_intent=payload.get("active_intent"),
            last_user_query=payload.get("last_user_query"),
            last_resolved_question=payload.get("last_resolved_question"),
        )

    def to_session(self) -> dict[str, Any]:
        return asdict(self)


class ConversationAgent:
    # Conservative refusal categories for committee-mandated safety guardrails.
    # See README "Safety guardrails" section for the design rationale.
    # ALLOW examples (must stay as biomedical_followup):
    #   - "How does TP53 mediate breast cancer susceptibility?"
    #   - "What is the literature on BRCA1?"
    #   - "Why is this gene in the top 5?"
    #   - "How is PRS calculated?"
    # REFUSE examples (medical_advice_seeking):
    #   - "Should I get tested for breast cancer?"
    #   - "Do I have cancer?" / "Will I develop cancer?"
    #   - "What treatment do I need?" / "Should I take tamoxifen?"
    #   - "How worried should I be?" / "Should I tell my family?"
    TURN_TYPES = {"biomedical_followup", "casual_chat", "off_domain_request", "medical_advice_seeking"}
    TRANSLATION_REQUEST_PATTERNS = (
        re.compile(r"\btranslate\s+(?:this|that|the above|the previous|your (?:answer|response)|the (?:answer|response|summary|report))\b", re.I),
        re.compile(r"\b(?:korean|english)\s+(?:translation|version)\b", re.I),
        re.compile(r"(?:이것|이거|위\s*내용|이전\s*(?:답변|응답)|답변|응답|요약|보고서).*(?:번역|옮겨|바꿔)", re.I),
    )
    SMALLTALK_FALLBACK_PATTERNS = [
        re.compile(r"^\s*(hi|hello|hey|yo|sup|what'?s up|whats up|howdy)\b", re.I),
        re.compile(r"^\s*(thanks|thank you|thx|cool|nice|lol|haha|ok|okay)\b[!. ]*$", re.I),
    ]
    OFFTOPIC_FALLBACK_PATTERNS = [
        re.compile(r"\bwhat('?s| is) the date\b", re.I),
        re.compile(r"\bwhat time is it\b", re.I),
        re.compile(r"\bweather\b", re.I),
        re.compile(r"^\s*i\s*(?:'m| am)\s+in\b", re.I),
    ]
    OFFDOMAIN_FALLBACK_PATTERNS = [
        re.compile(r"\bpython\b", re.I),
        re.compile(r"\bc\+\+\b", re.I),
        re.compile(r"\bjavascript\b", re.I),
        re.compile(r"\bsql\b", re.I),
        re.compile(r"\b(?:write|generate|provide|create)\s+(?:a\s+)?(?:code|script)\b", re.I),
        re.compile(r"\bdebug(?:ging)?\s+(?:the\s+)?(?:code|software|pipeline)\b", re.I),
    ]
    # Deliberately conservative: only catch unambiguous first-person, action-seeking phrasing.
    # General/research questions like "what does TP53 do" must not match these.
    MEDICAL_ADVICE_FALLBACK_PATTERNS = [
        re.compile(r"\bshould\s+i\b", re.I),
        re.compile(r"\b(do|did|will|am|was)\s+i\s+(have|get|develop|need|require|qualify|risk)\b", re.I),
        re.compile(r"\bdoes\s+this\s+mean\s+i\s+(?:have|will|get|develop|need)\b", re.I),
        re.compile(
            r"\bshould\s+my\s+(?:child|children|family|parent|parents|sibling|siblings)\s+"
            r"(?:get|have|undergo|seek|take)\b",
            re.I,
        ),
        re.compile(r"\bwhat\s+(should|do)\s+i\s+(do|take|use|try)\b", re.I),
        re.compile(r"\bhow\s+worried\s+(should\s+)?i\b", re.I),
        re.compile(r"\b(my)\s+(treatment|medication|prognosis|diagnosis|screening)\s+(plan|option|choice|should)\b", re.I),
        re.compile(r"\bam\s+i\s+(at\s+risk|going\s+to\s+(get|have|develop))\b", re.I),
        re.compile(
            r"(?:제가|나는|내가).*(?:걱정해야|검사를?\s*받아야|검진을?\s*받아야|"
            r"치료를?\s*받아야|약을?\s*먹어야|복용해야)",
        ),
        re.compile(
            r"(?:저|제|나|내)\s*(?:아이|자녀|가족).*(?:검사|검진).*(?:받아야|해야)",
        ),
        re.compile(r"(?:저|제가|나는|내가).*(?:암|당뇨병|질환).*(?:인가요|입니까|있나요|걸리나요)"),
    ]
    BIOMEDICAL_KEYWORDS = (
        "gene", "genes", "cancer", "cancers", "tumor", "tumors", "tumour", "tumours",
        "disease", "diseases", "phenotype", "phenotypes", "mutation", "mutations",
        "variant", "variants", "breast", "ovarian", "lung", "prostate", "colorectal",
        "pancreatic", "melanoma", "alzheimer", "dementia", "parkinson", "schizophrenia",
        "diabetes", "coronary", "inflammatory bowel", "migraine", "ataxia", "epilepsy",
    )

    def __init__(self, llm: Any | None = None):
        self.llm = llm

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any]:
        raw = (raw or "").strip()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except Exception:
            pass
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return {}
        return {}

    @staticmethod
    def _match_available_genes(text: str, available_genes: list[str]) -> list[str]:
        text_lower = (text or "").lower()
        hits = [
            gene for gene in available_genes
            if re.search(
                rf"(?<![a-z0-9_-]){re.escape(gene.lower())}(?![a-z0-9_-])",
                text_lower,
            )
        ]
        return unique_preserving_order(hits)

    @staticmethod
    def _history_text(history: list[str] | None) -> str:
        values = [str(h).strip() for h in (history or []) if str(h).strip()]
        return "\n".join(f"- {item}" for item in values[-4:])

    @classmethod
    def translation_target(cls, question: str) -> str | None:
        text = (question or "").strip()
        if not text:
            return None
        is_translation_request = bool(
            re.search(r"\btranslat(?:e|ion)\b", text, re.I)
            or re.search(r"(?:번역|옮겨)", text)
            or any(pattern.search(text) for pattern in cls.TRANSLATION_REQUEST_PATTERNS)
        )
        if not is_translation_request:
            return None
        if re.search(r"\b(?:into|to|in)\s+korean\b|\bkorean\s+(?:translation|version)\b", text, re.I) \
                or re.search(r"(?:한국어|한글)로", text):
            return "ko"
        if re.search(r"\b(?:into|to|in)\s+english\b|\benglish\s+(?:translation|version)\b", text, re.I) \
                or re.search(r"영어로", text):
            return "en"
        return "auto"

    @classmethod
    def _deterministic_context_resolution(
        cls,
        question: str,
        state: ConversationState,
        available_genes: list[str],
    ) -> dict[str, Any] | None:
        """Resolve unambiguous corrections and ordinal references locally.

        These short turns should not depend on an LLM correctly remembering the
        order of genes in the preceding answer. More open-ended references still
        go through the normal resolver.
        """
        text = (question or "").strip()
        state_genes = [gene for gene in state.active_genes if gene in available_genes]
        if not text or not state_genes:
            return None

        correction_segment: str | None = None
        english_correction = re.search(
            r"\b(?:i\s+meant|i\s+was\s+asking\s+about|what\s+i\s+meant\s+was)\b(.+)",
            text,
            re.I,
        )
        if english_correction:
            correction_segment = re.split(
                r"\b(?:not|rather\s+than|instead\s+of)\b",
                english_correction.group(1),
                maxsplit=1,
                flags=re.I,
            )[0]
        elif re.search(r"(?:말고|아니고)", text):
            correction_segment = re.split(r"(?:말고|아니고)", text, maxsplit=1)[-1]

        if correction_segment is not None:
            corrected_genes = cls._match_available_genes(correction_segment, available_genes)
            if corrected_genes:
                # A correction changes the entity in the preceding question; it
                # does not normally replace the question itself.  For example,
                # after "Does CDKAL1 have direct evidence for type 2 diabetes?",
                # "I meant KCNQ1" should ask the same evidence question about
                # KCNQ1 rather than degrade into generic gene information.
                prior_question = (
                    state.last_resolved_question or state.last_user_query or text
                    if len(state_genes) == 1
                    else text
                )
                corrected_text = " and ".join(corrected_genes)
                explicitly_named = cls._match_available_genes(text, available_genes)
                rejected_genes = [
                    gene for gene in explicitly_named
                    if gene not in corrected_genes
                ]
                if not rejected_genes and len(state_genes) == 1:
                    rejected_genes = state_genes

                resolved_question = prior_question
                for rejected_gene in rejected_genes:
                    resolved_question = re.sub(
                        rf"(?<![a-z0-9_-]){re.escape(rejected_gene)}(?![a-z0-9_-])",
                        corrected_text,
                        resolved_question,
                        flags=re.I,
                    )
                if resolved_question == prior_question and prior_question == text:
                    resolved_question = text
                return {
                    "turn_type": "biomedical_followup",
                    "resolved_genes": corrected_genes,
                    "resolved_phenotypes": list(state.active_phenotypes),
                    "resolved_intent": state.active_intent or "followup",
                    "resolved_question": resolved_question,
                }

        ordinal_patterns = (
            (r"\b(?:first|1st)\s+gene\b|(?:첫\s*번째|첫째)\s*유전자", 0),
            (r"\b(?:second|2nd)\s+gene\b|(?:두\s*번째|둘째)\s*유전자", 1),
            (r"\b(?:third|3rd)\s+gene\b|(?:세\s*번째|셋째)\s*유전자", 2),
            (r"\b(?:fourth|4th)\s+gene\b|(?:네\s*번째|넷째)\s*유전자", 3),
            (r"\b(?:fifth|5th)\s+gene\b|(?:다섯\s*번째|다섯째)\s*유전자", 4),
        )
        selected_gene: str | None = None
        matched_pattern: str | None = None
        for pattern, index in ordinal_patterns:
            if re.search(pattern, text, re.I) and index < len(state_genes):
                selected_gene = state_genes[index]
                matched_pattern = pattern
                break
        if selected_gene is None and re.search(r"\b(?:last|final)\s+gene\b|마지막\s*유전자", text, re.I):
            selected_gene = state_genes[-1]
            matched_pattern = r"\b(?:last|final)\s+gene\b|마지막\s*유전자"

        if selected_gene and matched_pattern:
            return {
                "turn_type": "biomedical_followup",
                "resolved_genes": [selected_gene],
                "resolved_phenotypes": list(state.active_phenotypes),
                "resolved_intent": state.active_intent or "followup",
                "resolved_question": re.sub(matched_pattern, selected_gene, text, flags=re.I),
            }
        return None

    @staticmethod
    def _fallback_resolution(
        question: str,
        state: ConversationState,
        available_genes: list[str],
    ) -> dict[str, Any]:
        translation_target = ConversationAgent.translation_target(question)
        if translation_target:
            return {
                "turn_type": "biomedical_followup",
                "resolved_genes": list(state.active_genes),
                "resolved_phenotypes": list(state.active_phenotypes),
                "resolved_intent": state.active_intent or "translate_previous_response",
                "resolved_question": question,
                "translation_target": translation_target,
            }

        turn_type = ConversationAgent.classify_turn_fallback(question, available_genes)
        if turn_type == "off_domain_request":
            return {
                "turn_type": "off_domain_request",
                "resolved_genes": [],
                "resolved_phenotypes": [],
                "resolved_intent": "off_domain_request",
                "resolved_question": question,
            }
        if turn_type == "medical_advice_seeking":
            return {
                "turn_type": "medical_advice_seeking",
                "resolved_genes": [],
                "resolved_phenotypes": [],
                "resolved_intent": "medical_advice_seeking",
                "resolved_question": question,
            }
        if turn_type == "casual_chat":
            return {
                "turn_type": "casual_chat",
                "resolved_genes": [],
                "resolved_phenotypes": [],
                "resolved_intent": "casual_chat",
                "resolved_question": question,
            }

        explicit_genes = ConversationAgent._match_available_genes(question, available_genes)
        q_lower = (question or "").lower()
        referential = bool(re.search(r"\b(this gene|these|those|both|them|they|latter|former)\b", q_lower))
        clarification = bool(
            re.search(r"\bi meant\b", q_lower)
            or re.search(r"\bi was asking\b", q_lower)
            or re.search(r"\bwhat i meant\b", q_lower)
            or q_lower.startswith("no,")
        )

        if clarification and explicit_genes and state.last_user_query:
            gene_text = " and ".join(explicit_genes)
            rewritten = re.sub(r"\bthese two genes\b", gene_text, state.last_user_query, flags=re.IGNORECASE)
            rewritten = re.sub(r"\bthese genes\b", gene_text, rewritten, flags=re.IGNORECASE)
            rewritten = re.sub(r"\bboth\b", gene_text, rewritten, flags=re.IGNORECASE)
            rewritten = re.sub(r"\bthem\b", gene_text, rewritten, flags=re.IGNORECASE)
            rewritten = re.sub(r"\bthey\b", gene_text, rewritten, flags=re.IGNORECASE)
            return {
                "turn_type": "biomedical_followup",
                "resolved_genes": explicit_genes,
                "resolved_phenotypes": state.active_phenotypes,
                "resolved_intent": state.active_intent or "followup",
                "resolved_question": rewritten,
            }

        if explicit_genes:
            return {
                "turn_type": "biomedical_followup",
                "resolved_genes": explicit_genes,
                "resolved_phenotypes": state.active_phenotypes,
                "resolved_intent": state.active_intent if referential else "followup",
                "resolved_question": question,
            }

        if referential and state.active_genes:
            return {
                "turn_type": "biomedical_followup",
                "resolved_genes": state.active_genes,
                "resolved_phenotypes": state.active_phenotypes,
                "resolved_intent": state.active_intent or "followup",
                "resolved_question": question,
            }

        return {
            "turn_type": "biomedical_followup",
            "resolved_genes": [],
            "resolved_phenotypes": state.active_phenotypes,
            "resolved_intent": state.active_intent,
            "resolved_question": question,
        }

    def resolve_turn(
        self,
        *,
        question: str,
        state: ConversationState,
        available_genes: list[str],
    ) -> dict[str, Any]:
        explicit_genes = self._match_available_genes(question, available_genes)
        state_genes = [g for g in state.active_genes if g in available_genes]

        translation_target = self.translation_target(question)
        if translation_target:
            return {
                "turn_type": "biomedical_followup",
                "resolved_genes": state_genes,
                "resolved_phenotypes": list(state.active_phenotypes),
                "resolved_intent": state.active_intent or "translate_previous_response",
                "resolved_question": question,
                "translation_target": translation_target,
            }

        deterministic_route = self.classify_turn_fallback(question, available_genes)
        if deterministic_route in {"medical_advice_seeking", "off_domain_request"}:
            return self._fallback_resolution(question, state, available_genes)

        deterministic_context = self._deterministic_context_resolution(
            question,
            state,
            available_genes,
        )
        if deterministic_context:
            return deterministic_context

        if not self.llm:
            return self._fallback_resolution(question, state, available_genes)

        prompt = f"""
You resolve the user's latest turn in a genetics/XPRS chat.

Return JSON with keys:
- turn_type: one of biomedical_followup, casual_chat, off_domain_request, medical_advice_seeking
- resolved_genes: array of gene symbols currently in focus
- resolved_phenotypes: array of phenotype strings to carry forward if still relevant
- resolved_intent: short label like "breast_cancer_associations", "other_cancers", "general_followup", "clarification"
- resolved_question: the effective fully explicit question to answer next

Rules:
- Questions about XPRS/PRS methodology, interpretation, scoring logic, required inputs, or meaning of outputs are biomedical_followup.
- Requests to translate, rephrase, or restate the previous XPRS response are biomedical_followup and preserve the current genes and intent.
- Requests to write code, scripts, reproduce the pipeline computationally, debug software, or implement XPRS/PRS are off_domain_request even if they mention XPRS/PRS.
- casual_chat is only for light banter, greetings, jokes, or small side remarks.
- medical_advice_seeking is reserved for clearly first-person, action-seeking medical questions where the user is asking what THEY personally should do, take, be tested for, or worry about. Examples:
    * "Should I get tested for breast cancer?"
    * "Do I have cancer?" / "Will I develop cancer?"
    * "What treatment do I need?" / "Should I take tamoxifen?"
    * "How worried should I be?" / "Should I tell my family?"
- Be CONSERVATIVE with medical_advice_seeking. The following are NOT medical_advice_seeking (they are biomedical_followup):
    * "How does TP53 mediate breast cancer susceptibility?"
    * "What does this gene do?"
    * "What is the literature on BRCA1?"
    * "What is the prognosis associated with high HER2 expression?" (asking about research, not personal prognosis)
    * "What treatments exist for breast cancer?" (general, not personal)
    * "What does my PRS value mean as a statistical signal?" (interpretation of displayed value)
    * "Why is this gene in the top 5?"
- If the user explicitly names genes, use those genes.
- If the user refers to prior genes indirectly, use the currently active genes from state.
- If the user is clarifying which genes they meant, preserve the prior question's intent but replace the active genes.
- Do not invent genes outside the available list.
- Prefer preserving the previous intent when the new message is a clarification or referential follow-up.
- If turn_type is casual_chat, off_domain_request, or medical_advice_seeking, leave resolved_genes and resolved_phenotypes empty.
- Do not classify an in-domain XPRS/PRS methodology question as off_domain_request merely because it mentions computation or calculation conceptually.
- Output JSON only.

Available genes:
{", ".join(available_genes)}

Current state:
{json.dumps(state.to_session(), ensure_ascii=False)}

Explicit genes in current question:
{json.dumps(explicit_genes, ensure_ascii=False)}

Current question:
{question}

Recent conversation:
{self._history_text([state.last_user_query, state.last_resolved_question])}
""".strip()

        try:
            parsed = self._extract_json(self.llm.chat([
                {"role": "system", "content": "You are a precise turn resolver for a genetics/XPRS application. Output JSON only."},
                {"role": "user", "content": prompt},
            ], timeout=30))
        except Exception:
            return self._fallback_resolution(question, state, available_genes)

        turn_type = (parsed.get("turn_type") or "").strip()
        if turn_type not in self.TURN_TYPES:
            return self._fallback_resolution(question, state, available_genes)

        if turn_type == "off_domain_request":
            return {
                "turn_type": "off_domain_request",
                "resolved_genes": [],
                "resolved_phenotypes": [],
                "resolved_intent": "off_domain_request",
                "resolved_question": question,
            }
        if turn_type == "medical_advice_seeking":
            return {
                "turn_type": "medical_advice_seeking",
                "resolved_genes": [],
                "resolved_phenotypes": [],
                "resolved_intent": "medical_advice_seeking",
                "resolved_question": question,
            }
        if turn_type == "casual_chat":
            return {
                "turn_type": "casual_chat",
                "resolved_genes": [],
                "resolved_phenotypes": [],
                "resolved_intent": "casual_chat",
                "resolved_question": question,
            }

        llm_genes = [g for g in parsed.get("resolved_genes", []) if g in available_genes]
        resolved_genes = unique_preserving_order(explicit_genes + llm_genes)
        if not resolved_genes and state_genes:
            resolved_genes = state_genes

        resolved_phenotypes = [
            p for p in parsed.get("resolved_phenotypes", [])
            if isinstance(p, str) and p.strip()
        ] or list(state.active_phenotypes)

        resolved_intent = parsed.get("resolved_intent")
        if not isinstance(resolved_intent, str) or not resolved_intent.strip():
            resolved_intent = state.active_intent or "followup"

        resolved_question = parsed.get("resolved_question")
        if not isinstance(resolved_question, str) or not resolved_question.strip():
            resolved_question = question

        return {
            "turn_type": "biomedical_followup",
            "resolved_genes": resolved_genes,
            "resolved_phenotypes": resolved_phenotypes,
            "resolved_intent": resolved_intent,
            "resolved_question": resolved_question,
        }

    def classify_turn(
        self,
        *,
        question: str,
        state: ConversationState,
        available_genes: list[str],
    ) -> str:
        resolution = self.resolve_turn(
            question=question,
            state=state,
            available_genes=available_genes,
        )
        turn_type = (resolution.get("turn_type") or "").strip()
        if turn_type in self.TURN_TYPES:
            return turn_type
        return self.classify_turn_fallback(question, available_genes)

    @classmethod
    def is_smalltalk_turn(cls, question: str) -> bool:
        text = question or ""
        return any(pattern.search(text) for pattern in cls.SMALLTALK_FALLBACK_PATTERNS)

    @classmethod
    def classify_turn_fallback(
        cls,
        question: str,
        available_genes: list[str] | None = None,
    ) -> str:
        text = (question or "").strip()
        if not text:
            return "biomedical_followup"
        lowered = text.lower()
        if cls.translation_target(text):
            return "biomedical_followup"
        # Medical-advice patterns are checked BEFORE the biomedical-keyword shortcut,
        # because "should I get tested for cancer?" contains "cancer" but is still
        # a medical-advice request, not a research question.
        if any(pattern.search(text) for pattern in cls.MEDICAL_ADVICE_FALLBACK_PATTERNS):
            return "medical_advice_seeking"
        if cls.is_smalltalk_turn(text):
            return "casual_chat"
        if any(pattern.search(text) for pattern in cls.OFFTOPIC_FALLBACK_PATTERNS):
            return "casual_chat"
        if any(pattern.search(text) for pattern in cls.OFFDOMAIN_FALLBACK_PATTERNS):
            return "off_domain_request"
        if any(
            re.search(
                rf"(?<![a-z0-9_-]){re.escape(gene.lower())}(?![a-z0-9_-])",
                lowered,
            )
            for gene in (available_genes or [])
        ):
            return "biomedical_followup"
        if any(keyword in lowered for keyword in cls.BIOMEDICAL_KEYWORDS):
            return "biomedical_followup"
        return "biomedical_followup"

    @classmethod
    def is_non_biomedical_turn(
        cls,
        question: str,
        available_genes: list[str] | None = None,
    ) -> bool:
        return cls.classify_turn_fallback(question, available_genes) in {
            "casual_chat", "off_domain_request", "medical_advice_seeking",
        }

    @classmethod
    def is_off_domain_turn(
        cls,
        question: str,
        available_genes: list[str] | None = None,
    ) -> bool:
        return cls.classify_turn_fallback(question, available_genes) == "off_domain_request"

    def build_next_state(
        self,
        *,
        previous_state: ConversationState,
        question: str,
        resolution: dict[str, Any],
        discussed_genes: list[str],
    ) -> ConversationState:
        if resolution.get("resolved_intent") == "casual_chat":
            return previous_state

        next_state = ConversationState(
            active_genes=unique_preserving_order(
                discussed_genes or resolution.get("resolved_genes", []) or previous_state.active_genes
            ),
            active_phenotypes=unique_preserving_order(
                resolution.get("resolved_phenotypes", []) or previous_state.active_phenotypes
            ),
            active_intent=resolution.get("resolved_intent") or previous_state.active_intent,
            last_user_query=question,
            last_resolved_question=resolution.get("resolved_question") or question,
        )
        return next_state
