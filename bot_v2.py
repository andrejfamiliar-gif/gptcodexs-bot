from __future__ import annotations

"""Inline storefront UI for the Telegram shop.

This module intentionally reuses the battle-tested database, Crypto Pay client,
manual-payment state machine and admin tools from ``bot.py``.  It replaces only
the customer-facing navigation/checkout layer:

* no persistent reply keyboard; every menu is inline;
* category-first catalogue with blue category buttons;
* green/red product buttons based on *real* stock;
* buy-one and buy-many checkout;
* three product payment methods: Crypto Bot, direct cryptocurrency, balance;
* direct cryptocurrency payments are linked to the order and, after an admin
  verifies the tx hash, the order is paid and delivered automatically.

Run this file instead of ``bot.py``.  The legacy router is still included after
this router so admin commands and existing support flows continue to work.
"""

import asyncio
import html
import logging
import secrets
from datetime import datetime, timezone
from decimal import Decimal

import bot as legacy
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ButtonStyle, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
    User,
)


logger = logging.getLogger("tg-account-shop.inline-v2")
router = Router(name="inline-shop-v2")


# ---------------------------------------------------------------------------
# Localised customer UI
# ---------------------------------------------------------------------------

_UI: dict[str, dict[str, str]] = {
    "home_title": {
        "ru": "👋 <b>Добро пожаловать в магазин!</b>",
        "en": "👋 <b>Welcome to the store!</b>",
        "zh": "👋 <b>欢迎来到商店！</b>",
    },
    "products": {"ru": "🛒 Товары", "en": "🛒 Products", "zh": "🛒 商品"},
    "wallet": {"ru": "💳 Кошелёк", "en": "💳 Wallet", "zh": "💳 钱包"},
    "profile": {"ru": "👤 Профиль", "en": "👤 Profile", "zh": "👤 个人资料"},
    "referrals": {"ru": "👥 Рефералы", "en": "👥 Referrals", "zh": "👥 邀请"},
    "support": {"ru": "🆘 Поддержка", "en": "🆘 Support", "zh": "🆘 客服"},
    "language": {"ru": "🌐 Язык", "en": "🌐 Language", "zh": "🌐 语言"},
    "terms": {"ru": "📜 Условия", "en": "📜 Terms of Use", "zh": "📜 使用条款"},
    "home": {"ru": "🏠 Главное меню", "en": "🏠 Main menu", "zh": "🏠 主菜单"},
    "back": {"ru": "⬅️ Назад", "en": "⬅️ Back", "zh": "⬅️ 返回"},
    "refresh": {"ru": "🔄 Обновить", "en": "🔄 Refresh", "zh": "🔄 刷新"},
    "categories_title": {
        "ru": "🛒 <b>Категории товаров</b>\n\nВыберите категорию:",
        "en": "🛒 <b>Product categories</b>\n\nChoose a category:",
        "zh": "🛒 <b>商品分类</b>\n\n请选择分类：",
    },
    "category_empty": {
        "ru": "В этой категории пока нет товаров.",
        "en": "There are no products in this category yet.",
        "zh": "该分类暂时没有商品。",
    },
    "stock": {"ru": "Наличие", "en": "Stock", "zh": "库存"},
    "price": {"ru": "Цена", "en": "Price", "zh": "价格"},
    "buy_one": {"ru": "🛒 Купить 1", "en": "🛒 Buy 1", "zh": "🛒 购买 1 个"},
    "buy_many": {
        "ru": "📦 Купить несколько",
        "en": "📦 Buy several",
        "zh": "📦 购买多个",
    },
    "change_quantity": {
        "ru": "📦 Изменить количество",
        "en": "📦 Change quantity",
        "zh": "📦 修改数量",
    },
    "out_of_stock": {
        "ru": "🔴 Сейчас товара нет в наличии.",
        "en": "🔴 This product is currently out of stock.",
        "zh": "🔴 当前无库存。",
    },
    "waitlist": {"ru": "🔔 Уведомить о наличии", "en": "🔔 Notify me", "zh": "🔔 到货提醒"},
    "waitlist_added": {
        "ru": "Готово. Сообщу, когда товар появится.",
        "en": "Done. I will notify you when it is available.",
        "zh": "已设置，到货后会通知您。",
    },
    "quantity_prompt": {
        "ru": "Введите количество от 2 до {available}:\n<b>{product}</b>",
        "en": "Enter a quantity from 2 to {available}:\n<b>{product}</b>",
        "zh": "请输入 2 到 {available} 的数量：\n<b>{product}</b>",
    },
    "quantity_invalid": {
        "ru": "Введите целое число от 2 до {available}.",
        "en": "Enter a whole number from 2 to {available}.",
        "zh": "请输入 2 到 {available} 的整数。",
    },
    "quantity_title": {
        "ru": "📦 <b>Выберите количество</b>\n\n{product}\nВ наличии: <b>{available}</b>",
        "en": "📦 <b>Choose quantity</b>\n\n{product}\nIn stock: <b>{available}</b>",
        "zh": "📦 <b>选择数量</b>\n\n{product}\n库存：<b>{available}</b>",
    },
    "continue_buy": {"ru": "✅ Продолжить", "en": "✅ Continue", "zh": "✅ 继续"},
    "checkout_title": {
        "ru": "💳 <b>Выберите способ оплаты</b>",
        "en": "💳 <b>Choose payment method</b>",
        "zh": "💳 <b>选择支付方式</b>",
    },
    "crypto_bot": {"ru": "🤖 Crypto Bot", "en": "🤖 Crypto Bot", "zh": "🤖 Crypto Bot"},
    "cryptocurrency": {
        "ru": "🪙 Cryptocurrency",
        "en": "🪙 Cryptocurrency",
        "zh": "🪙 Cryptocurrency",
    },
    "balance_pay": {"ru": "💰 Баланс", "en": "💰 Balance", "zh": "💰 余额"},
    "balance_insufficient": {
        "ru": "Недостаточно средств на балансе.",
        "en": "Insufficient balance.",
        "zh": "余额不足。",
    },
    "choose_coin": {
        "ru": "🪙 <b>Выберите криптовалюту</b>\n\nК оплате: <b>{usd}</b>",
        "en": "🪙 <b>Choose cryptocurrency</b>\n\nAmount due: <b>{usd}</b>",
        "zh": "🪙 <b>选择加密货币</b>\n\n应付：<b>{usd}</b>",
    },
    "choose_network": {
        "ru": "Выберите сеть для <b>{asset}</b>:",
        "en": "Choose a network for <b>{asset}</b>:",
        "zh": "请选择 <b>{asset}</b> 网络：",
    },
    "crypto_unavailable": {
        "ru": "Прямая оплата криптовалютой сейчас недоступна.",
        "en": "Direct cryptocurrency payment is currently unavailable.",
        "zh": "当前无法直接使用加密货币支付。",
    },
    "rate_unavailable": {
        "ru": "Не удалось получить актуальный курс этой монеты. Выберите другую валюту или Crypto Bot.",
        "en": "Could not get a current rate for this coin. Choose another coin or Crypto Bot.",
        "zh": "无法获取该币种的当前汇率，请选择其他币种或 Crypto Bot。",
    },
    "crypto_instructions": {
        "ru": (
            "🪙 <b>Оплата криптовалютой</b>\n\n"
            "Товар: <b>{product}</b>\n"
            "Количество: <b>{quantity}</b>\n"
            "Стоимость: <b>{usd}</b>\n\n"
            "Монета: <b>{asset}</b>\n"
            "Сеть: <b>{network}</b>\n"
            "Отправьте ровно: <b>{crypto_amount} {asset}</b>\n"
            "Курс: 1 {asset} = ${rate} ({rate_at} UTC)\n\n"
            "Адрес:\n<code>{address}</code>\n\n"
            "⚠️ Используйте только сеть <b>{network}</b>. После перевода отправьте tx hash. "
            "После проверки администратором заказ будет оплачен и товар выдастся автоматически."
        ),
        "en": (
            "🪙 <b>Cryptocurrency payment</b>\n\n"
            "Product: <b>{product}</b>\n"
            "Quantity: <b>{quantity}</b>\n"
            "Price: <b>{usd}</b>\n\n"
            "Coin: <b>{asset}</b>\n"
            "Network: <b>{network}</b>\n"
            "Send exactly: <b>{crypto_amount} {asset}</b>\n"
            "Rate: 1 {asset} = ${rate} ({rate_at} UTC)\n\n"
            "Address:\n<code>{address}</code>\n\n"
            "⚠️ Use only the <b>{network}</b> network. Submit the tx hash after sending. "
            "Once an admin verifies it, the order is paid and delivered automatically."
        ),
        "zh": (
            "🪙 <b>加密货币支付</b>\n\n"
            "商品：<b>{product}</b>\n"
            "数量：<b>{quantity}</b>\n"
            "价格：<b>{usd}</b>\n\n"
            "币种：<b>{asset}</b>\n"
            "网络：<b>{network}</b>\n"
            "请准确发送：<b>{crypto_amount} {asset}</b>\n"
            "汇率：1 {asset} = ${rate}（{rate_at} UTC）\n\n"
            "地址：\n<code>{address}</code>\n\n"
            "⚠️ 仅使用 <b>{network}</b> 网络。转账后请提交 tx hash。"
            "管理员核验后订单会自动付款并发货。"
        ),
    },
    "invoice_created": {
        "ru": "🤖 <b>Счёт Crypto Bot создан</b>\n\n{product} × {quantity}\nК оплате: <b>{amount}</b>",
        "en": "🤖 <b>Crypto Bot invoice created</b>\n\n{product} × {quantity}\nAmount: <b>{amount}</b>",
        "zh": "🤖 <b>Crypto Bot 账单已创建</b>\n\n{product} × {quantity}\n金额：<b>{amount}</b>",
    },
    "open_invoice": {"ru": "💳 Открыть Crypto Bot", "en": "💳 Open Crypto Bot", "zh": "💳 打开 Crypto Bot"},
    "check_payment": {"ru": "🔄 Проверить оплату", "en": "🔄 Check payment", "zh": "🔄 检查付款"},
    "payment_pending": {"ru": "Платёж пока не получен.", "en": "Payment has not arrived yet.", "zh": "尚未收到付款。"},
    "payment_done": {"ru": "✅ Оплата подтверждена.", "en": "✅ Payment confirmed.", "zh": "✅ 付款已确认。"},
    "payment_expired": {"ru": "Счёт истёк.", "en": "The invoice has expired.", "zh": "账单已过期。"},
    "order_not_found": {"ru": "Заказ не найден.", "en": "Order not found.", "zh": "未找到订单。"},
    "direct_confirmed": {
        "ru": "✅ Перевод подтверждён. Заказ оплачен; товар будет отправлен автоматически.",
        "en": "✅ Transfer confirmed. The order is paid and will be delivered automatically.",
        "zh": "✅ 转账已确认，订单已付款并会自动发货。",
    },
    "direct_rejected": {
        "ru": "❌ Перевод не подтверждён. Если это ошибка, свяжитесь с поддержкой.",
        "en": "❌ Transfer was not confirmed. Contact support if this is a mistake.",
        "zh": "❌ 转账未确认，如有疑问请联系客服。",
    },
}


