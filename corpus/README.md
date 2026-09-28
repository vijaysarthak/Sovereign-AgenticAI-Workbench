# SEVERANCE Corpus Management Guide

## 1. Purpose of the Corpus Directory

This directory houses the structured manifest and document repository for Mangalore Refinery and Petrochemicals Limited (MRPL).

- `manifest.json`: Stores the declarative security labels (hierarchical classification tier + orthogonal compartments) for all documents.
- `documents/`: Stores the physical digital PDF files.

---

## 2. Transparent Disclosure for SIH 2026 Judges

> [!IMPORTANT]
> **Judges & Evaluators Notice**:
> Real, authentic internal operational documents and vigilance investigation files from MRPL are classified sovereign industrial secrets and are legally and ethically unobtainable for public hackathon submissions.
>
> In accordance with ethical AI and security best practices:
> 1. Public documents (such as MRPL's published RTI manuals and CVC guidelines) represent authentic public records.
> 2. Internal refinery operating procedures and vigilance reports are simulated based on public OISD (Oil Industry Safety Directorate) specifications and CVC manuals to demonstrate the technical validity of the two-axis security gate without compromising national energy infrastructure confidentiality.
> 3. Security classification labels (`tier` and `compartments`) are declared in `manifest.json`.

---

## 3. How to Ingest Genuine Refinery PDFs

Authorized refinery administrators can add proprietary documents at any time:

1. **Place the PDF** into `corpus/documents/`:
   ```bash
   cp /secure/path/my-refinery-doc.pdf corpus/documents/
   ```
2. **Add an entry** to `corpus/manifest.json`:
   ```json
   {
     "doc_id": "mrpl-sop-crude-desalter",
     "file": "my-refinery-doc.pdf",
     "title": "Standard Operating Procedure: Crude Desalter Wash Water Control",
     "source": "MRPL Operations Manual 2025 (Internal Technical Record)",
     "label": {
       "tier": "confidential",
       "compartments": ["technical", "hse"]
     }
   }
   ```
3. **Restart the server** or call the corpus refresh service. The two-axis gate will immediately index and protect the new material according to its declared label.

---

## 4. Scanned PDF Requirement

All ingested PDFs **must contain an embedded digital text layer**.
Scanned image-only PDFs lacking text are deliberately rejected with a loud `ScannedPdfError` to prevent silent OCR degradation and hallucination on critical engineering documents.
