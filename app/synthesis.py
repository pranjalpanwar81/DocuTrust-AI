"""Optional grounded synthesis via an OpenAI-compatible chat-completions endpoint."""
import json
import urllib.request

from .config import settings
from typing import Optional


def synthesize(question: str, evidence) -> Optional[str]:
    """Return None on unavailable/failed LLM so callers safely use source text."""
    if not settings.openai_api_key:
        return None
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
    payload = json.dumps({"model": settings.openai_model, "temperature": 0, "messages": [{"role": "system", "content": "You are a compliance evidence assistant."}, {"role": "user", "content": prompt}]}).encode()
    request = urllib.request.Request(
        f"{settings.openai_base_url.rstrip('/')}/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            answer = json.loads(response.read())["choices"][0]["message"]["content"].strip()
        return None if answer == "INSUFFICIENT_EVIDENCE" else answer
    # LLM synthesis is an optional enhancement. Network failures, an invalid
    # key/billing state, or an unexpected provider response must never take
    # down the evidence-first query path.
    except Exception:
        return None