def ui(language: str, key: str, **kwargs: object) -> str:
    table = _UI[key]
    template = table.get(language, table.get("en", next(iter(table.values()))))
    return template.format(**kwargs)


def _fmt_usd(cents: int) -> str:
    return f"${cents / 100:.2f}"


def _safe_category(raw: str) -> str:
    raw = (raw or "catalog").strip().lower()
    # Existing built-in products use plus/pro; the new storefront presents them
    # as one ChatGPT category without rewriting historical database rows.
    if raw in {"plus", "pro", "chatgpt", "gpt"}:
        return "chatgpt"
    return raw or "catalog"


def _category_title(category: str) -> str:
    known = {
        "chatgpt": "🤖 ChatGPT",
        "google": "🌐 Google",
        "vpn": "🛡 VPN",
        "streaming": "🎬 Streaming",
        "design": "🎨 Design",
        "ai": "✨ AI",
        "catalog": "📦 Other",
    }
    return known.get(category, f"📦 {category.replace('_', ' ').strip().title()}")


def _products_by_category() -> dict[str, list[tuple[str, legacy.Product]]]:
    result: dict[str, list[tuple[str, legacy.Product]]] = {}
    for key, product in legacy.get_runtime().settings.products.items():
        result.setdefault(_safe_category(product.category), []).append((key, product))
    return result


# ---------------------------------------------------------------------------
# Navigation and storefront keyboards
# ---------------------------------------------------------------------------


def main_menu_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=ui(language, "products"),
                    callback_data="shop:products",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(text=ui(language, "wallet"), callback_data="shop:wallet"),
            ],
            [
                InlineKeyboardButton(text=ui(language, "profile"), callback_data="shop:profile"),
                InlineKeyboardButton(text=ui(language, "referrals"), callback_data="shop:referrals"),
            ],
            [
                InlineKeyboardButton(
                    text=ui(language, "support"),
                    callback_data="shop:support",
                    style=ButtonStyle.DANGER,
                ),
                InlineKeyboardButton(text=ui(language, "language"), callback_data="shop:language"),
            ],
            [InlineKeyboardButton(text=ui(language, "terms"), callback_data="shop:terms")],
        ]
    )


