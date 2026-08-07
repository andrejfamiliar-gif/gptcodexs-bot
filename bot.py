from __future__ import annotations

import asyncio
import html
import json
import logging
import secrets
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

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


LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("tg-account-shop")
router = Router()


@dataclass
class Runtime:
    settings: Settings
    db: Database
    crypto: CryptoPayClient


runtime: Runtime | None = None
ADMIN_USERS_PAGE_SIZE = 15


class TopUpStates(StatesGroup):
    waiting_amount = State()


class ProductQuantityStates(StatesGroup):
    waiting_quantity = State()


class AdminStockStates(StatesGroup):
    waiting_payload = State()
    waiting_remove_id = State()


class AdminBalanceStates(StatesGroup):
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


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:users:0"),
                InlineKeyboardButton(text="📊 Сводка", callback_data="admin:stats"),
            ],
            [InlineKeyboardButton(text="📦 Остатки", callback_data="admin:stock")],
            [InlineKeyboardButton(text="💵 Пополнить баланс", callback_data="admin:balance")],
        ]
    )


def admin_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ В панель", callback_data="admin:home")]]
    )


def admin_stock_keyboard() -> InlineKeyboardMarkup:
    labels = {
        "gpt_plus_nw": "Plus NW",
        "gpt_plus_fw": "Plus FW",
        "pro_5x_nw": "Pro 5x",
        "pro_20x_nw": "Pro 20x",
    }
    rows = [
        [
            InlineKeyboardButton(text=f"➕ {label}", callback_data=f"admin:stock:add:{key}"),
            InlineKeyboardButton(text="➖ Удалить", callback_data="admin:stock:remove"),
        ]
        for key, label in labels.items()
    ]
    rows.extend(
        [
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin:stock")],
            [InlineKeyboardButton(text="⬅️ В панель", callback_data="admin:home")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_users_keyboard(page: int, total: int) -> InlineKeyboardMarkup:
    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin:users:{page - 1}"))
    if (page + 1) * ADMIN_USERS_PAGE_SIZE < total:
        buttons.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"admin:users:{page + 1}"))
    rows = [buttons] if buttons else []
    rows.append([InlineKeyboardButton(text="⬅️ В панель", callback_data="admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def notify_admins_on_start(bot: Bot, message: Message) -> None:
    rt = get_runtime()
    user = message.from_user
    if user is None or not rt.settings.admin_ids:
        return
    username = f"@{html.escape(user.username)}" if user.username else "не указан"
    notification = (
        "🟢 Вход в бота\n"
        f"Пользователь: {username}\n"
        f"ID: <code>{user.id}</code>\n"
        f"Имя: {html.escape(user.full_name)}"
    )
    for admin_id in rt.settings.admin_ids:
        if admin_id == user.id:
            continue
        try:
            await bot.send_message(admin_id, notification)
        except Exception:
            logger.exception("Could not notify admin %s about user start", admin_id)


async def admin_only_callback(callback: CallbackQuery) -> bool:
    if not is_admin(callback.from_user.id):
        await callback.answer("Только для администратора", show_alert=True)
        return False
    return True


async def edit_admin_message(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    if callback.message is None:
        return
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=reply_markup)


async def admin_users_text(page: int) -> tuple[str, InlineKeyboardMarkup]:
    rt = get_runtime()
    total = await rt.db.count_users()
    rows = await rt.db.list_users(ADMIN_USERS_PAGE_SIZE, page * ADMIN_USERS_PAGE_SIZE)
    lines = [f"👥 Пользователи: {total}", f"Страница {page + 1}", ""]
    if not rows:
        lines.append("Список пока пуст.")
    else:
        for index, row in enumerate(rows, start=page * ADMIN_USERS_PAGE_SIZE + 1):
            username = row["username"]
            if username:
                name = f'<a href="tg://user?id={row["user_id"]}">@{html.escape(username)}</a>'
            else:
                name = f'<code>{row["user_id"]}</code>'
            language = row["language"] or "не выбран"
            created_at = str(row["created_at"]).replace("T", " ")[:19]
            lines.append(f"{index}. {name} · {language} · {created_at}")
    return "\n".join(lines), admin_users_keyboard(page, total)


async def admin_stats_text() -> str:
    rt = get_runtime()
    total_users = await rt.db.count_users()
    stock = await rt.db.available_stock()
    stock_total = sum(stock.values())
    return (
        "📊 Сводка\n\n"
        f"Зарегистрировано пользователей: {total_users}\n"
        f"Товаров в базе: {stock_total}"
    )


async def admin_stock_text() -> str:
    rt = get_runtime()
    stock = await rt.db.available_stock()
    goods = await rt.db.list_available_goods()
    ids_by_product: dict[str, list[str]] = {}
    for row in goods:
        ids_by_product.setdefault(str(row["product_key"]), []).append(str(row["id"]))
    labels = {
        "gpt_plus_nw": "Plus NW",
        "gpt_plus_fw": "Plus FW",
        "pro_5x_nw": "Pro 5x",
        "pro_20x_nw": "Pro 20x",
    }
    lines = ["📦 Склад", ""]
    for key, label in labels.items():
        ids = ids_by_product.get(key, [])
        lines.append(f"{label}: {stock.get(key, 0)}")
        if ids:
            lines.append(f"ID: {', '.join(ids[:80])}")
    return "\n".join(lines)


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


def quantity_prompt(language: str, product_name: str, available: int) -> str:
    prompts = {
        "zh": "请输入购买数量（可用库存：{available}）：\n商品：{product}",
        "en": "Enter the quantity to buy (available: {available}):\nProduct: {product}",
        "ru": "Введите количество для покупки (доступно: {available}):\nТовар: {product}",
    }
    return prompts.get(language, prompts["en"]).format(
        available=available,
        product=html.escape(product_name),
    )


def quantity_error(language: str, available: int) -> str:
    messages = {
        "zh": "请输入至少 2 个，且数量不能超过库存（当前可用：{available}）。",
        "en": "Enter at least 2 and no more than the available stock (currently: {available}).",
        "ru": "Введите минимум 2 и не больше доступного остатка (сейчас: {available}).",
    }
    return messages.get(language, messages["en"]).format(available=available)


def quantity_line(language: str, quantity: int) -> str:
    labels = {"zh": "数量", "en": "Quantity", "ru": "Количество"}
    return f"{labels.get(language, labels['en'])}: {quantity}"


async def available_stock_for_product(product_key: str) -> int:
    stock = await get_runtime().db.available_stock()
    return stock.get(product_key, 0)


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
    quantity: int = 1,
    order_type: str = "product",
    balance_amount_cents: int | None = None,
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
        quantity=quantity,
        currency=fiat,
        order_type=order_type,
        balance_amount_cents=balance_amount_cents,
    )
    return order_id, invoice


def formatted_account_payload(raw_payload: str | None) -> str:
    if not raw_payload:
        return ""
    try:
        parsed = json.loads(raw_payload)
    except (TypeError, json.JSONDecodeError):
        parsed = [raw_payload]
    if not isinstance(parsed, list):
        parsed = [parsed]
    payloads = [str(item) for item in parsed if str(item).strip()]
    blocks: list[str] = []
    for index, payload in enumerate(payloads, start=1):
        if ":" in payload:
            login, password = payload.split(":", maxsplit=1)
            block = (
                f"Account {index}:\n"
                f"Login: {html.escape(login)}\n"
                f"Password: {html.escape(password)}\n"
                f"Login + password: {html.escape(payload)}"
            )
        else:
            block = f"Account {index}:\nData: {html.escape(payload)}"
        blocks.append(block)
    return "\n\n".join(blocks)


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
                payload = formatted_account_payload(order["delivery_payload"])
                await bot.send_message(
                    order["user_id"],
                    t(
                        language,
                        "delivery_account",
                        product=html.escape(product_name),
                        payload=payload,
                    ),
                )
            await rt.db.mark_delivery_sent(order["id"])
        except Exception:
            await rt.db.reset_delivery(order["id"])
            logger.exception("Could not deliver order %s", order["id"])


async def notify_admins_payment(bot: Bot, settlement: dict[str, object]) -> None:
    rt = get_runtime()
    if not rt.settings.admin_ids:
        return
    user_id = int(settlement["user_id"])
    user = await rt.db.get_user(user_id)
    username = f"@{html.escape(user['username'])}" if user and user["username"] else "не указан"
    product_key = str(settlement["product_key"])
    if product_key == "balance_topup":
        product_name = "Пополнение баланса"
    else:
        product = rt.settings.products.get(product_key)
        product_name = product.title.get("ru", product.key) if product else product_key
    quantity = int(settlement.get("quantity", 1))
    currency = str(settlement.get("currency", "USD"))
    amount = format_fiat_price(int(settlement["amount_cents"]), currency)
    notification = (
        "💳 Оплата подтверждена\n"
        f"Заказ: <code>#{settlement['order_id']}</code>\n"
        f"Пользователь: {username}\n"
        f"ID: <code>{user_id}</code>\n"
        f"Товар: {html.escape(product_name)}\n"
        f"Количество: {quantity}\n"
        f"Сумма: {amount}"
    )
    for admin_id in rt.settings.admin_ids:
        try:
            await bot.send_message(admin_id, notification)
        except Exception:
            logger.exception("Could not notify admin %s about payment", admin_id)


async def settle_invoice(bot: Bot, order_id: int) -> dict[str, object] | None:
    rt = get_runtime()
    settlement = await rt.db.settle_paid_order(
        order_id,
        decrement_stock=rt.settings.decrement_stock_on_payment,
    )
    if settlement is not None:
        await notify_admins_payment(bot, settlement)
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

            for order in await rt.db.get_waiting_stock_orders():
                if await rt.db.try_fulfill_waiting_order(
                    order["id"],
                    decrement_stock=rt.settings.decrement_stock_on_payment,
                ):
                    logger.info("Stock restored; order %s is ready for delivery", order["id"])
            await deliver_pending_orders(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Payment watcher iteration failed")
        await asyncio.sleep(rt.settings.payment_poll_seconds)


@router.message(CommandStart())
async def start_handler(message: Message, bot: Bot) -> None:
    referrer_id: int | None = None
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("ref_"):
        try:
            referrer_id = int(parts[1][4:])
        except ValueError:
            referrer_id = None
    language = await ensure_message_user(message, referrer_id)
    await notify_admins_on_start(bot, message)
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


@router.message(Command("id"))
async def id_command(message: Message) -> None:
    await ensure_message_user(message)
    await message.answer(f"Ваш Telegram ID: <code>{user_id_from_message(message)}</code>")


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


@router.message(ProductQuantityStates.waiting_quantity)
async def product_quantity_handler(message: Message, state: FSMContext) -> None:
    language = await selected_language(message)
    if language is None:
        await state.clear()
        await send_language_prompt(message)
        return
    data = await state.get_data()
    product_key = str(data.get("product_key", ""))
    rt = get_runtime()
    product = rt.settings.products.get(product_key)
    if product is None:
        await state.clear()
        await message.answer(t(language, "generic_error"))
        return
    try:
        quantity = int((message.text or "").strip())
    except ValueError:
        quantity = 0
    available = await available_stock_for_product(product_key)
    if quantity < 2 or quantity > available:
        await message.answer(quantity_error(language, available))
        return
    await state.clear()
    await product_message(
        message,
        product,
        language,
        buyer_id=user_id_from_message(message),
        quantity=quantity,
    )


async def product_message(
    message: Message,
    product: Product,
    language: str,
    buyer_id: int | None = None,
    quantity: int = 1,
) -> None:
    rt = get_runtime()
    buyer_id = buyer_id or user_id_from_message(message)
    available = await available_stock_for_product(product.key)
    if available <= 0:
        await message.answer(
            t(language, "product_out_of_stock"),
            reply_markup=queue_button_keyboard(language, product.key),
        )
        return
    if quantity < 1 or quantity > available:
        await message.answer(quantity_error(language, available))
        return
    amount_cents = product_amount(rt.settings, product, language)
    total_cents = amount_cents * quantity
    balance_amount_cents = product.price_cents * quantity
    fiat = currency_for_language(language)
    balance_cents = await rt.db.get_balance_cents(buyer_id)
    try:
        order_id, invoice = await create_payment_for_order(
            user_id=buyer_id,
            product_key=product.key,
            amount_cents=total_cents,
            description=(
                f"{product.title.get(language, product.key)} x{quantity} - "
                f"{format_fiat_price(total_cents, fiat)}"
            ),
            fiat=fiat,
            quantity=quantity,
            balance_amount_cents=balance_amount_cents,
        )
    except Exception:
        logger.exception("Could not create product invoice")
        await message.answer(
            t(language, "payment_error", support=support_contact(rt.settings)),
            reply_markup=main_keyboard(language),
        )
        return
    invoice_text = t(
        language,
        "product_invoice",
        product=product.title.get(language, product.key),
        amount=format_fiat_price(total_cents, fiat),
        usd_amount=format_fiat_price(total_cents, fiat),
    )
    if quantity > 1:
        invoice_text = f"{invoice_text}\n{quantity_line(language, quantity)}"
    await message.answer(
        invoice_text,
        reply_markup=payment_keyboard(
            language,
            str(invoice["bot_invoice_url"]),
            order_id,
            product_key=product.key,
            show_balance_payment=balance_cents >= balance_amount_cents,
        ),
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


@router.callback_query(F.data.startswith("buy_many:"))
async def buy_many_callback(callback: CallbackQuery, state: FSMContext) -> None:
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
    available = await available_stock_for_product(product_key)
    if available < 2:
        await callback.answer(quantity_error(language, available), show_alert=True)
        return
    await state.set_state(ProductQuantityStates.waiting_quantity)
    await state.update_data(product_key=product_key)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            quantity_prompt(language, product.title.get(language, product.key), available)
        )


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
    balance_amount_cents = product.price_cents * quantity
    balance_cents = await rt.db.get_balance_cents(callback.from_user.id)
    product_name = product.title.get(language, product.key)
    try:
        order_id, invoice = await create_payment_for_order(
            user_id=callback.from_user.id,
            product_key=product_key,
            amount_cents=total_cents,
            description=f"Queue {product_name} x{quantity} - {format_fiat_price(total_cents, fiat)}",
            fiat=fiat,
            quantity=quantity,
            order_type="queue",
            balance_amount_cents=balance_amount_cents,
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
            reply_markup=queue_payment_keyboard(
                language,
                str(invoice["bot_invoice_url"]),
                order_id,
                show_balance_payment=balance_cents >= balance_amount_cents,
            ),
        )


@router.callback_query(F.data.startswith("balance_pay:"))
async def balance_payment_callback(callback: CallbackQuery, bot: Bot) -> None:
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
    if order is None or int(order["user_id"]) != callback.from_user.id:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    if order["status"] == "paid":
        await deliver_pending_orders(bot)
        await callback.answer(t(language, "payment_confirmed"))
        return
    if order["status"] != "pending":
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return

    settlement = await rt.db.pay_order_with_balance(
        order_id,
        callback.from_user.id,
        decrement_stock=rt.settings.decrement_stock_on_payment,
    )
    if settlement is None:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    if settlement.get("status") == "insufficient":
        await callback.answer(t(language, "balance_insufficient"), show_alert=True)
        return

    await notify_admins_payment(bot, settlement)
    if settlement["delivery_status"] == "waiting_stock":
        await bot.send_message(
            callback.from_user.id,
            t(language, "no_stock_after_payment", support=support_contact(rt.settings)),
        )
    await deliver_pending_orders(bot)
    await callback.answer(
        t(language, "payment_confirmed"),
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


@router.message(Command("admin"))
async def admin_command(message: Message) -> None:
    if not is_admin(user_id_from_message(message)):
        await message.answer(t("en", "admin_only"))
        return
    await message.answer("🔐 Админ-панель", reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "admin:home")
async def admin_home_callback(callback: CallbackQuery) -> None:
    if not await admin_only_callback(callback):
        return
    await callback.answer()
    await edit_admin_message(callback, "🔐 Админ-панель", admin_panel_keyboard())


@router.callback_query(F.data.startswith("admin:users:"))
async def admin_users_callback(callback: CallbackQuery) -> None:
    if not await admin_only_callback(callback):
        return
    try:
        page = max(0, int((callback.data or "").rsplit(":", maxsplit=1)[1]))
    except (IndexError, ValueError):
        page = 0
    text, keyboard = await admin_users_text(page)
    await callback.answer()
    await edit_admin_message(callback, text, keyboard)


@router.callback_query(F.data == "admin:stats")
async def admin_stats_callback(callback: CallbackQuery) -> None:
    if not await admin_only_callback(callback):
        return
    await callback.answer()
    await edit_admin_message(callback, await admin_stats_text(), admin_back_keyboard())


@router.callback_query(F.data == "admin:balance")
async def admin_balance_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    await state.set_state(AdminBalanceStates.waiting_amount)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Введите Telegram ID пользователя и сумму в USD через пробел.\n"
            "Пример: 123456789 10.50\n\n"
            "Для отмены отправьте /cancel."
        )


@router.message(AdminBalanceStates.waiting_amount)
async def admin_balance_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(user_id_from_message(message)):
        await state.clear()
        await message.answer(t("en", "admin_only"))
        return
    raw_text = (message.text or "").strip()
    if raw_text.lower() == "/cancel":
        await state.clear()
        await message.answer("Пополнение баланса отменено.")
        return

    parts = raw_text.split()
    if len(parts) != 2:
        await message.answer(
            "Формат: Telegram ID сумма в USD\n"
            "Пример: 123456789 10.50\n"
            "Для отмены: /cancel"
        )
        return
    try:
        target_user_id = int(parts[0])
    except ValueError:
        await message.answer("Telegram ID должен быть числом.")
        return
    if target_user_id <= 0:
        await message.answer("Telegram ID должен быть положительным числом.")
        return
    amount_cents = parse_amount_cents(parts[1])
    if amount_cents is None:
        await message.answer("Введите положительную сумму в USD, например 10.50.")
        return

    new_balance_cents = await get_runtime().db.add_balance_cents(target_user_id, amount_cents)
    if new_balance_cents is None:
        await message.answer(
            "Пользователь не найден в базе. Сначала он должен открыть бота через /start."
        )
        return

    await state.clear()
    await message.answer(
        "Баланс пополнен.\n"
        f"Пользователь: <code>{target_user_id}</code>\n"
        f"Зачислено: <b>{format_usd(amount_cents)}</b>\n"
        f"Новый баланс: <b>{format_usd(new_balance_cents)}</b>\n\n"
        "Уведомление пользователю не отправлялось.",
        reply_markup=admin_panel_keyboard(),
    )


@router.callback_query(F.data == "admin:stock")
async def admin_stock_callback(callback: CallbackQuery) -> None:
    if not await admin_only_callback(callback):
        return
    await callback.answer()
    await edit_admin_message(callback, await admin_stock_text(), admin_stock_keyboard())
    return
    stock = await get_runtime().db.available_stock()
    if stock:
        stock_text = "\n".join(f"{key}: {count}" for key, count in sorted(stock.items()))
    else:
        stock_text = "Склад пуст."
    await callback.answer()
    await edit_admin_message(callback, f"📦 Остатки\n\n{stock_text}", admin_back_keyboard())


@router.callback_query(F.data.startswith("admin:stock:add:"))
async def admin_stock_add_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    product_key = (callback.data or "").split(":", maxsplit=3)[-1]
    if product_key not in get_runtime().settings.products:
        await callback.answer("Неизвестный товар", show_alert=True)
        return
    await state.set_state(AdminStockStates.waiting_payload)
    await state.update_data(product_key=product_key)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Отправь данные аккаунта одним сообщением.\n"
            "Можно указать несколько строк — каждая строка станет отдельным товаром.\n"
            "Для отмены отправь /cancel."
        )


@router.callback_query(F.data == "admin:stock:remove")
async def admin_stock_remove_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    await state.set_state(AdminStockStates.waiting_remove_id)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Отправь ID товара из списка склада. Можно указать несколько ID через пробел.\n"
            "Для отмены отправь /cancel."
        )


@router.message(AdminStockStates.waiting_payload)
async def admin_stock_payload_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(user_id_from_message(message)):
        await state.clear()
        await message.answer(t("en", "admin_only"))
        return
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear()
        await message.answer("Добавление отменено.")
        return
    data = await state.get_data()
    product_key = str(data.get("product_key", ""))
    if product_key not in get_runtime().settings.products:
        await state.clear()
        await message.answer("Неизвестный товар.")
        return
    payloads = [line.strip() for line in (message.text or "").splitlines() if line.strip()]
    if not payloads or len(payloads) > 100:
        await message.answer("Отправь от 1 до 100 строк с данными товара.")
        return
    ids = [str(await get_runtime().db.add_good(product_key, payload)) for payload in payloads]
    await state.clear()
    await message.answer(
        f"Добавлено товаров: {len(ids)}\nID: {', '.join(ids)}",
        reply_markup=admin_stock_keyboard(),
    )


@router.message(AdminStockStates.waiting_remove_id)
async def admin_stock_remove_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(user_id_from_message(message)):
        await state.clear()
        await message.answer(t("en", "admin_only"))
        return
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear()
        await message.answer("Удаление отменено.")
        return
    raw_ids = (message.text or "").replace(",", " ").split()
    try:
        good_ids = [int(raw_id) for raw_id in raw_ids]
    except ValueError:
        await message.answer("Отправь числовые ID товаров через пробел.")
        return
    removed = 0
    for good_id in good_ids:
        if await get_runtime().db.remove_good(good_id):
            removed += 1
    await state.clear()
    await message.answer(
        f"Удалено товаров: {removed}",
        reply_markup=admin_stock_keyboard(),
    )


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
        stock = await rt.db.available_stock()
        await message.answer(
            t(
                language,
                "stock",
                plus_nw=stock.get("gpt_plus_nw", 0),
                plus_fw=stock.get("gpt_plus_fw", 0),
                pro5_nw=stock.get("pro_5x_nw", 0),
                pro20_nw=stock.get("pro_20x_nw", 0),
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
