import math
import re
from collections import Counter
from difflib import get_close_matches
from typing import Optional

from .models import Evidence


TOKEN = re.compile(r"[a-zA-Z0-9]{2,}")
STOPWORDS = {"the", "is", "are", "was", "were", "what", "who", "when", "where", "why", "how", "with", "from", "that", "this", "for", "and", "or", "of", "to", "in", "on", "by", "at", "be", "an", "a"}
DATE_RANGE = re.compile(r"(\d{1,2}-[A-Za-z]{3}-\d{4})\s+to\s+(\d{1,2}-[A-Za-z]{3}-\d{4})", re.IGNORECASE)
DATE_VALUE = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{4}")
MONEY = re.compile(r"(?:€|₹|\$)\s?\d+(?:[.,]\d{2})|(?:Rs\.?\s*)\d+(?:[.,]\d{2})?", re.IGNORECASE)
NAME_FIELD = re.compile(
    r"\b(?:student\s+name|applicant\s+name|candidate\s+name|full\s+name|name)\s*[:\-]\s*"
    r"([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3})"
    r"(?=\s*(?:\||$|,|;|\n|email\b|e-mail\b|phone\b|mobile\b|contact\b|linkedin\b|github\b))",
    re.IGNORECASE,
)
NAME_HEADER = re.compile(
    r"^\s*([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3})"
    r"(?=\s+(?:email|e-mail|phone|mobile|contact|linkedin|github)\b|\s*\||"
    r"\s+(?:projects|education|skills|experience|summary|objective|certifications)\b)",
    re.IGNORECASE,
)
IDENTITY_TERMS = {"student", "applicant", "candidate", "name", "named"}
FILENAME_NAME_WORDS = {"resume", "cv", "curriculum", "vitae", "profile", "applicant", "candidate", "student", "name"}


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
    query = corrected_tokens(question, rows)[0]
    if not query or not rows:
        return []
    identity_question = is_identity_question(question, query)
    doc_count = len(rows)
    document_frequency = Counter({token: sum(token in _tokens(row["text"]) for row in rows) for token in query})
    results: list[Evidence] = []
    filename_fallback_documents: set[str] = set()
    for row in rows:
        tokens = _tokens(row["text"])
        person_name = None
        if identity_question:
            person_name = extract_person_name(row["text"])
            if not person_name and row["document_id"] not in filename_fallback_documents:
                person_name = extract_person_name_from_filename(row["filename"])
                if person_name:
                    filename_fallback_documents.add(row["document_id"])
        if identity_question and not person_name:
            continue
        frequencies = Counter(tokens)
        # The +1 inside log preserves useful scores for a one-document demo
        # corpus, where classic unsmoothed IDF would otherwise be zero.
        score = sum((frequencies[token] / max(1, len(tokens))) * math.log(1 + (doc_count / (document_frequency[token] + 1))) for token in query)
        if score > 0 or person_name:
            if person_name:
                score = max(score, 0.2)
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


def corrected_question(question: str, rows: list[dict]) -> tuple[str, list[dict[str, str]]]:
    """Correct likely misspelled document keywords before retrieval.

    Corrections are deliberately conservative: only a close vocabulary match in
    the selected document corpus is accepted, and short words are not changed.
    """
    _, corrections = corrected_tokens(question, rows)
    updated = question
    for correction in corrections:
        updated = re.sub(
            rf"\b{re.escape(correction['original'])}\b",
            correction["corrected"],
            updated,
            count=1,
            flags=re.IGNORECASE,
        )
    return updated, corrections


def corrected_tokens(question: str, rows: list[dict]) -> tuple[list[str], list[dict[str, str]]]:
    """Return normalized query tokens plus visible, corpus-based corrections."""
    query = _tokens(question)
    if not query or not rows:
        return query, []
    vocabulary = set()
    for row in rows:
        vocabulary.update(_tokens(row["text"]))
    corrected: list[str] = []
    corrections: list[dict[str, str]] = []
    for token in query:
        if token in vocabulary or len(token) < 4 or token.isdigit():
            corrected.append(token)
            continue
        candidate = get_close_matches(token, vocabulary, n=1, cutoff=0.82)
        if candidate:
            corrected.append(candidate[0])
            corrections.append({"original": token, "corrected": candidate[0]})
        else:
            corrected.append(token)
    return corrected, corrections


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
    if is_identity_question(question, _tokens(question)):
        person_name = extract_person_name(top.text) or extract_person_name_from_filename(top.document_name)
        if person_name:
            return f"Student name: {person_name}."
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


def extract_person_name(text: str) -> Optional[str]:
    """Extract a labeled person name for resume identity questions."""
    match = NAME_FIELD.search(text)
    if not match:
        match = NAME_HEADER.search(text)
    return " ".join(match.group(1).split()) if match else None


def extract_person_name_from_filename(filename: str) -> Optional[str]:
    """Use a resume filename as a fallback when PDF text has no identity field."""
    stem = re.sub(r"\.[A-Za-z0-9]+$", "", filename or "")
    words = [word for word in re.split(r"[_\-\s]+", stem) if word]
    name_words = [word for word in words if word.lower() not in FILENAME_NAME_WORDS]
    if len(name_words) < 2 or len(name_words) > 4:
        return None
    if not all(re.fullmatch(r"[A-Za-z][A-Za-z.' ]*", word) for word in name_words):
        return None
    return " ".join(word.capitalize() for word in name_words)


def is_identity_question(question: str, query_tokens: list[str]) -> bool:
    """Recognize name questions even when identity words contain typos."""
    if set(query_tokens) & IDENTITY_TERMS:
        return True
    for token in _tokens(question):
        if get_close_matches(token, IDENTITY_TERMS, n=1, cutoff=0.72):
            return True
    return False


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
