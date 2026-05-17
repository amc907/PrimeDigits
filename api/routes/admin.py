from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from database.connection import get_db
from database import crud

router = APIRouter(prefix="/admin", tags=["admin"])


class BroadcastRequest(BaseModel):
    message: str
    sent_by: str


class AddCreditsRequest(BaseModel):
    telegram_id: str
    number_id: str
    amount: int


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    from datetime import datetime, timedelta
    total_users = await crud.get_user_count(db)
    total_revenue = await crud.get_total_revenue(db)
    daily_revenue = await crud.get_revenue_since(db, datetime.utcnow() - timedelta(days=1))
    weekly_revenue = await crud.get_revenue_since(db, datetime.utcnow() - timedelta(days=7))
    return {
        "total_users": total_users,
        "total_revenue_ngn": total_revenue,
        "daily_revenue_ngn": daily_revenue,
        "weekly_revenue_ngn": weekly_revenue
    }


@router.post("/broadcast")
async def broadcast_message(req: BroadcastRequest, db: AsyncSession = Depends(get_db)):
    from utils.notifications import notify_user
    users = await crud.get_all_users(db)
    sent = 0
    for user in users:
        if not user.is_banned:
            await notify_user(user.telegram_id, req.message)
            sent += 1
    await crud.create_announcement(db, req.message, req.sent_by)
    return {"sent": sent}


@router.post("/add-credits")
async def add_credits(req: AddCreditsRequest, db: AsyncSession = Depends(get_db)):
    import uuid
    user = await crud.get_user_by_telegram_id(db, req.telegram_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    number = await crud.get_number_by_id(db, uuid.UUID(req.number_id))
    if not number:
        raise HTTPException(status_code=404, detail="Number not found")
    credit = await crud.add_sms_credits(db, user.id, number.id, req.amount)
    return {"total_credits": credit.total_credits, "used_credits": credit.used_credits}
