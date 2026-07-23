import math
import re
from collections import Counter

from .models import Evidence


TOKEN = re.compile(r"[a-zA-Z0-9]{2,}")
STOPWORDS = {"the", "is", "are", "was", "were", "what", "who", "when", "where", "why", "how", "with", "from", "that", "this", "for", "and", "or", "of", "to", "in", "on", "by", "at", "be", "an", "a"}
DATE_RANGE = re.compile(r"(\d{1,2}-[A-Za-z]{3}-\d{4})\s+to\s+(\d{1,2}-[A-Za-z]{3}-\d{4})", re.IGNORECASE)
DATE_VALUE = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{4}")
MONEY = re.compile(r"(?:€|₹|\$)\s?\d+(?:[.,]\d{2})|(?:Rs\.?\s*)\d+(?:[.,]\d{2})?", re.IGNORECASE)


def chunk_pages(document_id: str, pages, chunk_size: int = 900, overlap: int = 150) -> list[dict]:
    chunks: list[dict] = []
    for page in pages:
        text = " ".join(page.text.split())
        start, part = 0, 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            if end < len(text):
                end = text.rfind(". ", start, end) + 1 or end
            value = text[start:end].strip()
            if value:
                chunks.append({"id": f"{document_id}:p{page.page_number}:c{part}", "document_id": document_id, "page_number": page.page_number, "section": page.section, "text": value})
                part += 1
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
    return chunks


def retrieve(question: str, rows: list[dict], limit: int = 5) -> list[Evidence]:
    query = _tokens(question)
    if not query or not rows:
        return []
    doc_count = len(rows)
    document_frequency = Counter({token: sum(token in _tokens(row["text"]) for row in rows) for token in query})
    results: list[Evidence] = []
    for row in rows:
        tokens = _tokens(row["text"])
        frequencies = Counter(tokens)
        # The +1 inside log preserves useful scores for a one-document demo
        # corpus, where classic unsmoothed IDF would otherwise be zero.
        score = sum((frequencies[token] / max(1, len(tokens))) * math.log(1 + (doc_count / (document_frequency[token] + 1))) for token in query)
        if score > 0:
            # Use named arguments: metadata ordering must never accidentally
            # put document text in the numeric score field.
            results.append(Evidence(
                chunk_id=row["id"],
                document_id=row["document_id"],
                document_name=row["filename"],
                page=row["page_number"],
                text=row["text"],
                score=score,
                section=row["section"],
            ))
    return sorted(results, key=lambda evidence: evidence.score, reverse=True)[:limit]


def confidence(evidence: list[Evidence]) -> float:
    if not evidence:
        return 0.0
    return round(min(1.0, evidence[0].score * 9), 2)


def focused_excerpt(question: str, text: str, max_length: int = 300) -> str:
    """Return a compact, readable source quote rather than a raw PDF dump."""
    normalized = " ".join(text.split())
    fields = bill_fields(normalized)
    query_words = set(_tokens(question))
    if fields and query_words & {"amount", "bill", "total", "due", "invoice", "period", "payment"}:
        return format_fields(fields)
    date_match = DATE_RANGE.search(normalized)
    if date_match and any(word in _tokens(question) for word in {"date", "valid", "validity", "period", "until", "tax"}):
        return f"Tax period: {date_match.group(1)} to {date_match.group(2)}."
    fragments = re.split(r"(?<=[.!?])\s+|(?<=;)\s+", normalized)
    best = max(fragments, key=lambda fragment: len(query_words & set(_tokens(fragment))), default=normalized)
    if len(best) <= max_length:
        return best
    return best[:max_length].rsplit(" ", 1)[0] + "…"


def concise_answer(question: str, evidence: list[Evidence]) -> str:
    """Safe no-LLM answer writer; facts are copied only from top evidence."""
    top = evidence[0]
    fields = bill_fields(" ".join(top.text.split()))
    question_words = set(_tokens(question))
    if fields and question_words & {"amount", "bill", "total", "due", "invoice", "period", "payment"}:
        return f"Bill details\n{format_fields(fields)}"
    date_match = DATE_RANGE.search(" ".join(top.text.split()))
    if date_match and question_words & {"date", "valid", "validity", "period", "until", "tax"}:
        return f"The tax is valid until {date_match.group(2)}.\n\nValidity period: {date_match.group(1)} to {date_match.group(2)}."
    return f"Most relevant information:\n{focused_excerpt(question, top.text)}"


def bill_fields(text: str) -> list[tuple[str, str]]:
    """Extract common invoice fields from flattened OCR text for readable UI."""
    fields: list[tuple[str, str]] = []
    invoice = re.search(r"Invoice Number\s+([A-Za-z0-9-]+)", text, re.IGNORECASE)
    period = re.search(r"Billing Period\s+(.+?)(?=\s+Invoice Date|$)", text, re.IGNORECASE)
    due = re.search(r"Payment Due Date\s+(\d{1,2}[/-]\d{1,2}[/-]\d{4})", text, re.IGNORECASE)
    totals: list[str] = []
    for match in re.finditer(r"Total Amount", text, re.IGNORECASE):
        values = MONEY.findall(text[match.end():match.end() + 110])
        if values:
            totals.append(values[-1])
    if invoice:
        fields.append(("Invoice number", invoice.group(1)))
    if period:
        fields.append(("Billing period", period.group(1).strip()))
    if due:
        fields.append(("Payment due date", due.group(1)))
    if totals:
        fields.append(("Total amount", totals[-1]))
    return fields


def format_fields(fields: list[tuple[str, str]]) -> str:
    return "\n".join(f"{label}: {value}" for label, value in fields)


def _tokens(text: str) -> list[str]:
    return [normalized for token in TOKEN.findall(text) if (normalized := _normalize(token)) not in STOPWORDS]


def _normalize(token: str) -> str:
    """Small deterministic stemmer for the offline baseline.

    Production deployments should compare this baseline against an embedding
    retriever; this keeps common query/document word-form differences useful
    without downloading a model.
    """
    value = token.lower()
    for suffix in ("ing", "ed", "es", "s"):
        if value.endswith(suffix) and len(value) > len(suffix) + 3:
            return value[: -len(suffix)]
    return value
