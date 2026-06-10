from abc import ABC, abstractmethod
from typing import Optional


class BaseProvider(ABC):
    @abstractmethod
    async def search_numbers(self, country: str, state: Optional[str] = None) -> list:
        """Return list of available phone numbers."""
        pass

    @abstractmethod
    async def purchase_number(self, phone_number: str) -> dict:
        """Purchase a number and return {sid, phone_number, status}."""
        pass

    @abstractmethod
    async def release_number(self, number_sid: str) -> bool:
        """Release a number back to the provider."""
        pass

    @abstractmethod
    async def configure_webhook(self, number_sid: str, webhook_url: str) -> bool:
        """Set SMS webhook for a number."""
        pass
