import random
from providers.base_provider import BaseProvider


class TelnyxProvider(BaseProvider):
    """Mock Telnyx provider for UK numbers."""

    async def search_numbers(self, country: str) -> list:
        prefixes = ["+447400", "+447401", "+447500", "+447700", "+447900"]
        return [
            {"phone_number": f"{random.choice(prefixes)}{random.randint(100000, 999999)}", "friendly_name": "UK Mobile"}
            for _ in range(5)
        ]

    async def purchase_number(self, phone_number: str) -> dict:
        return {
            "sid": f"TELNYX_MOCK_{phone_number}",
            "phone_number": phone_number,
            "status": "mock_active"
        }

    async def release_number(self, number_sid: str) -> bool:
        return True

    async def configure_webhook(self, number_sid: str, webhook_url: str) -> bool:
        return True
