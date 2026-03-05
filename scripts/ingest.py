"""
Offline ingestion pipeline for POLI 319 Research Assistant.

Run once (locally) to build the ChromaDB index from source documents.
The built index is committed to the repo and loaded by the live app.

Usage:
    cd ~/projects/poli319-assistant
    python scripts/ingest.py

Source documents must be in data/sources/:
    data/sources/textbook.pdf
    data/sources/assignment.pdf
    data/sources/trusted_sources.md
"""

import sys
import time
import hashlib
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger

from src.config.settings import settings
from src.data.models import DocumentChunk, ZoteroItem
from src.data.pdf_extractor import PDFExtractor
from src.data.chunker import DocumentChunker
from src.embeddings.embedding_service import EmbeddingService
from src.embeddings.vector_store import VectorStore


# ── Document definitions ──────────────────────────────────────────────────────
DOCUMENTS = [
    {
        "path": "data/sources/textbook.pdf",
        "key": "textbook",
        "title": "Latin American Politics and Society: A Comparative and Historical Analysis",
        "authors": ["Munck, Gerardo", "Luna, Juan Pablo"],
        "year": 2022,
        "source_type": "textbook",
        "publication": "Cambridge University Press",
    },
    {
        "path": "data/sources/assignment.pdf",
        "key": "assignment",
        "title": "POLI 319 Textbook Addendum — Assignment Instructions & Rubric",
        "authors": ["Luna, Juan Pablo"],
        "year": 2026,
        "source_type": "assignment",
        "publication": "McGill University",
    },
]

MARKDOWN_DOCS = [
    {
        "path": "data/sources/trusted_sources.md",
        "key": "trusted_sources",
        "title": "Trusted Data Sources for POLI 319",
        "authors": ["Luna, Juan Pablo"],
        "year": 2026,
        "source_type": "trusted_sources",
        "publication": "McGill University",
    },
]
# ─────────────────────────────────────────────────────────────────────────────


def file_id(key: str) -> int:
    """Generate a stable numeric ID from a document key."""
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16) % 100000


def make_zotero_item(doc_def: dict, path: Path) -> ZoteroItem:
    """Create a ZoteroItem from a document definition (reuses chunker's interface)."""
    return ZoteroItem(
        item_id=file_id(doc_def["key"]),
        zotero_key=doc_def["key"],
        title=doc_def["title"],
        authors=doc_def["authors"],
        year=doc_def["year"],
        publication=doc_def.get("publication"),
        collections=[doc_def["source_type"]],
        pdf_path=str(path),
    )


def chunk_markdown_by_sections(text: str, max_chars: int = 3000) -> list[str]:
    """Split markdown into chunks at ## section boundaries."""
    chunks = []
    current = []
    current_len = 0

    for line in text.splitlines(keepends=True):
        if line.startswith("## ") and current_len > 200:
            chunks.append("".join(current).strip())
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += len(line)
            if current_len > max_chars:
                chunks.append("".join(current).strip())
                current = []
                current_len = 0

    if current:
        chunks.append("".join(current).strip())

    return [c for c in chunks if len(c) > 50]


def process_pdf(doc_def: dict, chunker: DocumentChunker) -> list[DocumentChunk]:
    """Extract and chunk a PDF document."""
    path = project_root / doc_def["path"]
    if not path.exists():
        logger.error(f"File not found: {path}")
        return []

    logger.info(f"Processing PDF: {path.name}")
    extractor = PDFExtractor()
    pdf_doc = extractor.extract_text(str(path))

    if not pdf_doc.success:
        logger.error(f"Extraction failed for {path.name}: {pdf_doc.error_message}")
        return []

    logger.info(f"Extracted {pdf_doc.total_pages} pages, {pdf_doc.total_chars:,} chars")

    # Use the chunker's chunk_document() which handles section detection
    item = make_zotero_item(doc_def, path)
    chunks = chunker.chunk_document(pdf_doc, item)

    logger.info(f"Created {len(chunks)} chunks from {path.name}")
    return chunks


def process_markdown(doc_def: dict) -> list[DocumentChunk]:
    """Chunk a markdown file by section headers."""
    path = project_root / doc_def["path"]
    if not path.exists():
        logger.error(f"File not found: {path}")
        return []

    logger.info(f"Processing markdown: {path.name}")
    text = path.read_text(encoding="utf-8")
    raw_chunks = chunk_markdown_by_sections(text)

    doc_id = file_id(doc_def["key"])
    chunks = []
    for i, chunk_text in enumerate(raw_chunks):
        first_line = chunk_text.splitlines()[0].lstrip("#").strip()
        chunk = DocumentChunk(
            chunk_id=f"{doc_def['key']}_chunk_{i}",
            text=chunk_text,
            item_id=doc_id,
            zotero_key=doc_def["key"],
            title=doc_def["title"],
            authors=doc_def["authors"],
            year=doc_def["year"],
            collections=[doc_def["source_type"]],
            tags=[],
            section=first_line,
            chunk_index=i,
            total_chunks=len(raw_chunks),
            pdf_path=str(path),
        )
        chunks.append(chunk)

    logger.info(f"Created {len(chunks)} chunks from {path.name}")
    return chunks


def main():
    start = time.time()
    logger.info("=" * 60)
    logger.info("POLI 319 Research Assistant — Ingestion Pipeline")
    logger.info("=" * 60)

    # Ensure chromadb output dir exists
    settings.chromadb_path.mkdir(parents=True, exist_ok=True)

    chunker = DocumentChunker()
    embedding_service = EmbeddingService()
    vector_store = VectorStore(persist_directory=settings.chromadb_path)

    all_chunks = []

    # Process PDFs
    for doc_def in DOCUMENTS:
        chunks = process_pdf(doc_def, chunker)
        all_chunks.extend(chunks)

    # Process markdown
    for doc_def in MARKDOWN_DOCS:
        chunks = process_markdown(doc_def)
        all_chunks.extend(chunks)

    if not all_chunks:
        logger.error("No chunks to index. Check that source files exist in data/sources/")
        sys.exit(1)

    logger.info(f"Total chunks to embed: {len(all_chunks):,}")

    # Generate embeddings in batches
    logger.info("Generating embeddings (this may take several minutes for the textbook)...")
    texts = [c.text for c in all_chunks]
    embeddings = embedding_service.embed_batch(texts)
    logger.info(f"Generated {len(embeddings):,} embeddings")

    # Add to vector store
    logger.info("Adding to ChromaDB...")
    vector_store.add_chunks(all_chunks, embeddings)

    elapsed = time.time() - start
    count = vector_store.count()
    logger.info("=" * 60)
    logger.info(f"Ingestion complete in {elapsed:.1f}s")
    logger.info(f"Total chunks indexed: {count:,}")
    logger.info(f"ChromaDB saved to: {settings.chromadb_path}")
    logger.info("Next: git add data/chromadb/ && git commit -m 'Add pre-built vector index'")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
