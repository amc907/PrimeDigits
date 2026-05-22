import os
import asyncio
import logging
from providers.base_provider import BaseProvider

logger = logging.getLogger(__name__)

TELNYX_API_KEY = os.getenv("TELNYX_API_KEY", "")
TELNYX_MESSAGING_PROFILE_ID = os.getenv(
    "TELNYX_MESSAGING_PROFILE_ID", ""
)


class TelnyxProvider(BaseProvider):
    def __init__(self):
        try:
            import telnyx
            telnyx.api_key = TELNYX_API_KEY
            self.telnyx = telnyx
            self.available = bool(TELNYX_API_KEY)
        except ImportError:
            self.telnyx = None
            self.available = False

    async def search_numbers(
        self, country: str
    ) -> list:
        if not self.available:
            return self._mock_numbers(country)
        country_code = (
            "GB" if country.lower() == "uk"
            else "US" if country.lower() == "us"
            else "CA"
        )
        try:
            results = await asyncio.get_event_loop()\
                .run_in_executor(
                None,
                lambda: self.telnyx\
                    .AvailablePhoneNumber.list(
                    **{
                        "filter[country_code]":
                            country_code,
                        "filter[features]": "sms",
                        "filter[limit]": 5
                    }
                )
            )
            numbers = []
            for n in results:
                numbers.append({
                    "phone_number": n.phone_number,
                    "friendly_name": n.phone_number
                })
            return numbers if numbers \
                else self._mock_numbers(country)
        except Exception as e:
            logger.error(
                f"Telnyx search error: {e}"
            )
            return self._mock_numbers(country)

    def _mock_numbers(self, country: str) -> list:
        mock = {
            "us": "+12025550100",
            "ca": "+16135550100",
            "uk": "+441234567890"
        }
        return [{
            "phone_number": mock.get(
                country.lower(), "+12025550100"
            ),
            "friendly_name": "Mock Number"
        }]

    async def purchase_number(
        self, phone_number: str
    ) -> dict:
        if not self.available:
            return {
                "sid": f"MOCK_{phone_number}",
                "phone_number": phone_number,
                "status": "mock"
            }
        try:
            result = await asyncio.get_event_loop()\
                .run_in_executor(
                None,
                lambda: self.telnyx\
                    .PhoneNumber.create(
                    phone_number=phone_number,
                    messaging_profile_id=
                        TELNYX_MESSAGING_PROFILE_ID
                )
            )
            return {
                "sid": result.id,
                "phone_number": result.phone_number,
                "status": "active"
            }
        except Exception as e:
            logger.error(
                f"Telnyx purchase error: {e}"
            )
            return {
                "sid": f"MOCK_{phone_number}",
                "phone_number": phone_number,
                "status": "error",
                "error": str(e)
            }

    async def release_number(
        self, number_sid: str
    ) -> bool:
        if not self.available or \
                number_sid.startswith("MOCK_"):
            return True
        try:
            await asyncio.get_event_loop()\
                .run_in_executor(
                None,
                lambda: self.telnyx\
                    .PhoneNumber.retrieve(
                    number_sid
                ).delete()
            )
            return True
        except Exception as e:
            logger.error(
                f"Telnyx release error: {e}"
            )
            return False

    async def configure_webhook(
        self, number_sid: str, webhook_url: str
    ) -> bool:
        # Webhook already configured via
        # messaging profile — no action needed
        return True
