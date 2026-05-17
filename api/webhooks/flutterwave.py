import logging
import uuid
from fastapi import APIRouter, Request

from database.connection import AsyncSessionLocal
from database import crud

router = APIRouter(prefix="/webhooks/flutterwave", tags=["flutterwave"])
logger = logging.getLogger(__name__)


@router.post("/payment")
async def flutterwave_webhook(request: Request):
    """
    Mock Flutterwave webhook.
    In production, verify signature and update transaction status.
    """
    payload = await request.json()
    logger.info(f"Flutterwave webhook: {payload}")

    tx_ref = payload.get("txRef") or payload.get("tx_ref")
    status = payload.get("status", "successful")

    if not tx_ref:
        return {"status": "ignored"}

    async with AsyncSessionLocal() as db:
        try:
            tx_uuid = uuid.UUID(tx_ref)
        except ValueError:
            return {"status": "bad_ref"}

        tx = await crud.get_transaction_by_id(db, tx_uuid)
        if tx and status.lower() in ("successful", "completed"):
            await crud.update_transaction_status(db, tx.id, "completed")
            logger.info(f"Transaction {tx.id} marked completed")

    return {"status": "ok"}
