"""Configuration settings for the POLI 319 Research Assistant."""

import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# On Hugging Face Spaces, persistent storage is mounted at /data/
# Locally, use ./data/
_IS_HF = os.path.exists("/data")
_DATA_ROOT = Path("/data") if _IS_HF else Path("./data")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",
    )

    # API — defaults to "" so settings loads without crashing on Streamlit Cloud;
    # actual key is read from st.secrets at call time in engine.py
    anthropic_api_key: str = Field(default="", description="Anthropic API key")

    # Instructor dashboard password
    instructor_password: str = Field(
        default="changeme",
        description="Password for instructor dashboard",
    )

    # Student access code
    course_code: str = Field(
        default="2426",
        description="Access code shared with enrolled students via MyCourses",
    )

    # Model settings
    embedding_model: str = Field(default="all-MiniLM-L6-v2")
    llm_model: str = Field(default="claude-3-5-sonnet-20241022")

    # Paths
    chromadb_path: Path = Field(default=Path("./data/chromadb"))
    db_path: Path = Field(default=_DATA_ROOT / "logs.db")
    logs_path: Path = Field(default=_DATA_ROOT / "logs")

    # Retrieval
    chunk_size: int = Field(default=800)
    chunk_overlap: int = Field(default=150)
    batch_size: int = Field(default=32)
    top_k: int = Field(default=8)
    similarity_threshold: float = Field(default=0.5)

    # Generation
    max_tokens: int = Field(default=2000)
    temperature: float = Field(default=0.5)

    def get_collections_list(self):
        return None  # No collection filtering; all documents in one collection

    def ensure_directories(self) -> None:
        self.chromadb_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)


settings = Settings()
