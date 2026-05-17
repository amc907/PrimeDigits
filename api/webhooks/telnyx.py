import logging
from fastapi import APIRouter, Request

router = APIRouter(prefix="/webhooks/telnyx", tags=["telnyx"])
logger = logging.getLogger(__name__)


@router.post("/sms")
async def telnyx_sms_webhook(request: Request):
    """Mock Telnyx webhook — not used in production since Telnyx is mocked."""
    payload = await request.json()
    logger.info(f"Telnyx mock webhook received: {payload}")
    return {"status": "mock_ok"}
