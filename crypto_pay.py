from __future__ import annotations

from typing import Any

import aiohttp


class CryptoPayError(RuntimeError):
    pass


class CryptoPayClient:
    def __init__(self, token: str, base_url: str, accepted_assets: str) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.accepted_assets = accepted_assets
        self.session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"Crypto-Pay-API-Token": self.token},
        )

    async def close(self) -> None:
        if self.session is not None:
            await self.session.close()
            self.session = None

    async def request(self, method: str, parameters: dict[str, Any] | None = None) -> Any:
        if self.session is None:
            raise RuntimeError("Crypto Pay client is not started")
        async with self.session.post(
            f"{self.base_url}/api/{method}",
            json=parameters or {},
        ) as response:
            response.raise_for_status()
            data = await response.json()
        if not data.get("ok"):
            error = data.get("error") or {}
            raise CryptoPayError(str(error))
        return data.get("result")

    async def get_me(self) -> dict[str, Any]:
        return await self.request("getMe")

    async def create_invoice(
        self,
        amount_cents: int,
        payload: str,
        description: str,
        fiat: str = "USD",
    ) -> dict[str, Any]:
        return await self.request(
            "createInvoice",
            {
                "currency_type": "fiat",
                "fiat": fiat,
                "amount": f"{amount_cents / 100:.2f}",
                "accepted_assets": self.accepted_assets,
                "description": description[:1024],
                "payload": payload[:4096],
                "allow_comments": False,
                "allow_anonymous": False,
                "expires_in": 1800,
            },
        )

    async def get_invoice(self, invoice_id: int | str) -> dict[str, Any] | None:
        result = await self.request(
            "getInvoices",
            {"invoice_ids": str(invoice_id), "count": 1},
        )
        invoices = result.get("items", []) if isinstance(result, dict) else result
        return invoices[0] if invoices else None