def categories_keyboard(language: str) -> InlineKeyboardMarkup:
    grouped = _products_by_category()
    buttons: list[InlineKeyboardButton] = []
    for category, products in sorted(grouped.items(), key=lambda item: _category_title(item[0]).lower()):
        buttons.append(
            InlineKeyboardButton(
                text=f"{_category_title(category)} ({len(products)})",
                callback_data=f"shop:cat:{category}",
                style=ButtonStyle.PRIMARY,
            )
        )
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text=ui(language, "home"), callback_data="shop:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_keyboard(
    language: str,
    category: str,
    stock: dict[str, int],
) -> InlineKeyboardMarkup:
    grouped = _products_by_category()
    rows: list[list[InlineKeyboardButton]] = []
    for key, product in grouped.get(category, []):
        count = int(stock.get(key, 0))
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{product.title.get(language, product.title.get('en', key))} · "
                        f"{legacy.product_price(legacy.get_runtime().settings, product, language)} · 📦 {count}"
                    ),
                    callback_data=f"shop:product:{key}",
                    style=ButtonStyle.SUCCESS if count > 0 else ButtonStyle.DANGER,
                )
            ]
        )
    rows.extend(
        [
            [InlineKeyboardButton(text=ui(language, "refresh"), callback_data=f"shop:cat:{category}")],
            [
                InlineKeyboardButton(text=ui(language, "back"), callback_data="shop:products"),
                InlineKeyboardButton(text=ui(language, "home"), callback_data="shop:home"),
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_keyboard(language: str, product_key: str, stock: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if stock > 0:
        rows.append(
            [
                InlineKeyboardButton(
                    text=ui(language, "buy_one"),
                    callback_data=f"shop:checkout:{product_key}:1",
                    style=ButtonStyle.SUCCESS,
                )
            ]
        )
        if stock >= 2:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=ui(language, "buy_many"),
                        callback_data=f"shop:many:{product_key}",
                        style=ButtonStyle.PRIMARY,
                    )
                ]
            )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text=ui(language, "waitlist"),
                    callback_data=f"shop:wait:{product_key}",
                    style=ButtonStyle.PRIMARY,
                )
            ]
        )
    category = _safe_category(legacy.get_runtime().settings.products[product_key].category)
    rows.append(
        [
            InlineKeyboardButton(text=ui(language, "back"), callback_data=f"shop:cat:{category}"),
            InlineKeyboardButton(text=ui(language, "home"), callback_data="shop:home"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def quantity_selector_keyboard(
    language: str,
    product_key: str,
    quantity: int,
    stock: int,
) -> InlineKeyboardMarkup:
    quantity = max(2, min(quantity, stock))
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="➖",
                callback_data=f"shop:q:{product_key}:{max(2, quantity - 1)}",
            ),
            InlineKeyboardButton(text=f"{quantity}", callback_data="shop:noop"),
            InlineKeyboardButton(
                text="➕",
                callback_data=f"shop:q:{product_key}:{min(stock, quantity + 1)}",
            ),
        ]
    ]
    quick = [value for value in (2, 3, 5, 10) if value <= stock and value != quantity]
    if quick:
        rows.append(
            [
                InlineKeyboardButton(
                    text=str(value),
                    callback_data=f"shop:q:{product_key}:{value}",
                    style=ButtonStyle.PRIMARY,
                )
                for value in quick[:4]
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=ui(language, "continue_buy"),
                    callback_data=f"shop:qconfirm:{product_key}:{quantity}",
                    style=ButtonStyle.SUCCESS,
                )
            ],
            [InlineKeyboardButton(text=ui(language, "back"), callback_data=f"shop:product:{product_key}")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def checkout_keyboard(
    language: str,
    product_key: str,
    quantity: int,
    balance_cents: int,
    required_balance_cents: int,
) -> InlineKeyboardMarkup:
    balance_style = ButtonStyle.SUCCESS if balance_cents >= required_balance_cents else ButtonStyle.DANGER
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=ui(language, "crypto_bot"),
                    callback_data=f"shop:pay_cpay:{product_key}:{quantity}",
                    style=ButtonStyle.PRIMARY,
                )
            ],
            [
                InlineKeyboardButton(
                    text=ui(language, "cryptocurrency"),
                    callback_data=f"shop:pay_crypto:{product_key}:{quantity}",
                    style=ButtonStyle.PRIMARY,
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"{ui(language, 'balance_pay')} · {_fmt_usd(balance_cents)}",
                    callback_data=f"shop:pay_balance:{product_key}:{quantity}",
                    style=balance_style,
                )
            ],
            [
                InlineKeyboardButton(
                    text=ui(language, "change_quantity" if quantity > 1 else "buy_many"),
                    callback_data=f"shop:many:{product_key}",
                )
            ],
            [InlineKeyboardButton(text=ui(language, "back"), callback_data=f"shop:product:{product_key}")],
        ]
    )


def crypto_assets_keyboard(language: str, order_id: int) -> InlineKeyboardMarkup:
    assets = legacy.wallet_assets(legacy.get_runtime().settings.crypto_wallets)
    buttons = [
        InlineKeyboardButton(
            text=asset,
            callback_data=f"shop:crypto_asset:{order_id}:{asset}",
            style=ButtonStyle.PRIMARY,
        )
        for asset in assets
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append(
        [InlineKeyboardButton(text=ui(language, "back"), callback_data=f"shop:cancel_order:{order_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def crypto_networks_keyboard(
    language: str,
    order_id: int,
    asset: str,
    options: list[tuple[int, str]],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=network,
                callback_data=f"shop:crypto_wallet:{order_id}:{index}:{asset}",
                style=ButtonStyle.PRIMARY,
            )
        ]
        for index, network in options
    ]
    rows.append(
        [InlineKeyboardButton(text=ui(language, "back"), callback_data=f"shop:crypto_assets:{order_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def invoice_keyboard(language: str, invoice_url: str, order_id: int, product_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=ui(language, "open_invoice"),
                    url=invoice_url,
                    style=ButtonStyle.PRIMARY,
                )
            ],
            [InlineKeyboardButton(text=ui(language, "check_payment"), callback_data=f"shop:check:{order_id}")],
            [InlineKeyboardButton(text=ui(language, "back"), callback_data=f"shop:product:{product_key}")],
        ]
    )


# ---------------------------------------------------------------------------
# Message rendering helpers
# ---------------------------------------------------------------------------


async def home_text(user: User, language: str) -> str:
    rt = legacy.get_runtime()
    balance = await rt.db.get_balance_cents(user.id)
    total_users = await rt.db.count_users()
    username = f"@{html.escape(user.username)}" if user.username else "—"
    name = html.escape(user.full_name or user.first_name or "—")
    return (
        f"{ui(language, 'home_title')}\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"👤 Name: {name}\n"
        f"🔗 Username: {username}\n"
        f"👥 Users: {total_users}\n"
        f"💰 Balance: <b>{_fmt_usd(balance)}</b>"
    )


