import os
import asyncio
import logging
from providers.base_provider import BaseProvider

logger = logging.getLogger(__name__)

TELNYX_API_KEY = os.getenv("TELNYX_API_KEY", "")
TELNYX_MESSAGING_PROFILE_ID = os.getenv(
    "TELNYX_MESSAGING_PROFILE_ID", ""
)


def _get_client():
    import telnyx
    return telnyx.Telnyx(api_key=TELNYX_API_KEY)


class TelnyxProvider(BaseProvider):
    def __init__(self):
        try:
            import telnyx  # noqa: F401
            self.available = bool(TELNYX_API_KEY)
        except ImportError:
            self.available = False

    async def search_numbers(self, country: str) -> list:
        logger.info(
            f"Telnyx search called. "
            f"API key set: {bool(TELNYX_API_KEY)}, "
            f"Country: {country}"
        )
        if not self.available:
            return self._mock_numbers(country)

        country_code = (
            "GB" if country.lower() == "uk"
            else "US" if country.lower() == "us"
            else "CA"
        )

        try:
            client = _get_client()
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.available_phone_numbers.list(
                    filter={
                        "country_code": country_code,
                        "features": ["sms"],
                        "limit": 5,
                    }
                ),
            )

            numbers = []
            for item in (response.data or []):
                if item.phone_number:
                    numbers.append({
                        "phone_number": item.phone_number,
                        "friendly_name": item.phone_number,
                    })

            return numbers if numbers else self._mock_numbers(country)

        except Exception as e:
            logger.error(
                f"Telnyx search_numbers FULL ERROR: "
                f"{type(e).__name__}: {e}"
            )
            return self._mock_numbers(country)

    def _mock_numbers(self, country: str) -> list:
        mock = {
            "us": "+12025550100",
            "ca": "+16135550100",
            "uk": "+441234567890",
        }
        return [{
            "phone_number": mock.get(country.lower(), "+12025550100"),
            "friendly_name": "Mock Number",
        }]

    async def purchase_number(self, phone_number: str) -> dict:
        if not self.available:
            return {
                "sid": f"MOCK_{phone_number}",
                "phone_number": phone_number,
                "status": "mock",
            }

        try:
            client = _get_client()
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.number_orders.create(
                    phone_numbers=[{"phone_number": phone_number}],
                    messaging_profile_id=TELNYX_MESSAGING_PROFILE_ID or None,
                ),
            )

            order = response.data
            # Use the phone number record ID as the SID for future operations
            pn_records = order.phone_numbers if order else []
            pn_id = pn_records[0].id if pn_records else None

            return {
                "sid": pn_id or order.id,
                "phone_number": phone_number,
                "status": order.status or "active",
            }

        except Exception as e:
            logger.error(
                f"Telnyx purchase_number FULL ERROR: "
                f"{type(e).__name__}: {e}"
            )
            return {
                "sid": f"MOCK_{phone_number}",
                "phone_number": phone_number,
                "status": "error",
                "error": str(e),
            }

    async def release_number(self, number_sid: str) -> bool:
        if not self.available or number_sid.startswith("MOCK_"):
            return True

        try:
            client = _get_client()
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.phone_numbers.delete(id=number_sid),
            )
            return True

        except Exception as e:
            logger.error(
                f"Telnyx release_number FULL ERROR: "
                f"{type(e).__name__}: {e}"
            )
            return False

    async def configure_webhook(
        self, number_sid: str, webhook_url: str
    ) -> bool:
        # Webhook already configured via
        # messaging profile — no action needed
        return True
