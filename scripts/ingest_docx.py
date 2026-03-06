"""
Ingestion pipeline for Luna-Munck textbook Word chapters.

Extracts text from .docx files using textutil, chunks them, and builds
the ChromaDB index. Run once locally; commit data/chromadb/ to the repo.

Usage:
    cd ~/projects/poli319-assistant
    python scripts/ingest_docx.py
"""

import sys
import subprocess
import time
import hashlib
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger

from src.config.settings import settings
from src.data.models import DocumentChunk
from src.embeddings.embedding_service import EmbeddingService
from src.embeddings.vector_store import VectorStore


# ── Textbook chapter definitions ──────────────────────────────────────────────
TEXTBOOK_BASE = Path("/Users/jpl/Dropbox/Luna-Munck Latin America Textbook copy")

CHAPTERS = [
    {
        "path": TEXTBOOK_BASE / "1. Introduction" / "4. Introduction. Democracy and Citizenship Rights in Latin America_Jan 28, 2021.docx",
        "chapter": "Introduction",
        "title": "Introduction: Democracy and Citizenship Rights in Latin America",
        "part": "Introduction",
    },
    {
        "path": TEXTBOOK_BASE / "3. Part 2. Problems of Democracy" / "Chapter 5" / "6. LunaMunck_Ch5_Democracy and the Quality of Democracy_BACEdit_30Jan2021.docx",
        "chapter": "Chapter 5",
        "title": "Chapter 5: Democracy and the Quality of Democracy",
        "part": "Part II: Problems of Democracy in a Democratic Age",
    },
    {
        "path": TEXTBOOK_BASE / "3. Part 2. Problems of Democracy" / "Chapter 6" / "2. Chapter 6_Political Inclusion and Institutional Innovations_Dec 29, 2020.docx",
        "chapter": "Chapter 6",
        "title": "Chapter 6: Political Inclusion and Institutional Innovations",
        "part": "Part II: Problems of Democracy in a Democratic Age",
    },
    {
        "path": TEXTBOOK_BASE / "3. Part 2. Problems of Democracy" / "Chapter 7" / "9. Chapter 7_Political Parties and the Citizen-Politician Link_Dec 29, 2020.docx",
        "chapter": "Chapter 7",
        "title": "Chapter 7: Political Parties and the Citizen-Politician Link",
        "part": "Part II: Problems of Democracy in a Democratic Age",
    },
    {
        "path": TEXTBOOK_BASE / "4. Part 3. Civil Rights as a Problem for Democracy" / "Chapter 8" / "4. Chapter 8. The Protection of Civil Rights_Jan 27, 2021.docx",
        "chapter": "Chapter 8",
        "title": "Chapter 8: The Protection of Civil Rights",
        "part": "Part III: Civil Rights as a Problem for Democracy",
    },
    {
        "path": TEXTBOOK_BASE / "4. Part 3. Civil Rights as a Problem for Democracy" / "Chapter 9" / "2. Chapter 9. Transitional Justice_Jan 27, 2021.docx",
        "chapter": "Chapter 9",
        "title": "Chapter 9: Transitional Justice",
        "part": "Part III: Civil Rights as a Problem for Democracy",
    },
    {
        "path": TEXTBOOK_BASE / "4. Part 3. Civil Rights as a Problem for Democracy" / "Chapter 10" / "2. Chapter 10_High-Level Corruption_Jan 27, 2021.docx",
        "chapter": "Chapter 10",
        "title": "Chapter 10: High-Level Corruption",
        "part": "Part III: Civil Rights as a Problem for Democracy",
    },
    {
        "path": TEXTBOOK_BASE / "4. Part 3. Civil Rights as a Problem for Democracy" / "Chapter 11" / "1. Chapter 11_The New Violence_Jan 30, 2021.docx",
        "chapter": "Chapter 11",
        "title": "Chapter 11: The New Violence — Homicides, Drugs and the State",
        "part": "Part III: Civil Rights as a Problem for Democracy",
    },
    {
        "path": TEXTBOOK_BASE / "5. Part 4. Social Rights as a Problem for Democracy" / "Chapter 12" / "23. Chapter 12. Social Rights in Law and Reality_Jan 31, 2021.docx",
        "chapter": "Chapter 12",
        "title": "Chapter 12: Social Rights in Law and Reality",
        "part": "Part IV: Social Rights as a Problem for Democracy",
    },
    {
        "path": TEXTBOOK_BASE / "5. Part 4. Social Rights as a Problem for Democracy" / "Chapter 13" / "5. Chapter 13. Basic Social Inclusion and Social Policy_Jan 30, 2021.docx",
        "chapter": "Chapter 13",
        "title": "Chapter 13: Basic Social Inclusion and Social Policy",
        "part": "Part IV: Social Rights as a Problem for Democracy",
    },
    {
        "path": TEXTBOOK_BASE / "5. Part 4. Social Rights as a Problem for Democracy" / "Chapter 14" / "7. Chapter 14. Sustainable Development and Neoextractivism_Jan 31, 2021.docx",
        "chapter": "Chapter 14",
        "title": "Chapter 14: Sustainable Development and Neoextractivism",
        "part": "Part IV: Social Rights as a Problem for Democracy",
    },
    {
        "path": TEXTBOOK_BASE / "5. Part 4. Social Rights as a Problem for Democracy" / "Chapter 15" / "9. Chapter 15. Unequal Democracies_Jan 30, 2021.docx",
        "chapter": "Chapter 15",
        "title": "Chapter 15: Unequal Democracies",
        "part": "Part IV: Social Rights as a Problem for Democracy",
    },
    {
        "path": TEXTBOOK_BASE / "6. Part 5. Conclusions" / "Chapter 16" / "4. Chapter 16. The New Latin American Politics_Jan 19, 2021.docx",
        "chapter": "Chapter 16",
        "title": "Chapter 16: The New Latin American Politics",
        "part": "Part V: Conclusions",
    },
    {
        "path": TEXTBOOK_BASE / "7. Appendix" / "Appendix II. Glossary_Jan 29, 2021.docx",
        "chapter": "Appendix II",
        "title": "Appendix II: Glossary of Key Terms",
        "part": "Appendix",
    },
]

