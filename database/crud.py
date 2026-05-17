import uuid
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    User, Number, SmsCredit, Transaction, SmsLog, SupportAgent, Referral, Announcement,
    SupportMessage, DeletionLog
)


# ------------------ Users ------------------

async def get_user_by_telegram_id(db: AsyncSession, telegram_id: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.telegram_id == str(telegram_id)))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, telegram_id: str, username: Optional[str] = None, referred_by_code: Optional[str] = None):
    referrer = None
    if referred_by_code:
        result = await db.execute(select(User).where(User.referral_code == referred_by_code))
        referrer = result.scalar_one_or_none()

    user = User(
        telegram_id=str(telegram_id),
        username=username,
        referred_by=referrer.id if referrer else None
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    if referrer:
        referral = Referral(referrer_id=referrer.id, referred_id=user.id, reward_given=False)
        db.add(referral)
        await db.commit()

    return user


async def update_username(db: AsyncSession, telegram_id: str, username: Optional[str]):
    await db.execute(
        update(User).where(User.telegram_id == str(telegram_id)).values(username=username)
    )
    await db.commit()


async def ban_user(db: AsyncSession, telegram_id: str, ban: bool = True):
    await db.execute(
        update(User).where(User.telegram_id == str(telegram_id)).values(is_banned=ban)
    )
    await db.commit()


async def get_all_users(db: AsyncSession) -> List[User]:
    result = await db.execute(select(User).order_by(User.joined_at.desc()))
    return result.scalars().all()


async def get_user_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count(User.id)))
    return result.scalar() or 0


async def get_active_number_count_for_user(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count(Number.id)).where(and_(Number.user_id == user_id, Number.is_active == True))
    )
    return result.scalar() or 0


async def set_user_number_limit(db: AsyncSession, user_id: uuid.UUID, limit: int):
    await db.execute(update(User).where(User.id == user_id).values(number_limit=limit))
    await db.commit()


# ------------------ Numbers ------------------

async def create_number(db: AsyncSession, user_id: uuid.UUID, phone_number: str, number_sid: str, provider: str, country: str, duration_months: int) -> Number:
    expires = datetime.utcnow() + timedelta(days=30 * duration_months)
    number = Number(
        user_id=user_id,
        phone_number=phone_number,
        number_sid=number_sid,
        provider=provider,
        country=country,
        expires_at=expires,
        is_active=True
    )
    db.add(number)
    await db.commit()
    await db.refresh(number)
    return number


async def get_number_by_id(db: AsyncSession, number_id: uuid.UUID) -> Optional[Number]:
    result = await db.execute(select(Number).where(Number.id == number_id))
    return result.scalar_one_or_none()


async def get_active_numbers_for_user(db: AsyncSession, user_id: uuid.UUID) -> List[Number]:
    result = await db.execute(
        select(Number).where(and_(Number.user_id == user_id, Number.is_active == True))
    )
    return result.scalars().all()


async def renew_number(db: AsyncSession, number_id: uuid.UUID, duration_months: int) -> Optional[Number]:
    number = await get_number_by_id(db, number_id)
    if not number:
        return None
    now = datetime.utcnow()
    base = number.expires_at if number.expires_at and number.expires_at > now else now
    number.expires_at = base + timedelta(days=30 * duration_months)
    number.is_active = True
    number.released_at = None
    await db.commit()
    await db.refresh(number)
    return number


async def release_number(db: AsyncSession, number_id: uuid.UUID):
    number = await get_number_by_id(db, number_id)
    if number:
        number.is_active = False
        number.released_at = datetime.utcnow()
        await db.commit()


async def delete_number_and_logs(db: AsyncSession, number_id: uuid.UUID):
    from sqlalchemy import delete
    await db.execute(delete(SmsLog).where(SmsLog.number_id == number_id))
    await db.execute(delete(SmsCredit).where(SmsCredit.number_id == number_id))
    await db.execute(delete(Number).where(Number.id == number_id))
    await db.commit()


async def log_number_deletion(db: AsyncSession, number_id: uuid.UUID, phone_number: str, deleted_by_telegram_id: str):
    log = DeletionLog(
        number_id=number_id,
        phone_number=phone_number,
        deleted_by_telegram_id=deleted_by_telegram_id
    )
    db.add(log)
    await db.commit()


async def replace_number(db: AsyncSession, number_id: uuid.UUID, new_phone: str, new_sid: str, provider: str):
    number = await get_number_by_id(db, number_id)
    if number:
        number.phone_number = new_phone
        number.number_sid = new_sid
        number.provider = provider
        await db.commit()
        await db.refresh(number)
    return number


async def get_expiring_numbers(db: AsyncSession, days: int) -> List[Number]:
    target = datetime.utcnow() + timedelta(days=days)
    start = target.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    result = await db.execute(
        select(Number).where(
            and_(
                Number.is_active == True,
                Number.expires_at >= start,
                Number.expires_at < end
            )
        )
    )
    return result.scalars().all()


async def get_expired_numbers(db: AsyncSession) -> List[Number]:
    result = await db.execute(
        select(Number).where(
            and_(
                Number.is_active == True,
                Number.expires_at < datetime.utcnow()
            )
        )
    )
    return result.scalars().all()


# ------------------ SMS Credits ------------------

async def get_or_create_sms_credit(db: AsyncSession, user_id: uuid.UUID, number_id: uuid.UUID, initial: int = 0) -> SmsCredit:
    result = await db.execute(
        select(SmsCredit).where(and_(SmsCredit.user_id == user_id, SmsCredit.number_id == number_id))
    )
    credit = result.scalar_one_or_none()
    if not credit:
        credit = SmsCredit(user_id=user_id, number_id=number_id, total_credits=initial, used_credits=0)
        db.add(credit)
        await db.commit()
        await db.refresh(credit)
    return credit


