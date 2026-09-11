from datetime import date as date_type, datetime
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
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
    data: Mapped[date_type] = mapped_column(Date, index=True)
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
    meta: Mapped["InvoiceMeta | None"] = relationship(back_populates="invoice", uselist=False, cascade="all, delete-orphan")
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
    policy: Mapped["InvoiceRowPolicy | None"] = relationship(back_populates="row", uselist=False, cascade="all, delete-orphan")


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
    entity_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


class AppSetting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Hotel(Base):
    __tablename__ = "hotels"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class UserProfile(Base):
    __tablename__ = "user_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    role_name: Mapped[str] = mapped_column(String(30), index=True)
    home_hotel_id: Mapped[int | None] = mapped_column(ForeignKey("hotels.id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    can_manage_config: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    home_hotel: Mapped[Hotel | None] = relationship()


class RoleExclusion(Base):
    __tablename__ = "role_exclusions"
    id: Mapped[int] = mapped_column(primary_key=True)
    role_name: Mapped[str] = mapped_column(String(30), index=True)
    exclusion_type: Mapped[str] = mapped_column(String(30), index=True)
    value: Mapped[str] = mapped_column(String(240), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("role_name", "exclusion_type", "value"),)


class InvoiceMeta(Base):
    __tablename__ = "invoice_meta"
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), primary_key=True)
    hotel_id: Mapped[int | None] = mapped_column(ForeignKey("hotels.id"), index=True)
    sync_uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    sync_status: Mapped[str] = mapped_column(String(20), default="local", index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, index=True)
    invoice: Mapped[Invoice] = relationship(back_populates="meta")
    hotel: Mapped[Hotel | None] = relationship()


class InvoiceRowPolicy(Base):
    __tablename__ = "invoice_row_policy"
    row_id: Mapped[int] = mapped_column(ForeignKey("invoice_rows.id", ondelete="CASCADE"), primary_key=True)
    analysis_status: Mapped[str] = mapped_column(String(30), default="product", index=True)
    exclusion_reason: Mapped[str | None] = mapped_column(String(160), index=True)
    manually_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    row: Mapped[InvoiceRow] = relationship(back_populates="policy")


class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[int] = mapped_column(primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40), index=True)
    label: Mapped[str | None] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    hotel: Mapped[Hotel] = relationship()
    __table_args__ = (UniqueConstraint("hotel_id", "code"),)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    hotel_id: Mapped[int] = mapped_column(ForeignKey("hotels.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.id"), index=True)
    source: Mapped[str | None] = mapped_column(String(80), index=True)
    author: Mapped[str | None] = mapped_column(String(160))
    rating: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), index=True)
    date: Mapped[date_type] = mapped_column(Date, index=True)
    text: Mapped[str] = mapped_column(Text)
    sentiment_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), index=True)
    raw_file: Mapped[str | None] = mapped_column(String(500))
    sync_uuid: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    hotel: Mapped[Hotel] = relationship()
    room: Mapped[Room | None] = relationship()
    tags: Mapped[list["ReviewTag"]] = relationship(back_populates="review", cascade="all, delete-orphan")


class ReviewCategory(Base):
    __tablename__ = "review_categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    parent_name: Mapped[str | None] = mapped_column(String(120))
    auto_learned: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ReviewTag(Base):
    __tablename__ = "review_tags"
    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("review_categories.id", ondelete="CASCADE"), index=True)
    polarity: Mapped[str] = mapped_column(String(12), index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=1)
    excerpt: Mapped[str | None] = mapped_column(Text)
    review: Mapped[Review] = relationship(back_populates="tags")
    category: Mapped[ReviewCategory] = relationship()
    __table_args__ = (UniqueConstraint("review_id", "category_id", "polarity"),)


class EmergingTheme(Base):
    __tablename__ = "emerging_themes"
    id: Mapped[int] = mapped_column(primary_key=True)
    hotel_id: Mapped[int | None] = mapped_column(ForeignKey("hotels.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    normalized: Mapped[str] = mapped_column(String(120), index=True)
    occurrences: Mapped[int] = mapped_column(Integer, default=1, index=True)
    status: Mapped[str] = mapped_column(String(20), default="candidate", index=True)
    merged_into_id: Mapped[int | None] = mapped_column(ForeignKey("review_categories.id"))
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    __table_args__ = (UniqueConstraint("hotel_id", "normalized"),)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    hotel_id: Mapped[int | None] = mapped_column(ForeignKey("hotels.id"), index=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info", index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(40), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)


class SyncState(Base):
    __tablename__ = "sync_state"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40), index=True)
    entity_uuid: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    remote_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    __table_args__ = (UniqueConstraint("entity_type", "entity_uuid"),)
