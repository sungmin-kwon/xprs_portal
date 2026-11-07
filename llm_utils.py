import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests
from openai import BadRequestError

from dotenv import load_dotenv


load_dotenv()

logger = logging.getLogger(__name__)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter").lower()
LLM_TEMPERATURE = 0.2

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
VLLM_MODEL = os.getenv("VLLM_MODEL", "openai/gpt-oss")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "EMPTY")

# OpenRouter is OpenAI-API-compatible: same SDK, only base_url/key/model IDs differ.
# Model IDs are namespaced, e.g. "openai/gpt-6.1-sol", "anthropic/claude-...".
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-6.1-sol")
OPENROUTER_ZDR_REQUIRED = os.getenv("OPENROUTER_ZDR_REQUIRED", "true").lower() in {
    "1", "true", "yes", "on",
}
OPENROUTER_DATA_COLLECTION = os.getenv("OPENROUTER_DATA_COLLECTION", "deny").strip().lower()
if OPENROUTER_DATA_COLLECTION != "deny":
    raise ValueError("OPENROUTER_DATA_COLLECTION must be 'deny' for the XPRS privacy policy")


_KPREDICT_SENSITIVE_PATTERNS = (
    (re.compile(r"\bKP-[A-F0-9]{12}\b", re.I), "[PSEUDONYMOUS_ID_REMOVED]"),
    (re.compile(r"\brs\d{3,}\b", re.I), "[VARIANT_ID_REMOVED]"),
    (re.compile(r"\b(?:NC|NM|NP|NG|NR)_\d+(?:\.\d+)?:[^\s,;]+", re.I), "[HGVS_REMOVED]"),
    (re.compile(r"\bchr(?:om(?:osome)?)?\s*[0-9XYM]+\s*[:/]\s*\d+\b", re.I), "[GENOMIC_COORDINATE_REMOVED]"),
    (re.compile(r"(?<!\d)\b[012][|/][012]\b(?!\d)"), "[GENOTYPE_REMOVED]"),
    (
        re.compile(
            r"\b(?:PRS|polygenic\s+risk\s+score)\s*(?:value\s*)?(?:is|=|:)?\s*-?\d+(?:\.\d+)?\b",
            re.I,
        ),
        "[PRS_VALUE_REMOVED]",
    ),
    (
        re.compile(r"\b\d+(?:\.\d+)?(?:st|nd|rd|th)?\s+percentile\b", re.I),
        "[PERCENTILE_REMOVED]",
    ),
    (
        re.compile(r"\b\d+(?:\.\d+)?%\s+of\s+(?:this|the)\s+cohort\b", re.I),
        "[PERCENTILE_REMOVED]",
    ),
    (
        re.compile(r"\b(?:percentile|Pctl)\s*(?:is|=|:)?\s*\d+(?:\.\d+)?%?\b", re.I),
        "[PERCENTILE_REMOVED]",
    ),
    (
        re.compile(
            r"\b(?:gene\s+)?contribution(?:\s+score)?\s*(?:is|=|:)?\s*-?\d+(?:\.\d+)?\b",
            re.I,
        ),
        "[CONTRIBUTION_VALUE_REMOVED]",
    ),
    (
        re.compile(r"\b(?:sex|gender)\s*(?:is|=|:)\s*(?:male|female|M|F)\b", re.I),
        "[DEMOGRAPHIC_REMOVED]",
    ),
)


def sanitize_kpredict_text(value: str) -> str:
    sanitized = str(value)
    for pattern, replacement in _KPREDICT_SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def mask_kpredict_sensitive_values(value: str) -> tuple[str, dict[str, str]]:
    """Replace private values with stable opaque tokens for reversible transforms.

    This is used for tasks such as translation where the exact locally rendered
    values must survive, but must not be sent to the hosted model.
    """
    masked = str(value)
    replacements: dict[str, str] = {}
    next_index = 0

    for pattern, _replacement in _KPREDICT_SENSITIVE_PATTERNS:
        def replace_match(match: re.Match[str]) -> str:
            nonlocal next_index
            token = f"XPRSPRIVATEVALUE{next_index:04d}X"
            next_index += 1
            replacements[token] = match.group(0)
            return token

        masked = pattern.sub(replace_match, masked)

    return masked, replacements


