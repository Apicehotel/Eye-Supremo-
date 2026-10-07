from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base
from .models import UserProfile


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
