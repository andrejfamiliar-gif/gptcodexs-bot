from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import aiohttp


logger = logging.getLogger("tg-account-shop.crypto_pay")

# How long a fetched rate table stays usable. Short enough that a buyer never
# sees a badly stale price, long enough that a burst of buyers is one API call.
RATES_TTL_SECONDS = 120


class CryptoPayError(RuntimeError):
    pass


class CryptoPayClient:
    def __init__(self, token: str, base_url: str, accepted_assets: str) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.accepted_assets = accepted_assets
        self.session: aiohttp.ClientSession | None = None
        self._rates: dict[str, Decimal] = {}
        self._rates_at: datetime | None = None
        self._rates_lock = asyncio.Lock()

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
                "allow_anonymous": True,
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

    async def exchange_rates(self, fiat: str = "USD") -> tuple[dict[str, Decimal], datetime | None]:
        """Return ``{asset: units_of_fiat_per_1_asset}`` plus when it was fetched.

        Cached for ``RATES_TTL_SECONDS``. On a network or API failure the last
        good table is returned unchanged — the caller sees the older timestamp
        and can decide what to show. If nothing was ever fetched the mapping is
        empty, which callers must treat as "no rate available" rather than
        substituting a guess.
        """
        async with self._rates_lock:
            now = datetime.now(timezone.utc)
            fresh = (
                self._rates_at is not None
                and (now - self._rates_at).total_seconds() < RATES_TTL_SECONDS
            )
            if fresh:
                return dict(self._rates), self._rates_at
            try:
                result = await self.request("getExchangeRates")
            except (CryptoPayError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
                logger.warning("could not refresh exchange rates: %s", exc)
                return dict(self._rates), self._rates_at

            target = fiat.upper()
            rates: dict[str, Decimal] = {}
            for entry in result or []:
                if not isinstance(entry, dict) or not entry.get("is_valid", True):
                    continue
                if str(entry.get("target", "")).upper() != target:
                    continue
                try:
                    rate = Decimal(str(entry.get("rate")))
                except (InvalidOperation, TypeError):
                    continue
                if rate <= 0:
                    continue
                rates[str(entry.get("source", "")).upper()] = rate
            if rates:
                self._rates = rates
                self._rates_at = now
            else:
                logger.warning("exchange rate table had no usable %s pairs", target)
            return dict(self._rates), self._rates_at
