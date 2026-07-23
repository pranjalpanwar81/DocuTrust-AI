from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf" / "DocuTrust_AI_Project_Explanation.pdf"

NAVY = colors.HexColor("#172B4D")
BLUE = colors.HexColor("#356DF0")
MINT = colors.HexColor("#DFF7ED")
INK = colors.HexColor("#192640")
MUTED = colors.HexColor("#5E6D86")
LINE = colors.HexColor("#DDE4EF")
PALE = colors.HexColor("#F5F8FC")
WHITE = colors.white


def header_footer(canvas, document):
    canvas.saveState()
    width, height = A4
    if document.page > 1:
        canvas.setStrokeColor(LINE)
        canvas.line(44, height - 39, width - 44, height - 39)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(NAVY)
        canvas.drawString(44, height - 30, "DOCUTRUST AI")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(width - 44, height - 30, "Final Year Project Brief")
        canvas.line(44, 37, width - 44, 37)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(44, 25, "Citation-grounded document intelligence")
        canvas.drawRightString(width - 44, 25, f"Page {document.page}")
    canvas.restoreState()


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="CoverKicker", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10,
    leading=14, textColor=BLUE, alignment=TA_CENTER, spaceAfter=12,
))
styles.add(ParagraphStyle(
    name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=29,
    leading=35, textColor=NAVY, alignment=TA_CENTER, spaceAfter=14,
))
styles.add(ParagraphStyle(
    name="CoverSubtitle", parent=styles["Normal"], fontName="Helvetica", fontSize=13,
    leading=19, textColor=MUTED, alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    name="H1Custom", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=19,
    leading=24, textColor=NAVY, spaceBefore=15, spaceAfter=9,
))
styles.add(ParagraphStyle(
    name="H2Custom", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12,
    leading=16, textColor=NAVY, spaceBefore=12, spaceAfter=6,
))
styles.add(ParagraphStyle(
    name="BodyCustom", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.7,
    leading=14.4, textColor=INK, spaceAfter=7,
))
styles.add(ParagraphStyle(
    name="Small", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.4,
    leading=11.7, textColor=INK,
))
styles.add(ParagraphStyle(
    name="Callout", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=10.5,
    leading=15, textColor=NAVY, leftIndent=12, rightIndent=12, spaceBefore=5, spaceAfter=5,
))
styles.add(ParagraphStyle(
    name="BulletCustom", parent=styles["BodyText"], fontName="Helvetica", fontSize=9.5,
    leading=14, textColor=INK, leftIndent=16, firstLineIndent=-9, spaceAfter=4,
))


def p(text, style="BodyCustom"):
    return Paragraph(text, styles[style])


def bullets(items):
    return [p(f"- {item}", "BulletCustom") for item in items]


def section(title, intro=None):
    flow = [p(title, "H1Custom")]
    if intro:
        flow.append(p(intro))
    return flow


def table(headers, rows, widths=None):
    data = [[p(value, "Small") for value in headers]]
    data += [[p(value, "Small") for value in row] for row in rows]
    result = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("BACKGROUND", (0, 1), (-1, -1), WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, PALE]),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return result


def callout(text):
    block = Table([[p(text, "Callout")]], colWidths=[7.05 * inch])
    block.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), MINT),
        ("LINEBEFORE", (0, 0), (0, -1), 4, colors.HexColor("#28A978")),
        ("BOX", (0, 0), (-1, -1), 0.35, colors.HexColor("#BEE8D7")),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return block


