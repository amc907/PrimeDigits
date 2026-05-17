import asyncio
import os
from typing import Optional
from providers.base_provider import BaseProvider

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")


class TwilioProvider(BaseProvider):
    def __init__(self):
        try:
            from twilio.rest import Client
            self.client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        except Exception:
            self.client = None

    async def search_numbers(self, country: str) -> list:
        if not self.client:
            return []
        try:
            country_code = "US" if country.lower() == "us" else "CA"
            numbers = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.available_phone_numbers(country_code).local.list(limit=5)
            )
            return [{"phone_number": n.phone_number, "friendly_name": n.friendly_name} for n in numbers]
        except Exception:
            return []

    async def purchase_number(self, phone_number: str) -> dict:
        if not self.client:
            return {"sid": f"MOCK_{phone_number}", "phone_number": phone_number, "status": "mock"}
        try:
            incoming = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.incoming_phone_numbers.create(phone_number=phone_number)
            )
            return {"sid": incoming.sid, "phone_number": incoming.phone_number, "status": "active"}
        except Exception as e:
            return {"sid": "", "phone_number": phone_number, "status": "error", "error": str(e)}

    async def release_number(self, number_sid: str) -> bool:
        if not self.client or number_sid.startswith("MOCK_"):
            return True
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.incoming_phone_numbers(number_sid).delete()
            )
            return True
        except Exception:
            return False

    async def configure_webhook(self, number_sid: str, webhook_url: str) -> bool:
        if not self.client or number_sid.startswith("MOCK_"):
            return True
        try:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.incoming_phone_numbers(number_sid).update(
                    sms_url=webhook_url,
                    sms_method="POST"
                )
            )
            return True
        except Exception:
            return False
