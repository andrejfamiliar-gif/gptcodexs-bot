from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from os import getenv
from pathlib import Path
from urllib.request import getproxies
import re

from dotenv import load_dotenv

from crypto_wallets import Wallet, enabled_wallets, load_wallets
from i18n import LANGUAGES


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _decimal_env(name: str, default: str) -> Decimal:
    raw = getenv(name, default)
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise RuntimeError(f"{name} must be a valid decimal number") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def to_cents(value: Decimal) -> int:
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def product_title(title: str) -> dict[str, str]:
    """One product name, repeated for every language the bot speaks.

    Product names are brand names, so they read the same everywhere. Building
    the dict from ``LANGUAGES`` instead of writing it out per language means
    adding a language can never leave a buyer looking at a raw product key.
    """
    return {code: title for code in LANGUAGES}



@dataclass(frozen=True)
class Product:
    key: str
    title: dict[str, str]
    price_cents: int
    category: str = "catalog"
    discount_percent: int = 0
    description: str = ""


@dataclass(frozen=True)
class Settings:
    bot_token: str
    crypto_pay_token: str
    db_path: str
    support_username: str
    support_label: str
    support_link: str
    offer_link: str
    privacy_link: str
    admin_ids: tuple[int, ...]
    payment_poll_seconds: int
    crypto_pay_base_url: str
    accepted_assets: str
    telegram_proxy: str | None
    stock_display: dict[str, int]
    decrement_stock_on_payment: bool
    currency_rates: dict[str, Decimal]
    regional_prices: dict[str, dict[str, int]]
    products: dict[str, Product]
    crypto_wallets: tuple[Wallet, ...]
    manual_crypto_note_hours: int
    preorder_delivery_hours: int


