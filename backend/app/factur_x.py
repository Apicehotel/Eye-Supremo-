from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from typing import Any

from lxml import etree
from pypdf import PdfReader

from .normalization import normalize_text

FACTURX_NAMES = {"factur-x.xml", "zugferd-invoice.xml", "zugferd-invoice.xml", "zugferd.xml"}

NS = {
    "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
    "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    "udt": "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100",
}


@dataclass
class FacturXDocument:
    filename: str
    xml: bytes
    profile: str | None
    syntax_valid: bool
    structure_valid: bool
    validation_errors: list[str]


def _decimal(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value not in {None, ""} else default))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def _text(node: etree._Element, xpath: str) -> str | None:
    values = node.xpath(xpath, namespaces=NS)
    if not values:
        return None
    value = values[0]
    if isinstance(value, etree._Element):
        value = value.text
    value = str(value or "").strip()
    return value or None


def extract_facturx_xml(pdf_path: Path) -> tuple[str, bytes] | None:
    """Return the embedded Factur-X/ZUGFeRD XML, if present.

    pypdf exposes embedded attachments without executing PDF content. We only
    accept conventional XML attachment names and cap extraction to 10 MB.
    """
    reader = PdfReader(str(pdf_path), strict=False)
    attachments = getattr(reader, "attachments", {}) or {}
    for name in attachments:
        if Path(str(name)).name.lower() not in FACTURX_NAMES:
            continue
        values = attachments[name]
        if isinstance(values, (bytes, bytearray)):
            values = [values]
        for value in values or []:
            raw = bytes(value)
            if 0 < len(raw) <= 10 * 1024 * 1024:
                return Path(str(name)).name, raw
    return None


def validate_facturx_xml(xml_bytes: bytes) -> FacturXDocument:
    errors: list[str] = []
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False, huge_tree=False)
    try:
        root = etree.parse(BytesIO(xml_bytes), parser).getroot()
    except etree.XMLSyntaxError as exc:
        return FacturXDocument("", xml_bytes, None, False, False, [f"XML non valido: {exc.msg}"])

    local_name = etree.QName(root).localname
    namespace = etree.QName(root).namespace
    if local_name != "CrossIndustryInvoice":
        errors.append("Root XML non CrossIndustryInvoice")
    if namespace != NS["rsm"]:
        errors.append("Namespace CII non riconosciuto")

    required = {
        "numero": "//rsm:ExchangedDocument/ram:ID",
        "data": "//rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString",
        "fornitore": "//ram:ApplicableHeaderTradeAgreement/ram:SellerTradeParty/ram:Name",
        "totale": "//ram:SpecifiedTradeSettlementHeaderMonetarySummation/ram:GrandTotalAmount",
    }
    for label, xpath in required.items():
        if not _text(root, xpath):
            errors.append(f"Campo EN16931 mancante: {label}")

    profile = _text(root, "//rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID")
    return FacturXDocument("", xml_bytes, profile, True, not errors, errors)


def _parse_cii_date(raw: str | None) -> str:
    if not raw:
        return date.today().isoformat()
    raw = raw.strip()
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    if len(raw) >= 10 and raw[4] == "-":
        return raw[:10]
    return date.today().isoformat()