async def edit_or_send(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    if callback.message is None:
        return
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=markup)


async def show_home_callback(callback: CallbackQuery, language: str) -> None:
    await edit_or_send(callback, await home_text(callback.from_user, language), main_menu_keyboard(language))


async def actual_stock_for(product_key: str) -> int:
    return int((await legacy.get_runtime().db.actual_stock()).get(product_key, 0))


async def render_product(callback: CallbackQuery, language: str, product_key: str) -> None:
    rt = legacy.get_runtime()
    product = rt.settings.products.get(product_key)
    if product is None:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    stock = await actual_stock_for(product_key)
    name = html.escape(product.title.get(language, product.title.get("en", product_key)))
    price = legacy.product_price(rt.settings, product, language)
    text = (
        f"📦 <b>{name}</b>\n\n"
        f"💵 {ui(language, 'price')}: <b>{price}</b>\n"
        f"📦 {ui(language, 'stock')}: <b>{stock}</b>"
    )
    if stock <= 0:
        text += f"\n\n{ui(language, 'out_of_stock')}"
    await edit_or_send(callback, text, product_keyboard(language, product_key, stock))


async def render_checkout(callback: CallbackQuery, language: str, product_key: str, quantity: int) -> None:
    rt = legacy.get_runtime()
    product = rt.settings.products.get(product_key)
    if product is None:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    stock = await actual_stock_for(product_key)
    if quantity < 1 or quantity > stock:
        await callback.answer(ui(language, "quantity_invalid", available=stock), show_alert=True)
        return
    local_total = legacy.product_amount(rt.settings, product, language) * quantity
    base_total = product.price_cents * quantity
    balance = await rt.db.get_balance_cents(callback.from_user.id)
    local_currency = legacy.currency_for_language(language)
    local_price = legacy.format_fiat_price(local_total, local_currency)
    usd_line = "" if local_currency == "USD" else f"\nUSD: <b>{_fmt_usd(base_total)}</b>"
    text = (
        f"{ui(language, 'checkout_title')}\n\n"
        f"📦 {html.escape(product.title.get(language, product.key))}\n"
        f"🔢 × {quantity}\n"
        f"💵 <b>{local_price}</b>{usd_line}\n"
        f"💰 Balance: <b>{_fmt_usd(balance)}</b>"
    )
    await edit_or_send(
        callback,
        text,
        checkout_keyboard(language, product_key, quantity, balance, base_total),
    )


# ---------------------------------------------------------------------------
# Order helpers.  Manual/balance orders intentionally use invoice_id=NULL so
# the Crypto Pay watcher never tries to query them as Crypto Pay invoices.
# ---------------------------------------------------------------------------


async def ensure_v2_schema() -> None:
    db = legacy.get_runtime().db
    async with db.lock:
        await db._conn().executescript(
            """
            CREATE TABLE IF NOT EXISTS manual_order_links (
                payment_id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY(payment_id) REFERENCES manual_payments(id),
                FOREIGN KEY(order_id) REFERENCES orders(id)
            );
            CREATE INDEX IF NOT EXISTS idx_manual_order_links_order
                ON manual_order_links(order_id);
            """
        )
        await db._conn().commit()


async def create_non_invoice_order(
    user_id: int,
    product_key: str,
    amount_cents: int,
    quantity: int,
    balance_amount_cents: int,
    order_type: str = "product",
) -> int:
    if quantity < 1:
        raise ValueError("quantity must be at least 1")
    db = legacy.get_runtime().db
    token = secrets.token_urlsafe(18)
    async with db.lock:
        cursor = await db._conn().execute(
            """
            INSERT INTO orders(
                user_id, product_key, amount_cents, balance_amount_cents,
                quantity, currency, order_type, order_token, invoice_id, created_at
            ) VALUES (?, ?, ?, ?, ?, 'USD', ?, ?, NULL, ?)
            """,
            (
                user_id,
                product_key,
                amount_cents,
                balance_amount_cents,
                quantity,
                order_type,
                token,
                legacy.utc_now() if hasattr(legacy, "utc_now") else datetime.now(timezone.utc).isoformat(),
            ),
        )
        await db._conn().commit()
        return int(cursor.lastrowid)


async def link_manual_order(payment_id: int, order_id: int) -> None:
    db = legacy.get_runtime().db
    async with db.lock:
        await db._conn().execute(
            """
            INSERT OR REPLACE INTO manual_order_links(payment_id, order_id, created_at)
            VALUES (?, ?, ?)
            """,
            (payment_id, order_id, datetime.now(timezone.utc).isoformat()),
        )
        await db._conn().commit()


async def linked_order_id(payment_id: int) -> int | None:
    db = legacy.get_runtime().db
    row = await db._fetchone(
        "SELECT order_id FROM manual_order_links WHERE payment_id = ?",
        (payment_id,),
    )
    return int(row["order_id"]) if row is not None else None


async def cancel_non_invoice_order(order_id: int, user_id: int) -> bool:
    db = legacy.get_runtime().db
    async with db.lock:
        cursor = await db._conn().execute(
            """
            UPDATE orders SET status = 'cancelled'
            WHERE id = ? AND user_id = ? AND status = 'pending' AND invoice_id IS NULL
            """,
            (order_id, user_id),
        )
        await db._conn().commit()
        return cursor.rowcount == 1


async def settle_paid_order_v2(bot: Bot, order_id: int) -> dict[str, object] | None:
    rt = legacy.get_runtime()
    settlement = await rt.db.settle_paid_order(order_id, decrement_stock=True)
    if settlement is not None:
        await legacy.notify_admins_payment(bot, settlement)
        await legacy.broadcast_purchase_notification(bot, settlement)
    if settlement is not None and settlement["delivery_status"] == "waiting_stock":
        language = await rt.db.get_language(int(settlement["user_id"])) or "en"
        await bot.send_message(
            int(settlement["user_id"]),
            legacy.t(language, "no_stock_after_payment", support=legacy.support_contact(rt.settings)),
        )
    await legacy.deliver_pending_orders(bot)
    return settlement


async def cancel_expired_linked_orders() -> int:
    """Cancel product orders whose direct-crypto request expired before a hash."""
    db = legacy.get_runtime().db
    async with db.lock:
        cursor = await db._conn().execute(
            """
            UPDATE orders
            SET status = 'cancelled'
            WHERE id IN (
                SELECT l.order_id
                FROM manual_order_links l
                JOIN manual_payments m ON m.id = l.payment_id
                WHERE m.status = 'expired'
            )
              AND status = 'pending'
              AND invoice_id IS NULL
            """
        )
        await db._conn().commit()
        return int(cursor.rowcount)


