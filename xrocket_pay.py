from __future__ import annotations

from decimal import Decimal
from typing import Any

import aiohttp


class XRocketPayError(RuntimeError):
    pass


class XRocketPayClient:
    """Small async client for the xRocket Pay invoice API."""

    def __init__(self, token: str, base_url: str, currency: str = "USDT") -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.currency = currency.strip().upper()
        self.session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )

    async def close(self) -> None:
        if self.session is not None:
            await self.session.close()
            self.session = None

    async def request(
        self,
        method: str,
        path: str,
        parameters: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
    ) -> Any:
        if self.session is None:
            raise RuntimeError("xRocket Pay client is not started")
        url = f"{self.base_url}/api/v1/{path.lstrip('/')}"
        async with self.session.request(method, url, params=query, json=parameters) as response:
            try:
                data = await response.json(content_type=None)
            except (aiohttp.ContentTypeError, ValueError):
                data = await response.text()
            if response.status >= 400:
                raise XRocketPayError(f"HTTP {response.status}: {data}")
        if isinstance(data, dict) and data.get("success") is False:
            raise XRocketPayError(str(data.get("error") or data))
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data

    async def get_app_info(self) -> dict[str, Any]:
        result = await self.request("GET", "app-info")
        return result if isinstance(result, dict) else {}

    async def create_invoice(
        self,
        amount_cents: int,
        payload: str,
        description: str,
        fiat: str = "USD",
    ) -> dict[str, Any]:
        del fiat  # xRocket invoices use a crypto asset, not a display fiat currency.
        amount = format(Decimal(amount_cents) / Decimal("100"), "f").rstrip("0").rstrip(".")
        result = await self.request(
            "POST",
            "invoices",
            {
                "priceAmount": amount,
                "numPayments": 1,
                "priceCurrency": self.currency,
                "payoutCurrency": self.currency,
                "payCurrencies": [self.currency],
                "clientInvoiceId": payload[:150],
                "description": description[:1000],
                "expiresIn": 1_800_000,
                "isFeePaidByUser": False,
                "data": {"payload": payload[:4000]},
            },
        )
        if not isinstance(result, dict) or "id" not in result:
            raise XRocketPayError(f"Unexpected invoice response: {result}")
        links = result.get("links") if isinstance(result.get("links"), dict) else {}
        invoice_link = (
            links.get("telegramBotLink")
            or result.get("telegramBotLink")
            or result.get("link")
            or result.get("bot_invoice_url")
        )
        if not invoice_link:
            raise XRocketPayError(f"Invoice response has no Telegram link: {result}")
        return {
            **result,
            "invoice_id": str(result["id"]),
            "bot_invoice_url": str(invoice_link),
        }

    async def get_invoice(self, invoice_id: int | str) -> dict[str, Any] | None:
        result = await self.request(
            "GET",
            "invoice",
            query={"invoiceId": str(invoice_id)},
        )
        if not isinstance(result, dict):
            return None
        return {
            **result,
            "invoice_id": str(result.get("id", invoice_id)),
        }
