"""Deterministic citation verification engine.

NON-NEGOTIABLE DESIGN PRINCIPLES:
1. Pure Python string matching, zero model calls.
2. Every quote must appear verbatim in the exact passage it claims,
   matched by BOTH doc_id AND page (never across the whole corpus).
3. Quotes must be 20-300 characters and contain at least 5 words.
4. check() returns None when clean, or a single precise feedback string naming
   the first problem. One clear problem is more fixable by an agent than five.
5. NEVER derive citations by regexing or scraping the model's prose.
"""

from __future__ import annotations

import re
from typing import Optional, Sequence
from contracts import Citation, Passage

# PDF text extraction introduces formatting noise that a model naturally
# "cleans up" when composing a readable quote, even while copying the actual
# WORDS faithfully -- e.g.:
#   - Amendment/footnote markers this corpus's source documents use, like
#     "72[to promptly act...]" (digits+bracket around inserted text).
#   - Mid-word line-wrap splits from page layout, like "work f unctions"
#     instead of "work functions".
#   - A section header on its own line immediately followed by its content,
#     like "First Aid \nPour water...", which a model naturally renders as
#     "First Aid: Pour water..." -- a reasonable transcription, but a colon
#     that was never in the source.
#   - Curly vs. straight quotes, en/em dashes, and other punctuation
#     variants a model may normalize when quoting.
# Rather than special-case each punctuation type discovered one at a time,
# the fallback comparison strips footnote markers, then reduces both sides to
# a bare lowercase alphanumeric sequence -- no whitespace, no punctuation, no
# case. This still can't let fabricated text through: the actual sequence of
# WORDS must still appear in the real passage in the same order: only
# formatting/punctuation cosmetics are ignored, not content. This does not
# replace the exact/whitespace-normalized checks below -- it only kicks in as
# a second-chance comparison when those fail.


def _lenient_normalize(text: str) -> str:
    """Strip footnote-bracket markers, then reduce to a bare lowercase
    alphanumeric sequence (no whitespace, no punctuation, no case) for a
    fallback compare. See module-level comment above for why."""
    without_markers = re.sub(r"\d*\[", "", text).replace("]", "")
    return re.sub(r"[^a-z0-9]", "", without_markers.lower())


def check(
    citations: Sequence[Citation],
    passages: Sequence[Passage],
) -> Optional[str]:
    """Verify that every citation quote appears verbatim in its claimed passage.

    An answer with zero citations is NEVER considered verified, even though there
    is nothing to fail structurally: with readable passages available, a claimed
    answer must be grounded in at least one verbatim citation. Silently accepting
    an empty citation list let malformed/unparseable model output (e.g. a raw
    non-JSON response returned as the 'answer' after JSON parsing failed) get
    recorded as a verified "answered" response, which is exactly what this
    citation-verification gate exists to prevent.

    Returns:
        None if all citations are verified.
        A descriptive string explaining the first failure encountered.
    """
    if not citations:
        return (
            "No citations were provided. Every answer must be grounded in at least one "
            "verbatim citation from the provided passages. Respond with valid JSON containing "
            "an 'answer' and a non-empty 'citations' array; if the passages genuinely do not "
            "address the question, say so plainly in 'answer' but still cite the passage(s) you "
            "checked."
        )

    # Index passages by (doc_id, page)
    passage_map: dict[tuple[str, int], str] = {
        (p.doc_id, p.page): p.text for p in passages
    }

    for idx, cit in enumerate(citations):
        # 1. Structural requirements
        quote = cit.quote
        if len(quote) < 20:
            return f"Citation {idx + 1} quote is too short ({len(quote)} chars, minimum 20 required)."

        if len(quote) > 300:
            return f"Citation {idx + 1} quote exceeds maximum length ({len(quote)} chars, maximum 300 allowed)."

        words = quote.strip().split()
        if len(words) < 5:
            return f"Citation {idx + 1} quote has only {len(words)} words; minimum 5 words required."

        # 2. Exact passage resolution
        key = (cit.doc_id, cit.page)
        if key not in passage_map:
            # Sharpen the feedback when this looks like the classic mistake: the
            # model copied a clause/item number printed inside the passage body
            # (e.g. "25. Cause of leakage...") as if it were the page number.
            # We do NOT auto-correct or accept this citation either way — wrong
            # page is always a hard rejection — but naming the real page here
            # makes the next retry far more likely to self-correct instead of
            # repeating the same mistake.
            actual_pages = sorted(p for (d, p) in passage_map if d == cit.doc_id)
            if actual_pages:
                return (
                    f"Citation {idx + 1} claims doc_id='{cit.doc_id}' page {cit.page}, but that page was not "
                    f"provided. This document's actual in-context pages are {actual_pages}. If you copied a "
                    f"number like 'page {cit.page}' from a clause/item/schedule number printed INSIDE the "
                    f"passage text (e.g. '{cit.page}. Cause of leakage...'), that is NOT a page number — re-check "
                    f"which '--- Document: ... | Page: N ---' header the quote actually appeared under and use "
                    f"that exact number."
                )
            return (
                f"Citation {idx + 1} claims doc_id='{cit.doc_id}' page {cit.page}, "
                f"but no passage for that document and page was provided in the prompt context."
            )

        # 3. Verbatim exact substring match within that specific page
        passage_text = passage_map[key]
        normalized_quote = " ".join(quote.strip().split())
        normalized_passage = " ".join(passage_text.strip().split())
        if (
            quote not in passage_text
            and normalized_quote not in normalized_passage
            and _lenient_normalize(quote) not in _lenient_normalize(passage_text)
        ):
            snippet = quote[:50] + ("..." if len(quote) > 50 else "")
            return (
                f"Citation {idx + 1} quote '{snippet}' was NOT found verbatim in "
                f"doc_id='{cit.doc_id}' page {cit.page}."
            )

    return None
