from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SupplierIn(BaseModel):
    ragione_sociale: str = Field(min_length=2, max_length=180)
    partita_iva: str | None = None
    codice_fiscale: str | None = None
    indirizzo: str | None = None
    email: str | None = None
    telefono: str | None = None
    note: str | None = None


class SupplierOut(SupplierIn, ORMModel):
    id: int


class ProductIn(BaseModel):
    nome_canonico: str = Field(min_length=2)
    categoria: str | None = None
    sottocategoria: str | None = None
    marca: str | None = None
    codice: str | None = None
    unita_base: str | None = None
    note: str | None = None


class ProductOut(ProductIn, ORMModel):
    id: int


class RowIn(BaseModel):
    descrizione_originale: str
    descrizione_normalizzata: str | None = None
    product_id: int | None = None
    quantita: Decimal = Decimal("1")
    unita_originale: str | None = None
    prezzo_unitario: Decimal = Decimal("0")
    totale_riga: Decimal = Decimal("0")
    aliquota_iva: Decimal | None = None
    confidence: Decimal = Decimal("1")


class InvoiceIn(BaseModel):
    supplier_id: int
    numero: str
    data: date
    imponibile: Decimal
    iva: Decimal
    totale: Decimal
    valuta: str = "EUR"
    file_originale: str | None = None
    hash_file: str | None = None
    testo_estratto: str | None = None
    rows: list[RowIn] = []


class InvoiceListOut(ORMModel):
    id: int
    numero: str
    data: date
    imponibile: Decimal
    iva: Decimal
    totale: Decimal
    valuta: str
    stato_importazione: str
    file_originale: str | None
    supplier: SupplierOut
    row_count: int = 0


class LogOut(ORMModel):
    id: int
    event_type: str
    message: str
    severity: str
    created_at: datetime
