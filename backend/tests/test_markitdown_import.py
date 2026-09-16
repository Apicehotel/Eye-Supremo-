from pathlib import Path

from openpyxl import Workbook

from app.importers import parse_document


def test_xlsx_preview_uses_markitdown(tmp_path: Path):
    path = tmp_path / "fattura.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Fattura 99", "Totale documento", "123,45"])
    sheet.append(["Acqua naturale", 10, "12,00"])
    workbook.save(path)

    result = parse_document(path)

    assert "Fattura 99" in result["extracted_text"]
    assert result["invoice"]["numero"] == "99"
    assert result["confidence"] < 1
    assert result["rows"] == []
