"""Unit tests for harness/semantic.py.

These require a live local Ollama instance with nomic-embed-text pulled.
Skip gracefully rather than fail if Ollama isn't reachable, so the rest of
the suite still runs clean on a machine without it configured.
"""
import httpx
import pytest
from contracts import Label, Passage, Tier
from harness.semantic import cosine_similarity, semantic_score_passage

def _ollama_available() -> bool:
    try:
        httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        return True
    except Exception:
        return False

pytestmark = pytest.mark.skipif(not _ollama_available(), reason="Ollama not reachable")

def test_cosine_similarity_identical_vectors():
    v = [1.0, 2.0, 3.0]
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-6

def test_semantic_score_relevant_passage_scores_above_zero():
    passage = Passage(doc_id="d1", page=1, text="Fire safety evacuation procedure for refinery staff.", label=Label(tier=Tier.INTERNAL))
    score = semantic_score_passage("what is the evacuation procedure", passage)
    assert score > 0.0

def test_semantic_score_greeting_scores_zero():
    passage = Passage(doc_id="d1", page=1, text="Fire safety evacuation procedure for refinery staff.", label=Label(tier=Tier.INTERNAL))
    score = semantic_score_passage("hello", passage)
    assert score == 0.0