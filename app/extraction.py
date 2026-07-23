from io import BytesIO
from pathlib import Path
import re
import os

from docx import Document
from pypdf import PdfReader

from .models import ExtractedPage


class ExtractionError(ValueError):
    pass


def sanitize_filename(filename: str) -> str:
    name = Path(filename or "upload").name
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:120]


def extract_pages(filename: str, data: bytes) -> tuple[list[ExtractedPage], str]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(BytesIO(data))
        pages = [ExtractedPage(index + 1, page.extract_text() or "") for index, page in enumerate(reader.pages)]
        return _nonempty(pages), "native_pdf"
    if suffix == ".docx":
        document = Document(BytesIO(data))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
        return _nonempty([ExtractedPage(1, text)]), "native_docx"
    if suffix in {".txt", ".md"}:
        return _nonempty([ExtractedPage(1, data.decode("utf-8", errors="replace"))]), "plain_text"
    if suffix in {".png", ".jpg", ".jpeg", ".tiff", ".bmp"}:
        try:
            from PIL import Image
            import pytesseract
        except ImportError as error:
            raise ExtractionError("Image OCR dependencies are not installed. Run: pip install -r requirements.txt") from error
        command = os.getenv("TESSERACT_CMD")
        if command:
            pytesseract.pytesseract.tesseract_cmd = command
        try:
            text = pytesseract.image_to_string(Image.open(BytesIO(data)))
        except pytesseract.TesseractNotFoundError as error:
            raise ExtractionError("OCR requires the Tesseract binary. Install it and set TESSERACT_CMD if needed.") from error
        return _nonempty([ExtractedPage(1, text)]), "tesseract_ocr"
    raise ExtractionError("Supported file types are PDF, DOCX, TXT, MD, PNG, JPG, JPEG, TIFF, and BMP.")


def _nonempty(pages: list[ExtractedPage]) -> list[ExtractedPage]:
    usable = [page for page in pages if page.text.strip()]
    if not usable:
        raise ExtractionError("No machine-readable text was found. Use an OCR-enabled deployment for scanned files.")
    return usable