async def payment_watcher_v2(bot: Bot) -> None:
    rt = legacy.get_runtime()
    while True:
        try:
            for order in await rt.db.get_pending_orders():
                # Balance/direct-crypto orders deliberately have no Crypto Pay
                # invoice.  Leave them for their own settlement handlers.
                if order["invoice_id"] is None:
                    continue
                try:
                    invoice = await rt.crypto.get_invoice(order["invoice_id"])
                    if invoice is None:
                        continue
                    if invoice.get("status") == "paid":
                        await settle_paid_order_v2(bot, int(order["id"]))
                    elif invoice.get("status") == "expired":
                        await rt.db.mark_order_expired(int(order["id"]))
                except Exception:
                    logger.exception("Could not refresh invoice for order %s", order["id"])

            for order in await rt.db.get_waiting_stock_orders():
                if await rt.db.try_fulfill_waiting_order(int(order["id"]), decrement_stock=True):
                    logger.info("Stock restored; order %s is ready for delivery", order["id"])
            await legacy.deliver_pending_orders(bot)
            expired = await rt.db.expire_stale_manual_payments(rt.settings.manual_crypto_note_hours)
            if expired:
                await cancel_expired_linked_orders()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Inline v2 payment watcher iteration failed")
        await asyncio.sleep(rt.settings.payment_poll_seconds)


# ---------------------------------------------------------------------------
# Main menu / catalogue handlers
# ---------------------------------------------------------------------------


@router.message(CommandStart())
async def start_handler(message: Message, bot: Bot) -> None:
    referrer_id: int | None = None
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("ref_"):
        try:
            referrer_id = int(parts[1][4:])
        except ValueError:
            referrer_id = None
    language = await legacy.ensure_message_user(message, referrer_id)
    await legacy.notify_admins_on_start(bot, message)
    if language not in legacy.LANGUAGES:
        await message.answer("请选择语言：", reply_markup=legacy.language_keyboard())
        return

    # Remove the old persistent reply keyboard once, then use inline only.
    cleanup = await message.answer("\u2063", reply_markup=ReplyKeyboardRemove())
    try:
        await cleanup.delete()
    except TelegramBadRequest:
        pass
    if message.from_user is not None:
        await message.answer(
            await home_text(message.from_user, language),
            reply_markup=main_menu_keyboard(language),
        )


@router.message(Command("menu"))
async def menu_command(message: Message) -> None:
    language = await legacy.selected_language(message)
    if language not in legacy.LANGUAGES or message.from_user is None:
        await legacy.send_language_prompt(message)
        return
    cleanup = await message.answer("\u2063", reply_markup=ReplyKeyboardRemove())
    try:
        await cleanup.delete()
    except TelegramBadRequest:
        pass
    await message.answer(
        await home_text(message.from_user, language),
        reply_markup=main_menu_keyboard(language),
    )


@router.callback_query(F.data.startswith("lang:"))
async def language_callback(callback: CallbackQuery) -> None:
    code = (callback.data or "").split(":", maxsplit=1)[1]
    if code not in legacy.LANGUAGES:
        await callback.answer("Unknown language", show_alert=True)
        return
    await legacy.ensure_callback_user(callback)
    await legacy.get_runtime().db.set_language(callback.from_user.id, code)
    await callback.answer(legacy.t(code, "language_saved"))
    await show_home_callback(callback, code)


@router.callback_query(F.data == "shop:home")
async def home_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    await callback.answer()
    await show_home_callback(callback, language)


@router.callback_query(F.data == "shop:products")
async def products_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    await callback.answer()
    await edit_or_send(callback, ui(language, "categories_title"), categories_keyboard(language))


@router.callback_query(F.data.startswith("shop:cat:"))
async def category_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    category = (callback.data or "").split(":", maxsplit=2)[2]
    grouped = _products_by_category()
    if category not in grouped:
        await callback.answer(ui(language, "category_empty"), show_alert=True)
        return
    stock = await legacy.get_runtime().db.actual_stock()
    await callback.answer()
    await edit_or_send(
        callback,
        f"{_category_title(category)}\n\n{ui(language, 'stock')}",
        category_keyboard(language, category, stock),
    )


@router.callback_query(F.data.startswith("shop:product:"))
async def product_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    product_key = (callback.data or "").split(":", maxsplit=2)[2]
    await callback.answer()
    await render_product(callback, language, product_key)


@router.callback_query(F.data.startswith("shop:wait:"))
async def waitlist_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    product_key = (callback.data or "").split(":", maxsplit=2)[2]
    if product_key not in legacy.get_runtime().settings.products:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    await legacy.get_runtime().db.add_waitlist_entry(callback.from_user.id, product_key)
    await callback.answer(ui(language, "waitlist_added"), show_alert=True)


@router.callback_query(F.data.startswith("shop:many:"))
async def many_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    product_key = (callback.data or "").split(":", maxsplit=2)[2]
    product = legacy.get_runtime().settings.products.get(product_key)
    if product is None:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    available = await actual_stock_for(product_key)
    if available < 2:
        await callback.answer(ui(language, "out_of_stock"), show_alert=True)
        return
    await callback.answer()
    await edit_or_send(
        callback,
        ui(
            language,
            "quantity_title",
            product=html.escape(product.title.get(language, product.key)),
            available=available,
        ),
        quantity_selector_keyboard(language, product_key, 2, available),
    )


@router.callback_query(F.data == "shop:noop")
async def noop_callback(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("shop:q:"))
async def quantity_select_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    product_key = parts[2]
    product = legacy.get_runtime().settings.products.get(product_key)
    if product is None:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    try:
        quantity = int(parts[3])
    except ValueError:
        quantity = 0
    available = await actual_stock_for(product_key)
    if available < 2:
        await callback.answer(ui(language, "out_of_stock"), show_alert=True)
        return
    quantity = max(2, min(quantity, available))
    await callback.answer()
    await edit_or_send(
        callback,
        ui(
            language,
            "quantity_title",
            product=html.escape(product.title.get(language, product.key)),
            available=available,
        ),
        quantity_selector_keyboard(language, product_key, quantity, available),
    )


@router.callback_query(F.data.startswith("shop:qconfirm:"))
async def quantity_confirm_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    try:
        quantity = int(parts[3])
    except ValueError:
        quantity = 0
    await callback.answer()
    await render_checkout(callback, language, parts[2], quantity)


@router.callback_query(F.data.startswith("shop:checkout:"))
async def checkout_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    try:
        quantity = int(parts[3])
    except ValueError:
        quantity = 0
    await callback.answer()
    await render_checkout(callback, language, parts[2], quantity)


