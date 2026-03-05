"""Data models for the POLI 319 Research Assistant."""

import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, field_validator


# ── Kept from literature-expert-agent for compatibility with copied RAG modules ──

class ZoteroItem(BaseModel):
    """Source document metadata (reused as CourseSource internally)."""

    item_id: int = Field(..., description="Numeric document ID")
    zotero_key: str = Field(..., description="Document key (e.g. 'textbook', 'assignment')")
    title: str = Field(..., description="Document title")
    authors: List[str] = Field(default_factory=list, description="Authors")
    year: Optional[int] = Field(None, description="Publication year")
    abstract: Optional[str] = Field(None, description="Abstract or description")
    publication: Optional[str] = Field(None, description="Publication/Journal name")
    doi: Optional[str] = Field(None, description="DOI")
    url: Optional[str] = Field(None, description="URL")
    collections: List[str] = Field(default_factory=list, description="Source types (e.g. textbook, assignment)")
    tags: List[str] = Field(default_factory=list, description="Tags")
    pdf_path: Optional[str] = Field(None, description="Path to source file")
    date_added: Optional[datetime] = Field(None, description="Date added")
    date_modified: Optional[datetime] = Field(None, description="Date last modified")

    @field_validator("year", mode="before")
    @classmethod
    def parse_year(cls, v):
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            import re
            match = re.search(r"\b(19|20)\d{2}\b", v)
            if match:
                return int(match.group())
        return None

    def get_citation_text(self) -> str:
        author_text = ", ".join(self.authors[:2])
        if len(self.authors) > 2:
            author_text += " et al."
        year_text = str(self.year) if self.year else "n.d."
        return f"{author_text} ({year_text})"

    def get_full_citation(self) -> str:
        parts = []
        if self.authors:
            parts.append(", ".join(self.authors))
        year_text = f"({self.year})" if self.year else "(n.d.)"
        parts.append(year_text)
        parts.append(f'"{self.title}"')
        if self.publication:
            parts.append(f"*{self.publication}*")
        if self.doi:
            parts.append(f"DOI: {self.doi}")
        elif self.url:
            parts.append(f"URL: {self.url}")
        return ". ".join(parts) + "."


class PDFPage(BaseModel):
    page_number: int
    text: str
    char_count: int


class PDFDocument(BaseModel):
    pdf_path: str
    full_text: str
    pages: List[PDFPage]
    total_pages: int
    total_chars: int
    extraction_date: datetime = Field(default_factory=datetime.now)
    success: bool = True
    error_message: Optional[str] = None


class DocumentChunk(BaseModel):
    """A chunk of text from a course document."""

    chunk_id: str
    text: str
    item_id: int
    zotero_key: str
    title: str
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    collections: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    section: Optional[str] = None
    chunk_index: int
    total_chunks: int
    pdf_path: Optional[str] = None
    page_numbers: Optional[List[int]] = None

    def get_metadata_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "zotero_key": self.zotero_key,
            "title": self.title,
            "authors": ";".join(self.authors),
            "year": self.year or 0,
            "collections": ";".join(self.collections),
            "tags": ";".join(self.tags),
            "section": self.section or "",
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "pdf_path": self.pdf_path or "",
        }


class RetrievalResult(BaseModel):
    chunk: DocumentChunk
    distance: float
    similarity: float

    @classmethod
    def from_chroma_result(
        cls, document: str, metadata: Dict[str, Any], distance: float
    ) -> "RetrievalResult":
        authors = metadata["authors"].split(";") if metadata["authors"] else []
        collections = metadata["collections"].split(";") if metadata["collections"] else []
        tags = metadata["tags"].split(";") if metadata["tags"] else []

        chunk = DocumentChunk(
            chunk_id=f"doc_{metadata['item_id']}_chunk_{metadata['chunk_index']}",
            text=document,
            item_id=metadata["item_id"],
            zotero_key=metadata["zotero_key"],
            title=metadata["title"],
            authors=authors,
            year=metadata["year"] if metadata["year"] > 0 else None,
            collections=collections,
            tags=tags,
            section=metadata.get("section"),
            chunk_index=metadata["chunk_index"],
            total_chunks=metadata["total_chunks"],
            pdf_path=metadata.get("pdf_path"),
        )
        similarity = 1 - distance if distance <= 1 else 0
        return cls(chunk=chunk, distance=distance, similarity=similarity)


class Answer(BaseModel):
    question: str
    answer: str
    sources: List[ZoteroItem] = Field(default_factory=list)
    chunks_used: int
    generation_time: float


class ProcessingStats(BaseModel):
    total_items: int
    pdfs_processed: int
    pdfs_failed: int
    total_chunks: int
    total_embeddings: int
    processing_time: float
    failed_items: List[Dict[str, str]] = Field(default_factory=list)


# ── New classes for POLI 319 session logging ──

class ChatMessage(BaseModel):
    """A single message in a student chat session."""
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    role: str  # "user" or "assistant"
    content: str
    retrieved_sources: List[str] = Field(default_factory=list)  # source titles


class Session(BaseModel):
    """A student chat session."""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    student_name: str
    student_id: str
    group_name: str
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    n_messages: int = 0
    disclosure_draft: Optional[str] = None