async def add_sms_credits(db: AsyncSession, user_id: uuid.UUID, number_id: uuid.UUID, amount: int):
    credit = await get_or_create_sms_credit(db, user_id, number_id)
    credit.total_credits += amount
    await db.commit()
    await db.refresh(credit)
    return credit


async def deduct_sms_credit(db: AsyncSession, user_id: uuid.UUID, number_id: uuid.UUID) -> bool:
    credit = await get_or_create_sms_credit(db, user_id, number_id)
    if credit.total_credits - credit.used_credits > 0:
        credit.used_credits += 1
        await db.commit()
        await db.refresh(credit)
        return True
    return False


async def get_sms_credit_for_number(db: AsyncSession, user_id: uuid.UUID, number_id: uuid.UUID) -> Optional[SmsCredit]:
    result = await db.execute(
        select(SmsCredit).where(and_(SmsCredit.user_id == user_id, SmsCredit.number_id == number_id))
    )
    return result.scalar_one_or_none()


# ------------------ Transactions ------------------

async def create_transaction(db: AsyncSession, user_id: uuid.UUID, amount_ngn: float, tx_type: str, flutterwave_ref: Optional[str] = None) -> Transaction:
    tx = Transaction(
        user_id=user_id,
        amount_ngn=amount_ngn,
        type=tx_type,
        status="pending",
        flutterwave_ref=flutterwave_ref
    )
    db.add(tx)
    await db.commit()
    await db.refresh(tx)
    return tx


async def get_transaction_by_id(db: AsyncSession, tx_id: uuid.UUID) -> Optional[Transaction]:
    result = await db.execute(select(Transaction).where(Transaction.id == tx_id))
    return result.scalar_one_or_none()


async def update_transaction_status(db: AsyncSession, tx_id: uuid.UUID, status: str):
    await db.execute(update(Transaction).where(Transaction.id == tx_id).values(status=status, updated_at=datetime.utcnow()))
    await db.commit()


async def get_pending_transactions(db: AsyncSession) -> List[Transaction]:
    result = await db.execute(select(Transaction).where(Transaction.status == "pending").order_by(Transaction.created_at.desc()))
    return result.scalars().all()


async def get_total_revenue(db: AsyncSession) -> float:
    result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount_ngn), 0)).where(Transaction.status == "completed")
    )
    return float(result.scalar() or 0)


async def get_revenue_since(db: AsyncSession, since: datetime) -> float:
    result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount_ngn), 0)).where(
            and_(Transaction.status == "completed", Transaction.created_at >= since)
        )
    )
    return float(result.scalar() or 0)


# ------------------ SMS Logs ------------------

async def create_sms_log(db: AsyncSession, number_id: uuid.UUID, from_number: str, body: str, delivered: bool = True, credit_deducted: bool = True) -> SmsLog:
    log = SmsLog(
        number_id=number_id,
        from_number=from_number,
        body=body,
        delivered=delivered,
        credit_deducted=credit_deducted
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


async def get_sms_logs_for_number(db: AsyncSession, number_id: uuid.UUID) -> List[SmsLog]:
    result = await db.execute(
        select(SmsLog).where(SmsLog.number_id == number_id).order_by(SmsLog.received_at.desc())
    )
    return result.scalars().all()


# ------------------ Support Agents ------------------

async def get_support_agent(db: AsyncSession, telegram_id: str) -> Optional[SupportAgent]:
    result = await db.execute(select(SupportAgent).where(SupportAgent.telegram_id == str(telegram_id)))
    return result.scalar_one_or_none()


async def add_support_agent(db: AsyncSession, telegram_id: str, username: Optional[str] = None, can_replace: bool = True):
    agent = SupportAgent(telegram_id=str(telegram_id), username=username, can_replace_numbers=can_replace)
    db.add(agent)
    await db.commit()


async def remove_support_agent(db: AsyncSession, telegram_id: str):
    from sqlalchemy import delete
    await db.execute(delete(SupportAgent).where(SupportAgent.telegram_id == str(telegram_id)))
    await db.commit()


async def get_all_support_agents(db: AsyncSession) -> List[SupportAgent]:
    result = await db.execute(select(SupportAgent))
    return result.scalars().all()


# ------------------ Support Messages ------------------

async def add_support_message_mapping(db: AsyncSession, customer_telegram_id: str, group_message_id: int):
    mapping = SupportMessage(
        customer_telegram_id=str(customer_telegram_id),
        group_message_id=group_message_id
    )
    db.add(mapping)
    await db.commit()


async def get_support_mapping_by_group_message_id(db: AsyncSession, group_message_id: int) -> Optional[SupportMessage]:
    result = await db.execute(
        select(SupportMessage).where(SupportMessage.group_message_id == group_message_id)
    )
    return result.scalar_one_or_none()


# ------------------ Referrals ------------------

async def get_unrewarded_referrals(db: AsyncSession) -> List[Referral]:
    result = await db.execute(select(Referral).where(Referral.reward_given == False))
    return result.scalars().all()


async def mark_referral_rewarded(db: AsyncSession, referral_id: uuid.UUID):
    await db.execute(update(Referral).where(Referral.id == referral_id).values(reward_given=True))
    await db.commit()


# ------------------ Announcements ------------------

async def create_announcement(db: AsyncSession, message: str, sent_by: str) -> Announcement:
    ann = Announcement(message=message, sent_by=sent_by)
    db.add(ann)
    await db.commit()
    await db.refresh(ann)
    return ann
