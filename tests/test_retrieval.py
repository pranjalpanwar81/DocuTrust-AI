from app.models import ExtractedPage
from app.retrieval import bill_fields, chunk_pages, concise_answer, confidence, corrected_question, focused_excerpt, retrieve


def test_retrieval_returns_relevant_policy_evidence():
    chunks = chunk_pages("doc-1", [ExtractedPage(2, "Leave requests must be approved by the reporting manager within five working days.")])
    rows = [{**chunk, "filename": "leave-policy.pdf"} for chunk in chunks]
    results = retrieve("Who approves leave requests?", rows)
    assert results
    assert results[0].page == 2
    assert confidence(results) > 0


def test_retrieval_abstains_without_overlap():
    chunks = chunk_pages("doc-1", [ExtractedPage(1, "The office opens at nine in the morning.")])
    rows = [{**chunk, "filename": "office.pdf"} for chunk in chunks]
    assert retrieve("What is the encryption standard?", rows) == []


def test_evidence_score_is_numeric_not_document_text():
    chunks = chunk_pages("doc-1", [ExtractedPage(1, "Tax is valid from 6 July 2026 to 5 July 2028.")])
    rows = [{**chunk, "filename": "tax-receipt.pdf"} for chunk in chunks]
    result = retrieve("Till which date is the tax valid?", rows)[0]
    assert isinstance(result.score, float)
    assert "Tax is valid" in result.text


def test_date_question_gets_a_concise_grounded_answer():
    chunks = chunk_pages("doc-1", [ExtractedPage(1, "MV Tax 06-Jul-2026 to 05-Jul-2028. Amount paid: Rs 920.")])
    rows = [{**chunk, "filename": "tax-receipt.pdf"} for chunk in chunks]
    evidence = retrieve("Till which date is the tax valid?", rows)
    assert concise_answer("Till which date is the tax valid?", evidence).startswith("The tax is valid until 05-Jul-2028")
    assert focused_excerpt("Till which date is the tax valid?", evidence[0].text) == "Tax period: 06-Jul-2026 to 05-Jul-2028."


def test_flattened_bill_is_returned_as_aligned_fields():
    text = "Invoice Number 2023001322993 Billing Period 01/10/2023-31/10/2023 Invoice Date 04/11/2023 Payment Due Date 18/11/2023 Total Amount €30,00"
    chunks = chunk_pages("doc-1", [ExtractedPage(1, text)])
    rows = [{**chunk, "filename": "utility_bill.png"} for chunk in chunks]
    answer = concise_answer("What is the total amount bill?", retrieve("What is the total amount bill?", rows))
    assert bill_fields(text)[-1] == ("Total amount", "€30,00")
    assert "Total amount: €30,00" in answer
    assert "Payment due date: 18/11/2023" in answer


def test_misspelled_document_keyword_is_corrected_before_retrieval():
    chunks = chunk_pages("doc-1", [ExtractedPage(1, "The total amount payable is Rs. 920.00.")])
    rows = [{**chunk, "filename": "invoice.txt"} for chunk in chunks]
    interpreted, corrections = corrected_question("What is the amunt payable?", rows)
    assert interpreted == "What is the amount payable?"
    assert corrections == [{"original": "amunt", "corrected": "amount"}]
    assert retrieve("What is the amunt payable?", rows)


def test_identity_question_prefers_labeled_resume_name():
    rows = [
        {"id": "project", "document_id": "doc-1", "page_number": 1, "section": None, "text": "Projects Placency AI Powered Campus Placement Management Platform." , "filename": "resume.pdf"},
        {"id": "identity", "document_id": "doc-1", "page_number": 1, "section": None, "text": "Applicant Name: Pranjal Panwar | Email: pranjal@example.com", "filename": "resume.pdf"},
    ]

    evidence = retrieve("What is the applicant name?", rows)

    assert len(evidence) == 1
    assert "Pranjal Panwar" in concise_answer("What is the applicant name?", evidence)


def test_identity_question_abstains_without_name_field():
    rows = [{"id": "project", "document_id": "doc-1", "page_number": 1, "section": None, "text": "Projects include a campus placement management platform.", "filename": "resume.pdf"}]

    assert retrieve("What is the student name?", rows) == []


def test_identity_question_handles_resume_section_header():
    rows = [{"id": "identity", "document_id": "doc-1", "page_number": 1, "section": None, "text": "Pranjal Panwar Projects Placency AI-powered platform", "filename": "resume.pdf"}]

    evidence = retrieve("what is the studnt nam", rows)

    assert evidence
    assert concise_answer("what is the studnt nam", evidence) == "Student name: Pranjal Panwar."


def test_identity_question_uses_resume_filename_when_pdf_text_has_no_name():
    rows = [{"id": "identity", "document_id": "doc-1", "page_number": 1, "section": None, "text": "Projects Placency AI-powered platform", "filename": "Pranjal_Panwar_Resume.pdf"}]

    evidence = retrieve("applicant name", rows)

    assert evidence
    assert concise_answer("applicant name", evidence) == "Student name: Pranjal Panwar."
