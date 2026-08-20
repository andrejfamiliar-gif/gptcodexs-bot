"""Parsing of the crypto receive-address table used for manual payments.

The table is deliberately kept outside the source code so the operator can add,
disable, or rotate an address without a redeploy. Two sources are supported:

* ``CRYPTO_WALLETS``      — the table itself, inline. Use this for a GitHub
  Actions secret, where there is no writable file to point at.
* ``CRYPTO_WALLETS_FILE`` — a path to the table on disk. Defaults to
  ``crypto_wallets.txt`` next to the bot.

Inline content wins when both are present.

Line format, ``|``-separated::

    ASSET | NETWORK | ADDRESS | ENABLED

Only rows with ``ENABLED`` set to yes/true/1/on are ever offered to a buyer.
A row whose address is missing or malformed is dropped with a warning: it is
better to show the buyer one fewer payment option than a broken address.

This module never holds private keys or seed phrases — receive addresses only.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass


logger = logging.getLogger("tg-account-shop.wallets")

_TRUTHY = {"yes", "true", "1", "on", "enabled"}
# Deliberately permissive: the per-network checksum rules live with the
# operator, not here. This only rejects obvious junk such as embedded spaces,
# markup, or a leftover placeholder.
_ADDRESS_RE = re.compile(r"[A-Za-z0-9:_\-]{20,120}")
_PLACEHOLDERS = {"", "-", "todo", "tbd", "xxx", "address", "<address>", "your_address"}


@dataclass(frozen=True)
class Wallet:
    asset: str
    network: str
    address: str
    enabled: bool

    @property
    def label(self) -> str:
        """Asset plus network, because a ticker alone is not payable."""
        return f"{self.asset} · {self.network}"


def parse_wallets(text: str) -> tuple[Wallet, ...]:
    wallets: list[Wallet] = []
    seen: set[tuple[str, str]] = set()
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 4:
            logger.warning("wallet table line %s: expected 4 fields, got %s", lineno, len(parts))
            continue
        asset, network, address, enabled_raw = parts
        if not asset or not network:
            logger.warning("wallet table line %s: asset and network are required", lineno)
            continue
        if address.lower() in _PLACEHOLDERS or not _ADDRESS_RE.fullmatch(address):
            logger.warning(
                "wallet table line %s: %s on %s has no usable address, skipped",
                lineno,
                asset,
                network,
            )
            continue
        key = (asset.upper(), network.lower())
        if key in seen:
            logger.warning(
                "wallet table line %s: duplicate %s on %s, keeping the first",
                lineno,
                asset,
                network,
            )
            continue
        seen.add(key)
        wallets.append(
            Wallet(
                asset=asset.upper(),
                network=network,
                address=address,
                enabled=enabled_raw.strip().lower() in _TRUTHY,
            )
        )
    return tuple(wallets)


def load_wallets(inline: str | None, path: str | None) -> tuple[Wallet, ...]:
    if inline and inline.strip():
        return parse_wallets(inline)
    if not path:
        return ()
    try:
        with open(path, encoding="utf-8") as handle:
            return parse_wallets(handle.read())
    except FileNotFoundError:
        logger.info("wallet table %s not found; manual crypto payment disabled", path)
        return ()
    except OSError as exc:
        logger.warning("could not read wallet table %s: %s", path, exc)
        return ()


def enabled_wallets(wallets: tuple[Wallet, ...]) -> tuple[Wallet, ...]:
    return tuple(wallet for wallet in wallets if wallet.enabled)
