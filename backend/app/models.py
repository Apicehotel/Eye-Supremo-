from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class Supplier(Base):
    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    ragione_sociale: Mapped[str] = mapped_column(String(180), index=True)
    partita_iva: Mapped[str | None] = mapped_column(String(20), unique=True)
    codice_fiscale: Mapped[str | None] = mapped_column(String(24))
    indirizzo: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(180))
    telefono: Mapped[str | None] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(Text)
    invoices: Mapped[list["Invoice"]] = relationship(back_populates="supplier")


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100), unique=True)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome_canonico: Mapped[str] = mapped_column(String(240), index=True)
    categoria: Mapped[str | None] = mapped_column(String(100), index=True)
    sottocategoria: Mapped[str | None] = mapped_column(String(100))
    marca: Mapped[str | None] = mapped_column(String(100), index=True)
    codice: Mapped[str | None] = mapped_column(String(80), index=True)
    unita_base: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)


class ProductAlias(Base):
    __tablename__ = "product_aliases"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    descrizione: Mapped[str] = mapped_column(String(300), index=True)
    normalized: Mapped[str] = mapped_column(String(300), index=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("product_id", "normalized"),)


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    numero: Mapped[str] = mapped_column(String(80), index=True)
    data: Mapped[date] = mapped_column(Date, index=True)
    imponibile: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    iva: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    totale: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, index=True)
    valuta: Mapped[str] = mapped_column(String(3), default="EUR")
    file_originale: Mapped[str | None] = mapped_column(String(500))
    hash_file: Mapped[str | None] = mapped_column(String(64), index=True)
    stato_importazione: Mapped[str] = mapped_column(String(30), default="confermata", index=True)
    testo_estratto: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    supplier: Mapped[Supplier] = relationship(back_populates="invoices")
    rows: Mapped[list["InvoiceRow"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    __table_args__ = (Index("ix_invoice_supplier_date", "supplier_id", "data"),)


class InvoiceRow(Base):
    __tablename__ = "invoice_rows"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), index=True)
    descrizione_originale: Mapped[str] = mapped_column(Text)
    descrizione_normalizzata: Mapped[str] = mapped_column(String(300), index=True)
    quantita: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=1)
    unita_originale: Mapped[str | None] = mapped_column(String(30))
    unita_normalizzata: Mapped[str | None] = mapped_column(String(20), index=True)
    prezzo_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0)
    totale_riga: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    aliquota_iva: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    prezzo_normalizzato: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=1)
    invoice: Mapped[Invoice] = relationship(back_populates="rows")
    product: Mapped[Product | None] = relationship()


class ImportJob(Base):
    __tablename__ = "import_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(300))
    stored_path: Mapped[str] = mapped_column(String(500))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    payload_json: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    message: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="info", index=True)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


class AppSetting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
