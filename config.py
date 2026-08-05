from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from os import getenv
from pathlib import Path
from urllib.request import getproxies

from dotenv import load_dotenv


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


@dataclass(frozen=True)
class Product:
    key: str
    title: dict[str, str]
    price_cents: int


@dataclass(frozen=True)
class Settings:
    bot_token: str
    crypto_pay_token: str
    db_path: str
    support_username: str
    support_label: str
    support_link: str
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


def load_settings() -> Settings:
    bot_token = getenv("BOT_TOKEN", "").strip()
    crypto_pay_token = getenv("CRYPTO_PAY_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")
    if not crypto_pay_token:
        raise RuntimeError("CRYPTO_PAY_TOKEN is not set. Create an app in @CryptoBot first.")

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
    accepted_assets = getenv(
        "CRYPTO_ACCEPTED_ASSETS",
        "USDT,TON,BTC,ETH,LTC,BNB,TRX,USDC",
    ).strip()
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
    decrement_stock_on_payment = getenv("DECREMENT_STOCK_ON_PAYMENT", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    currency_rates = {
        "en": Decimal("1.00"),
        "zh": _decimal_env("CNY_PER_USD", "7.20"),
        "ru": _decimal_env("RUB_PER_USD", "80.00"),
    }
    products = {
        "gpt_plus_nw": Product(
            key="gpt_plus_nw",
            title={"ru": "ChatGPT Plus NW", "en": "ChatGPT Plus NW", "zh": "ChatGPT Plus NW"},
            price_cents=to_cents(_decimal_env("GPT_PLUS_NW_PRICE_USD", "2")),
        ),
        "gpt_plus_fw": Product(
            key="gpt_plus_fw",
            title={"ru": "ChatGPT Plus FW", "en": "ChatGPT Plus FW", "zh": "ChatGPT Plus FW"},
            price_cents=to_cents(_decimal_env("GPT_PLUS_FW_PRICE_USD", "4.5")),
        ),
        "pro_5x_nw": Product(
            key="pro_5x_nw",
            title={"ru": "GPT Pro/5x NW", "en": "GPT Pro/5x NW", "zh": "GPT Pro/5x NW"},
            price_cents=to_cents(_decimal_env("PRO_5X_NW_PRICE_USD", "45")),
        ),
        "pro_20x_nw": Product(
            key="pro_20x_nw",
            title={"ru": "GPT Pro/20x NW", "en": "GPT Pro/20x NW", "zh": "GPT Pro/20x NW"},
            price_cents=to_cents(_decimal_env("PRO_20X_NW_PRICE_USD", "135")),
        ),
    }
    regional_prices = {
        "gpt_plus_nw": {
            "en": products["gpt_plus_nw"].price_cents,
            "zh": _convert_usd_cents(products["gpt_plus_nw"].price_cents, currency_rates["zh"]),
            "ru": to_cents(_decimal_env("GPT_PLUS_NW_PRICE_RUB", "200")),
        },
        "gpt_plus_fw": {
            "en": products["gpt_plus_fw"].price_cents,
            "zh": _convert_usd_cents(products["gpt_plus_fw"].price_cents, currency_rates["zh"]),
            "ru": to_cents(_decimal_env("GPT_PLUS_FW_PRICE_RUB", "450")),
        },
        "pro_5x_nw": {
            "en": products["pro_5x_nw"].price_cents,
            "zh": _convert_usd_cents(products["pro_5x_nw"].price_cents, currency_rates["zh"]),
            "ru": to_cents(_decimal_env("PRO_5X_NW_PRICE_RUB", "2950")),
        },
        "pro_20x_nw": {
            "en": products["pro_20x_nw"].price_cents,
            "zh": _convert_usd_cents(products["pro_20x_nw"].price_cents, currency_rates["zh"]),
            "ru": to_cents(_decimal_env("PRO_20X_NW_PRICE_RUB", "5900")),
        },
    }

    return Settings(
        bot_token=bot_token,
        crypto_pay_token=crypto_pay_token,
        db_path=db_path,
        support_username=getenv("SUPPORT_USERNAME", "@codexrepIybot").strip() or "@codexrepIybot",
        support_label=getenv("SUPPORT_LABEL", "@admingpt").strip() or "@admingpt",
        support_link=getenv("SUPPORT_LINK", "https://t.me/codexrepIybot").strip()
        or "https://t.me/codexrepIybot",
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
    )


def format_usd(cents: int) -> str:
    return f"${cents / 100:.2f}"


def _convert_usd_cents(cents: int, rate: Decimal) -> int:
    return int((Decimal(cents) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def currency_for_language(language: str) -> str:
    return {"en": "USD", "zh": "CNY", "ru": "RUB"}.get(language, "USD")


def format_fiat_price(minor_units: int, currency: str) -> str:
    amount = Decimal(minor_units) / Decimal("100")
    formatted = f"{amount:.2f}"
    if currency == "RUB":
        return f"{formatted.replace('.', ',')} ₽"
    if currency == "CNY":
        return f"¥{formatted}"
    return f"${formatted}"


def format_local_price(cents: int, language: str, rates: dict[str, Decimal]) -> str:
    language = language if language in {"zh", "en", "ru"} else "en"
    amount = (Decimal(cents) / Decimal("100") * rates.get(language, Decimal("1.00"))).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    formatted = f"{amount:.2f}"
    if language == "zh":
        return f"¥{formatted}"
    if language == "ru":
        return f"{formatted.replace('.', ',')} ₽"
    return f"${formatted}"