def parse_facturx_xml(xml_bytes: bytes) -> dict:
    validation = validate_facturx_xml(xml_bytes)
    if not validation.syntax_valid:
        raise ValueError("; ".join(validation.validation_errors))

    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False, huge_tree=False)
    root = etree.parse(BytesIO(xml_bytes), parser).getroot()

    supplier_name = _text(root, "//ram:ApplicableHeaderTradeAgreement/ram:SellerTradeParty/ram:Name") or "Fornitore da verificare"
    vat_id = _text(root, "//ram:ApplicableHeaderTradeAgreement/ram:SellerTradeParty/ram:SpecifiedTaxRegistration/ram:ID")
    number = _text(root, "//rsm:ExchangedDocument/ram:ID") or "SENZA-NUMERO"
    issue_date = _parse_cii_date(_text(root, "//rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString"))
    currency = _text(root, "//ram:ApplicableHeaderTradeSettlement/ram:InvoiceCurrencyCode") or "EUR"

    rows: list[dict] = []
    for line in root.xpath("//ram:IncludedSupplyChainTradeLineItem", namespaces=NS):
        desc = (
            _text(line, ".//ram:SpecifiedTradeProduct/ram:Name")
            or _text(line, ".//ram:SpecifiedTradeProduct/ram:Description")
            or "Riga senza descrizione"
        )
        qty_node = line.xpath(".//ram:SpecifiedLineTradeDelivery/ram:BilledQuantity", namespaces=NS)
        qty = _decimal(qty_node[0].text if qty_node else "1", "1")
        unit = qty_node[0].get("unitCode") if qty_node else None
        unit_price = _decimal(
            _text(line, ".//ram:SpecifiedLineTradeAgreement/ram:NetPriceProductTradePrice/ram:ChargeAmount")
            or _text(line, ".//ram:SpecifiedLineTradeAgreement/ram:GrossPriceProductTradePrice/ram:ChargeAmount")
        )
        line_total = _decimal(_text(line, ".//ram:SpecifiedLineTradeSettlement/ram:SpecifiedTradeSettlementLineMonetarySummation/ram:LineTotalAmount"))
        tax_rate = _decimal(_text(line, ".//ram:SpecifiedLineTradeSettlement/ram:ApplicableTradeTax/ram:RateApplicablePercent"))
        if unit_price == 0 and qty != 0 and line_total != 0:
            unit_price = line_total / qty
        rows.append({
            "descrizione_originale": desc,
            "descrizione_normalizzata": normalize_text(desc),
            "quantita": str(qty),
            "unita_originale": unit,
            "prezzo_unitario": str(unit_price),
            "totale_riga": str(line_total),
            "aliquota_iva": str(tax_rate),
            "confidence": 1.0,
        })

    summary = "//ram:ApplicableHeaderTradeSettlement/ram:SpecifiedTradeSettlementHeaderMonetarySummation"
    taxable = _decimal(_text(root, summary + "/ram:TaxBasisTotalAmount") or _text(root, summary + "/ram:LineTotalAmount"))
    grand_total = _decimal(_text(root, summary + "/ram:GrandTotalAmount"))
    tax_total_nodes = root.xpath("//ram:ApplicableHeaderTradeSettlement/ram:ApplicableTradeTax/ram:CalculatedAmount", namespaces=NS)
    tax_total = sum((_decimal(x.text) for x in tax_total_nodes), Decimal("0"))
    if grand_total == 0:
        grand_total = taxable + tax_total
    if taxable == 0:
        taxable = sum((_decimal(row["totale_riga"]) for row in rows), Decimal("0"))
    if tax_total == 0 and grand_total >= taxable:
        tax_total = grand_total - taxable

    warnings = list(validation.validation_errors)
    if not rows:
        warnings.append("Factur-X senza righe prodotto estraibili")

    return {
        "supplier": {"ragione_sociale": supplier_name, "partita_iva": vat_id},
        "invoice": {
            "numero": number,
            "data": issue_date,
            "imponibile": str(taxable),
            "iva": str(tax_total),
            "totale": str(grand_total),
            "valuta": currency,
        },
        "rows": rows,
        "confidence": 1.0 if validation.structure_valid else 0.9,
        "warnings": warnings,
        "source": "factur-x",
        "e_invoice": {
            "format": "Factur-X/ZUGFeRD",
            "profile": validation.profile,
            "syntax_valid": validation.syntax_valid,
            "structure_valid": validation.structure_valid,
            "xsd_validated": False,
            "validation_errors": validation.validation_errors,
        },
        "extracted_text": xml_bytes.decode("utf-8", errors="replace"),
    }


def parse_facturx_pdf(path: Path) -> dict | None:
    attachment = extract_facturx_xml(path)
    if not attachment:
        return None
    filename, xml_bytes = attachment
    result = parse_facturx_xml(xml_bytes)
    result["e_invoice"]["attachment"] = filename
    return result
