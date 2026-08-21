"""Optional grounded synthesis via an OpenAI-compatible chat-completions endpoint."""
import json
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from .config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SynthesisResult:
    text: Optional[str]
    source: str  # "llm" | "fallback"
    error: Optional[str] = None


def synthesize(question: str, evidence) -> SynthesisResult:
    """Return structured synthesis metadata so callers can fall back safely."""
    if not settings.openai_api_key:
        logger.info("LLM synthesis skipped: OPENAI_API_KEY is not configured.")
        return SynthesisResult(None, "fallback", "api_key_missing")

    sources = "\n\n".join(
        f"[S{index}] {item.document_name}, page {item.page}\n{item.text}"
        for index, item in enumerate(evidence, 1)
    )
    prompt = (
        "Answer only from the sources below. Do not use outside knowledge. "
        "If the sources do not establish the answer, reply exactly: INSUFFICIENT_EVIDENCE. "
        "Use concise sentences and cite each claim as [S1], [S2], etc.\n\n"
        f"Question: {question}\n\nSources:\n{sources}"
    )
    payload = {
        "model": settings.openai_model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "You are a compliance evidence assistant."},
            {"role": "user", "content": prompt},
        ],
    }
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"].strip()
    except httpx.TimeoutException:
        logger.warning(
            "LLM synthesis timed out after 20s (model=%s, base_url=%s). Falling back to deterministic answer.",
            settings.openai_model,
            settings.openai_base_url,
        )
        return SynthesisResult(None, "fallback", "timeout")
    except httpx.HTTPStatusError as error:
        body = error.response.text[:240].replace("\n", " ")
        logger.warning(
            "LLM synthesis HTTP error %s (model=%s): %s. Falling back to deterministic answer.",
            error.response.status_code,
            settings.openai_model,
            body,
        )
        return SynthesisResult(None, "fallback", f"http_{error.response.status_code}")
    except httpx.RequestError as error:
        logger.warning(
            "LLM synthesis network error (%s): %s. Falling back to deterministic answer.",
            settings.openai_model,
            error,
        )
        return SynthesisResult(None, "fallback", "network_error")
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        logger.warning(
            "LLM synthesis returned an unexpected response shape (%s): %s. Falling back to deterministic answer.",
            settings.openai_model,
            error,
        )
        return SynthesisResult(None, "fallback", "malformed_response")

    if answer == "INSUFFICIENT_EVIDENCE":
        logger.info("LLM synthesis abstained: sources did not support the question.")
        return SynthesisResult(None, "fallback", "llm_abstained")

    logger.info("LLM synthesis succeeded (model=%s, answer_chars=%s).", settings.openai_model, len(answer))
    return SynthesisResult(answer, "llm")