# ---------------------------------------------------------------------------
# Main menu secondary pages
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "shop:wallet")
async def wallet_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    rt = legacy.get_runtime()
    balance = await rt.db.get_balance_cents(callback.from_user.id)
    markup = legacy.top_up_keyboard(language, legacy.top_up_price_labels(rt.settings, language))
    # Add an inline way back home to the existing top-up keyboard.
    markup.inline_keyboard.append([InlineKeyboardButton(text=ui(language, "home"), callback_data="shop:home")])
    await callback.answer()
    await edit_or_send(
        callback,
        legacy.t(language, "balance", balance=legacy.localized_price(rt.settings, language, balance)),
        markup,
    )


@router.callback_query(F.data == "shop:profile")
async def profile_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    rt = legacy.get_runtime()
    balance = await rt.db.get_balance_cents(callback.from_user.id)
    notify = await rt.db.get_purchase_notifications(callback.from_user.id)
    username = f"@{html.escape(callback.from_user.username)}" if callback.from_user.username else "—"
    text = (
        f"👤 <b>{ui(language, 'profile').split(' ', 1)[-1]}</b>\n\n"
        f"ID: <code>{callback.from_user.id}</code>\n"
        f"Username: {username}\n"
        f"Language: {language.upper()}\n"
        f"Balance: <b>{_fmt_usd(balance)}</b>\n"
        f"Notifications: {'ON' if notify else 'OFF'}"
    )
    await callback.answer()
    await edit_or_send(
        callback,
        text,
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=ui(language, "home"), callback_data="shop:home")]]
        ),
    )


@router.callback_query(F.data == "shop:referrals")
async def referrals_callback(callback: CallbackQuery, bot: Bot) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{callback.from_user.id}"
    await callback.answer()
    await edit_or_send(
        callback,
        legacy.t(language, "invite", link=html.escape(link)),
        InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=ui(language, "home"), callback_data="shop:home")]]
        ),
    )


@router.callback_query(F.data == "shop:support")
async def support_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    rt = legacy.get_runtime()
    await callback.answer()
    await edit_or_send(
        callback,
        legacy.t(language, "help", support=legacy.support_contact(rt.settings)),
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=rt.settings.support_label, url=rt.settings.support_link)],
                [InlineKeyboardButton(text=ui(language, "home"), callback_data="shop:home")],
            ]
        ),
    )


@router.callback_query(F.data == "shop:language")
async def language_menu_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        language = "en"
    markup = legacy.language_keyboard()
    markup.inline_keyboard.append([InlineKeyboardButton(text=ui(language, "home"), callback_data="shop:home")])
    await callback.answer()
    await edit_or_send(callback, legacy.t(language, "choose_language"), markup)


@router.callback_query(F.data == "shop:terms")
async def terms_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        language = "en"
    rt = legacy.get_runtime()
    await callback.answer()
    await edit_or_send(
        callback,
        ui(language, "terms"),
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=ui(language, "terms"), url=rt.settings.offer_link)],
                [InlineKeyboardButton(text=ui(language, "home"), callback_data="shop:home")],
            ]
        ),
    )


# ---------------------------------------------------------------------------
# Checkout: Crypto Bot / Balance / direct Cryptocurrency
# ---------------------------------------------------------------------------


async def _validated_product_checkout(
    callback: CallbackQuery,
    language: str,
    product_key: str,
    quantity: int,
) -> legacy.Product | None:
    product = legacy.get_runtime().settings.products.get(product_key)
    if product is None:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return None
    stock = await actual_stock_for(product_key)
    if quantity < 1 or quantity > stock:
        await callback.answer(ui(language, "quantity_invalid", available=stock), show_alert=True)
        return None
    return product


@router.callback_query(F.data.startswith("shop:pay_cpay:"))
async def pay_cpay_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    product_key = parts[2]
    try:
        quantity = int(parts[3])
    except ValueError:
        quantity = 0
    product = await _validated_product_checkout(callback, language, product_key, quantity)
    if product is None:
        return
    rt = legacy.get_runtime()
    local_total = legacy.product_amount(rt.settings, product, language) * quantity
    base_total = product.price_cents * quantity
    fiat = legacy.currency_for_language(language)
    try:
        order_id, invoice = await legacy.create_payment_for_order(
            user_id=callback.from_user.id,
            product_key=product_key,
            amount_cents=local_total,
            description=f"{product.title.get(language, product.key)} x{quantity}",
            fiat=fiat,
            quantity=quantity,
            balance_amount_cents=base_total,
        )
    except Exception:
        logger.exception("Could not create Crypto Bot invoice")
        await callback.answer(legacy.t(language, "payment_error", support=legacy.support_contact(rt.settings)), show_alert=True)
        return
    await callback.answer()
    await edit_or_send(
        callback,
        ui(
            language,
            "invoice_created",
            product=html.escape(product.title.get(language, product.key)),
            quantity=quantity,
            amount=legacy.format_fiat_price(local_total, fiat),
        ),
        invoice_keyboard(language, str(invoice["bot_invoice_url"]), order_id, product_key),
    )


@router.callback_query(F.data.startswith("shop:check:"))
async def check_payment_callback(callback: CallbackQuery, bot: Bot) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    try:
        order_id = int((callback.data or "").split(":", maxsplit=2)[2])
    except ValueError:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    rt = legacy.get_runtime()
    order = await rt.db.get_order(order_id)
    if order is None or int(order["user_id"]) != callback.from_user.id:
        await callback.answer(ui(language, "order_not_found"), show_alert=True)
        return
    if str(order["status"]) == "paid":
        await legacy.deliver_pending_orders(bot)
        await callback.answer(ui(language, "payment_done"), show_alert=True)
        return
    if str(order["status"]) == "expired":
        await callback.answer(ui(language, "payment_expired"), show_alert=True)
        return
    if not order["invoice_id"]:
        await callback.answer(ui(language, "order_not_found"), show_alert=True)
        return
    try:
        invoice = await rt.crypto.get_invoice(order["invoice_id"])
    except Exception:
        logger.exception("Could not check invoice %s", order["invoice_id"])
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    if invoice is not None and invoice.get("status") == "paid":
        await settle_paid_order_v2(bot, order_id)
        await callback.answer(ui(language, "payment_done"), show_alert=True)
    elif invoice is not None and invoice.get("status") == "expired":
        await rt.db.mark_order_expired(order_id)
        await callback.answer(ui(language, "payment_expired"), show_alert=True)
    else:
        await callback.answer(ui(language, "payment_pending"), show_alert=True)


