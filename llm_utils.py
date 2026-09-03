import logging
import os
from typing import Any, Dict, List, Optional

import requests
from openai import BadRequestError

from dotenv import load_dotenv


load_dotenv()

logger = logging.getLogger(__name__)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()
LLM_TEMPERATURE = 0.2

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
VLLM_MODEL = os.getenv("VLLM_MODEL", "openai/gpt-oss")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "EMPTY")

QWEN_API_KEY = os.getenv("QWEN_API_KEY")
QWEN_BASE_URL = os.getenv(
    "QWEN_BASE_URL",
    "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
)
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen3.5-27b")

# OpenRouter is OpenAI-API-compatible: same SDK, only base_url/key/model IDs differ.
# Model IDs are namespaced, e.g. "openai/gpt-5.1", "anthropic/claude-...".
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-5.1")


class LLMAgent:
    """Wraps OpenAI, vLLM, Qwen, or Ollama chat completions."""

    def __init__(
        self,
        provider: str = "openai",
        client: Optional[Any] = None,
        model: str = "gpt-5.1",
        temperature: float = 0.2,
        ollama_url: str = "http://localhost:11434",
    ):
        self.provider = provider
        self.client = client
        self.model = model
        self.temperature = temperature
        self.ollama_url = ollama_url

    def chat(self, messages: List[Dict[str, str]], timeout: int = 600) -> str:
        if self.provider in {"openai", "vllm", "qwen", "openrouter"}:
            try:
                request_kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "timeout": timeout,
                }
                if self.temperature is not None:
                    request_kwargs["temperature"] = self.temperature
                resp = self.client.chat.completions.create(**request_kwargs)
                return resp.choices[0].message.content
            except BadRequestError as e:
                provider_name = {
                    "openai": "OpenAI",
                    "vllm": "vLLM",
                    "qwen": "Qwen",
                    "openrouter": "OpenRouter",
                }.get(self.provider, self.provider)
                # Some models (e.g. reasoning models) reject a custom temperature.
                # If that's what failed, retry once without it before giving up.
                if self.temperature is not None and "temperature" in str(e).lower():
                    try:
                        resp = self.client.chat.completions.create(
                            model=self.model, messages=messages, timeout=timeout
                        )
                        logger.warning(
                            "[LLM] %s retried model=%s without temperature after bad request",
                            provider_name,
                            self.model,
                        )
                        return resp.choices[0].message.content
                    except Exception as retry_err:
                        e = retry_err
                body = getattr(e, "body", None)
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
                    "openai": "OpenAI",
                    "vllm": "vLLM",
                    "qwen": "Qwen",
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

    if provider == "openai":
        if not OPENAI_API_KEY:
            raise ValueError("Missing OPENAI_API_KEY. Please add it to your .env file.")
        os.environ.pop("OPENAI_API_BASE", None)
        return OpenAI(api_key=OPENAI_API_KEY), os.getenv("LLM_MODEL", "gpt-5.1")

    if provider == "vllm":
        return OpenAI(api_key=VLLM_API_KEY, base_url=VLLM_BASE_URL), VLLM_MODEL

    if provider == "qwen":
        if not QWEN_API_KEY:
            raise ValueError("Missing QWEN_API_KEY. Please add it to your .env file.")
        return OpenAI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL), QWEN_MODEL

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


def build_llm_agent(provider: str, client: Optional[Any], model: Optional[str]):
    return build_llm_agent_with_temperature(provider, client=client, model=model, temperature=LLM_TEMPERATURE)


def build_llm_agent_with_temperature(
    provider: str,
    client: Optional[Any],
    model: Optional[str],
    temperature: float | None,
):
    if provider == "ollama":
        logger.info("[INIT] LLM Agent: Ollama (Model: %s @ %s)", OLLAMA_MODEL, OLLAMA_BASE_URL)
        return LLMAgent(
            provider="ollama",
            model=OLLAMA_MODEL,
            temperature=temperature if temperature is not None else LLM_TEMPERATURE,
            ollama_url=OLLAMA_BASE_URL,
        )

    provider_label = {
        "openai": "OpenAI",
        "vllm": "vLLM",
        "qwen": "Qwen",
        "openrouter": "OpenRouter",
    }.get(provider, provider)
    endpoint = {
        "vllm": VLLM_BASE_URL,
        "qwen": QWEN_BASE_URL,
        "openrouter": OPENROUTER_BASE_URL,
    }.get(provider)

    if endpoint:
        logger.info("[INIT] LLM Agent: %s (Model: %s @ %s)", provider_label, model, endpoint)
    else:
        logger.info("[INIT] LLM Agent: %s (Model: %s)", provider_label, model)

    return LLMAgent(
        provider=provider,
        client=client,
        model=model or "gpt-5.1",
        temperature=temperature,
    )