# Assignment instructions and trusted sources
EXTRA_DOCS = [
    {
        "path": project_root / "data" / "sources" / "assignment.pdf",
        "chapter": "Assignment",
        "title": "POLI 319 Textbook Addendum — Assignment Instructions & Rubric",
        "part": "Course Materials",
        "is_pdf": True,
    },
    {
        "path": project_root / "data" / "sources" / "trusted_sources.md",
        "chapter": "Trusted Sources",
        "title": "Trusted Data Sources for POLI 319",
        "part": "Course Materials",
        "is_markdown": True,
    },
]

AUTHORS = ["Luna, Juan Pablo", "Munck, Gerardo"]
YEAR = 2022
PUBLICATION = "Cambridge University Press"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


def doc_id(key: str) -> int:
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16) % 100000


def extract_docx(path: Path) -> str:
    """Extract plain text from a .docx using macOS textutil."""
    result = subprocess.run(
        ["textutil", "-convert", "txt", "-stdout", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"textutil failed on {path.name}: {result.stderr}")
    return result.stdout


def extract_pdf(path: Path) -> str:
    """Extract text from a PDF using PyMuPDF."""
    import fitz
    doc = fitz.open(str(path))
    pages = [page.get_text() for page in doc]
    return "\n\n".join(p for p in pages if p.strip())


def extract_markdown(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks by word boundary."""
    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        if len(chunk.strip()) > 100:
            chunks.append(chunk.strip())
        start += chunk_size - overlap

    return chunks


def process_chapter(ch: dict) -> list[DocumentChunk]:
    path = Path(ch["path"])
    if not path.exists():
        logger.warning(f"File not found, skipping: {path}")
        return []

    logger.info(f"Extracting: {path.name}")
    try:
        if ch.get("is_pdf"):
            text = extract_pdf(path)
        elif ch.get("is_markdown"):
            text = extract_markdown(path)
        else:
            text = extract_docx(path)
    except Exception as e:
        logger.error(f"Extraction failed for {path.name}: {e}")
        return []

    text = text.strip()
    if len(text) < 200:
        logger.warning(f"Very short text ({len(text)} chars) from {path.name} — skipping")
        return []

    logger.info(f"  Extracted {len(text):,} chars from {path.name}")
    raw_chunks = chunk_text(text)
    logger.info(f"  Created {len(raw_chunks)} chunks")

    item_id = doc_id(ch["chapter"])
    chunks = []
    for i, chunk_text_str in enumerate(raw_chunks):
        chunk = DocumentChunk(
            chunk_id=f"{ch['chapter'].replace(' ', '_').lower()}_chunk_{i}",
            text=chunk_text_str,
            item_id=item_id,
            zotero_key=ch["chapter"].replace(" ", "_").lower(),
            title=ch["title"],
            authors=AUTHORS if not ch.get("is_pdf") and not ch.get("is_markdown") else ["Luna, Juan Pablo"],
            year=YEAR if not ch.get("is_pdf") and not ch.get("is_markdown") else 2026,
            collections=[ch["part"]],
            tags=[],
            section=ch.get("part", ""),
            chunk_index=i,
            total_chunks=len(raw_chunks),
            pdf_path=str(path),
        )
        chunks.append(chunk)

    return chunks


def main():
    start = time.time()
    logger.info("=" * 60)
    logger.info("POLI 319 — Textbook Docx Ingestion Pipeline")
    logger.info("=" * 60)

    settings.chromadb_path.mkdir(parents=True, exist_ok=True)

    embedding_service = EmbeddingService()
    vector_store = VectorStore(persist_directory=settings.chromadb_path)

    # Reset existing collection
    logger.info("Resetting ChromaDB collection...")
    vector_store.reset()

    all_chapters = CHAPTERS + EXTRA_DOCS
    all_chunks = []

    for ch in all_chapters:
        chunks = process_chapter(ch)
        all_chunks.extend(chunks)

    if not all_chunks:
        logger.error("No chunks extracted. Check file paths above.")
        sys.exit(1)

    logger.info(f"\nTotal chunks to embed: {len(all_chunks):,}")
    logger.info("Generating embeddings (this will take a few minutes)...")

    texts = [c.text for c in all_chunks]
    embeddings = embedding_service.embed_batch(texts)

    logger.info("Adding to ChromaDB...")
    vector_store.add_chunks(all_chunks, embeddings.tolist())

    elapsed = time.time() - start
    count = vector_store.count()
    logger.info("=" * 60)
    logger.info(f"Done in {elapsed:.1f}s")
    logger.info(f"Total chunks indexed: {count:,}")
    logger.info(f"ChromaDB at: {settings.chromadb_path}")
    logger.info("Next: git add data/chromadb/ && git commit && git push")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
