import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_db
from database import crud

logger = logging.getLogger(__name__)

router = APIRouter(tags=["web"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class RegisterWebUserRequest(BaseModel):
    email: str
    full_name: Optional[str] = None
    supabase_id: str


class VerifyWebUserRequest(BaseModel):
    supabase_id: str


# ---------------------------------------------------------------------------
# 1. GET /numbers/web/{email}
# ---------------------------------------------------------------------------

@router.get("/numbers/web/{email}")
async def get_web_user_numbers(email: str, db: AsyncSession = Depends(get_db)):
    user = await crud.get_user_by_email(db, email)
    if not user:
        return {"numbers": []}

    numbers = await crud.get_active_numbers_for_user(db, user.id)
    result = []
    for num in numbers:
        credit = await crud.get_sms_credit_for_number(db, user.id, num.id)
        result.append({
            "id": str(num.id),
            "phone_number": num.phone_number,
            "country": num.country,
            "provider": num.provider,
            "purchased_at": num.purchased_at.isoformat() if num.purchased_at else None,
            "expires_at": num.expires_at.isoformat() if num.expires_at else None,
            "is_active": num.is_active,
            "sms_credits": {
                "total": credit.total_credits if credit else 0,
                "used": credit.used_credits if credit else 0,
                "remaining": (credit.total_credits - credit.used_credits) if credit else 0,
            } if credit else None,
        })

    return {"numbers": result}


# ---------------------------------------------------------------------------
# 2. GET /sms/web/{number_id}
# ---------------------------------------------------------------------------

@router.get("/sms/web/{number_id}")
async def get_web_sms_logs(number_id: str, db: AsyncSession = Depends(get_db)):
    try:
        nid = uuid.UUID(number_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid number_id UUID")

    logs = await crud.get_sms_logs_for_number(db, nid)
    return {
        "sms_logs": [
            {
                "id": str(log.id),
                "from_number": log.from_number,
                "body": log.body,
                "received_at": log.received_at.isoformat() if log.received_at else None,
                "delivered": log.delivered,
            }
            for log in logs
        ]
    }


# ---------------------------------------------------------------------------
# 3. POST /auth/web/register
# ---------------------------------------------------------------------------

@router.post("/auth/web/register")
async def register_web_user(req: RegisterWebUserRequest, db: AsyncSession = Depends(get_db)):
    existing = await crud.get_user_by_supabase_id(db, req.supabase_id)
    if existing:
        return {"status": "exists", "user_id": str(existing.id)}

    if req.email:
        existing_email = await crud.get_user_by_email(db, req.email)
        if existing_email:
            # Link supabase_id to existing email user
            existing_email.supabase_id = req.supabase_id
            await db.commit()
            return {"status": "linked", "user_id": str(existing_email.id)}

    user = await crud.create_web_user(
        db,
        email=req.email,
        full_name=req.full_name,
        supabase_id=req.supabase_id,
    )
    return {"status": "created", "user_id": str(user.id)}


# ---------------------------------------------------------------------------
# 4. POST /auth/web/verify
# ---------------------------------------------------------------------------

@router.post("/auth/web/verify")
async def verify_web_user(req: VerifyWebUserRequest, db: AsyncSession = Depends(get_db)):
    user = await crud.get_user_by_supabase_id(db, req.supabase_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "user_id": str(user.id),
        "email": user.email,
        "username": user.username,
        "joined_at": user.joined_at.isoformat() if user.joined_at else None,
        "number_limit": user.number_limit,
        "is_banned": user.is_banned,
    }