@router.callback_query(F.data.startswith("shop:pay_balance:"))
async def pay_balance_callback(callback: CallbackQuery, bot: Bot) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    product_key = parts[2]
    try:
        quantity = int(parts[3])
    except ValueError:
        quantity = 0
    product = await _validated_product_checkout(callback, language, product_key, quantity)
    if product is None:
        return
    base_total = product.price_cents * quantity
    balance = await legacy.get_runtime().db.get_balance_cents(callback.from_user.id)
    if balance < base_total:
        await callback.answer(ui(language, "balance_insufficient"), show_alert=True)
        return
    order_id = await create_non_invoice_order(
        callback.from_user.id,
        product_key,
        base_total,
        quantity,
        base_total,
    )
    settlement = await legacy.get_runtime().db.pay_order_with_balance(
        order_id,
        callback.from_user.id,
        decrement_stock=True,
    )
    if settlement is None or settlement.get("status") == "insufficient":
        await callback.answer(ui(language, "balance_insufficient"), show_alert=True)
        return
    await legacy.notify_admins_payment(bot, settlement)
    await legacy.broadcast_purchase_notification(bot, settlement)
    await legacy.deliver_pending_orders(bot)
    await callback.answer(ui(language, "payment_done"), show_alert=True)
    await render_product(callback, language, product_key)


@router.callback_query(F.data.startswith("shop:pay_crypto:"))
async def pay_crypto_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    product_key = parts[2]
    try:
        quantity = int(parts[3])
    except ValueError:
        quantity = 0
    product = await _validated_product_checkout(callback, language, product_key, quantity)
    if product is None:
        return
    rt = legacy.get_runtime()
    if not rt.settings.crypto_wallets:
        await callback.answer(ui(language, "crypto_unavailable"), show_alert=True)
        return
    base_total = product.price_cents * quantity
    order_id = await create_non_invoice_order(
        callback.from_user.id,
        product_key,
        base_total,
        quantity,
        base_total,
    )
    await callback.answer()
    await edit_or_send(
        callback,
        ui(language, "choose_coin", usd=_fmt_usd(base_total)),
        crypto_assets_keyboard(language, order_id),
    )


@router.callback_query(F.data.startswith("shop:crypto_assets:"))
async def crypto_assets_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    try:
        order_id = int((callback.data or "").split(":", maxsplit=2)[2])
    except ValueError:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    order = await legacy.get_runtime().db.get_order(order_id)
    if order is None or int(order["user_id"]) != callback.from_user.id or str(order["status"]) != "pending":
        await callback.answer(ui(language, "order_not_found"), show_alert=True)
        return
    await callback.answer()
    await edit_or_send(
        callback,
        ui(language, "choose_coin", usd=_fmt_usd(int(order["balance_amount_cents"] or order["amount_cents"]))),
        crypto_assets_keyboard(language, order_id),
    )


@router.callback_query(F.data.startswith("shop:crypto_asset:"))
async def crypto_asset_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    try:
        order_id = int(parts[2])
    except ValueError:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    asset = parts[3].upper()
    rt = legacy.get_runtime()
    order = await rt.db.get_order(order_id)
    if order is None or int(order["user_id"]) != callback.from_user.id or str(order["status"]) != "pending":
        await callback.answer(ui(language, "order_not_found"), show_alert=True)
        return
    options = [
        (index, wallet.network)
        for index, wallet in enumerate(rt.settings.crypto_wallets)
        if wallet.asset == asset
    ]
    if not options:
        await callback.answer(ui(language, "crypto_unavailable"), show_alert=True)
        return
    if len(options) == 1:
        await create_direct_crypto_payment(callback, language, order_id, options[0][0], asset)
        return
    await callback.answer()
    await edit_or_send(
        callback,
        ui(language, "choose_network", asset=html.escape(asset)),
        crypto_networks_keyboard(language, order_id, asset, options),
    )


@router.callback_query(F.data.startswith("shop:crypto_wallet:"))
async def crypto_wallet_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 5:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    try:
        order_id = int(parts[2])
        wallet_index = int(parts[3])
    except ValueError:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    await create_direct_crypto_payment(callback, language, order_id, wallet_index, parts[4].upper())


async def create_direct_crypto_payment(
    callback: CallbackQuery,
    language: str,
    order_id: int,
    wallet_index: int,
    asset: str,
) -> None:
    rt = legacy.get_runtime()
    order = await rt.db.get_order(order_id)
    if order is None or int(order["user_id"]) != callback.from_user.id or str(order["status"]) != "pending":
        await callback.answer(ui(language, "order_not_found"), show_alert=True)
        return
    wallets = rt.settings.crypto_wallets
    if wallet_index < 0 or wallet_index >= len(wallets) or wallets[wallet_index].asset != asset:
        await callback.answer(ui(language, "crypto_unavailable"), show_alert=True)
        return
    wallet = wallets[wallet_index]
    amount_usd_cents = int(order["balance_amount_cents"] or order["amount_cents"])
    crypto_amount, rate, rate_at = await legacy.quote_for_asset(asset, amount_usd_cents)
    if not crypto_amount or not rate or not rate_at:
        await callback.answer(ui(language, "rate_unavailable"), show_alert=True)
        return

    existing = await rt.db.open_manual_payment_for_user(callback.from_user.id)
    if existing is not None:
        if str(existing["status"]) == "pending":
            await callback.answer(
                legacy.t(language, "mpay_open_exists", payment_id=int(existing["id"])),
                show_alert=True,
            )
            return
        old_link = await linked_order_id(int(existing["id"]))
        await rt.db.cancel_manual_payment(int(existing["id"]), callback.from_user.id)
        if old_link is not None:
            await cancel_non_invoice_order(old_link, callback.from_user.id)

    payment_id = await rt.db.create_manual_payment(
        user_id=callback.from_user.id,
        asset=wallet.asset,
        network=wallet.network,
        address=wallet.address,
        amount_cents=amount_usd_cents,
        currency="USD",
        crypto_amount=crypto_amount,
        rate=rate,
        rate_at=rate_at,
    )
    await link_manual_order(payment_id, order_id)
    product = rt.settings.products.get(str(order["product_key"]))
    product_name = product.title.get(language, product.key) if product else str(order["product_key"])
    text = ui(
        language,
        "crypto_instructions",
        product=html.escape(product_name),
        quantity=int(order["quantity"] or 1),
        usd=_fmt_usd(amount_usd_cents),
        asset=html.escape(wallet.asset),
        network=html.escape(wallet.network),
        crypto_amount=html.escape(crypto_amount),
        rate=html.escape(rate),
        rate_at=html.escape(rate_at),
        address=html.escape(wallet.address),
    )
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            text,
            reply_markup=legacy.mpay_pending_keyboard(language, payment_id),
        )


@router.callback_query(F.data.startswith("shop:cancel_order:"))
async def cancel_order_callback(callback: CallbackQuery) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        language = "en"
    try:
        order_id = int((callback.data or "").split(":", maxsplit=2)[2])
    except ValueError:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    order = await legacy.get_runtime().db.get_order(order_id)
    product_key = str(order["product_key"]) if order is not None else ""
    await cancel_non_invoice_order(order_id, callback.from_user.id)
    await callback.answer()
    if product_key:
        await render_product(callback, language, product_key)
    else:
        await show_home_callback(callback, language)


