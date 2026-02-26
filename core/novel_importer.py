"""
Novel/story text import utilities.
Handles text extraction from .txt and .docx files, and text chunking
for AI-driven analysis of long-form content.
"""

import os
import re
from typing import List, Tuple


MAX_WORDS_PER_CHUNK = 3000
SINGLE_PASS_THRESHOLD = 5000
MIN_WORDS = 100
LARGE_TEXT_WARNING_THRESHOLD = 200000

LENGTH_CHARACTER_CAPS = {
    "micro": 2,
    "short": 3,
    "medium": 5,
    "long": 8,
}

LENGTH_DURATION_LABELS = {
    "micro": "15-30 seconds",
    "short": "30-60 seconds",
    "medium": "1-3 minutes",
    "long": "3-5 minutes",
}


def extract_text_from_file(filepath: str) -> str:
    """Extract plain text from a .txt or .docx file.

    Raises ValueError for unsupported formats or read errors.
    """
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".txt":
        for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
            try:
                with open(filepath, "r", encoding=encoding) as f:
                    return f.read()
            except (UnicodeDecodeError, UnicodeError):
                continue
        raise ValueError(f"Could not decode text file with any supported encoding: {filepath}")

    if ext == ".docx":
        try:
            from docx import Document
        except ImportError:
            raise ValueError(
                "python-docx is required for .docx import. "
                "Install it with: pip install python-docx"
            )
        try:
            doc = Document(filepath)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs)
        except Exception as e:
            raise ValueError(f"Failed to parse .docx file: {e}")

    raise ValueError(f"Unsupported file format: {ext}. Please use .txt or .docx files.")


def word_count(text: str) -> int:
    """Return approximate word count."""
    return len(text.split())


def chunk_text(text: str) -> List[str]:
    """Split text into processable chunks, preferring paragraph boundaries.

    Short texts (under SINGLE_PASS_THRESHOLD words) are returned as a single chunk.
    Longer texts are split at paragraph boundaries (double newlines) aiming for
    roughly MAX_WORDS_PER_CHUNK words per chunk.
    """
    words = text.split()
    if len(words) <= SINGLE_PASS_THRESHOLD:
        return [text]

    paragraphs = re.split(r"\n\s*\n", text)
    chunks: List[str] = []
    current_parts: List[str] = []
    current_words = 0

    for para in paragraphs:
        para_words = len(para.split())
        if current_words + para_words > MAX_WORDS_PER_CHUNK and current_parts:
            chunks.append("\n\n".join(current_parts))
            current_parts = []
            current_words = 0
        current_parts.append(para)
        current_words += para_words

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return chunks if chunks else [text]


def validate_text(text: str) -> Tuple[bool, str]:
    """Validate imported text and return (is_valid, message).

    Returns warnings for edge cases (too short, very long) and errors
    for empty content.
    """
    if not text or not text.strip():
        return False, "The file appears to be empty."

    wc = word_count(text)

    if wc < MIN_WORDS:
        return False, (
            f"The text is only {wc} words. For very short content, "
            "consider using the Story Creation Wizard instead."
        )

    if wc > LARGE_TEXT_WARNING_THRESHOLD:
        return True, (
            f"This text is approximately {wc:,} words. "
            "Processing will require many AI calls and may take several minutes. "
            "Consider trimming to the most important sections for better results."
        )

    return True, ""


def estimate_processing_time(text: str) -> str:
    """Estimate processing time based on text length."""
    wc = word_count(text)
    chunks = len(chunk_text(text))

    if chunks <= 1:
        return "~1-2 minutes"
    elif chunks <= 5:
        return "~2-4 minutes"
    elif chunks <= 15:
        return "~4-8 minutes"
    else:
        return f"~{chunks // 2}-{chunks} minutes (large text)"
