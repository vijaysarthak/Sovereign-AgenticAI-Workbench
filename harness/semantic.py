"""
Semantic (embeddings-based) passage scoring — an additive alternative to the
lexical BM25-style scorer already in harness/retrieve.py.

NON-NEGOTIABLE DESIGN PRINCIPLE (unchanged from retrieve.py):
This module has zero knowledge of Principal, Label, or the two-axis gate.
retrieve() still scores everything BEFORE gating; only the scoring function
itself is swappable. This is exactly the "drop-in" embeddings upgrade path
described in this project's own README.

Uses a local Ollama embeddings model -- no document content leaves the
machine, same sovereignty guarantee as the drafting agent.
"""

from __future__ import annotations

import math
import os

import httpx
from contracts import Passage

OLLAMA_URL = os.getenv("OLLAMA_API_BASE", "http://localhost:11434").rstrip("/") + "/api/embeddings"
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

# Cosine similarity between unrelated text is rarely exactly 0 (unlike the
# lexical scorer's clean "no token overlap = 0.0"). A bare greeting like
# "hello" still shows nonzero similarity against every passage. Without a
# floor, the early-abstention safeguard in retrieve() (see its own comments)
# would never fire, and every query would return a "relevant-looking" but
# actually unrelated passage instead of correctly abstaining.
# NOTE: this default is a starting point, not empirically tuned yet --
# verify against real queries and adjust if abstention behaves too
# eagerly/rarely.
RELEVANCE_FLOOR = 0.55

_embedding_cache: dict[str, list[float]] = {}


def embed_text(text: str) -> list[float]:
    """Embeds text via a local Ollama model. Cached by exact text so a
    passage already embedded once isn't re-sent to Ollama on every query."""
    if text in _embedding_cache:
        return _embedding_cache[text]
    resp = httpx.post(OLLAMA_URL, json={"model": EMBED_MODEL, "prompt": text}, timeout=90.0)
    resp.raise_for_status()
    vector = resp.json()["embedding"]
    _embedding_cache[text] = vector
    return vector


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def semantic_score_passage(query: str, passage: Passage) -> float:
    """Returns a relevance score using the SAME convention as
    harness.retrieve.score_passage: 0.0 means 'not relevant enough to
    consider', anything above 0 is a real candidate. Values below
    RELEVANCE_FLOOR are clamped to 0.0 so retrieve()'s early-abstention
    logic keeps working unchanged."""
    similarity = cosine_similarity(embed_text(query), embed_text(passage.text))
    return similarity if similarity >= RELEVANCE_FLOOR else 0.0