def build_report():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(OUTPUT), pagesize=A4, rightMargin=44, leftMargin=44, topMargin=54, bottomMargin=48,
        title="DocuTrust AI - Project Explanation",
        author="DocuTrust AI Project Team",
    )
    frame = doc.pagesize[0] - doc.leftMargin - doc.rightMargin
    doc.addPageTemplates([PageTemplate(id="main", frames=[
        __import__("reportlab.platypus", fromlist=["Frame"]).Frame(doc.leftMargin, doc.bottomMargin, frame, doc.pagesize[1] - doc.topMargin - doc.bottomMargin, id="body")
    ], onPage=header_footer)])

    story = []
    story += [Spacer(1, 1.2 * inch), p("FINAL YEAR AIML PROJECT", "CoverKicker")]
    story += [p("DocuTrust AI", "CoverTitle")]
    story += [p("A Citation-Grounded Multimodal RAG System for Reliable Policy and Compliance Intelligence", "CoverSubtitle")]
    story += [Spacer(1, 0.36 * inch)]
    story += [callout("DocuTrust AI turns organizational documents into a trustworthy, searchable knowledge base. Every answer is linked to source evidence instead of being presented as an unsupported chatbot response.")]
    story += [Spacer(1, 0.48 * inch)]
    cover_data = [
        [p("Project type", "Small"), p("Full-stack AIML document intelligence application", "Small")],
        [p("Core focus", "Small"), p("Grounded retrieval, OCR, citations, analytics, and auditability", "Small")],
        [p("Primary users", "Small"), p("Organizations, compliance teams, HR, operations, and students", "Small")],
    ]
    cover = Table(cover_data, colWidths=[1.45 * inch, 5.6 * inch])
    cover.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), PALE), ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story += [cover, Spacer(1, 1.35 * inch), p("Prepared for project explanation, reviews, placement interviews, and viva preparation.", "CoverSubtitle"), PageBreak()]

    story += section("1. Executive Summary")
    story += [p("DocuTrust AI is an AI-powered document intelligence platform. Users upload PDFs, Word documents, text files, or image documents such as bills and receipts. The system extracts text, indexes it as evidence chunks, answers natural-language questions, and displays source citations with page information.")]
    story += [p("The project is designed to reduce a key risk of generic chatbots: hallucination. Rather than relying only on a language model, DocuTrust retrieves relevant evidence first and returns a grounded answer. When evidence is weak, it responds with an insufficient-evidence message instead of guessing.")]
    story += [callout("Core value proposition: trustworthy answers from uploaded documents, supported by evidence that the user can verify.")]

    story += section("2. Problem Statement and Objectives")
    story += [p("Organizations store important information across policies, SOPs, invoices, contracts, compliance manuals, and circulars. Manual search is slow, while general chatbots may answer incorrectly without proof.")]
    story += [p("Problem statement: How can an AI assistant answer questions from organizational documents while preserving traceability, showing evidence, and refusing unsupported answers?")]
    story += [p("H2Custom") if False else Spacer(1, 1)]
    story += [p("Project objectives", "H2Custom")]
    story += bullets([
        "Accept common enterprise document formats and extract searchable text.",
        "Use OCR for image-based bills, receipts, and scans.",
        "Retrieve the most relevant evidence for a natural-language question.",
        "Return concise answers with document and page citations.",
        "Use confidence and abstention to reduce unsupported answers.",
        "Provide audit, analytics, document management, and a usable web interface.",
    ])

    story += section("3. Architecture and End-to-End Workflow")
    workflow = [
        ["1. Upload", "User uploads PDF, DOCX, TXT, Markdown, or image file."],
        ["2. Extract", "Native parsers extract PDF/DOCX text; Tesseract OCR reads image text."],
        ["3. Chunk", "Text is divided into smaller chunks with document and page metadata."],
        ["4. Index", "Document metadata and chunks are stored in SQLite."],
        ["5. Retrieve", "Question words are compared with chunks and ranked by relevance."],
        ["6. Decide", "Confidence determines grounded answer vs. insufficient evidence."],
        ["7. Respond", "System returns concise answer, evidence, page citation, and audit event."],
    ]
    story += [table(["Stage", "What happens"], workflow, [1.1 * inch, 5.95 * inch])]
    story += [Spacer(1, 8), p("Architecture summary", "H2Custom")]
    story += [callout("Upload -> Extract/OCR -> Chunk + metadata -> SQLite -> Retrieve -> Confidence gate -> Grounded answer + citation -> Audit and analytics")]

    story += section("4. Core AIML Approach")
    story += [p("DocuTrust follows a Retrieval-Augmented Generation (RAG) style workflow. RAG has two stages: retrieval finds relevant source content, and generation creates an answer from that retrieved content.")]
    story += [table(["Mode", "How it works", "Why it matters"], [
        ["Offline grounded mode", "Creates a structured answer directly from retrieved source text.", "Works without API cost and does not invent unsupported prose."],
        ["Optional LLM mode", "Sends only retrieved evidence to an OpenAI-compatible model for synthesis.", "Produces more natural language while keeping the answer source constrained."],
    ], [1.35 * inch, 3.0 * inch, 2.7 * inch])]
    story += [p("The current retrieval baseline is intentionally explainable. It uses tokenization, stop-word removal, basic word normalization, and a TF-IDF-inspired relevance score. This is a strong baseline for a final-year project because it can be measured and later compared against embeddings.")]
    story += [p("Important technical honesty: the current version is not yet a vector-database semantic search system. Adding Sentence Transformers, embeddings, FAISS/ChromaDB, and reranking is an important planned enhancement.")]

    story += section("5. Document Processing and OCR")
    story += [table(["Input", "Library or engine", "Result"], [
        ["PDF", "PyPDF", "Native page-level text extraction"],
        ["DOCX", "python-docx", "Paragraph-level extraction"],
        ["TXT / Markdown", "Python text decoding", "Direct searchable text"],
        ["PNG / JPG / TIFF / BMP", "Pillow + pytesseract + Tesseract", "OCR text extraction"],
    ], [1.45 * inch, 2.5 * inch, 3.1 * inch])]
    story += [p("After extraction, the system divides text into chunks. Each chunk retains chunk ID, document ID, page number, optional section, and text. Chunking enables faster retrieval, smaller LLM context, and page-level citations.")]
    story += [p("For OCR bills, raw output is often a long unstructured line. DocuTrust detects common invoice fields such as invoice number, billing period, payment due date, and total amount, then formats them as aligned label-value output.")]

    # Keep the feature matrix together at the beginning of a fresh page so it
    # does not begin with only a few rows at the bottom of the previous page.
    story += [PageBreak()]
    story += section("6. Features Implemented")
    features = [
        ["Citation-grounded answers", "Shows document name, page number, and focused evidence.", "Lets users verify answers and improves trust."],
        ["Confidence + abstention", "Returns grounded or insufficient-evidence status.", "Reduces hallucination risk."],
        ["Structured bill extraction", "Formats invoice number, period, due date, and amount.", "Turns messy OCR into readable information."],
        ["Document-scoped queries", "Search all sources or only one selected document.", "Avoids mixing unrelated document content."],
        ["Source document management", "Delete one document or clear all sources with confirmation.", "Supports removal of old or irrelevant documents."],
        ["Audit trail", "Stores question, status, confidence, timestamp, and citation IDs.", "Provides traceability and accountability."],
        ["Audit entry deletion", "Delete a single audit record using a dustbin action.", "Lets users manage query-history data."],
        ["Workspace analytics", "Shows documents, chunks, grounded-answer rate, and average confidence.", "Measures usage and answer quality."],
        ["Light / dark theme", "Theme selector is saved in browser local storage.", "Improves usability and product polish."],
        ["Swagger API documentation", "FastAPI exposes interactive documentation at /docs.", "Simplifies testing and demonstrates API engineering."],
    ]
    story += [table(["Feature", "What it does", "Why it is useful"], features, [1.55 * inch, 2.85 * inch, 2.65 * inch])]

    story += [PageBreak()]
    story += section("7. Database and Audit Design")
    story += [p("DocuTrust uses SQLite because it is lightweight, local, easy to demonstrate, and appropriate for an MVP. A future production deployment can use PostgreSQL.")]
    story += [table(["Table", "Important fields", "Purpose"], [
        ["documents", "id, filename, media type, page count, extraction method", "Stores source-document metadata."],
        ["chunks", "document ID, page number, section, text", "Stores searchable evidence chunks."],
        ["query_events", "question, status, confidence, citation IDs, time", "Stores audit trail and analytics data."],
    ], [1.15 * inch, 3.1 * inch, 2.8 * inch])]
    story += [p("The analytics dashboard uses database aggregates to calculate document count, evidence-chunk count, query count, grounded-answer rate, and average confidence. This changes the project from a simple demo into a measurable system.")]

    story += section("8. Backend APIs")
    apis = [
        ["GET /", "Open the user-facing DocuTrust application."],
        ["GET /health", "Check service status, LLM configuration, and document count."],
        ["POST /api/v1/documents", "Upload, extract, chunk, and index a document."],
        ["GET /api/v1/documents", "List indexed source documents."],
        ["DELETE /api/v1/documents/{id}", "Delete one source document and its chunks."],
        ["DELETE /api/v1/documents", "Delete all source documents."],
        ["POST /api/v1/query", "Run document-scoped retrieval and return answer/citations."],
        ["GET /api/v1/analytics", "Return workspace quality metrics."],
        ["GET /api/v1/query-history", "Return recent audit events."],
        ["DELETE /api/v1/query-history/{id}", "Delete a selected audit entry."],
        ["GET /docs", "Open Swagger interactive API documentation."],
    ]
    story += [table(["Endpoint", "Purpose"], apis, [2.65 * inch, 4.4 * inch])]

    story += section("9. Frontend and User Experience")
    story += [p("The frontend is implemented with HTML, CSS, and vanilla JavaScript. It communicates with FastAPI using fetch requests. Keeping the frontend dependency-light makes local execution and viva explanation easier.")]
    story += bullets([
        "Upload panel and source-document list.",
        "Dustbin actions for document and audit deletion, always protected by confirmation.",
        "Document scope selector for precise retrieval.",
        "Aligned answer cards and source evidence blocks.",
        "Analytics dashboard and reusable recent questions.",
        "Responsive layout with persistent light/dark theme selection.",
    ])

    story += section("10. Security and Reliability")
    story += [table(["Control", "Implementation"], [
        ["API key isolation", "OPENAI_API_KEY is stored in local .env and never exposed to browser JavaScript."],
        ["Git safety", ".env and local data are excluded using .gitignore."],
        ["Upload protection", "Filenames are sanitized and upload size is limited."],
        ["Deletion safety", "Document and audit deletion requires browser confirmation."],
        ["Answer safety", "Weak retrieval causes insufficient-evidence response rather than a guess."],
        ["LLM resilience", "Optional LLM failures fall back to evidence-first local answers."],
    ], [1.75 * inch, 5.3 * inch])]

    story += section("11. Testing and Validation")
    story += [p("Core project checks cover relevant retrieval, unsupported-question abstention, numeric confidence handling, tax validity extraction, structured bill extraction, document deletion, audit deletion, analytics calculations, and API-level query behaviour.")]
    story += [p("The interface was also reviewed after implementing aligned bill fields, citations, dark mode, analytics, source deletion, and audit deletion.")]

    story += section("12. Limitations and Future Scope")
    story += [table(["Current limitation", "Recommended next upgrade"], [
        ["Lexical retrieval baseline", "Add sentence embeddings, FAISS/ChromaDB, and hybrid search."],
        ["No user authentication", "Add JWT login, role-based access control, and document ACLs."],
        ["No PDF source viewer", "Add a PDF viewer with highlighted evidence passage."],
        ["Basic OCR structure", "Add layout-aware OCR, table extraction, and scanned-PDF OCR."],
        ["SQLite MVP database", "Use PostgreSQL for production multi-user deployment."],
        ["Prompt-based grounding in LLM mode", "Add automated claim-to-citation verification."],
    ], [2.7 * inch, 4.35 * inch])]

    story += section("13. Evaluation Plan for Report or Paper")
    story += [p("Create a benchmark of approximately 10-20 public or synthetic policy documents and 75-100 labelled questions. Record the expected source page for each question.")]
    story += [table(["Metric", "Definition", "Why it matters"], [
        ["Retrieval Recall@5", "Correct source appears in top 5 retrieved chunks.", "Measures retrieval quality."],
        ["Citation precision", "Cited passage truly supports answer.", "Measures trustworthiness."],
        ["Faithfulness", "Answer claims are supported by evidence.", "Measures hallucination reduction."],
        ["Abstention accuracy", "Unsupported questions are correctly refused.", "Measures safety behaviour."],
        ["Latency", "Time required to return an answer.", "Measures user experience."],
    ], [1.55 * inch, 3.1 * inch, 2.4 * inch])]

    story += section("14. Placement and Viva Explanation")
    story += [callout("I developed DocuTrust AI, a citation-grounded document intelligence platform. It extracts text from PDFs, Word files, text files, and images; indexes the content as page-aware chunks; retrieves relevant evidence for a natural-language question; and returns a cited answer with confidence. It also supports OCR bill formatting, document-scoped search, audit history, analytics, document lifecycle management, and optional LLM synthesis constrained to retrieved evidence.")]
    story += [p("Why it is placement-level", "H2Custom")]
    story += bullets([
        "Combines AIML concepts with backend engineering and product UX.",
        "Solves a real enterprise problem rather than only demonstrating a generic chatbot.",
        "Includes reliability controls: citations, confidence, abstention, audit trail, and analytics.",
        "Has measurable future experimentation paths: embeddings, vector search, reranking, and evaluation metrics.",
        "Demonstrates API design, database design, OCR, deployment readiness, and secure secret handling.",
    ])
    story += [p("Common viva questions", "H2Custom")]
    story += [table(["Question", "Short answer"], [
        ["What is RAG?", "Retrieval-Augmented Generation retrieves source evidence before generating an answer."],
        ["Why citations?", "They let users verify exactly where the answer came from."],
        ["Why abstain?", "A safe system should not invent an answer when evidence is missing."],
        ["Why SQLite?", "It is lightweight and suitable for a local MVP; PostgreSQL is planned for production."],
        ["How is the API key protected?", "It is stored only in backend .env configuration and is never sent to the browser."],
        ["What is the next ML upgrade?", "Embedding-based hybrid retrieval with a vector database and reranker."],
    ], [2.35 * inch, 4.7 * inch])]

    story += [Spacer(1, 16), p("End of report", "CoverKicker")]
    doc.build(story)
    print(OUTPUT)


if __name__ == "__main__":
    build_report()
