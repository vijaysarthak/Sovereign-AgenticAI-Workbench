"""Script to generate synthetic PDF test fixtures without requiring reportlab.

Outputs:
1. tests/fixtures/normal_2page.pdf (2 pages of extractable text)
2. tests/fixtures/scanned_notext.pdf (1 page with 0 extractable text)
3. tests/fixtures/mixed_pages.pdf (Page 1 text, Page 2 blank)
"""

from pathlib import Path


def make_pdf_bytes(pages_text: list[str]) -> bytes:
    """Generate minimal valid PDF 1.4 byte streams with standard fonts and xref table."""
    out = bytearray()
    out.extend(b"%PDF-1.4\n")
    offsets = [0]

    def add_obj(content: str):
        offsets.append(len(out))
        out.extend(content.encode("latin1"))
        out.extend(b"\n")

    num_pages = len(pages_text)
    page_ids = [4 + i * 2 for i in range(num_pages)]
    content_ids = [5 + i * 2 for i in range(num_pages)]

    # Catalog & Pages root
    add_obj("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj")
    kids_str = " ".join(f"{pid} 0 R" for pid in page_ids)
    add_obj(f"2 0 obj\n<< /Type /Pages /Kids [{kids_str}] /Count {num_pages} >>\nendobj")

    # Font Resource
    add_obj("3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj")

    for i, txt in enumerate(pages_text):
        pid = page_ids[i]
        cid = content_ids[i]
        add_obj(
            f"{pid} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {cid} 0 R >>\nendobj"
        )
        stream_data = f"BT /F1 12 Tf 72 712 Td ({txt}) Tj ET" if txt else ""
        add_obj(
            f"{cid} 0 obj\n<< /Length {len(stream_data)} >>\nstream\n{stream_data}\nendstream\nendobj"
        )

    xref_pos = len(out)
    num_objs = len(offsets)
    out.extend(f"xref\n0 {num_objs}\n0000000000 65535 f \n".encode("latin1"))
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("latin1"))
    out.extend(
        f"trailer\n<< /Size {num_objs} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "latin1"
        )
    )
    return bytes(out)


def main():
    fixtures_dir = Path(__file__).parent.parent / "tests" / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    # 1. Normal 2-page document
    normal_pdf = make_pdf_bytes([
        "This is page one text for unit testing extraction. It contains operational refinery parameters.",
        "This is page two text with emergency shutdown instructions and nitrogen purge protocols.",
    ])
    (fixtures_dir / "normal_2page.pdf").write_bytes(normal_pdf)
    print(f"Generated: {fixtures_dir / 'normal_2page.pdf'}")

    # 2. Scanned / No-text document
    scanned_pdf = make_pdf_bytes([""])
    (fixtures_dir / "scanned_notext.pdf").write_bytes(scanned_pdf)
    print(f"Generated: {fixtures_dir / 'scanned_notext.pdf'}")

    # 3. Mixed pages document (page 1 has text, page 2 is blank)
    mixed_pdf = make_pdf_bytes([
        "Page one valid content describing daily throughput logs and desalter temperatures.",
        "",
    ])
    (fixtures_dir / "mixed_pages.pdf").write_bytes(mixed_pdf)
    print(f"Generated: {fixtures_dir / 'mixed_pages.pdf'}")


if __name__ == "__main__":
    main()
