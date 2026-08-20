"""Offline smoke test for the SQLite layer, the address parser and Crypto Pay.

Run it with a throwaway database, no network and no secrets:

    python smoke_test.py

Nothing here touches the production database or the real Crypto Pay token. The
Crypto Pay client is exercised against a stub transport, so the test asserts how
the client behaves on well-formed, malformed and failing responses without ever
calling the live API.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

import aiohttp

from config import Product
from crypto_pay import CryptoPayClient
from crypto_wallets import load_wallets, parse_wallets
from database import Database

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {label}")
        return
    failures.append(label)
    print(f"  FAIL  {label}{(' — ' + detail) if detail else ''}")


BASE_PRODUCTS = {
    "plus_nw": Product(
        key="plus_nw",
        title={"ru": "GPT Plus NW", "en": "GPT Plus NW", "zh": "GPT Plus NW"},
        price_cents=500,
        category="plus",
    ),
    "pro_5x": Product(
        key="pro_5x",
        title={"ru": "GPT Pro 5x", "en": "GPT Pro 5x", "zh": "GPT Pro 5x"},
        price_cents=2500,
        category="pro",
    ),
}
REGIONAL = {
    "plus_nw": {"en": 500, "ru": 45000, "zh": 3600},
    "pro_5x": {"en": 2500, "ru": 225000, "zh": 18000},
}


async def test_catalog(db: Database) -> None:
    print("\n[catalog]")
    await db.ensure_product_catalog(BASE_PRODUCTS, REGIONAL, {"plus_nw": 3})
    rows = {r["product_key"]: r for r in await db.list_products()}
    check("base products seeded", set(rows) == {"plus_nw", "pro_5x"}, str(sorted(rows)))
    check("regional price applied", rows["plus_nw"]["price_rub_cents"] == 45000)
    check("display stock default applied", rows["plus_nw"]["display_stock"] == 3)

    # An admin edits a price, then the bot restarts and seeds again. The edit
    # must survive: this is the exact regression handoff §4.4 warns about.
    await db.update_product_prices("plus_nw", 777, 66600, 5550)
    await db.ensure_product_catalog(BASE_PRODUCTS, REGIONAL, {"plus_nw": 3})
    rows = {r["product_key"]: r for r in await db.list_products()}
    check("re-seed does not overwrite admin price", rows["plus_nw"]["price_usd_cents"] == 777,
          str(rows["plus_nw"]["price_usd_cents"]))

    created = await db.create_product("promo_x", "catalog", "Промо", "Promo", "促销", 199, 18000, 1400)
    check("new product created", created is True)
    duplicate = await db.create_product("promo_x", "catalog", "Промо", "Promo", "促销", 199, 18000, 1400)
    check("duplicate key rejected", duplicate is False)
    try:
        await db.create_product("bad_x", "catalog", "a", "a", "a", 0, 1, 1)
        check("zero price rejected", False, "no ValueError raised")
    except ValueError:
        check("zero price rejected", True)
    check("new product visible in catalog",
          "promo_x" in {r["product_key"] for r in await db.list_products()})

    check("price change applies", await db.update_product_prices("promo_x", 250, 22000, 1750) is True)
    check("price change on unknown key reports failure",
          await db.update_product_prices("no_such_key", 250, 22000, 1750) is False)

    check("display stock +5", await db.adjust_display_stock("promo_x", 5) == (0, 5))
    check("display stock clamps at zero", (await db.adjust_display_stock("promo_x", -99))[1] == 0)
    check("display stock set", (await db.set_display_stock("promo_x", 7))[1] == 7)
    check("display stock on unknown key returns None",
          await db.adjust_display_stock("no_such_key", 1) is None)


async def test_users(db: Database) -> None:
    print("\n[users]")
    await db.ensure_user(1001, "BuyerOne")
    await db.set_language(1001, "ru")
    found = await db.find_user_by_username("@buyerone")
    check("username lookup is case-insensitive and tolerates @",
          found is not None and int(found["user_id"]) == 1001)
    check("unknown username returns None", await db.find_user_by_username("@nobody") is None)

    check("notifications default on", await db.get_purchase_notifications(1001) is True)
    await db.set_purchase_notifications(1001, False)
    check("notifications turn off", await db.get_purchase_notifications(1001) is False)
    check("opted-out user excluded from notify list",
          1001 not in {int(r["user_id"]) for r in await db.list_purchase_notification_users()})
    await db.set_purchase_notifications(1001, True)
    check("notifications turn back on", await db.get_purchase_notifications(1001) is True)


async def test_stock_semantics(db: Database) -> None:
    print("\n[stock semantics]")
    # display_stock is a shop-window number; it must never conjure credentials.
    await db.set_display_stock("pro_5x", 4)
    actual = await db.actual_stock()
    available = await db.available_stock()
    check("no real payloads yet", actual.get("pro_5x", 0) == 0, str(actual))
    check("display counter shows in available", available.get("pro_5x", 0) == 4, str(available))
    await db.add_good("pro_5x", "smoke-test-payload-not-a-real-account")
    check("real payload counted", (await db.actual_stock()).get("pro_5x") == 1)


async def test_manual_payments(db: Database) -> None:
    print("\n[manual payments]")
    await db.ensure_user(2002, "PayerTwo")
    start_balance = await db.get_balance_cents(2002)

    pid = await db.create_manual_payment(
        user_id=2002, asset="USDT", network="TRC20", address="TAddrExample",
        amount_cents=1000, currency="USD", crypto_amount="10", rate="1", rate_at="2026-08-21 10:00",
    )
    row = await db.get_manual_payment(pid)
    check("created awaiting_hash", row is not None and row["status"] == "awaiting_hash")
    check("open request found", (await db.open_manual_payment_for_user(2002))["id"] == pid)

    check("hash rejected for the wrong user",
          await db.submit_manual_payment_hash(pid, 9999, "hash-aaa") is None)
    submitted = await db.submit_manual_payment_hash(pid, 2002, "hash-aaa")
    check("hash accepted", submitted is not None and submitted["status"] == "pending")
    check("second submit on the same row is refused",
          await db.submit_manual_payment_hash(pid, 2002, "hash-bbb") is None)
    check("pending row counted", await db.count_pending_manual_payments() == 1)
    check("pending list carries the username",
          (await db.list_pending_manual_payments())[0]["username"] == "PayerTwo")

    # A tx hash is public on any explorer, so a second user must not be able to
    # claim a transfer somebody else already reported.
    await db.ensure_user(3003, "PayerThree")
    other = await db.create_manual_payment(
        user_id=3003, asset="TON", network="TON", address="TonAddrExample",
        amount_cents=500, currency="USD", crypto_amount=None, rate=None, rate_at=None,
    )
    check("duplicate hash from another user is refused",
          await db.submit_manual_payment_hash(other, 3003, "hash-aaa") is None)
    check("cross-user hash lookup finds the original",
          (await db.find_manual_payment_by_hash("hash-aaa"))["user_id"] == 2002)
    check("own hash still accepted after the clash",
          await db.submit_manual_payment_hash(other, 3003, "hash-ccc") is not None)

    decided = await db.decide_manual_payment(pid, admin_id=7, approve=True)
    check("approval returns the row", decided is not None and decided["status"] == "confirmed")
    check("balance credited once", await db.get_balance_cents(2002) == start_balance + 1000,
          str(await db.get_balance_cents(2002)))
    check("second approval is refused (double-tap safe)",
          await db.decide_manual_payment(pid, admin_id=7, approve=True) is None)
    check("balance unchanged after the refused retry",
          await db.get_balance_cents(2002) == start_balance + 1000)

    rejected = await db.decide_manual_payment(other, admin_id=7, approve=False)
    check("rejection returns the row", rejected is not None and rejected["status"] == "rejected")
    check("rejection credits nothing", await db.get_balance_cents(3003) == 0)

    # Approving a payment whose user row is gone must roll back rather than
    # mark a payment confirmed that credited nobody. The foreign key normally
    # prevents such a row, so it is forged here with enforcement off — which is
    # how one could still arrive from a restored or migrated database, since
    # `PRAGMA foreign_keys` is per-connection and defaults to off.
    orphan = await db.create_manual_payment(
        user_id=2002, asset="BTC", network="Bitcoin", address="bc1example",
        amount_cents=250, currency="USD", crypto_amount=None, rate=None, rate_at=None,
    )
    await db.submit_manual_payment_hash(orphan, 2002, "hash-ddd")
    await db._conn().execute("PRAGMA foreign_keys = OFF")
    await db._conn().execute("UPDATE manual_payments SET user_id = 424242 WHERE id = ?", (orphan,))
    await db._conn().commit()
    await db._conn().execute("PRAGMA foreign_keys = ON")
    check("missing user aborts the approval",
          await db.decide_manual_payment(orphan, admin_id=7, approve=True) is None)
    check("aborted approval leaves the row pending",
          (await db.get_manual_payment(orphan))["status"] == "pending")
    await db._conn().execute("UPDATE manual_payments SET status = 'cancelled' WHERE id = ?", (orphan,))
    await db._conn().commit()

    fresh = await db.create_manual_payment(
        user_id=2002, asset="LTC", network="Litecoin", address="ltc1example",
        amount_cents=300, currency="USD", crypto_amount=None, rate=None, rate_at=None,
    )
    check("cancel by the wrong user is refused", await db.cancel_manual_payment(fresh, 9999) is False)
    check("cancel by the owner works", await db.cancel_manual_payment(fresh, 2002) is True)
    check("cancel is not repeatable", await db.cancel_manual_payment(fresh, 2002) is False)

    # A pending row is waiting on an admin, not on the buyer: the money may
    # already be on-chain, so expiry must never touch it.
    stale = await db.create_manual_payment(
        user_id=2002, asset="ETH", network="ERC20", address="0xexample",
        amount_cents=400, currency="USD", crypto_amount=None, rate=None, rate_at=None,
    )
    await db._conn().execute(
        "UPDATE manual_payments SET created_at = '2000-01-01T00:00:00+00:00' WHERE id IN (?, ?)",
        (stale, pid),
    )
    await db._conn().commit()
    expired = await db.expire_stale_manual_payments(24)
    check("stale awaiting_hash expired", expired == 1, f"expired={expired}")
    check("expired row marked", (await db.get_manual_payment(stale))["status"] == "expired")
    check("confirmed row untouched by expiry",
          (await db.get_manual_payment(pid))["status"] == "confirmed")


def test_wallet_parser() -> None:
    print("\n[wallet parser]")
    good = parse_wallets(
        "USDT | TRC20 | TXXXXXXXXXXXXXXXXXXXXXXXXX | yes\n"
        "USDT | ERC20 | 0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA | yes\n"
        "TON  | TON   | UQXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX | no\n"
    )
    check("only ENABLED rows are payable", [w.asset for w in good if w.enabled] == ["USDT", "USDT"])
    check("disabled row parsed but flagged off", any(not w.enabled for w in good))
    check("bad field count skipped", parse_wallets("USDT | TRC20") == ())
    check("placeholder address skipped", parse_wallets("USDT | TRC20 | TODO | yes") == ())
    check("address with a space skipped",
          parse_wallets("USDT | TRC20 | TXXXXXXXX XXXXXXXXXXXXX | yes") == ())
    dupes = parse_wallets(
        "USDT | TRC20 | TXXXXXXXXXXXXXXXXXXXXXXXXX | yes\n"
        "usdt | trc20 | TYYYYYYYYYYYYYYYYYYYYYYYYY | yes\n"
    )
    check("duplicate asset/network collapsed", len(dupes) == 1, str(len(dupes)))
    check("inline source beats the file",
          load_wallets("USDT | TRC20 | TZZZZZZZZZZZZZZZZZZZZZZZZZ | yes", "no_such_file.txt")[0].address
          == "TZZZZZZZZZZZZZZZZZZZZZZZZZ")
    check("missing file is not fatal", load_wallets(None, "no_such_file.txt") == ())
    check("no source at all is not fatal", load_wallets(None, None) == ())

    shipped = Path(__file__).with_name("crypto_wallets.txt")
    if shipped.exists():
        live = load_wallets(None, str(shipped))
        check("shipped table parses", len(live) > 0, f"{len(live)} rows")
        check("every shipped row names a network", all(w.network for w in live))
        check("no seed/private-key wording in the table",
              not any(bad in shipped.read_text(encoding="utf-8").lower()
                      for bad in ("private key:", "seed phrase:", "mnemonic:")))


class _StubResponse:
    def __init__(self, payload: object, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise aiohttp.ClientResponseError(None, (), status=self.status)  # type: ignore[arg-type]

    async def json(self, *args: object, **kwargs: object) -> object:
        return self._payload

    async def __aenter__(self) -> "_StubResponse":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _StubSession:
    """Stands in for aiohttp so no request ever leaves the machine."""

    def __init__(self, payload: object, status: int = 200, boom: bool = False) -> None:
        self._payload = payload
        self._status = status
        self._boom = boom
        self.calls: list[str] = []

    def post(self, url: str, **kwargs: object) -> _StubResponse:
        self.calls.append(url)
        if self._boom:
            raise aiohttp.ClientConnectionError("network down")
        return _StubResponse(self._payload, self._status)

    def get(self, url: str, **kwargs: object) -> _StubResponse:
        return self.post(url, **kwargs)

    async def close(self) -> None:
        return None


def _client(payload: object, **kwargs: object) -> CryptoPayClient:
    """A client wired to a stub transport. The token is a placeholder string;
    the real secret is never read by this test."""
    client = CryptoPayClient("smoke-test-not-a-real-token", "https://pay.crypt.bot", "USDT,TON")
    client.session = _StubSession(payload, **kwargs)  # type: ignore[assignment]
    return client


async def test_crypto_pay_mock() -> None:
    print("\n[crypto pay - mocked, no token, no network]")
    rates_payload = {
        "ok": True,
        "result": [
            {"source": "USDT", "target": "USD", "rate": "1.0", "is_valid": True},
            {"source": "TON", "target": "USD", "rate": "5.25", "is_valid": True},
            {"source": "BTC", "target": "EUR", "rate": "60000", "is_valid": True},
            {"source": "DOGE", "target": "USD", "rate": "0", "is_valid": True},
            {"source": "SOL", "target": "USD", "rate": "abc", "is_valid": True},
            {"source": "LTC", "target": "USD", "rate": "80", "is_valid": False},
        ],
    }
    client = _client(rates_payload)
    rates, fetched_at = await client.exchange_rates("USD")
    check("USD rate parsed", rates.get("USDT") == Decimal("1.0"), str(rates.get("USDT")))
    check("second asset parsed", rates.get("TON") == Decimal("5.25"))
    check("other fiat ignored", "BTC" not in rates, str(sorted(rates)))
    check("zero rate dropped", "DOGE" not in rates)
    check("unparsable rate dropped", "SOL" not in rates)
    check("is_valid=false dropped", "LTC" not in rates)
    check("fetch time reported", fetched_at is not None)

    calls_before = len(client.session.calls)  # type: ignore[union-attr]
    await client.exchange_rates("USD")
    check("TTL cache prevents a second call",
          len(client.session.calls) == calls_before,  # type: ignore[union-attr]
          str(len(client.session.calls)))  # type: ignore[union-attr]

    # A dead API must leave the last good table in place rather than reporting
    # a rate of zero, which would quote a nonsense crypto amount.
    client._rates_at = None
    client.session = _StubSession(None, boom=True)  # type: ignore[assignment]
    stale_rates, _ = await client.exchange_rates("USD")
    check("failure keeps the previous rates", stale_rates.get("USDT") == Decimal("1.0"))

    no_rates, no_time = await _client({"ok": False, "error": "unauthorized"}).exchange_rates("USD")
    check("error response yields no rates", no_rates == {} and no_time is None)

    http_rates, http_time = await _client(None, status=502).exchange_rates("USD")
    check("HTTP 502 yields no rates", http_rates == {} and http_time is None)

    fiat_miss, fiat_time = await _client(
        {"ok": True, "result": [{"source": "TON", "target": "EUR", "rate": "5", "is_valid": True}]}
    ).exchange_rates("USD")
    check("no matching fiat pair yields no rates", fiat_miss == {} and fiat_time is None)

    # An invoice request must carry the fiat amount and the configured assets,
    # and must not leak the token into the request body.
    invoice_client = _client({"ok": True, "result": {"invoice_id": 1, "pay_url": "https://x"}})
    sent: dict[str, object] = {}
    original_post = invoice_client.session.post  # type: ignore[union-attr]

    def spy(url: str, **kwargs: object) -> _StubResponse:
        sent.update(kwargs.get("json") or {})  # type: ignore[arg-type]
        return original_post(url, **kwargs)

    invoice_client.session.post = spy  # type: ignore[union-attr,assignment]
    invoice = await invoice_client.create_invoice(1000, "topup:1", "Balance top-up $10.00")
    check("invoice returned", invoice.get("invoice_id") == 1)
    check("invoice amount is fiat major units", sent.get("amount") == "10.00", str(sent.get("amount")))
    check("configured assets forwarded", sent.get("accepted_assets") == "USDT,TON")
    check("token not present in the request body",
          "smoke-test-not-a-real-token" not in str(sent))


def test_callback_data_budget() -> None:
    print("\n[callback_data budget]")
    from i18n import (
        mpay_admin_keyboard,
        mpay_asset_keyboard,
        mpay_network_keyboard,
        mpay_pending_keyboard,
        payment_method_keyboard,
    )

    markups = [
        payment_method_keyboard("ru", 1_000_000),
        mpay_asset_keyboard("ru", ["USDT", "USDC", "BTC", "ETH", "TON"], 1_000_000),
        mpay_network_keyboard("ru", "USDT", [(21, "Solana (SPL)")], 1_000_000),
        mpay_pending_keyboard("ru", 999_999_999),
        mpay_admin_keyboard(999_999_999),
    ]
    worst = 0
    for markup in markups:
        for row in markup.inline_keyboard:
            for button in row:
                if button.callback_data is None:
                    continue
                size = len(button.callback_data.encode("utf-8"))
                worst = max(worst, size)
                if size > 64:
                    check(f"callback_data over the limit: {button.callback_data}", False)
    check(f"worst-case callback_data is {worst} bytes (limit 64)", worst <= 64)


def test_button_styles() -> None:
    print("\n[coloured buttons]")
    from aiogram.enums import ButtonStyle
    from aiogram.types import InlineKeyboardButton

    from i18n import catalog_keyboard, plus_keyboard

    check("aiogram exposes InlineKeyboardButton.style",
          "style" in InlineKeyboardButton.model_fields)
    check("ButtonStyle has success/danger/primary",
          {ButtonStyle.SUCCESS, ButtonStyle.DANGER, ButtonStyle.PRIMARY} <= set(ButtonStyle))

    markup = catalog_keyboard("en", [("in_stock", "In stock", "$5", 4), ("sold_out", "Gone", "$5", 0)])
    buttons = [b for row in markup.inline_keyboard for b in row]
    check("stocked catalog item is green", buttons[0].style == ButtonStyle.SUCCESS, str(buttons[0].style))
    check("empty catalog item is red", buttons[1].style == ButtonStyle.DANGER, str(buttons[1].style))
    check("text marker duplicates the colour for old clients",
          buttons[0].text.startswith("🟢") and buttons[1].text.startswith("🔴"))

    styled = [b for row in plus_keyboard("en", None, {"gpt_plus_nw": 2, "gpt_plus_fw": 0}).inline_keyboard
              for b in row]
    check("plus keyboard colours by stock",
          [b.style for b in styled] == [ButtonStyle.SUCCESS, ButtonStyle.DANGER],
          str([b.style for b in styled]))
    # Unknown stock must not claim a state we cannot back up.
    unknown = [b for row in plus_keyboard("en").inline_keyboard for b in row]
    check("unknown stock leaves the button unstyled",
          all(b.style is None for b in unknown), str([b.style for b in unknown]))

    # A styled button must still serialise for the API; this is what fails hard
    # on aiogram < 3.30.
    check("styled button serialises with the style field",
          markup.model_dump(exclude_none=True)["inline_keyboard"][0][0].get("style") == "success")


async def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(str(Path(tmp) / "smoke.sqlite3"))
        await db.initialize()
        try:
            await test_catalog(db)
            await test_users(db)
            await test_stock_semantics(db)
            await test_manual_payments(db)
        finally:
            await db.close()
    test_wallet_parser()
    await test_crypto_pay_mock()
    test_callback_data_budget()
    test_button_styles()

    print()
    if failures:
        print(f"FAILED ({len(failures)}):")
        for name in failures:
            print(f"  - {name}")
        return 1
    print("all smoke checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
