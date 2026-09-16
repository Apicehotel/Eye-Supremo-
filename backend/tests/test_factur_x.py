from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

from app.factur_x import parse_facturx_xml, validate_facturx_xml
from app.importers import parse_document


VALID_CII = b'''<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice
 xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
 xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
 xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
 <rsm:ExchangedDocumentContext>
  <ram:GuidelineSpecifiedDocumentContextParameter><ram:ID>urn:factur-x.eu:1p0:en16931</ram:ID></ram:GuidelineSpecifiedDocumentContextParameter>
 </rsm:ExchangedDocumentContext>
 <rsm:ExchangedDocument>
  <ram:ID>FX-2026-001</ram:ID>
  <ram:IssueDateTime><udt:DateTimeString format="102">20260916</udt:DateTimeString></ram:IssueDateTime>
 </rsm:ExchangedDocument>
 <rsm:SupplyChainTradeTransaction>
  <ram:IncludedSupplyChainTradeLineItem>
   <ram:AssociatedDocumentLineDocument><ram:LineID>1</ram:LineID></ram:AssociatedDocumentLineDocument>
   <ram:SpecifiedTradeProduct><ram:Name>Acqua minerale 1L</ram:Name></ram:SpecifiedTradeProduct>
   <ram:SpecifiedLineTradeAgreement><ram:NetPriceProductTradePrice><ram:ChargeAmount>1.50</ram:ChargeAmount></ram:NetPriceProductTradePrice></ram:SpecifiedLineTradeAgreement>
   <ram:SpecifiedLineTradeDelivery><ram:BilledQuantity unitCode="C62">10</ram:BilledQuantity></ram:SpecifiedLineTradeDelivery>
   <ram:SpecifiedLineTradeSettlement>
    <ram:ApplicableTradeTax><ram:RateApplicablePercent>22</ram:RateApplicablePercent></ram:ApplicableTradeTax>
    <ram:SpecifiedTradeSettlementLineMonetarySummation><ram:LineTotalAmount>15.00</ram:LineTotalAmount></ram:SpecifiedTradeSettlementLineMonetarySummation>
   </ram:SpecifiedLineTradeSettlement>
  </ram:IncludedSupplyChainTradeLineItem>
  <ram:ApplicableHeaderTradeAgreement>
   <ram:SellerTradeParty>
    <ram:Name>Fornitore Test SRL</ram:Name>
    <ram:SpecifiedTaxRegistration><ram:ID schemeID="VA">IT12345678901</ram:ID></ram:SpecifiedTaxRegistration>
   </ram:SellerTradeParty>
  </ram:ApplicableHeaderTradeAgreement>
  <ram:ApplicableHeaderTradeSettlement>
   <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
   <ram:ApplicableTradeTax><ram:CalculatedAmount>3.30</ram:CalculatedAmount></ram:ApplicableTradeTax>
   <ram:SpecifiedTradeSettlementHeaderMonetarySummation>
    <ram:LineTotalAmount>15.00</ram:LineTotalAmount>
    <ram:TaxBasisTotalAmount>15.00</ram:TaxBasisTotalAmount>
    <ram:GrandTotalAmount>18.30</ram:GrandTotalAmount>
   </ram:SpecifiedTradeSettlementHeaderMonetarySummation>
  </ram:ApplicableHeaderTradeSettlement>
 </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>'''


def test_parse_facturx_xml_extracts_structured_invoice():
    result = parse_facturx_xml(VALID_CII)
    assert result["source"] == "factur-x"
    assert result["supplier"]["ragione_sociale"] == "Fornitore Test SRL"
    assert result["invoice"]["numero"] == "FX-2026-001"
    assert result["invoice"]["data"] == "2026-09-16"
    assert result["invoice"]["totale"] == "18.30"
    assert result["rows"][0]["descrizione_originale"] == "Acqua minerale 1L"
    assert result["rows"][0]["quantita"] == "10"
    assert result["e_invoice"]["structure_valid"] is True


def test_invalid_xml_is_rejected():
    validation = validate_facturx_xml(b"<broken>")
    assert validation.syntax_valid is False
    with pytest.raises(ValueError):
        parse_facturx_xml(b"<broken>")


def test_direct_cii_xml_is_not_treated_as_fatturapa(tmp_path: Path):
    path = tmp_path / "invoice.xml"
    path.write_bytes(VALID_CII)
    result = parse_document(path)
    assert result["source"] == "factur-x"
    assert result["e_invoice"]["format"] == "Factur-X/ZUGFeRD"


def test_pdf_with_facturx_attachment_uses_xml_before_text(tmp_path: Path):
    path = tmp_path / "invoice.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_attachment("factur-x.xml", VALID_CII)
    with path.open("wb") as stream:
        writer.write(stream)

    result = parse_document(path)
    assert result["source"] == "factur-x"
    assert result["invoice"]["numero"] == "FX-2026-001"
    assert result["e_invoice"]["attachment"] == "factur-x.xml"


def test_pdf_without_attachment_falls_back(tmp_path: Path):
    path = tmp_path / "plain.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with path.open("wb") as stream:
        writer.write(stream)

    result = parse_document(path)
    assert result["source"] == "pdf-text"
    assert result["e_invoice"] if "e_invoice" in result else True
