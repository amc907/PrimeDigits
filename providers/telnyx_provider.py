import os
import logging
from typing import Optional

import httpx

from providers.base_provider import BaseProvider

logger = logging.getLogger(__name__)

TELNYX_API_KEY = os.getenv("TELNYX_API_KEY", "")
TELNYX_MESSAGING_PROFILE_ID = os.getenv(
    "TELNYX_MESSAGING_PROFILE_ID", "40019e4f-8160-4f99-b885-a3074f360bd5"
)
TELNYX_BASE_URL = "https://api.telnyx.com/v2"


class TelnyxProvider(BaseProvider):
    def __init__(self):
        self.available = bool(TELNYX_API_KEY)
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=TELNYX_BASE_URL,
                headers={
                    "Authorization": f"Bearer {TELNYX_API_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def search_numbers(self, country: str, state: Optional[str] = None) -> list:
        logger.info(
            f"Telnyx search called. "
            f"API key set: {bool(TELNYX_API_KEY)}, "
            f"Country: {country}, State: {state}"
        )
        if not self.available:
            return self._mock_numbers(country, state)

        country_code = "US" if country.lower() == "us" else "CA"
        client = await self._get_client()

        # US: try local first, then toll_free. CA: local only.
        types_to_try = (
            ["local", "toll_free"] if country_code == "US" else ["local"]
        )

        for number_type in types_to_try:
            try:
                params = {
                    "filter[country_code]": country_code,
                    "filter[number_type]": number_type,
                    "filter[features]": "sms",
                    "filter[limit]": "5",
                }
                if country_code == "US" and state:
                    params["filter[administrative_area]"] = state.upper()

                response = await client.get(
                    "/available_phone_numbers", params=params
                )
                response.raise_for_status()
                data = response.json()

                numbers = []
                for item in data.get("data", []):
                    pn = item.get("phone_number")
                    if pn:
                        numbers.append(
                            {
                                "phone_number": pn,
                                "friendly_name": pn,
                            }
                        )

                if numbers:
                    return numbers

            except Exception as e:
                logger.error(
                    f"Telnyx search_numbers error for "
                    f"{country_code}/{number_type}: "
                    f"{type(e).__name__}: {e}"
                )

        # Only return mock numbers when Telnyx is not configured.
        return self._mock_numbers(country, state) if not self.available else []

    def _mock_numbers(self, country: str, state: Optional[str] = None) -> list:
        mock = {
            "us": "+12025550100",
            "ca": "+16135550100",
        }
        return [
            {
                "phone_number": mock.get(
                    country.lower(), "+12025550100"
                ),
                "friendly_name": "Mock Number",
            }
        ]

    async def purchase_number(self, phone_number: str) -> dict:
        if not self.available:
            return {
                "sid": f"MOCK_{phone_number}",
                "phone_number": phone_number,
                "status": "mock",
            }

        client = await self._get_client()
        payload = {
            "phone_numbers": [{"phone_number": phone_number}],
            "messaging_profile_id": TELNYX_MESSAGING_PROFILE_ID or None,
        }

        try:
            response = await client.post(
                "/number_orders", json=payload
            )
            response.raise_for_status()
            data = response.json().get("data", {})

            order_id = data.get("id")
            status = data.get("status", "pending")
            phone_numbers = data.get("phone_numbers", [])
            pn_id = (
                phone_numbers[0].get("id")
                if phone_numbers
                else None
            )

            return {
                "sid": pn_id or order_id,
                "phone_number": phone_number,
                "status": status,
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

        client = await self._get_client()
        try:
            response = await client.delete(
                f"/phone_numbers/{number_sid}"
            )
            # 404 means already released / not found
            if response.status_code == 404:
                return True
            response.raise_for_status()
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

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
