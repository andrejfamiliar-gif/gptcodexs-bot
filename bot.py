from __future__ import annotations

import asyncio
import html
import logging
import secrets
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from config import (
    Product,
    Settings,
    currency_for_language,
    format_fiat_price,
    format_local_price,
    format_usd,
    load_settings,
)
from crypto_pay import CryptoPayClient
from database import Database
from i18n import (
    LANGUAGES,
    action_for_text,
    balance_keyboard,
    help_keyboard,
    language_keyboard,
    main_keyboard,
    payment_keyboard,
    plus_keyboard,
    pro_keyboard,
    queue_button_keyboard,
    queue_keyboard,
    queue_payment_keyboard,
    queue_purchase_keyboard,
    queue_quantity_keyboard,
    t,
    top_up_keyboard,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("tg-account-shop")
router = Router()


@dataclass
class Runtime:
    settings: Settings
    db: Database
    crypto: CryptoPayClient


runtime: Runtime | None = None


class TopUpStates(StatesGroup):
    waiting_amount = State()


def get_runtime() -> Runtime:
    if runtime is None:
        raise RuntimeError("Bot runtime is not initialized")
    return runtime


def user_id_from_message(message: Message) -> int:
    if message.from_user is None:
        raise RuntimeError("Telegram user is missing")
    return message.from_user.id


async def ensure_message_user(message: Message, referrer_id: int | None = None) -> str | None:
    rt = get_runtime()
    user = message.from_user
    if user is None:
        return None
    return await rt.db.ensure_user(user.id, user.username, referrer_id)


async def ensure_callback_user(callback: CallbackQuery) -> str | None:
    rt = get_runtime()
    return await rt.db.ensure_user(callback.from_user.id, callback.from_user.username)


async def selected_language(message: Message) -> str | None:
    language = await ensure_message_user(message)
    if language not in LANGUAGES:
        return None
    return language


def is_admin(user_id: int) -> bool:
    return user_id in get_runtime().settings.admin_ids


def product_for_action(action: str, settings: Settings) -> Product | None:
    return {
        "plus": settings.products.get("gpt_plus_nw"),
    }.get(action)


def localized_price(settings: Settings, language: str, amount_cents: int) -> str:
    return format_local_price(amount_cents, language, settings.currency_rates)


def product_amount(settings: Settings, product: Product, language: str) -> int:
    return settings.regional_prices.get(product.key, {}).get(language, product.price_cents)


def product_price(settings: Settings, product: Product, language: str) -> str:
    return format_fiat_price(product_amount(settings, product, language), currency_for_language(language))


def product_price_labels(settings: Settings, language: str) -> dict[str, str]:
    return {
        key: product_price(settings, product, language)
        for key, product in settings.products.items()
    }


def top_up_price_labels(settings: Settings, language: str) -> dict[int, str]:
    return {
        amount: localized_price(settings, language, amount * 100)
        for amount in (2, 5, 10)
    }


def support_contact(settings: Settings) -> str:
    label = html.escape(settings.support_label or settings.support_username)
    link = html.escape(settings.support_link or settings.support_username, quote=True)
    return f'<a href="{link}">{label}</a>'


async def send_language_prompt(message: Message) -> None:
    await message.answer("请选择语言：", reply_markup=language_keyboard())


async def create_payment_for_order(
    user_id: int,
    product_key: str,
    amount_cents: int,
    description: str,
    fiat: str = "USD",
) -> tuple[int, dict[str, object]]:
    rt = get_runtime()
    order_token = secrets.token_urlsafe(18)
    invoice = await rt.crypto.create_invoice(
        amount_cents=amount_cents,
        payload=f"order:{order_token}",
        description=description,
        fiat=fiat,
    )
    order_id = await rt.db.create_order(
        user_id=user_id,
        product_key=product_key,
        amount_cents=amount_cents,
        order_token=order_token,
        invoice_id=invoice["invoice_id"],
    )
    return order_id, invoice


async def deliver_pending_orders(bot: Bot) -> None:
    rt = get_runtime()
    for order in await rt.db.get_pending_deliveries():
        claimed = await rt.db.claim_delivery(order["id"])
        if claimed is None:
            continue
        language = await rt.db.get_language(order["user_id"]) or "en"
        try:
            if order["product_key"] == "balance_topup":
                balance_cents = await rt.db.get_balance_cents(order["user_id"])
                await bot.send_message(
                    order["user_id"],
                    t(
                        language,
                        "delivery_balance",
                        amount=localized_price(rt.settings, language, order["amount_cents"]),
                        balance=localized_price(rt.settings, language, balance_cents),
                    ),
                )
            else:
                product = rt.settings.products.get(order["product_key"])
                product_name = product.title.get(language, product.key) if product else order["product_key"]
                await bot.send_message(
                    order["user_id"],
                    t(
                        language,
                        "delivery_account",
                        product=html.escape(product_name),
                        payload=html.escape(order["delivery_payload"] or ""),
                    ),
                )
            await rt.db.mark_delivery_sent(order["id"])
        except Exception:
            await rt.db.reset_delivery(order["id"])
            logger.exception("Could not deliver order %s", order["id"])


async def settle_invoice(bot: Bot, order_id: int) -> dict[str, object] | None:
    rt = get_runtime()
    settlement = await rt.db.settle_paid_order(
        order_id,
        decrement_stock=rt.settings.decrement_stock_on_payment,
    )
    if settlement is not None and settlement["delivery_status"] == "waiting_stock":
        language = await rt.db.get_language(settlement["user_id"]) or "en"
        await bot.send_message(
            settlement["user_id"],
            t(language, "no_stock_after_payment", support=support_contact(rt.settings)),
        )
    await deliver_pending_orders(bot)
    return settlement


async def notify_waitlist_for_product(bot: Bot, product_key: str) -> None:
    rt = get_runtime()
    product = rt.settings.products.get(product_key)
    if product is None:
        return
    for row in await rt.db.get_waitlist_users(product_key):
        user_id = row["user_id"]
        language = await rt.db.get_language(user_id) or "en"
        product_name = product.title.get(language, product.key)
        try:
            await bot.send_message(
                user_id,
                t(language, "queue_available", product=html.escape(product_name)),
                reply_markup=queue_purchase_keyboard(language, product_key),
            )
            await rt.db.mark_waitlist_notified(user_id, product_key)
        except Exception:
            logger.exception("Could not notify waitlist user %s for %s", user_id, product_key)


async def payment_watcher(bot: Bot) -> None:
    rt = get_runtime()
    while True:
        try:
            for order in await rt.db.get_pending_orders():
                try:
                    invoice = await rt.crypto.get_invoice(order["invoice_id"])
                    if invoice is None:
                        continue
                    if invoice.get("status") == "paid":
                        await settle_invoice(bot, order["id"])
                    elif invoice.get("status") == "expired":
                        await rt.db.mark_order_expired(order["id"])
                except Exception:
                    logger.exception("Could not refresh invoice for order %s", order["id"])

            if rt.settings.decrement_stock_on_payment:
                for order in await rt.db.get_waiting_stock_orders():
                    if await rt.db.try_fulfill_waiting_order(order["id"]):
                        logger.info("Stock restored; order %s is ready for delivery", order["id"])
            await deliver_pending_orders(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Payment watcher iteration failed")
        await asyncio.sleep(rt.settings.payment_poll_seconds)


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    referrer_id: int | None = None
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("ref_"):
        try:
            referrer_id = int(parts[1][4:])
        except ValueError:
            referrer_id = None
    language = await ensure_message_user(message, referrer_id)
    if language not in LANGUAGES:
        await send_language_prompt(message)
        return
    await message.answer(t(language, "welcome"), reply_markup=main_keyboard(language))


@router.callback_query(F.data.startswith("lang:"))
async def language_callback(callback: CallbackQuery) -> None:
    rt = get_runtime()
    code = (callback.data or "").split(":", maxsplit=1)[1]
    if code not in LANGUAGES:
        await callback.answer("Unknown language", show_alert=True)
        return
    await ensure_callback_user(callback)
    await rt.db.set_language(callback.from_user.id, code)
    await callback.answer(t(code, "language_saved"))
    if callback.message is not None:
        try:
            await callback.message.edit_text(t(code, "language_saved"))
        except TelegramBadRequest:
            pass
        await callback.message.answer(t(code, "welcome"), reply_markup=main_keyboard(code))


@router.message(Command("language"))
async def language_command(message: Message) -> None:
    language = await selected_language(message)
    if language is None:
        await send_language_prompt(message)
        return
    await message.answer(t(language, "choose_language"), reply_markup=language_keyboard())


@router.message(Command("balance"))
async def balance_command(message: Message) -> None:
    language = await selected_language(message)
    if language is None:
        await send_language_prompt(message)
        return
    rt = get_runtime()
    balance = await rt.db.get_balance_cents(user_id_from_message(message))
    await message.answer(
        t(language, "balance", balance=localized_price(rt.settings, language, balance)),
        reply_markup=top_up_keyboard(language, top_up_price_labels(rt.settings, language)),
    )


@router.message(Command("invite"))
async def invite_command(message: Message, bot: Bot) -> None:
    language = await selected_language(message)
    if language is None:
        await send_language_prompt(message)
        return
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{user_id_from_message(message)}"
    await message.answer(t(language, "invite", link=html.escape(link)))


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    language = await selected_language(message)
    if language is None:
        await send_language_prompt(message)
        return
    rt = get_runtime()
    await message.answer(
        t(language, "help", support=support_contact(rt.settings)),
        reply_markup=help_keyboard(
            language,
            rt.settings.support_link,
            rt.settings.offer_link,
            rt.settings.privacy_link,
        ),
    )


@router.callback_query(F.data == "topup")
async def topup_menu_callback(callback: CallbackQuery) -> None:
    language = await ensure_callback_user(callback)
    if language not in LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        rt = get_runtime()
        await callback.message.answer(
            t(language, "top_up"),
            reply_markup=top_up_keyboard(language, top_up_price_labels(rt.settings, language)),
        )


@router.callback_query(F.data.startswith("topup:"))
async def topup_amount_callback(callback: CallbackQuery, state: FSMContext) -> None:
    rt = get_runtime()
    language = await ensure_callback_user(callback)
    if language not in LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    choice = (callback.data or "").split(":", maxsplit=1)[1]
    if choice == "other":
        await state.set_state(TopUpStates.waiting_amount)
        await callback.answer()
        if callback.message is not None:
            await callback.message.answer(t(language, "top_up_other"))
        return
    try:
        amount_cents = int(choice)
    except ValueError:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await send_topup_invoice(callback.message, callback.from_user.id, language, amount_cents)


def parse_amount_cents(raw_value: str) -> int | None:
    try:
        amount = Decimal(raw_value.strip().replace(",", "."))
    except InvalidOperation:
        return None
    if amount <= 0 or amount > Decimal("10000"):
        return None
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


async def send_topup_invoice(message: Message, user_id: int, language: str, amount_cents: int) -> None:
    rt = get_runtime()
    if amount_cents < 1 or amount_cents > 1_000_000:
        await message.answer(t(language, "top_up_invalid"))
        return
    try:
        order_id, invoice = await create_payment_for_order(
            user_id=user_id,
            product_key="balance_topup",
            amount_cents=amount_cents,
            description=f"Balance top-up {format_usd(amount_cents)}",
        )
    except Exception:
        logger.exception("Could not create top-up invoice")
        await message.answer(t(language, "payment_error", support=support_contact(rt.settings)))
        return
    await message.answer(
        t(
            language,
            "top_up_invoice",
            amount=localized_price(rt.settings, language, amount_cents),
            usd_amount=format_usd(amount_cents),
        ),
        reply_markup=payment_keyboard(language, str(invoice["bot_invoice_url"]), order_id),
    )


@router.message(TopUpStates.waiting_amount)
async def custom_topup_amount_handler(message: Message, state: FSMContext) -> None:
    language = await selected_language(message)
    if language is None:
        await state.clear()
        await send_language_prompt(message)
        return
    amount_cents = parse_amount_cents(message.text or "")
    if amount_cents is None:
        await message.answer(t(language, "top_up_invalid"))
        return
    await state.clear()
    await send_topup_invoice(message, user_id_from_message(message), language, amount_cents)


async def product_message(
    message: Message,
    product: Product,
    language: str,
    buyer_id: int | None = None,
) -> None:
    rt = get_runtime()
    if rt.settings.stock_display.get(product.key, 0) <= 0:
        await message.answer(
            t(language, "product_out_of_stock"),
            reply_markup=queue_button_keyboard(language, product.key),
        )
        return
    amount_cents = product_amount(rt.settings, product, language)
    fiat = currency_for_language(language)
    try:
        order_id, invoice = await create_payment_for_order(
            user_id=buyer_id or user_id_from_message(message),
            product_key=product.key,
            amount_cents=amount_cents,
            description=f"{product.title.get(language, product.key)} - {format_fiat_price(amount_cents, fiat)}",
            fiat=fiat,
        )
    except Exception:
        logger.exception("Could not create product invoice")
        await message.answer(
            t(language, "payment_error", support=support_contact(rt.settings)),
            reply_markup=main_keyboard(language),
        )
        return
    await message.answer(
        t(
            language,
            "product_invoice",
            product=product.title.get(language, product.key),
            amount=format_fiat_price(amount_cents, fiat),
            usd_amount=format_fiat_price(amount_cents, fiat),
        ),
        reply_markup=payment_keyboard(language, str(invoice["bot_invoice_url"]), order_id),
    )


@router.callback_query(F.data.startswith("product:"))
async def product_choice_callback(callback: CallbackQuery) -> None:
    rt = get_runtime()
    language = await ensure_callback_user(callback)
    if language not in LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    product_key = (callback.data or "").split(":", maxsplit=1)[1]
    product = rt.settings.products.get(product_key)
    if product is None:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await product_message(callback.message, product, language, callback.from_user.id)


@router.callback_query(F.data.startswith("buy:"))
async def queued_product_buy_callback(callback: CallbackQuery) -> None:
    rt = get_runtime()
    language = await ensure_callback_user(callback)
    if language not in LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    product_key = (callback.data or "").split(":", maxsplit=1)[1]
    product = rt.settings.products.get(product_key)
    if product is None:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await product_message(callback.message, product, language, callback.from_user.id)


@router.callback_query(F.data.startswith("queue:"))
async def queue_product_callback(callback: CallbackQuery) -> None:
    rt = get_runtime()
    language = await ensure_callback_user(callback)
    if language not in LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    product_key = (callback.data or "").split(":", maxsplit=1)[1]
    product = rt.settings.products.get(product_key)
    if product is None:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            t(language, "queue_choose_quantity"),
            reply_markup=queue_quantity_keyboard(language, product_key),
        )


@router.callback_query(F.data.startswith("queue_qty:"))
async def queue_quantity_callback(callback: CallbackQuery) -> None:
    rt = get_runtime()
    language = await ensure_callback_user(callback)
    if language not in LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 3:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    product_key = parts[1]
    try:
        quantity = int(parts[2])
    except ValueError:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    if quantity not in {1, 2, 3, 5}:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    product = rt.settings.products.get(product_key)
    if product is None:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return

    await callback.answer()
    fiat = currency_for_language(language)
    total_cents = product_amount(rt.settings, product, language) * quantity
    product_name = product.title.get(language, product.key)
    try:
        invoice = await rt.crypto.create_invoice(
            amount_cents=total_cents,
            payload=f"queue:{secrets.token_urlsafe(18)}",
            description=f"Queue {product_name} x{quantity} - {format_fiat_price(total_cents, fiat)}",
            fiat=fiat,
        )
    except Exception:
        logger.exception("Could not create queue invoice")
        if callback.message is not None:
            await callback.message.answer(
                t(language, "payment_error", support=support_contact(rt.settings))
            )
        return
    if callback.message is not None:
        await callback.message.answer(
                t(
                    language,
                    "queue_invoice",
                    product=html.escape(product_name),
                    quantity=quantity,
                    amount=format_fiat_price(total_cents, fiat),
                    usd_amount=format_fiat_price(total_cents, fiat),
                ),
            reply_markup=queue_payment_keyboard(language, str(invoice["bot_invoice_url"])),
        )


@router.callback_query(F.data.startswith("check:"))
async def check_payment_callback(callback: CallbackQuery, bot: Bot) -> None:
    rt = get_runtime()
    language = await ensure_callback_user(callback)
    if language not in LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    try:
        order_id = int((callback.data or "").split(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    order = await rt.db.get_order(order_id)
    if order is None or order["user_id"] != callback.from_user.id:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    if order["status"] == "expired":
        await callback.answer(t(language, "payment_expired"), show_alert=True)
        return
    if order["status"] == "paid":
        await deliver_pending_orders(bot)
        await callback.answer(
            t(language, "top_up_confirmed" if order["product_key"] == "balance_topup" else "payment_confirmed")
        )
        return
    invoice = await rt.crypto.get_invoice(order["invoice_id"])
    if invoice is None:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    if invoice.get("status") == "paid":
        settlement = await settle_invoice(bot, order_id)
        if settlement is not None and settlement["delivery_status"] == "waiting_stock":
            await callback.answer(
                t(language, "no_stock_after_payment", support=html.escape(rt.settings.support_label)),
                show_alert=True,
            )
        else:
            await callback.answer(
                t(language, "top_up_confirmed" if order["product_key"] == "balance_topup" else "payment_confirmed")
            )
    elif invoice.get("status") == "expired":
        await rt.db.mark_order_expired(order_id)
        await callback.answer(t(language, "payment_expired"), show_alert=True)
    else:
        await callback.answer(t(language, "payment_pending"), show_alert=True)


@router.message(Command("add_good"))
async def add_good_command(message: Message) -> None:
    if not is_admin(user_id_from_message(message)):
        await message.answer(t("en", "admin_only"))
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(t("en", "admin_add_usage"))
        return
    aliases = {
        "plus": "gpt_plus_nw",
        "gpt_plus": "gpt_plus_nw",
        "gpt_plus_nw": "gpt_plus_nw",
        "plus_nw": "gpt_plus_nw",
        "gpt_plus_fw": "gpt_plus_fw",
        "plus_fw": "gpt_plus_fw",
        "pro5x": "pro_5x_nw",
        "pro_5x": "pro_5x_nw",
        "pro_5x_nw": "pro_5x_nw",
        "pro5x_nw": "pro_5x_nw",
        "pro": "pro_20x_nw",
        "pro20x": "pro_20x_nw",
        "pro_20x": "pro_20x_nw",
        "pro_20x_nw": "pro_20x_nw",
        "pro20x_nw": "pro_20x_nw",
    }
    product_key = aliases.get(parts[1].lower())
    rt = get_runtime()
    if product_key not in rt.settings.products:
        await message.answer(t("en", "admin_add_usage"))
        return
    good_id = await rt.db.add_good(product_key, parts[2])
    await message.answer(t("en", "admin_good_added", product=product_key, good_id=good_id))


@router.message(Command("stock"))
async def stock_command(message: Message) -> None:
    if not is_admin(user_id_from_message(message)):
        await message.answer(t("en", "admin_only"))
        return
    stock = await get_runtime().db.available_stock()
    if not stock:
        text = t("en", "stock_empty")
    else:
        text = "\n".join(f"{key}: {count}" for key, count in sorted(stock.items()))
    await message.answer(t("en", "admin_stock", stock=text))


@router.message(F.text)
async def menu_handler(message: Message, bot: Bot) -> None:
    language = await selected_language(message)
    if language is None:
        await send_language_prompt(message)
        return
    rt = get_runtime()
    action = action_for_text(language, message.text or "")
    if action == "plus":
        await message.answer(
            t(language, "choose_plus_plan"),
            reply_markup=plus_keyboard(language, product_price_labels(rt.settings, language)),
        )
        return
    if action == "pro":
        await message.answer(
            t(language, "choose_pro_plan"),
            reply_markup=pro_keyboard(language, product_price_labels(rt.settings, language)),
        )
        return
    if action == "balance":
        balance = await rt.db.get_balance_cents(user_id_from_message(message))
        await message.answer(
            t(language, "balance", balance=localized_price(rt.settings, language, balance)),
            reply_markup=top_up_keyboard(language, top_up_price_labels(rt.settings, language)),
        )
        return
    if action == "invite":
        me = await bot.get_me()
        link = f"https://t.me/{me.username}?start=ref_{user_id_from_message(message)}"
        await message.answer(t(language, "invite", link=html.escape(link)))
        return
    if action == "stock":
        await message.answer(
            t(
                language,
                "stock",
                plus_nw=rt.settings.stock_display.get("gpt_plus_nw", 0),
                plus_fw=rt.settings.stock_display.get("gpt_plus_fw", 0),
                pro5_nw=rt.settings.stock_display.get("pro_5x_nw", 0),
                pro20_nw=rt.settings.stock_display.get("pro_20x_nw", 0),
            ),
            reply_markup=main_keyboard(language),
        )
        return
    if action == "queue":
        await message.answer(
            t(language, "queue"),
            reply_markup=queue_keyboard(language, product_price_labels(rt.settings, language)),
        )
        return
    if action == "help":
        await message.answer(
            t(language, "help", support=support_contact(rt.settings)),
            reply_markup=help_keyboard(
                language,
                rt.settings.support_link,
                rt.settings.offer_link,
                rt.settings.privacy_link,
            ),
        )
        return
    if action == "language":
        await message.answer(t(language, "choose_language"), reply_markup=language_keyboard())
        return
    await message.answer(t(language, "unknown_command"), reply_markup=main_keyboard(language))


async def main() -> None:
    global runtime
    settings = load_settings()
    db = Database(settings.db_path)
    await db.initialize()
    crypto = CryptoPayClient(
        token=settings.crypto_pay_token,
        base_url=settings.crypto_pay_base_url,
        accepted_assets=settings.accepted_assets,
    )
    await crypto.start()
    runtime = Runtime(settings=settings, db=db, crypto=crypto)

    bot = Bot(
        token=settings.bot_token,
        session=AiohttpSession(proxy=settings.telegram_proxy),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)
    watcher = asyncio.create_task(payment_watcher(bot))
    try:
        crypto_info = await crypto.get_me()
        logger.info("Crypto Pay app connected: %s", crypto_info.get("name", "unknown"))
        logger.info("Starting Telegram polling")
        await dispatcher.start_polling(bot)
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
        await bot.session.close()
        await crypto.close()
        await db.close()
        runtime = None


if __name__ == "__main__":
    asyncio.run(main())
