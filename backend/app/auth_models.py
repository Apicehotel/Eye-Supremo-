from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


ROLES = ("developer", "supremo", "level1", "level2", "level3", "uploader")


class UserProfile(Base):
    __tablename__ = "user_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    role_name: Mapped[str] = mapped_column(String(30), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    can_manage_config: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class LocalCredential(Base):
    __tablename__ = "local_credentials"
    user_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), primary_key=True)
    salt: Mapped[str] = mapped_column(String(64))
    pin_hash: Mapped[str] = mapped_column(String(128))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    user: Mapped[UserProfile] = relationship()


class LocalSession(Base):
    __tablename__ = "local_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    user: Mapped[UserProfile] = relationship()


class RemoteUpload(Base):
    """Coda locale dei file caricati su Supabase Storage (o mirror locale)."""
    __tablename__ = "remote_uploads"
    id: Mapped[int] = mapped_column(primary_key=True)
    original_name: Mapped[str] = mapped_column(String(300))
    # Stesso path content-addressable per hash identici (più tentativi → stessa locazione blob)
    storage_path: Mapped[str] = mapped_column(String(500), index=True)
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(default=0)
    content_type: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), index=True, default="pending_review")
    duplicate_invoice_ids: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("user_profiles.id", ondelete="SET NULL"), index=True)
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    uploader: Mapped[UserProfile | None] = relationship()
