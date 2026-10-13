from pathlib import Path

from app.importers import _parse_invoice_date, parse_pdf


def _minimal_text_pdf(path: Path, text: str) -> None:
    """PDF minimale con testo estraibile da pypdf (Helvetica)."""
    # Escape parentheses for PDF string literals.
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    lines = safe.split("\n")
    content_lines = ["BT /F1 12 Tf 50 750 Td"]
    for index, line in enumerate(lines):
        if index == 0:
            content_lines.append(f"({line}) Tj")
        else:
            content_lines.append(f"0 -16 Td ({line}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines)
    objects = [
        "1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        "2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        (
            "3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
        ),
        f"4 0 obj<< /Length {len(stream)} >>stream\n{stream}\nendstream endobj\n",
        "5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
    ]
    pdf = ["%PDF-1.4\n"]
    offsets = [0]
    for obj in objects:
        offsets.append(sum(len(part.encode("latin-1")) for part in pdf))
        pdf.append(obj)
    xref_pos = sum(len(part.encode("latin-1")) for part in pdf)
    pdf.append(f"xref\n0 {len(objects) + 1}\n")
    pdf.append("0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.append(f"{offset:010d} 00000 n \n")
    pdf.append(f"trailer<< /Size {len(objects) + 1} /Root 1 0 R >>\n")
    pdf.append(f"startxref\n{xref_pos}\n%%EOF\n")
    path.write_bytes("".join(pdf).encode("latin-1"))


def test_parse_invoice_date_formats():
    assert _parse_invoice_date("Data documento 15/02/2024") == "2024-02-15"
    assert _parse_invoice_date("Emessa il 2024-02-15") == "2024-02-15"
    assert _parse_invoice_date("del 15-02-24") == "2024-02-15"


def test_parse_pdf_extracts_date_and_totals(tmp_path: Path):
    pdf_path = tmp_path / "fattura.pdf"
    _minimal_text_pdf(
        pdf_path,
        "\n".join(
            [
                "FORNITORE DEMO SRL",
                "Fattura n. 88/B",
                "Data 15/02/2024",
                "Imponibile 100,00",
                "Totale IVA 22,00",
                "Totale documento 122,00",
            ]
        ),
    )
    result = parse_pdf(pdf_path)
    assert result["invoice"]["data"] == "2024-02-15"
    assert result["invoice"]["numero"] == "88/B"
    assert result["invoice"]["imponibile"] == "100.00"
    assert result["invoice"]["iva"] == "22.00"
    assert result["invoice"]["totale"] == "122.00"
    assert result["rows"] == []
    assert any("XML" in w for w in result["warnings"])
