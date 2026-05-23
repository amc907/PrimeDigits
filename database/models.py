import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, ForeignKey, Text, Numeric, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database.connection import Base


def generate_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id = Column(String, unique=True, nullable=True, index=True)
    supabase_id = Column(String, unique=True, nullable=True, index=True)
    email = Column(String, unique=True, nullable=True, index=True)
    username = Column(String, nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow)
    is_banned = Column(Boolean, default=False)
    number_limit = Column(Integer, default=3)
    referral_code = Column(String, unique=True, nullable=False, default=lambda: str(uuid.uuid4())[:8].upper())
    referred_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    numbers = relationship("Number", back_populates="user", lazy="selectin")
    transactions = relationship("Transaction", back_populates="user", lazy="selectin")
    referrals_made = relationship("Referral", foreign_keys="Referral.referrer_id", back_populates="referrer", lazy="selectin")


class Number(Base):
    __tablename__ = "numbers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number = Column(String, nullable=False)
    number_sid = Column(String, nullable=True)
    provider = Column(String, nullable=False)
    country = Column(String, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    purchased_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    released_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="numbers")
    sms_credits = relationship("SmsCredit", back_populates="number", lazy="selectin")
    sms_logs = relationship("SmsLog", back_populates="number", lazy="selectin")

    __table_args__ = (
        Index("ix_numbers_user_id_active", "user_id", "is_active"),
    )


class SmsCredit(Base):
    __tablename__ = "sms_credits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    number_id = Column(UUID(as_uuid=True), ForeignKey("numbers.id"), nullable=False)
    total_credits = Column(Integer, default=0)
    used_credits = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    number = relationship("Number", back_populates="sms_credits")
    user = relationship("User", lazy="selectin")

    __table_args__ = (
        Index("ix_sms_credits_user_number", "user_id", "number_id"),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    amount_ngn = Column(Numeric(12, 2), nullable=False)
    type = Column(String, nullable=False)
    status = Column(String, default="pending")
    flutterwave_ref = Column(String, nullable=True)
    stripe_payment_intent_id = Column(String, nullable=True, index=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="transactions")


class SmsLog(Base):
    __tablename__ = "sms_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number_id = Column(UUID(as_uuid=True), ForeignKey("numbers.id"), nullable=False)
    from_number = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    received_at = Column(DateTime, default=datetime.utcnow)
    delivered = Column(Boolean, default=True)
    credit_deducted = Column(Boolean, default=True)

    number = relationship("Number", back_populates="sms_logs")


class SupportAgent(Base):
    __tablename__ = "support_agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id = Column(String, unique=True, nullable=False)
    username = Column(String, nullable=True)
    can_replace_numbers = Column(Boolean, default=True)
    added_at = Column(DateTime, default=datetime.utcnow)


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    referrer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    referred_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    reward_given = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    referrer = relationship("User", foreign_keys=[referrer_id], back_populates="referrals_made", lazy="selectin")


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message = Column(Text, nullable=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
    sent_by = Column(String, nullable=False)


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_telegram_id = Column(String, nullable=False, index=True)
    group_message_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class DeletionLog(Base):
    __tablename__ = "deletion_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number_id = Column(UUID(as_uuid=True), nullable=True)
    phone_number = Column(String, nullable=False)
    deleted_by_telegram_id = Column(String, nullable=False)
    deleted_at = Column(DateTime, default=datetime.utcnow)
