from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str
    section: Optional[str] = None


@dataclass(frozen=True)
class Evidence:
    chunk_id: str
    document_id: str
    document_name: str
    page: int
    text: str
    score: float
    section: Optional[str] = None

