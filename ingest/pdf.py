"""Page-level PDF extraction and corpus ingestion.

NON-NEGOTIABLE DESIGN PRINCIPLES:
1. One Passage per page: Citations are page-scoped, making 'cited from page 14'
   deterministic and checkable.
2. Silent empty strings are banned: If every page of a PDF is blank, raise a loud
   ScannedPdfError naming the file. Silent empty strings cause models to hallucinate
   answers about documents they never read.
3. Graceful corpus loading: If the documents directory is empty or missing,
   log an informative message rather than failing with a stack trace.
"""

from __future__ import annotations

import json
from pathlib import Path
from pydoc import doc
from typing import Optional, Sequence
import pypdf # type: ignore
from contracts import Compartment, Label, Passage, Tier


class ScannedPdfError(Exception):
    """Raised when a PDF contains no extractable text layer across all pages."""

    def __init__(self, filename: str):
        super().__init__(
            f"SCANNED PDF ERROR: File '{filename}' contains no extractable text layer. "
            "SEVERANCE requires embedded text to prevent silent hallucination. "
            "Please submit a digital PDF or run OCR before ingesting."
        )
        self.filename = filename

def _ocr_fallback(pdf_path) -> list[str]:
    """Rasterizes each page to an image and runs local OCR (PaddleOCR) on it.
    Only called when the PDF has NO embedded text layer at all -- this is
    strictly additive: a digitally-authored PDF never touches this path."""
    import fitz
    from paddleocr import PaddleOCR

    ocr_engine = PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,
    )

    doc = fitz.open(str(pdf_path))
    page_texts = []
    for page in doc:
        pix = page.get_pixmap(dpi=200)
        import tempfile
        img_path = str(Path(tempfile.gettempdir()) / f"_ocr_page_{page.number}.png")
        pix.save(img_path)
        result = ocr_engine.predict(img_path)
        texts = []
        for res in result:
            texts.extend(res.get("rec_texts", []))
        page_texts.append("\n".join(texts))
    doc.close()
    return page_texts