def load_settings() -> Settings:
    bot_token = getenv("BOT_TOKEN", "").strip()
    crypto_pay_token = getenv("CRYPTO_PAY_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")
    if not crypto_pay_token:
        raise RuntimeError(
            "CRYPTO_PAY_TOKEN is not set. Create an app in @CryptoBot first."
        )

    raw_admin_ids = getenv("ADMIN_IDS", "").strip()
    admin_ids: list[int] = []
    for raw_id in raw_admin_ids.split(","):
        raw_id = raw_id.strip()
        if raw_id:
            try:
                admin_ids.append(int(raw_id))
            except ValueError as exc:
                raise RuntimeError("ADMIN_IDS must contain Telegram numeric IDs separated by commas") from exc

    try:
        payment_poll_seconds = int(getenv("PAYMENT_POLL_SECONDS", "15"))
    except ValueError as exc:
        raise RuntimeError("PAYMENT_POLL_SECONDS must be an integer") from exc
    if payment_poll_seconds < 5:
        raise RuntimeError("PAYMENT_POLL_SECONDS must be at least 5")

    db_path = getenv("DB_PATH", str(BASE_DIR / "shop.sqlite3")).strip()
    telegram_proxy = getenv("TELEGRAM_PROXY", "").strip() or getproxies().get("https") or getproxies().get("http")
    try:
        stock_display = {
            "gpt_plus_nw": int(getenv("DISPLAY_STOCK_GPT_PLUS_NW", getenv("DISPLAY_STOCK_GPT_PLUS", "4"))),
            "gpt_plus_fw": int(getenv("DISPLAY_STOCK_GPT_PLUS_FW", "4")),
            "pro_5x_nw": int(getenv("DISPLAY_STOCK_PRO_5X_NW", getenv("DISPLAY_STOCK_PRO_5X", "6"))),
            "pro_20x_nw": int(getenv("DISPLAY_STOCK_PRO_20X_NW", getenv("DISPLAY_STOCK_PRO_20X", "1"))),
        }
    except ValueError as exc:
        raise RuntimeError("DISPLAY_STOCK_* values must be integers") from exc
    if any(value < 0 for value in stock_display.values()):
        raise RuntimeError("DISPLAY_STOCK_* values cannot be negative")
    accepted_assets = getenv(
        "CRYPTO_ACCEPTED_ASSETS",
        "USDT,TON,BTC,ETH,LTC,BNB,TRX,USDC",
    ).strip()
    if not accepted_assets:
        raise RuntimeError("CRYPTO_ACCEPTED_ASSETS cannot be empty")
    decrement_stock_on_payment = getenv("DECREMENT_STOCK_ON_PAYMENT", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    currency_rates = {
        "en": Decimal("1.00"),
        "zh": _decimal_env("CNY_PER_USD", "7.20"),
        "ru": _decimal_env("RUB_PER_USD", "80.00"),
        "vi": _decimal_env("VND_PER_USD", "26000.00"),
        "hi": _decimal_env("INR_PER_USD", "88.00"),
    }
    products = {
        "gpt_plus_nw": Product(
            key="gpt_plus_nw",
            title=product_title("ChatGPT Plus NW"),
            price_cents=to_cents(_decimal_env("GPT_PLUS_NW_PRICE_USD", "1.63")),
            category="plus",
        ),
        "gpt_plus_fw": Product(
            key="gpt_plus_fw",
            title=product_title("ChatGPT Plus FW"),
            price_cents=to_cents(_decimal_env("GPT_PLUS_FW_PRICE_USD", "3.75")),
            category="plus",
        ),
        "pro_5x_nw": Product(
            key="pro_5x_nw",
            title=product_title("GPT Pro/5x NW"),
            price_cents=to_cents(_decimal_env("PRO_5X_NW_PRICE_USD", "20.63")),
            category="pro",
        ),
        "pro_20x_nw": Product(
            key="pro_20x_nw",
            title=product_title("GPT Pro/20x NW"),
            price_cents=to_cents(_decimal_env("PRO_20X_NW_PRICE_USD", "41.88")),
            category="pro",
        ),
    }
    # Local prices are derived from the USD source price. The admin panel only
    # asks for USD; using one conversion path prevents regional prices from
    # drifting apart after an edit or a restart.
    regional_prices = {
        key: {
            language: convert_usd_cents(product.price_cents, rate)
            for language, rate in currency_rates.items()
        }
        for key, product in products.items()
    }

    # Manual crypto payment: only enabled rows ever reach a buyer. An inline
    # CRYPTO_WALLETS value wins over the file so the table can live in a
    # GitHub Actions secret, where there is nothing to point a path at.
    crypto_wallets = enabled_wallets(
        load_wallets(
            getenv("CRYPTO_WALLETS"),
            getenv("CRYPTO_WALLETS_FILE", str(BASE_DIR / "crypto_wallets.txt")).strip(),
        )
    )
    try:
        manual_crypto_note_hours = int(getenv("MANUAL_CRYPTO_NOTE_HOURS", "24"))
    except ValueError as exc:
        raise RuntimeError("MANUAL_CRYPTO_NOTE_HOURS must be an integer") from exc
    if manual_crypto_note_hours < 1:
        raise RuntimeError("MANUAL_CRYPTO_NOTE_HOURS must be at least 1")

    # How long a paid-but-unstocked order may wait. The buyer is quoted this
    # figure, so it is a promise, not a guess — keep it at whatever the owner can
    # actually honour once accounts are loaded.
    try:
        preorder_delivery_hours = int(getenv("PREORDER_DELIVERY_HOURS", "24"))
    except ValueError as exc:
        raise RuntimeError("PREORDER_DELIVERY_HOURS must be an integer") from exc
    if preorder_delivery_hours < 1:
        raise RuntimeError("PREORDER_DELIVERY_HOURS must be at least 1")

    return Settings(
        bot_token=bot_token,
        crypto_pay_token=crypto_pay_token,
        db_path=db_path,
        # Kept as optional compatibility fields for older .env files. Customer
        # support is handled only through in-bot tickets; these values are no
        # longer rendered or used as outbound support links.
        support_username=getenv("SUPPORT_USERNAME", "").strip(),
        support_label=getenv("SUPPORT_LABEL", "").strip(),
        support_link=getenv("SUPPORT_LINK", "").strip(),
        offer_link=getenv(
            "OFFER_LINK",
            "https://telegra.ph/GPT-Codex-Shop-Terms-of-Sale-and-Public-Offer-08-05",
        ).strip(),
        privacy_link=getenv(
            "PRIVACY_LINK",
            "https://telegra.ph/GPT-Codex-Shop-Privacy-Policy-08-05",
        ).strip(),
        admin_ids=tuple(admin_ids),
        payment_poll_seconds=payment_poll_seconds,
        crypto_pay_base_url=getenv("CRYPTO_PAY_BASE_URL", "https://pay.crypt.bot").rstrip("/"),
        accepted_assets=accepted_assets,
        telegram_proxy=telegram_proxy,
        stock_display=stock_display,
        decrement_stock_on_payment=decrement_stock_on_payment,
        currency_rates=currency_rates,
        regional_prices=regional_prices,
        products=products,
        crypto_wallets=crypto_wallets,
        manual_crypto_note_hours=manual_crypto_note_hours,
        preorder_delivery_hours=preorder_delivery_hours,
    )


def format_usd(cents: int) -> str:
    return f"${cents / 100:.2f}"


def convert_usd_cents(cents: int, rate: Decimal) -> int:
    return int((Decimal(cents) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _regional_price(env_name: str, usd_cents: int, rate: Decimal, default: str | None = None) -> int:
    """A price in one local currency, in that currency's minor units.

    A pinned figure wins, because a round local price looks deliberate in a way
    that a converted one does not. With nothing pinned the price is the USD one
    at the configured rate, so a new currency needs no per-product setup.
    """
    raw = (getenv(env_name, "") or "").strip() or (default or "")
    if not raw:
        return convert_usd_cents(usd_cents, rate)
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise RuntimeError(f"{env_name} must be a valid decimal number") from exc
    if value <= 0:
        raise RuntimeError(f"{env_name} must be greater than zero")
    return to_cents(value)


def currency_for_language(language: str) -> str:
    return {
        "en": "USD",
        "zh": "CNY",
        "ru": "RUB",
        "vi": "VND",
        "hi": "INR",
    }.get(language, "USD")


def format_fiat_price(minor_units: int, currency: str) -> str:
    amount = Decimal(minor_units) / Decimal("100")
    if currency == "VND":
        # The đồng has no practical minor unit, and Vietnamese groups thousands
        # with dots: 42.380 ₫, not 42,380.00 ₫.
        whole = amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return f"{whole:,} ₫".replace(",", ".")
    formatted = f"{amount:.2f}"
    if currency == "RUB":
        return f"{formatted.replace('.', ',')} ₽"
    if currency == "CNY":
        return f"¥{formatted}"
    if currency == "INR":
        # Grouped, because ₹3,685.44 is easier to read at a glance than
        # ₹3685.44. Prices stay under a lakh, where Indian grouping and Western
        # grouping agree, so a plain comma is correct.
        return f"₹{amount:,.2f}"
    return f"${formatted}"


def local_amount_minor(cents: int, language: str, rates: dict[str, Decimal]) -> int:
    """USD cents expressed in the minor units of the buyer's currency."""
    if language not in rates:
        language = "en"
    amount = (Decimal(cents) / Decimal("100") * rates[language]).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_local_price(cents: int, language: str, rates: dict[str, Decimal]) -> str:
    """USD cents shown in the buyer's own currency.

    Any language with a rate is priced in its own currency; anything unknown
    falls back to dollars, which is the one wrong answer that cannot mislead —
    unlike printing a dollar figure under a ₫ sign.
    """
    if language not in rates:
        language = "en"
    return format_fiat_price(
        local_amount_minor(cents, language, rates),
        currency_for_language(language),
    )


def format_local_amount_plain(cents: int, language: str, rates: dict[str, Decimal]) -> str:
    """The same figure as ``format_local_price``, bare.

    Used for "for example 130 000" hints, which have to be something the buyer
    can literally type back — a grouped, symbol-bearing price is not.
    """
    currency = currency_for_language(language if language in rates else "en")
    amount = Decimal(local_amount_minor(cents, language, rates)) / Decimal("100")
    if currency == "VND":
        return str(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    text = f"{amount:.2f}"
    return text.replace(".", ",") if currency == "RUB" else text


_GROUPED_THOUSANDS = re.compile(r"\d{1,3}(,\d{3})+")


def _normalise_typed_number(text: str, currency: str) -> str:
    """Turn what a buyer typed into something ``Decimal`` accepts.

    Separators mean different things in different places: a comma is a decimal
    point in Russian, a thousands separator in English and Indian, and either of
    those in Vietnamese, which has no minor units at all. Guessing wrong is a
    hundredfold error in the amount, so each case is handled rather than
    blanket-replacing "," with ".".
    """
    for space in (" ", " ", " ", "	"):
        text = text.replace(space, "")
    text = text.strip()
    if currency == "VND":
        # No minor unit, so a dot or comma here groups thousands: "130.000" and
        # "130,000" both mean a hundred and thirty thousand, never a hundred
        # and thirty.
        return text.replace(".", "").replace(",", "")
    if "," in text and "." in text:
        # Whichever comes last is the decimal separator; the other one groups.
        if text.rfind(",") > text.rfind("."):
            return text.replace(".", "").replace(",", ".")
        return text.replace(",", "")
    if _GROUPED_THOUSANDS.fullmatch(text):
        # "1,650" is one thousand six hundred and fifty, not one point six five.
        return text.replace(",", "")
    return text.replace(",", ".")


def parse_local_amount_cents(
    raw_value: str,
    language: str,
    rates: dict[str, Decimal],
) -> int | None:
    """An amount the buyer typed in their own currency, as USD cents.

    Balances are kept in USD cents, so the conversion happens here rather than
    letting a figure in dong be read as dollars: 130000 typed by a Vietnamese
    buyer is five dollars, not a hundred and thirty thousand.
    """
    if language not in rates:
        language = "en"
    try:
        amount = Decimal(_normalise_typed_number(raw_value, currency_for_language(language)))
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    usd = (amount / rates[language]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if usd <= 0 or usd > Decimal("10000"):
        return None
    return int((usd * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