def restore_kpredict_sensitive_values(value: str, replacements: dict[str, str]) -> str:
    restored = str(value)
    for token, original in replacements.items():
        restored = re.sub(re.escape(token), lambda _match, text=original: text, restored, flags=re.I)
    return restored


class LLMAgent:
    """Wraps OpenRouter, local vLLM, or Ollama chat completions."""

    def __init__(
        self,
        provider: str = "openrouter",
        client: Optional[Any] = None,
        model: str = "openai/gpt-6.1-sol",
        temperature: float = 0.2,
        ollama_url: str = "http://localhost:11434",
        privacy_mode: str | None = None,
    ):
        self.provider = provider
        self.client = client
        self.model = model
        self.temperature = temperature
        self.ollama_url = ollama_url
        self.privacy_mode = privacy_mode

    def _messages_for_request(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        if self.privacy_mode != "kpredict":
            return messages
        return [
            {**message, "content": sanitize_kpredict_text(message.get("content", ""))}
            for message in messages
        ]

    @staticmethod
    def _completion_text(response: Any) -> str:
        """Extract one completion with a useful error for malformed providers."""
        choices = getattr(response, "choices", None)
        if not choices:
            raise RuntimeError("completion response contained no choices")
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None) if message is not None else None
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(getattr(item, "text", None), str):
                    parts.append(item.text)
            combined = "".join(parts)
            if combined.strip():
                return combined
        raise RuntimeError("completion response contained no message content")

    def chat(self, messages: List[Dict[str, str]], timeout: int = 600) -> str:
        if self.provider in {"vllm", "openrouter"}:
            try:
                request_kwargs = {
                    "model": self.model,
                    "messages": self._messages_for_request(messages),
                    "timeout": timeout,
                }
                if self.provider == "openrouter":
                    if not OPENROUTER_ZDR_REQUIRED:
                        raise RuntimeError("OpenRouter ZDR enforcement is disabled; refusing the request")
                    request_kwargs["extra_body"] = {
                        "provider": {
                            "zdr": True,
                            "data_collection": OPENROUTER_DATA_COLLECTION,
                        }
                    }
                if self.temperature is not None:
                    request_kwargs["temperature"] = self.temperature
                resp = self.client.chat.completions.create(**request_kwargs)
                try:
                    return self._completion_text(resp)
                except RuntimeError as malformed_error:
                    # OpenRouter can occasionally return a syntactically valid
                    # response envelope with no completion choice. Retry only
                    # that narrow condition, with a hard cap of three attempts.
                    for retry_number in (1, 2):
                        logger.warning(
                            "[LLM] %s returned a malformed completion for model=%s; "
                            "retrying %s/2: %s",
                            self.provider,
                            self.model,
                            retry_number,
                            malformed_error,
                        )
                        retry_resp = self.client.chat.completions.create(**request_kwargs)
                        try:
                            return self._completion_text(retry_resp)
                        except RuntimeError as retry_error:
                            malformed_error = retry_error
                    raise malformed_error
            except BadRequestError as e:
                provider_name = {
                    "vllm": "vLLM",
                    "openrouter": "OpenRouter",
                }.get(self.provider, self.provider)
                # Some models (e.g. reasoning models) reject a custom temperature.
                # If that's what failed, retry once without it before giving up.
                if self.temperature is not None and "temperature" in str(e).lower():
                    try:
                        retry_kwargs = dict(request_kwargs)
                        retry_kwargs.pop("temperature", None)
                        resp = self.client.chat.completions.create(**retry_kwargs)
                        logger.warning(
                            "[LLM] %s retried model=%s without temperature after bad request",
                            provider_name,
                            self.model,
                        )
                        return self._completion_text(resp)
                    except Exception as retry_err:
                        e = retry_err
                body = (
                    "[redacted for K-PREDICT privacy mode]"
                    if self.privacy_mode == "kpredict"
                    else getattr(e, "body", None)
                )
                logger.error(
                    "[LLM] %s bad request for model=%s: %s | body=%s",
                    provider_name,
                    self.model,
                    e,
                    body,
                )
                raise RuntimeError(f"{provider_name} chat call failed: {e}")
            except Exception as e:
                provider_name = {
                    "vllm": "vLLM",
                    "openrouter": "OpenRouter",
                }.get(self.provider, self.provider)
                raise RuntimeError(f"{provider_name} chat call failed: {e}")

        if self.provider == "ollama":
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                },
            }

            try:
                url = f"{self.ollama_url}/api/chat"
                resp = requests.post(url, json=payload, timeout=timeout)
                resp.raise_for_status()
                data = resp.json()
                return data.get("message", {}).get("content", "")
            except Exception as e:
                raise RuntimeError(f"Ollama chat call failed: {e}")

        raise ValueError(f"Unknown LLM provider: {self.provider}")