def pdf_to_page_texts(pdf_path: str | Path, enable_ocr: bool = False) -> list[str]:
    """Extract raw text from each page of a PDF file.

    enable_ocr: when True, and the PDF has no embedded text layer at all,
    falls back to local OCR instead of raising ScannedPdfError immediately.
    Defaults to False so existing behavior (loud failure on scanned PDFs)
    is completely unchanged unless explicitly opted into.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found at: {path}")

    reader = pypdf.PdfReader(str(path))
    num_pages = len(reader.pages)
    if num_pages == 0:
        raise ValueError(f"PDF '{path.name}' has 0 pages.")

    pages_text: list[str] = []
    has_any_text = False

    for page_idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        cleaned = text.strip()
        if cleaned:
            has_any_text = True
        pages_text.append(cleaned)

    if not has_any_text:
        if enable_ocr:
            ocr_pages = _ocr_fallback(path)
            if any(p.strip() for p in ocr_pages):
                print(f"[INGEST] '{path.name}' had no text layer — recovered via local OCR.")
                return ocr_pages
        raise ScannedPdfError(path.name)

    return pages_text


def pdf_to_passages(pdf_path, doc_id, label, title="", enable_ocr: bool = False):
    page_texts = pdf_to_page_texts(pdf_path, enable_ocr=enable_ocr)
    passages: list[Passage] = []

    for page_num, text in enumerate(page_texts, start=1):
        if not text:
            continue  # Skip blank pages in mixed documents
        passages.append(
            Passage(
                doc_id=doc_id,
                page=page_num,
                text=text,
                label=label,
                title=title or doc_id,
            )
        )

    return passages


def infer_default_label_and_title(filename: str) -> tuple[str, Label, str]:
    """Derive default title, two-axis label, and doc_id for an unmanifested PDF."""
    import re
    stem = Path(filename).stem
    clean_id = re.sub(r"[^a-zA-Z0-9_\-]+", "-", stem).strip("-").lower()
    title = stem.replace("_", " ").replace("-", " ").title()

    lower = stem.lower()
    if any(k in lower for k in ["emergency", "safety", "hse", "fire", "disaster", "hazard", "erdmp"]):
        tier = Tier.INTERNAL
        comps = frozenset([Compartment.HSE])
    elif any(k in lower for k in ["vigilance", "cvc", "fraud", "corruption", "investigation"]):
        tier = Tier.CONFIDENTIAL
        comps = frozenset([Compartment.VIGILANCE])
    elif any(k in lower for k in ["legal", "court", "act", "tribunal", "arbitration"]):
        tier = Tier.CONFIDENTIAL
        comps = frozenset([Compartment.LEGAL])
    elif any(k in lower for k in ["commercial", "tender", "contract", "procurement", "pricing"]):
        tier = Tier.CONFIDENTIAL
        comps = frozenset([Compartment.COMMERCIAL])
    elif any(k in lower for k in ["tech", "process", "drawing", "refinery", "cdu", "vdu"]):
        tier = Tier.CONFIDENTIAL
        comps = frozenset([Compartment.TECHNICAL])
    elif any(k in lower for k in ["public", "gazette", "notice", "rti", "annual"]):
        tier = Tier.PUBLIC
        comps = frozenset()
    else:
        tier = Tier.INTERNAL
        comps = frozenset()

    return clean_id, Label(tier=tier, compartments=comps), title


def load_corpus(
    manifest_path: str | Path,
    documents_dir: str | Path,
    enable_ocr: bool = False,
) -> list[Passage]:
    """Load and parse the corpus according to manifest.json.

    Auto-discovers any new PDF dropped into documents_dir without requiring code changes.

    enable_ocr: forwarded to pdf_to_passages()/pdf_to_page_texts() for every
    document in the corpus -- when True, a manifest PDF with no embedded
    text layer is recovered via local OCR instead of being skipped with a
    ScannedPdfError warning.
    """
    m_path = Path(manifest_path)
    d_dir = Path(documents_dir)

    manifest_entries: list[dict] = []
    if m_path.exists():
        try:
            with open(m_path, "r", encoding="utf-8") as f:
                manifest_entries = json.load(f)
        except Exception as exc:
            print(f"[INGEST] Error reading manifest: {exc}")
            manifest_entries = []

    if not d_dir.exists():
        print(f"[INGEST] Documents directory '{d_dir}' does not exist. Returning empty corpus.")
        return []

    # -----------------------------------------------------------------------
    # Auto-Discovery: Detect any PDF in documents/ not yet declared in manifest
    # -----------------------------------------------------------------------
    known_files = {e["file"] for e in manifest_entries if "file" in e}
    manifest_updated = False

    for pdf_file in sorted(d_dir.glob("*.pdf")):
        if pdf_file.name not in known_files:
            auto_id, auto_label, auto_title = infer_default_label_and_title(pdf_file.name)
            new_entry = {
                "doc_id": auto_id,
                "file": pdf_file.name,
                "title": auto_title,
                "source": "Auto-Discovered Document (Internal)",
                "label": {
                    "tier": auto_label.tier.value,
                    "compartments": [c.value for c in auto_label.compartments],
                },
            }
            manifest_entries.append(new_entry)
            known_files.add(pdf_file.name)
            manifest_updated = True
            print(f"[INGEST] Auto-discovered and registered new document: '{pdf_file.name}' as '{auto_id}' with label '{auto_label}'")

    if manifest_updated:
        try:
            with open(m_path, "w", encoding="utf-8") as f:
                json.dump(manifest_entries, f, indent=2)
            print(f"[INGEST] Updated '{m_path}' with newly discovered documents.")
        except Exception as exc:
            print(f"[INGEST] Warning: Could not save updated manifest: {exc}")

    all_passages: list[Passage] = []

    for entry in manifest_entries:
        doc_id = entry["doc_id"]
        filename = entry.get("file", "")
        title = entry.get("title", doc_id)
        label_info = entry.get("label", {})

        tier = Tier(label_info.get("tier", Tier.INTERNAL.value))
        comps = frozenset(Compartment(c) for c in label_info.get("compartments", []))
        label = Label(tier=tier, compartments=comps)

        pdf_file = d_dir / filename
        if not pdf_file.exists():
            continue

        try:
            doc_passages = pdf_to_passages(
                pdf_path=pdf_file,
                doc_id=doc_id,
                label=label,
                title=title,
                enable_ocr=enable_ocr,
            )
            all_passages.extend(doc_passages)
        except ScannedPdfError as exc:
            print(f"[INGEST] Warning: {exc}")
        except Exception as exc:
            print(f"[INGEST] Error processing '{filename}': {exc}")

    return all_passages