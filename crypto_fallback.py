from __future__ import annotations

"""A baked-in price list, used only when no live rate can be fetched.

Crypto Pay is the source of truth for rates. When its API is unreachable — or
simply has no entry for a coin the owner accepts — the bot used to have nothing
to quote, so the buyer got the fiat amount and had to work the conversion out
themselves. That is the case these numbers cover: a stale rate the buyer can see
is stale beats no number at all.

The rates were read off live markets on the date in ``CAPTURED_AT`` (Binance for
the majors, CoinGecko for the rest, cross-checked against each other). They are
frozen and will drift. Two things keep that from turning into a mispriced sale:

* every screen built from them shows ``CAPTURED_AT`` in place of a live
  timestamp, so nobody reads a week-old quote as current;
* a direct crypto transfer is credited by an admin against what actually
  arrived, not against what the bot quoted.

To refresh: replace the figures and move ``CAPTURED_AT`` to the day you read
them. Do not "adjust" one coin without moving the date.
"""

from decimal import Decimal


# The day the figures below were read, UTC. Shown to the buyer wherever a
# fallback rate is used.
CAPTURED_AT = "2026-08-21"

# USD per one unit of the coin. Tickers are Crypto Pay's spelling, upper-case.
FALLBACK_USD_RATES: dict[str, Decimal] = {
    # Stablecoins. Kept at their real quotes rather than a flat 1.00, so a
    # depegged reading is not silently rounded away.
    "USDT": Decimal("0.999646"),
    "USDC": Decimal("0.999771"),
    "DAI": Decimal("1.0"),
    # Majors.
    "BTC": Decimal("77316.51"),
    "ETH": Decimal("2388.79"),
    "BNB": Decimal("678.47"),
    "SOL": Decimal("90.88"),
    "XRP": Decimal("1.3779"),
    "LTC": Decimal("50.63"),
    "TRX": Decimal("0.3404"),
    "TON": Decimal("1.60"),
    "BCH": Decimal("262.17"),
    "XMR": Decimal("411.49"),
    # Mid-caps and the rest of the accepted table.
    "DOGE": Decimal("0.083757"),
    "ADA": Decimal("0.215717"),
    "DOT": Decimal("0.891271"),
    "AVAX": Decimal("7.53"),
    "MATIC": Decimal("0.126156"),
    "POL": Decimal("0.126156"),
    "XLM": Decimal("0.189967"),
    "NEAR": Decimal("1.88"),
    "NOT": Decimal("0.00044161"),
    "SHIB": Decimal("0.00000526"),
}


def fallback_rate(asset: str) -> Decimal | None:
    """USD per unit of ``asset`` from the frozen table, or ``None``.

    ``None`` means the coin is not in the table at all, which is a different
    situation from a stale rate: there is nothing to quote and the caller should
    keep showing the fiat amount.
    """
    rate = FALLBACK_USD_RATES.get(asset.strip().upper())
    if rate is None or rate <= 0:
        return None
    return rate