# Intercept manual-payment cancellation so a linked product order is also
# cancelled rather than lingering forever as a pending non-invoice order.
@router.callback_query(F.data.startswith("mpay:cancel:"))
async def linked_manual_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    language = await legacy.ensure_callback_user(callback)
    if language not in legacy.LANGUAGES:
        language = "en"
    try:
        payment_id = int((callback.data or "").split(":", maxsplit=2)[2])
    except ValueError:
        await callback.answer(legacy.t(language, "generic_error"), show_alert=True)
        return
    rt = legacy.get_runtime()
    payment = await rt.db.get_manual_payment(payment_id)
    if payment is None or int(payment["user_id"]) != callback.from_user.id:
        await callback.answer(legacy.t(language, "mpay_stale"), show_alert=True)
        return
    if str(payment["status"]) == "pending":
        # A hash was already submitted; the transfer may be on-chain, so do not
        # let the buyer discard the verification request.
        await callback.answer(
            legacy.t(language, "mpay_open_exists", payment_id=payment_id),
            show_alert=True,
        )
        return
    order_id = await linked_order_id(payment_id)
    cancelled = await rt.db.cancel_manual_payment(payment_id, callback.from_user.id)
    if not cancelled:
        await callback.answer(legacy.t(language, "mpay_stale"), show_alert=True)
        return
    if order_id is not None:
        await cancel_non_invoice_order(order_id, callback.from_user.id)
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            legacy.t(
                language,
                "mpay_cancelled",
                payment_id=payment_id,
                support=legacy.support_contact(legacy.get_runtime().settings),
            )
        )


# ---------------------------------------------------------------------------
# Manual crypto admin decisions.  For linked payments approval credits the
# exact USD amount, immediately spends it on the linked order, and delivers.
# Unlinked manual top-ups keep the original behaviour.
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("mpay:ok:"))
async def manual_admin_confirm_callback(callback: CallbackQuery, bot: Bot) -> None:
    await decide_manual_payment(callback, bot, approve=True)


@router.callback_query(F.data.startswith("mpay:rej:"))
async def manual_admin_reject_callback(callback: CallbackQuery, bot: Bot) -> None:
    await decide_manual_payment(callback, bot, approve=False)


async def decide_manual_payment(callback: CallbackQuery, bot: Bot, approve: bool) -> None:
    if not await legacy.admin_only_callback(callback):
        return
    try:
        payment_id = int((callback.data or "").split(":", maxsplit=2)[2])
    except ValueError:
        await callback.answer("Некорректный запрос", show_alert=True)
        return
    rt = legacy.get_runtime()
    order_id = await linked_order_id(payment_id)
    payment = await rt.db.decide_manual_payment(payment_id, callback.from_user.id, approve)
    if payment is None:
        await callback.answer(legacy.t("ru", "mpay_admin_already", payment_id=payment_id), show_alert=True)
        return

    user_id = int(payment["user_id"])
    language = await rt.db.get_language(user_id) or "en"
    settlement: dict[str, object] | None = None
    if approve and order_id is not None:
        settlement = await rt.db.pay_order_with_balance(order_id, user_id, decrement_stock=True)
        if settlement is not None and settlement.get("status") != "insufficient":
            await legacy.notify_admins_payment(bot, settlement)
            await legacy.broadcast_purchase_notification(bot, settlement)
            if settlement.get("delivery_status") == "waiting_stock":
                await bot.send_message(
                    user_id,
                    legacy.t(language, "no_stock_after_payment", support=legacy.support_contact(rt.settings)),
                )
            await legacy.deliver_pending_orders(bot)
    elif not approve and order_id is not None:
        await cancel_non_invoice_order(order_id, user_id)

    await callback.answer()
    if callback.message is not None:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
        await callback.message.answer(
            f"{'✅' if approve else '❌'} Manual payment #{payment_id} "
            f"{'confirmed' if approve else 'rejected'}"
        )

    try:
        if order_id is not None:
            if approve and settlement is not None and settlement.get("status") != "insufficient":
                await bot.send_message(user_id, ui(language, "direct_confirmed"))
            elif approve:
                # The transfer is valid, but the linked order could not be paid
                # (for example it was cancelled).  Funds remain on balance.
                balance = await rt.db.get_balance_cents(user_id)
                await bot.send_message(
                    user_id,
                    legacy.t(
                        language,
                        "mpay_confirmed",
                        payment_id=payment_id,
                        amount=legacy.localized_price(rt.settings, language, int(payment["amount_cents"])),
                        balance=legacy.localized_price(rt.settings, language, balance),
                    ),
                )
            else:
                await bot.send_message(user_id, ui(language, "direct_rejected"))
        elif approve:
            balance = await rt.db.get_balance_cents(user_id)
            await bot.send_message(
                user_id,
                legacy.t(
                    language,
                    "mpay_confirmed",
                    payment_id=payment_id,
                    amount=legacy.localized_price(rt.settings, language, int(payment["amount_cents"])),
                    balance=legacy.localized_price(rt.settings, language, balance),
                ),
            )
        else:
            await bot.send_message(
                user_id,
                legacy.t(
                    language,
                    "mpay_rejected",
                    payment_id=payment_id,
                    support=legacy.support_contact(rt.settings),
                ),
            )
    except Exception:
        logger.exception("Could not notify user %s about manual payment %s", user_id, payment_id)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


async def main() -> None:
    settings = legacy.load_settings()
    db = legacy.Database(settings.db_path)
    await db.initialize()
    await db.ensure_product_catalog(settings.products, settings.regional_prices, settings.stock_display)
    crypto = legacy.CryptoPayClient(
        token=settings.crypto_pay_token,
        base_url=settings.crypto_pay_base_url,
        accepted_assets=settings.accepted_assets,
    )
    await crypto.start()

    # All imported legacy helpers read this shared runtime.
    legacy.runtime = legacy.Runtime(settings=settings, db=db, crypto=crypto)
    await legacy.sync_runtime_products()
    await ensure_v2_schema()

    bot = Bot(
        token=settings.bot_token,
        session=AiohttpSession(proxy=settings.telegram_proxy),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    # New customer handlers must be first.  Legacy comes second for admin,
    # existing manual-payment hash FSM, top-up callbacks and compatibility.
    dispatcher.include_router(router)
    dispatcher.include_router(legacy.router)
    watcher = asyncio.create_task(payment_watcher_v2(bot))
    try:
        crypto_info = await crypto.get_me()
        logger.info("Crypto Pay app connected: %s", crypto_info.get("name", "unknown"))
        logger.info("Starting Telegram polling with inline storefront v2")
        await dispatcher.start_polling(bot)
    finally:
        watcher.cancel()
        await asyncio.gather(watcher, return_exceptions=True)
        await bot.session.close()
        await crypto.close()
        await db.close()
        legacy.runtime = None


if __name__ == "__main__":
    asyncio.run(main())
