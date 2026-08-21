from app.models import ExtractedPage
from app.retrieval import chunk_pages, confidence, retrieve


def test_hallucination_case_no_supporting_document():
    """Question with no lexical overlap must return no evidence (abstain)."""
    chunks = chunk_pages("doc-1", [ExtractedPage(1, "The office opens at nine in the morning.")])
    rows = [{**chunk, "filename": "office.pdf"} for chunk in chunks]
    evidence = retrieve("What is our encryption standard?", rows)
    assert evidence == []


def test_hallucination_case_out_of_corpus_fact():
    """Indexed text must not invent facts that are not present."""
    chunks = chunk_pages("doc-1", [ExtractedPage(1, "Leave requests must be approved by the reporting manager.")])
    rows = [{**chunk, "filename": "leave-policy.pdf"} for chunk in chunks]
    evidence = retrieve("When was the company founded?", rows)
    assert evidence == []


def test_hallucination_case_wrong_domain_question():
    """A finance question against a leave-policy document should not retrieve evidence."""
    chunks = chunk_pages("doc-1", [ExtractedPage(2, "Leave requests must be approved by the reporting manager within five working days.")])
    rows = [{**chunk, "filename": "leave-policy.pdf"} for chunk in chunks]
    evidence = retrieve("What was Q3 revenue?", rows)
    assert evidence == []


def test_hallucination_case_grounded_question_has_evidence():
    """Supported questions must retrieve the correct passage for manual citation review."""
    chunks = chunk_pages("doc-1", [ExtractedPage(2, "Leave requests must be approved by the reporting manager within five working days.")])
    rows = [{**chunk, "filename": "leave-policy.pdf"} for chunk in chunks]
    evidence = retrieve("Who approves leave requests?", rows)
    assert evidence
    assert evidence[0].page == 2
    assert confidence(evidence) > 0