def build_llm_client(provider: str) -> tuple[Optional[Any], Optional[str]]:
    from openai import OpenAI

    if provider == "vllm":
        return OpenAI(api_key=VLLM_API_KEY, base_url=VLLM_BASE_URL), VLLM_MODEL

    if provider == "openrouter":
        if not OPENROUTER_API_KEY:
            raise ValueError("Missing OPENROUTER_API_KEY. Please add it to your .env file.")
        # X-Title / HTTP-Referer are optional attribution headers OpenRouter uses
        # for its rankings; only send the referrer if one is configured.
        default_headers = {"X-Title": os.getenv("OPENROUTER_APP_TITLE", "XPRS Portal")}
        referrer = os.getenv("OPENROUTER_REFERRER")
        if referrer:
            default_headers["HTTP-Referer"] = referrer
        return (
            OpenAI(
                api_key=OPENROUTER_API_KEY,
                base_url=OPENROUTER_BASE_URL,
                default_headers=default_headers,
            ),
            os.getenv("LLM_MODEL", OPENROUTER_MODEL),
        )

    if provider == "ollama":
        return None, OLLAMA_MODEL

    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")


def build_llm_agent(
    provider: str,
    client: Optional[Any],
    model: Optional[str],
    privacy_mode: str | None = None,
):
    return build_llm_agent_with_temperature(
        provider,
        client=client,
        model=model,
        temperature=LLM_TEMPERATURE,
        privacy_mode=privacy_mode,
    )


def build_llm_agent_with_temperature(
    provider: str,
    client: Optional[Any],
    model: Optional[str],
    temperature: float | None,
    privacy_mode: str | None = None,
):
    if provider == "ollama":
        logger.info("[INIT] LLM Agent: Ollama (Model: %s @ %s)", OLLAMA_MODEL, OLLAMA_BASE_URL)
        return LLMAgent(
            provider="ollama",
            model=OLLAMA_MODEL,
            temperature=temperature if temperature is not None else LLM_TEMPERATURE,
            ollama_url=OLLAMA_BASE_URL,
            privacy_mode=privacy_mode,
        )

    provider_label = {
        "vllm": "vLLM",
        "openrouter": "OpenRouter",
    }.get(provider, provider)
    endpoint = {
        "vllm": VLLM_BASE_URL,
        "openrouter": OPENROUTER_BASE_URL,
    }.get(provider)

    if endpoint:
        logger.info("[INIT] LLM Agent: %s (Model: %s @ %s)", provider_label, model, endpoint)
    else:
        logger.info("[INIT] LLM Agent: %s (Model: %s)", provider_label, model)

    return LLMAgent(
        provider=provider,
        client=client,
        model=model or OPENROUTER_MODEL,
        temperature=temperature,
        privacy_mode=privacy_mode,
    )
