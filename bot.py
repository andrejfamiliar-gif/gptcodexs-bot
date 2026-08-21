from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_UP
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ButtonStyle, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import (
    Product,
    Settings,
    convert_usd_cents,
    currency_for_language,
    format_fiat_price,
    format_local_amount_plain,
    format_local_price,
    format_usd,
    load_settings,
    parse_local_amount_cents,
    product_title,
)
from database import Database
from i18n import (
    LANGUAGES,
    LANGUAGE_NAMES,
    MIN_TOPUP_CENTS,
    TOPUP_PRESETS_CENTS,
    action_for_text,
    balance_keyboard,
    cancel_keyboard,
    catalog_keyboard,
    help_keyboard,
    language_keyboard,
    main_keyboard,
    mpay_admin_keyboard,
    mpay_asset_keyboard,
    mpay_network_keyboard,
    mpay_pending_keyboard,
    payment_keyboard,
    payment_method_keyboard,
    plus_keyboard,
    pro_keyboard,
    queue_button_keyboard,
    queue_keyboard,
    queue_payment_keyboard,
    queue_purchase_keyboard,
    queue_quantity_keyboard,
    purchase_notification_keyboard,
    settings_keyboard,
    t,
    top_up_keyboard,
)
from crypto_fallback import CAPTURED_AT, fallback_rate
from crypto_pay import CryptoPayClient
from crypto_wallets import Wallet


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
PRODUCT_KEY_RE = re.compile(r"[a-z0-9_]{2,40}")
PRODUCT_KEY_HINT = "строчные латинские буквы, цифры и _, длина 2–40"
# A category slug travels inside callback data, which Telegram caps at 64 bytes,
# so it is kept shorter than a product key on purpose.
CATEGORY_SLUG_RE = re.compile(r"[a-z0-9_]{2,24}")
CATEGORY_SLUG_HINT = "строчные латинские буквы, цифры и _, длина 2–24"
MAX_PRICE_UNITS = Decimal("1000000")
# Telegram's hard message limit is 4096 characters.
MAX_BROADCAST_LENGTH = 4000
# Share of every paid order that goes to whoever invited the buyer. Changing it
# only affects orders settled from then on: past payouts are already recorded.
REFERRAL_PERCENT = 15
# Campaign dates are UTC and intentionally explicit so a restart cannot move
# the deadline based on the host's local timezone.
REFERRAL_PROMO_KEY = "referral_5_usd_to_1_usd_2026"
REFERRAL_PROMO_THRESHOLD_CENTS = 500
REFERRAL_PROMO_BONUS_CENTS = 100
REFERRAL_PROMO_START = "2026-08-22T00:00:00+00:00"
REFERRAL_PROMO_END = "2026-09-05T23:59:59+00:00"


def parse_price_cents(raw_value: str) -> int | None:
    try:
        amount = Decimal(raw_value.strip().replace(",", "."))
    except InvalidOperation:
        return None
    if amount <= 0 or amount > MAX_PRICE_UNITS:
        return None
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class TopUpStates(StatesGroup):
    waiting_amount = State()


class ProductQuantityStates(StatesGroup):
    waiting_quantity = State()


class AdminStockStates(StatesGroup):
    waiting_payload = State()
    waiting_remove_id = State()
    waiting_quantity = State()


class AdminBalanceStates(StatesGroup):
    waiting_amount = State()


class AdminProductStates(StatesGroup):
    waiting_definition = State()
    waiting_prices = State()
    waiting_title = State()
    waiting_discount = State()


class AdminCategoryStates(StatesGroup):
    waiting_definition = State()
    waiting_title = State()


class AdminBroadcastStates(StatesGroup):
    waiting_message = State()
    waiting_confirmation = State()


class SupportTicketStates(StatesGroup):
    waiting_message = State()


class AdminTicketStates(StatesGroup):
    waiting_reply = State()


class ManualPaymentStates(StatesGroup):
    waiting_tx_hash = State()


# A tx hash is opaque and its shape varies by chain (64 hex on EVM/BTC, base58
# on Solana, base64-ish on TON), so this only rejects text that cannot be a
# hash at all. The admin is the real check.
TX_HASH_RE = re.compile(r"[A-Za-z0-9:_\-]{16,120}")


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


async def sync_runtime_products() -> None:
    rt = get_runtime()
    rows = await rt.db.list_products()
    products: dict[str, Product] = {}
    regional_prices: dict[str, dict[str, int]] = {}
    for row in rows:
        key = str(row["product_key"])
        products[key] = Product(
            key=key,
            # The products table stores three title columns; a product name is
            # the same string in every language anyway, so the English one is
            # copied across the rest instead of falling back to the raw key.
            title=product_title(str(row["title_en"] or row["title_ru"] or key))
            | {
                "ru": str(row["title_ru"]),
                "en": str(row["title_en"]),
                "zh": str(row["title_zh"]),
            },
            price_cents=int(row["price_usd_cents"]),
            category=str(row["category"] or "catalog"),
            discount_percent=max(0, min(99, int(row["discount_percent"] or 0))),
        )
        usd_cents = discounted_product_usd_cents(products[key])
        # USD is the single source of truth. Every buyer currency is derived
        # from the configured rate, so an admin only has to change one number
        # and a restart cannot resurrect an old regional price.
        regional_prices[key] = {
            language: convert_usd_cents(usd_cents, rate)
            for language, rate in rt.settings.currency_rates.items()
        }
    rt.settings.products.clear()
    rt.settings.products.update(products)
    rt.settings.regional_prices.clear()
    rt.settings.regional_prices.update(regional_prices)
    await sync_category_titles()


# Category slug -> the title the owner gave it in the panel. Kept in memory so
# every keyboard build does not turn into a query; refreshed whenever the owner
# changes a category or a product.
CATEGORY_TITLES: dict[str, str] = {}


async def sync_category_titles() -> None:
    rows = await get_runtime().db.list_categories()
    CATEGORY_TITLES.clear()
    CATEGORY_TITLES.update({str(row["slug"]): str(row["title"]) for row in rows})


def product_label(product: Product, language: str = "ru") -> str:
    """The product's name in the buyer's language, or the closest thing to it.

    Titles are stored for ru/en/zh only, so a Vietnamese or Hindi buyer falls
    back to English instead of being shown the raw product key.
    """
    for code in (language, "en", "ru", "zh"):
        title = product.title.get(code)
        if title:
            return str(title)
    return product.key


def admin_panel_keyboard(pending_manual: int = 0) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin:users:0"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats"),
        ],
        [InlineKeyboardButton(text="📦 Остатки", callback_data="admin:stock")],
        [InlineKeyboardButton(text="🛍 Товары и цены", callback_data="admin:products")],
        [InlineKeyboardButton(text="🗂 Категории", callback_data="admin:cats")],
        [InlineKeyboardButton(text="💵 Пополнить баланс", callback_data="admin:balance")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="🎫 Тикеты поддержки", callback_data="admin:tickets")],
    ]
    # Only shown when something is actually waiting, and coloured so an unread
    # payment is hard to walk past.
    if pending_manual > 0:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🪙 Ручные платежи ({pending_manual})",
                    callback_data="admin:manual",
                    style=ButtonStyle.DANGER,
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ В панель", callback_data="admin:home")]]
    )


async def admin_stock_keyboard() -> InlineKeyboardMarkup:
    """One regulated number per product, with the number on the button.

    The count shown here is the same one the storefront shows and the same one a
    sale decrements — there is no second "real" figure to keep in sync.
    """
    rt = get_runtime()
    stock = await rt.db.available_stock()
    rows: list[list[InlineKeyboardButton]] = []
    for key, product in rt.settings.products.items():
        offered = stock.get(key, 0)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{'🟢' if offered else '🔴'} {product_label(product)} · {offered}",
                    callback_data=f"admin:stock:set:{key}",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(text="➖5", callback_data=f"admin:stock:adjust:{key}:-5"),
                InlineKeyboardButton(text="➖1", callback_data=f"admin:stock:adjust:{key}:-1"),
                InlineKeyboardButton(text="➕1", callback_data=f"admin:stock:adjust:{key}:1"),
                InlineKeyboardButton(text="➕5", callback_data=f"admin:stock:adjust:{key}:5"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="⬆️ Загрузить аккаунты",
                    callback_data=f"admin:stock:payload:{key}",
                )
            ]
        )
    rows.extend(
        [
            [InlineKeyboardButton(text="🗑 Удалить данные по ID", callback_data="admin:stock:remove")],
            [InlineKeyboardButton(text="📣 Объявить о поступлении", callback_data="admin:stock:announce")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin:stock")],
            [InlineKeyboardButton(text="⬅️ В панель", callback_data="admin:home")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_announce_confirm_keyboard() -> InlineKeyboardMarkup:
    """Two taps before a broadcast to everyone, because one tap is not undoable."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Отправить всем",
                    callback_data="admin:stock:announce:go",
                    style=ButtonStyle.SUCCESS,
                )
            ],
            [
                InlineKeyboardButton(
                    text="✖️ Отмена",
                    callback_data="admin:stock",
                    style=ButtonStyle.DANGER,
                )
            ],
        ]
    )


def admin_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Confirm a custom broadcast separately from the stock announcement."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Отправить всем",
                    callback_data="admin:broadcast:go",
                    style=ButtonStyle.SUCCESS,
                )
            ],
            [
                InlineKeyboardButton(
                    text="✖️ Отмена",
                    callback_data="admin:broadcast:cancel",
                    style=ButtonStyle.DANGER,
                )
            ],
        ]
    )


def admin_ticket_card_keyboard(
    ticket_id: int,
    closed: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if not closed:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✉️ Ответить",
                    callback_data=f"admin:ticket:reply:{ticket_id}",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    text="✅ Закрыть",
                    callback_data=f"admin:ticket:close:{ticket_id}",
                    style=ButtonStyle.SUCCESS,
                ),
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ К тикетам", callback_data="admin:tickets")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_tickets_keyboard(
    rows: list[object],
    page: int,
    total: int,
) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    for row in rows:
        ticket_id = int(row["id"])  # type: ignore[index]
        username = row["username"]  # type: ignore[index]
        label = f"@{username}" if username else str(row["user_id"])  # type: ignore[index]
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"🎫 #{ticket_id} · {label}",
                    callback_data=f"admin:ticket:card:{ticket_id}",
                )
            ]
        )
    navigation: list[InlineKeyboardButton] = []
    if page > 0:
        navigation.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin:tickets:{page - 1}"))
    if (page + 1) * 10 < total:
        navigation.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"admin:tickets:{page + 1}"))
    if navigation:
        buttons.append(navigation)
    buttons.append([InlineKeyboardButton(text="⬅️ В панель", callback_data="admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_products_keyboard() -> InlineKeyboardMarkup:
    rt = get_runtime()
    rows: list[list[InlineKeyboardButton]] = []
    for key, product in rt.settings.products.items():
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🛍 {product_label(product)}",
                    callback_data=f"admin:product:card:{key}",
                )
            ]
        )
    rows.extend(
        [
            [InlineKeyboardButton(text="➕ Новый товар", callback_data="admin:product:new")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin:products")],
            [InlineKeyboardButton(text="⬅️ В панель", callback_data="admin:home")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_product_card_keyboard(product_key: str) -> InlineKeyboardMarkup:
    """Everything that can be done to one product, on one screen."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💵 Цены",
                    callback_data=f"admin:product:price:{product_key}",
                ),
                InlineKeyboardButton(
                    text="🏷 Скидка",
                    callback_data=f"admin:product:discount:{product_key}",
                ),
                InlineKeyboardButton(
                    text="✏️ Название",
                    callback_data=f"admin:product:rename:{product_key}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗂 Категория",
                    callback_data=f"admin:product:cat:{product_key}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Снять с продажи",
                    callback_data=f"admin:product:del:{product_key}",
                    style=ButtonStyle.DANGER,
                )
            ],
            [
                InlineKeyboardButton(text="⬅️ К товарам", callback_data="admin:products"),
                InlineKeyboardButton(text="🏠 В панель", callback_data="admin:home"),
            ],
        ]
    )


def admin_confirm_keyboard(yes_data: str, no_data: str, yes_text: str = "✅ Подтвердить") -> InlineKeyboardMarkup:
    """Two taps for anything that cannot be undone with one."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=yes_text, callback_data=yes_data, style=ButtonStyle.DANGER)],
            [InlineKeyboardButton(text="✖️ Отмена", callback_data=no_data)],
        ]
    )


async def admin_categories_keyboard() -> InlineKeyboardMarkup:
    """One row per section, plus the way to add one."""
    rt = get_runtime()
    counts: dict[str, int] = {}
    for product in rt.settings.products.values():
        counts[product.category] = counts.get(product.category, 0) + 1
    rows: list[list[InlineKeyboardButton]] = []
    for row in await rt.db.list_categories():
        slug = str(row["slug"])
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{row['title']} ({counts.get(slug, 0)})",
                    callback_data=f"admin:cat:card:{slug}",
                )
            ]
        )
    rows.extend(
        [
            [InlineKeyboardButton(text="➕ Новая категория", callback_data="admin:cat:new")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin:cats")],
            [InlineKeyboardButton(text="⬅️ В панель", callback_data="admin:home")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_category_card_keyboard(slug: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Переименовать",
                    callback_data=f"admin:cat:rename:{slug}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Добавить товар сюда",
                    callback_data=f"admin:cat:add:{slug}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить категорию",
                    callback_data=f"admin:cat:del:{slug}",
                    style=ButtonStyle.DANGER,
                )
            ],
            [
                InlineKeyboardButton(text="⬅️ К категориям", callback_data="admin:cats"),
                InlineKeyboardButton(text="🏠 В панель", callback_data="admin:home"),
            ],
        ]
    )


def admin_pick_product_keyboard(exclude: str | None = None) -> InlineKeyboardMarkup:
    """Choose which product the pending category action applies to.

    Only the product key rides in the callback data — the category it is being
    moved into is held in FSM data, because both together would not fit in
    Telegram's 64-byte callback payload.
    """
    rt = get_runtime()
    rows = [
        [
            InlineKeyboardButton(
                text=product_label(product),
                callback_data=f"admin:setprod:{key}",
            )
        ]
        for key, product in rt.settings.products.items()
        if product.category != exclude
    ]
    rows.append([InlineKeyboardButton(text="✖️ Отмена", callback_data="admin:cats")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_pick_category_keyboard(product_key: str, categories: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{title} ({slug})",
                callback_data=f"admin:setcat:{slug}",
            )
        ]
        for slug, title in categories
    ]
    rows.append(
        [InlineKeyboardButton(text="✖️ Отмена", callback_data=f"admin:product:card:{product_key}")]
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


def _funnel_line(label: str, people: int, base: int, hits: int | None = None) -> str:
    """One funnel step with its share of the top of the funnel.

    The share is of everyone who ever opened the bot, so the numbers read as a
    funnel rather than as unrelated counters. ``hits`` is the raw event count
    where it says something the head-count does not — how many times the step was
    repeated.
    """
    share = f" · {people * 100 // base}%" if base > 0 else ""
    repeats = f" (событий: {hits})" if hits is not None and hits > people else ""
    return f"{label}: <b>{people}</b>{share}{repeats}"


async def admin_stats_text() -> str:
    rt = get_runtime()
    db = rt.db
    total_users = await db.count_users()
    events = await db.event_counts()
    orders = await db.order_stats()
    referrals = await db.referral_totals()
    manual = await db.manual_payment_stats()
    open_tickets = await db.count_support_tickets("open")
    languages = await db.users_by_language()
    waiting = await db.waitlist_counts()
    balances = await db.balance_total_cents()
    day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    new_day = await db.count_users_since(day_ago)
    new_week = await db.count_users_since(week_ago)
    events_day = await db.event_counts(day_ago)

    def people(event: str, table: dict[str, tuple[int, int]] | None = None) -> int:
        return (table if table is not None else events).get(event, (0, 0))[1]

    def hits(event: str) -> int:
        return events.get(event, (0, 0))[0]

    # Everyone who has ever pressed /start is the top of the funnel. Users who
    # predate event tracking have no 'start' row, so the registered count is the
    # honest denominator.
    base = max(total_users, people("start"))
    lines = [
        "📊 <b>Статистика</b>",
        "",
        "<b>Аудитория</b>",
        f"Всего пользователей: <b>{total_users}</b>",
        f"Пришло за сутки: <b>{new_day}</b> · за неделю: <b>{new_week}</b>",
        f"Заходов в бота за сутки: <b>{people('start', events_day)}</b>",
        "",
        "<b>Воронка</b>",
        _funnel_line("Зашли в бота", people("start"), base, hits("start")),
        _funnel_line("Открыли каталог", people("catalog"), base, hits("catalog")),
        _funnel_line("Открыли карточку товара", people("product_view"), base, hits("product_view")),
        _funnel_line("Дошли до выбора оплаты", people("checkout"), base, hits("checkout")),
        _funnel_line("Выбрали Crypto Bot", people("pay_cryptobot"), base, hits("pay_cryptobot")),
        _funnel_line("Выбрали Cryptocurrency", people("pay_crypto"), base, hits("pay_crypto")),
        _funnel_line("Выбрали оплату с баланса", people("pay_balance"), base, hits("pay_balance")),
        _funnel_line("Оплатили", orders["buyers"], base),
        "",
        "<b>Продажи</b>",
        f"Оплаченных заказов: <b>{orders['paid_orders']}</b> "
        f"(товаров: {orders['units']})",
        f"Выручка: <b>{format_usd(orders['revenue_cents'])}</b>",
        f"Ждут склад: <b>{orders['waiting_stock']}</b>",
        f"Открытых тикетов поддержки: <b>{open_tickets}</b>",
        "",
        "<b>Пополнения баланса</b>",
        f"Оплаченных: <b>{orders['topup_orders']}</b> "
        f"на <b>{format_usd(orders['topup_cents'])}</b>",
        f"Сумма всех балансов сейчас: <b>{format_usd(balances)}</b>",
        f"Открывали пополнение: <b>{people('topup_open')}</b>",
    ]

    if manual:
        pretty = {
            "awaiting_hash": "ждут хеш",
            "pending": "на проверке",
            "confirmed": "подтверждено",
            "rejected": "отклонено",
            "expired": "истекло",
        }
        lines.extend(
            [
                "",
                "<b>Ручные крипто-переводы</b>",
                " · ".join(
                    f"{pretty.get(status, status)}: {count}"
                    for status, count in sorted(manual.items())
                ),
            ]
        )

    lines.extend(
        [
            "",
            "<b>Рефералы</b>",
            f"Пришло по ссылкам: <b>{referrals['invited_users']}</b>",
            f"Выплат: <b>{referrals['payouts']}</b> "
            f"на <b>{format_usd(referrals['total_cents'])}</b> "
            f"({referrals['earners']} получателей)",
        ]
    )

    top = await db.paid_orders_by_product()
    sellers = [row for row in top if str(row["product_key"]) != "balance_topup"]
    if sellers:
        lines.extend(["", "<b>Что покупают</b>"])
        for row in sellers:
            key = str(row["product_key"])
            product = rt.settings.products.get(key)
            name = product_label(product) if product else key
            lines.append(
                f"• {html.escape(name)} — {int(row['units'])} шт. "
                f"({int(row['orders'])} заказов)"
            )

    if waiting:
        lines.extend(["", "<b>Ждут наличия</b>"])
        for key, count in sorted(waiting.items(), key=lambda item: -item[1]):
            product = rt.settings.products.get(key)
            name = product_label(product) if product else key
            lines.append(f"• {html.escape(name)} — {count}")

    if languages:
        lines.extend(
            [
                "",
                "<b>Языки</b>",
                " · ".join(f"{code}: {count}" for code, count in languages.items()),
            ]
        )

    if not events:
        lines.extend(
            [
                "",
                "<i>Воронка начала считаться с этого обновления, "
                "поэтому у старых пользователей шагов нет.</i>",
            ]
        )
    return "\n".join(lines)


async def admin_stock_text() -> str:
    rt = get_runtime()
    stock = await rt.db.available_stock()
    lines = [
        "📦 <b>Склад</b>",
        "",
        "<i>Одно число на товар — его видит покупатель и оно уменьшается после оплаты.</i>",
        "",
    ]
    for key, product in rt.settings.products.items():
        offered = stock.get(key, 0)
        lines.append(
            f"{'🟢' if offered > 0 else '🔴'} <b>{html.escape(product_label(product))}</b>: {offered}"
        )
    return "\n".join(lines)


async def admin_products_text() -> str:
    rt = get_runtime()
    lines = ["🛍 Товары и цены", "", "Нажми на товар, чтобы изменить или снять с продажи", ""]
    if not rt.settings.products:
        lines.append("Товаров пока нет.")
        return "\n".join(lines)
    stock = await rt.db.available_stock()
    for key, product in rt.settings.products.items():
        # Every currency the shop sells in, not just the original three: a price
        # the owner cannot see in the panel is a price they cannot check.
        prices = " · ".join(
            product_price(rt.settings, product, language) for language in LANGUAGES
        )
        lines.append(
            f"• <b>{html.escape(product_label(product))}</b> "
            f"(<code>{html.escape(key)}</code>)\n"
            f"  🗂 {html.escape(product.category)} · 📦 {stock.get(key, 0)}\n"
            f"  🏷 Скидка: <b>{int(product.discount_percent)}%</b>\n"
            f"  {prices}"
        )
    return "\n".join(lines)


async def admin_product_card_text(product_key: str) -> str | None:
    """One product's full card, or ``None`` if it is no longer on sale."""
    rt = get_runtime()
    product = rt.settings.products.get(product_key)
    if product is None:
        return None
    stock = await rt.db.available_stock()
    titles = " / ".join(
        html.escape(str(product.title.get(code, "—"))) for code in ("ru", "en", "zh")
    )
    prices = "\n".join(
        f"  {language}: {product_price(rt.settings, product, language)}" for language in LANGUAGES
    )
    return (
        f"🛍 <b>{html.escape(product_label(product))}</b>\n"
        f"<code>{html.escape(product_key)}</code>\n\n"
        f"🗂 Категория: <b>{html.escape(product.category)}</b>\n"
        f"📦 Остаток: <b>{stock.get(product_key, 0)}</b>\n"
        f"🏷 Скидка: <b>{int(product.discount_percent)}%</b>\n"
        f"💵 Цена USD: <s>{product.price_cents / 100:.2f}</s> → "
        f"<b>{discounted_product_usd_cents(product) / 100:.2f}</b>\n"
        "\n"
        f"🏷 Названия (ru / en / zh):\n  {titles}\n\n"
        f"💵 Цены:\n{prices}"
    )


async def admin_categories_text() -> str:
    rt = get_runtime()
    rows = await rt.db.list_categories()
    lines = [
        "🗂 <b>Категории</b>",
        "",
        "<i>Категория — это раздел в каталоге. Товар всегда лежит ровно в одной.</i>",
        "",
    ]
    if not rows:
        lines.append("Категорий пока нет — создай первую.")
        return "\n".join(lines)
    for row in rows:
        slug = str(row["slug"])
        names = [
            product_label(product)
            for product in rt.settings.products.values()
            if product.category == slug
        ]
        lines.append(
            f"• <b>{html.escape(str(row['title']))}</b> (<code>{html.escape(slug)}</code>) — "
            f"{len(names)} шт."
        )
        if names:
            lines.append("  " + html.escape(", ".join(names[:12])))
    orphans = sorted(
        {
            product.category
            for product in rt.settings.products.values()
            if product.category not in {str(row["slug"]) for row in rows}
        }
    )
    if orphans:
        lines.extend(
            [
                "",
                "⚠️ Товары ссылаются на разделы, которых нет в списке: "
                + html.escape(", ".join(orphans)),
                "Создай их с этими же slug или перенеси товары.",
            ]
        )
    return "\n".join(lines)


def product_for_action(action: str, settings: Settings) -> Product | None:
    return {
        "plus": settings.products.get("gpt_plus_nw"),
    }.get(action)


def localized_price(settings: Settings, language: str, amount_cents: int) -> str:
    return format_local_price(amount_cents, language, settings.currency_rates)


def discounted_product_usd_cents(product: Product) -> int:
    """Return the payable USD price after the product's individual discount."""
    percent = max(0, min(99, int(product.discount_percent)))
    if percent == 0:
        return product.price_cents
    return max(1, (product.price_cents * (100 - percent) + 50) // 100)


def product_amount(settings: Settings, product: Product, language: str) -> int:
    return settings.regional_prices.get(product.key, {}).get(
        language,
        convert_usd_cents(discounted_product_usd_cents(product), settings.currency_rates.get(language, Decimal("1"))),
    )


def original_product_amount(settings: Settings, product: Product, language: str) -> int:
    return convert_usd_cents(
        product.price_cents,
        settings.currency_rates.get(language, Decimal("1")),
    )


def product_price(settings: Settings, product: Product, language: str) -> str:
    return format_fiat_price(product_amount(settings, product, language), currency_for_language(language))


def product_price_button(settings: Settings, product: Product, language: str) -> str:
    current = product_price(settings, product, language)
    if not product.discount_percent:
        return current
    original = format_fiat_price(
        original_product_amount(settings, product, language),
        currency_for_language(language),
    )
    return f"{original} → {current} (-{int(product.discount_percent)}%)"


def product_price_display(settings: Settings, product: Product, language: str) -> str:
    current = product_price(settings, product, language)
    if not product.discount_percent:
        return current
    original = format_fiat_price(
        original_product_amount(settings, product, language),
        currency_for_language(language),
    )
    return f"<s>{original}</s> → <b>{current}</b> (-{int(product.discount_percent)}%)"


def product_price_labels(settings: Settings, language: str) -> dict[str, str]:
    return {
        key: product_price_button(settings, product, language)
        for key, product in settings.products.items()
    }


def top_up_price_labels(settings: Settings, language: str) -> dict[int, str]:
    """Preset top-up amounts in the buyer's currency, keyed by USD cents.

    Keyed by cents rather than whole dollars because the smallest preset is the
    $1.30 floor, which has no whole-dollar key to be looked up under.
    """
    return {
        cents: localized_price(settings, language, cents)
        for cents in TOPUP_PRESETS_CENTS
    }


def top_up_prompt_text(language: str) -> str:
    """"Enter an amount" — naming the currency the buyer is expected to type in."""
    return t(language, "top_up_other", currency=currency_for_language(language))


def invalid_amount_text(language: str) -> str:
    """"That is not a valid amount", with an example the buyer can actually type.

    The example is the smallest preset top-up rendered in the buyer's own
    currency, so a Vietnamese buyer sees 52000 rather than 2.00 and does not
    keep retyping a figure the bot will reject as too small.
    """
    rates = get_runtime().settings.currency_rates
    return t(language, "top_up_invalid", example=format_local_amount_plain(200, language, rates))


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


def formatted_account_payload(raw_payload: str | None, language: str = "en") -> str:
    if not raw_payload:
        return ""
    try:
        parsed = json.loads(raw_payload)
    except (TypeError, json.JSONDecodeError):
        parsed = [raw_payload]
    if not isinstance(parsed, list):
        parsed = [parsed]
    payloads = [str(item) for item in parsed if str(item).strip()]
    labels = {
        "ru": ("Аккаунт", "Логин", "Пароль", "Логин и пароль", "Данные"),
        "en": ("Account", "Login", "Password", "Login + password", "Data"),
        "zh": ("账号", "登录名", "密码", "登录名和密码", "数据"),
        "vi": ("Tài khoản", "Đăng nhập", "Mật khẩu", "Đăng nhập + mật khẩu", "Dữ liệu"),
        "hi": ("खाता", "लॉगिन", "पासवर्ड", "लॉगिन + पासवर्ड", "डेटा"),
    }.get(language, ("Account", "Login", "Password", "Login + password", "Data"))
    account_label, login_label, password_label, pair_label, data_label = labels
    blocks: list[str] = []
    for index, payload in enumerate(payloads, start=1):
        if ":" in payload:
            login, password = payload.split(":", maxsplit=1)
            block = (
                f"{account_label} {index}:\n"
                f"{login_label}: {html.escape(login)}\n"
                f"{password_label}: {html.escape(password)}\n"
                f"{pair_label}: {html.escape(payload)}"
            )
        else:
            block = f"{account_label} {index}:\n{data_label}: {html.escape(payload)}"
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
                product_name = product_label(product, language) if product else order["product_key"]
                payload = formatted_account_payload(order["delivery_payload"], language)
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
        product_name = product_label(product) if product else product_key
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


async def notify_admins_waiting_stock(bot: Bot, settlement: dict[str, object]) -> None:
    """Tell the admins that a paid order has nothing to deliver.

    Selling against display stock means an order can legitimately outrun the
    accounts on hand. The buyer was promised delivery within a fixed window, so
    this has to reach a human rather than sit in the ``waiting_stock`` table:
    once accounts are loaded ``deliver_pending_orders`` finishes the job by
    itself, but nobody loads them if nobody knows.
    """
    rt = get_runtime()
    if not rt.settings.admin_ids:
        return
    product_key = str(settlement["product_key"])
    product = rt.settings.products.get(product_key)
    product_name = product_label(product) if product else product_key
    stock = (await rt.db.actual_stock()).get(product_key, 0)
    notification = (
        "⚠️ Оплаченный заказ ждёт склад\n"
        f"Заказ: <code>#{settlement['order_id']}</code>\n"
        f"Товар: {html.escape(product_name)}\n"
        f"Количество: {int(settlement.get('quantity', 1))}\n"
        f"Реальных аккаунтов в наличии: {stock}\n"
        f"Покупателю обещана выдача за {rt.settings.preorder_delivery_hours} ч.\n"
        "Загрузите аккаунты через /admin → Склад — заказ выдастся сам."
    )
    for admin_id in rt.settings.admin_ids:
        try:
            await bot.send_message(admin_id, notification)
        except Exception:
            logger.exception("Could not notify admin %s about waiting stock", admin_id)


def preorder_notice(language: str) -> str:
    """"Payment accepted, delivery within N hours" in the buyer's language."""
    rt = get_runtime()
    return t(
        language,
        "no_stock_after_payment",
        support=support_contact(rt.settings),
        hours=rt.settings.preorder_delivery_hours,
    )


def masked_buyer(username: str | None, user_id: int) -> str:
    raw = f"@{username}" if username else str(user_id)
    safe = html.escape(raw)
    return f"{safe[:3]}***"


async def broadcast_stock_replenished(bot: Bot) -> None:
    rt = get_runtime()
    for row in await rt.db.list_users_for_broadcast():
        language = str(row["language"] or "en")
        try:
            await bot.send_message(row["user_id"], t(language, "stock_replenished"))
            await asyncio.sleep(0.04)
        except Exception:
            logger.exception("Could not send stock notification to %s", row["user_id"])


async def broadcast_custom_message(bot: Bot, body: str) -> tuple[int, int]:
    """Send one admin-authored plain-text message to every registered user.

    Plain text keeps punctuation, links, ``<``/``>`` and emoji from breaking a
    Telegram HTML request. A failed or blocked chat is counted and does not stop
    delivery to the remaining users.
    """
    rt = get_runtime()
    sent = 0
    failed = 0
    for row in await rt.db.list_users_for_broadcast():
        try:
            await bot.send_message(int(row["user_id"]), body, parse_mode=None)
            sent += 1
            await asyncio.sleep(0.04)
        except Exception:
            failed += 1
            logger.exception("Could not send custom broadcast to %s", row["user_id"])
    return sent, failed


async def admin_support_ticket_text(ticket_id: int) -> str | None:
    rt = get_runtime()
    ticket = await rt.db.get_support_ticket(ticket_id)
    if ticket is None:
        return None
    username = str(ticket["username"]).strip() if ticket["username"] else ""
    user_label = f"@{html.escape(username)}" if username else "без username"
    lines = [
        f"🎫 <b>Тикет #{ticket_id}</b>",
        f"Пользователь: {user_label}",
        f"ID пользователя: <code>{int(ticket['user_id'])}</code>",
        f"Язык: {html.escape(str(ticket['language'] or 'не выбран'))}",
        f"Статус: <b>{html.escape(str(ticket['status']))}</b>",
        "",
    ]
    messages = await rt.db.list_support_messages(ticket_id)
    for row in messages[-20:]:
        role = "Пользователь" if str(row["sender_role"]) == "user" else "Администратор"
        body = html.escape(str(row["body"]))
        if len(body) > 1500:
            body = body[:1500] + "…"
        lines.append(f"<b>{role}</b> · {html.escape(str(row['created_at'])[:19])}")
        lines.append(body)
        lines.append("")
    return "\n".join(lines).rstrip()


async def notify_admins_support_ticket(bot: Bot, ticket_id: int) -> None:
    text = await admin_support_ticket_text(ticket_id)
    if text is None:
        return
    rt = get_runtime()
    for admin_id in rt.settings.admin_ids:
        try:
            await bot.send_message(
                admin_id,
                text,
                reply_markup=admin_ticket_card_keyboard(ticket_id),
            )
        except Exception:
            logger.exception("Could not notify admin about support ticket %s", ticket_id)


async def broadcast_purchase_notification(bot: Bot, settlement: dict[str, object]) -> None:
    if settlement.get("product_key") == "balance_topup":
        return
    rt = get_runtime()
    user_id = int(settlement["user_id"])
    user = await rt.db.get_user(user_id)
    buyer = masked_buyer(user["username"] if user else None, user_id)
    product_key = str(settlement["product_key"])
    product = rt.settings.products.get(product_key)
    quantity = int(settlement.get("quantity", 1))
    amount_cents = int(settlement["amount_cents"])
    currency = str(settlement.get("currency", "USD"))
    for row in await rt.db.list_purchase_notification_users():
        # The buyer already got a receipt; a second message telling them
        # somebody bought something reads as another customer, not as
        # themselves, and it is their own purchase being counted back at them.
        if int(row["user_id"]) == user_id:
            continue
        language = str(row["language"] or "en")
        product_name = product_label(product, language) if product else product_key
        # Each recipient sees the price in their own currency. The settlement
        # currency is whatever the buyer paid in, and a Vietnamese reader has no
        # use for someone else's dollar figure.
        if product is not None:
            price = format_fiat_price(
                product_amount(rt.settings, product, language) * max(quantity, 1),
                currency_for_language(language),
            )
        elif currency == "USD":
            price = localized_price(rt.settings, language, amount_cents)
        else:
            price = format_fiat_price(amount_cents, currency)
        try:
            await bot.send_message(
                row["user_id"],
                t(
                    language,
                    "purchase_notification",
                    product=html.escape(product_name),
                    quantity=quantity,
                    price=price,
                    buyer=buyer,
                ),
                reply_markup=purchase_notification_keyboard(language),
            )
            await asyncio.sleep(0.04)
        except Exception:
            logger.exception("Could not send purchase notification to %s", row["user_id"])


async def credit_referral_for_order(bot: Bot, settlement: dict[str, object]) -> None:
    """Pay the inviter their cut of a settled order and tell them about it.

    Balance top-ups are skipped: paying a commission on money moved onto a
    balance and again on the purchase it funds would pay twice for one sale.
    The database call is idempotent per order, so a retried settlement cannot
    double-credit.
    """
    if settlement.get("product_key") == "balance_topup":
        return
    rt = get_runtime()
    payout: dict[str, int] | None = None
    try:
        # ``orders.amount_cents`` is the buyer's display currency for a
        # localized checkout. Referral balances are stored in USD cents, so
        # commission must use the canonical base amount instead.
        order = await rt.db.get_order(int(settlement["order_id"]))
        commission_amount = (
            int(order["balance_amount_cents"] or order["amount_cents"])
            if order is not None
            else int(settlement["amount_cents"])
        )
        payout = await rt.db.credit_referral(
            int(settlement["order_id"]),
            int(settlement["user_id"]),
            commission_amount,
            REFERRAL_PERCENT,
        )
    except Exception:
        logger.exception("Could not credit referral for order %s", settlement.get("order_id"))
    if payout is not None:
        referrer_id = int(payout["referrer_id"])
        language = await rt.db.get_language(referrer_id) or "en"
        try:
            await bot.send_message(
                referrer_id,
                t(
                    language,
                    "referral_bonus",
                    bonus=localized_price(rt.settings, language, int(payout["bonus_cents"])),
                    percent=REFERRAL_PERCENT,
                    balance=localized_price(rt.settings, language, int(payout["balance_cents"])),
                ),
            )
        except Exception:
            # The money is already on their balance; a failed message must not undo it.
            logger.exception("Could not notify referrer %s about a bonus", referrer_id)

    await credit_referral_campaign_for_order(bot, settlement)


async def credit_referral_campaign_for_order(
    bot: Bot,
    settlement: dict[str, object],
) -> None:
    """Apply the time-limited cumulative $5 → $1 referral campaign."""
    if settlement.get("product_key") == "balance_topup":
        return
    rt = get_runtime()
    try:
        reward = await rt.db.credit_referral_campaign(
            campaign_key=REFERRAL_PROMO_KEY,
            order_id=int(settlement["order_id"]),
            buyer_id=int(settlement["user_id"]),
            threshold_cents=REFERRAL_PROMO_THRESHOLD_CENTS,
            bonus_cents=REFERRAL_PROMO_BONUS_CENTS,
            starts_at=REFERRAL_PROMO_START,
            ends_at=REFERRAL_PROMO_END,
        )
    except Exception:
        logger.exception(
            "Could not credit referral campaign for order %s",
            settlement.get("order_id"),
        )
        return
    if reward is None:
        return
    referrer_id = int(reward["referrer_id"])
    language = await rt.db.get_language(referrer_id) or "en"
    try:
        await bot.send_message(
            referrer_id,
            t(
                language,
                "referral_campaign_bonus",
                bonus=localized_price(rt.settings, language, int(reward["bonus_cents"])),
                bonus_usd=format_usd(int(reward["bonus_cents"])),
                total=format_usd(int(reward["total_cents"])),
                balance=localized_price(rt.settings, language, int(reward["balance_cents"])),
            ),
        )
    except Exception:
        logger.exception("Could not notify referrer %s about campaign reward", referrer_id)


async def settle_invoice(bot: Bot, order_id: int) -> dict[str, object] | None:
    rt = get_runtime()
    settlement = await rt.db.settle_paid_order(
        order_id,
        decrement_stock=rt.settings.decrement_stock_on_payment,
    )
    if settlement is not None:
        await notify_admins_payment(bot, settlement)
        await broadcast_purchase_notification(bot, settlement)
        await credit_referral_for_order(bot, settlement)
    if settlement is not None and settlement["delivery_status"] == "waiting_stock":
        language = await rt.db.get_language(settlement["user_id"]) or "en"
        await bot.send_message(settlement["user_id"], preorder_notice(language))
        await notify_admins_waiting_stock(bot, settlement)
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
        product_name = product_label(product, language)
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
            # Requests the buyer never followed up on are cleared so a later
            # attempt is not blocked by an abandoned one. Rows already waiting
            # on an admin are left alone by the query itself.
            expired = await rt.db.expire_stale_manual_payments(
                rt.settings.manual_crypto_note_hours
            )
            if expired:
                logger.info("Expired %s stale manual payment request(s)", expired)
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


@router.message(SupportTicketStates.waiting_message)
async def support_ticket_message_handler(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    language = await selected_language(message)
    if language is None:
        await state.clear()
        await send_language_prompt(message)
        return
    body = (message.text or "").strip()
    if body.lower() == "/cancel":
        await state.clear()
        await message.answer(t(language, "action_cancelled"))
        return
    if not body:
        await message.answer(t(language, "support_ticket_prompt"))
        return
    if len(body) > MAX_BROADCAST_LENGTH:
        await message.answer(t(language, "support_ticket_too_long"))
        return
    db = get_runtime().db
    data = await state.get_data()
    existing_ticket = data.get("ticket_id")
    if existing_ticket is not None:
        try:
            ticket_id = int(existing_ticket)
        except (TypeError, ValueError):
            await state.clear()
            await message.answer(t(language, "generic_error"))
            return
        ticket = await db.get_support_ticket(ticket_id)
        if (
            ticket is None
            or int(ticket["user_id"]) != user_id_from_message(message)
            or str(ticket["status"]) != "open"
            or not await db.add_support_message(
                ticket_id,
                "user",
                user_id_from_message(message),
                body,
            )
        ):
            await state.clear()
            await message.answer(t(language, "support_ticket_already_closed"))
            return
        await state.clear()
        await message.answer(t(language, "support_ticket_message_sent", ticket_id=ticket_id))
        await notify_admins_support_ticket(bot, ticket_id)
        return
    ticket_id = await db.create_support_ticket(
        user_id=user_id_from_message(message),
        body=body,
    )
    await state.clear()
    await message.answer(t(language, "support_ticket_created", ticket_id=ticket_id))
    await notify_admins_support_ticket(bot, ticket_id)


async def send_settings_message(message: Message, language: str) -> None:
    rt = get_runtime()
    enabled = await rt.db.get_purchase_notifications(user_id_from_message(message))
    status = t(language, "notifications_on" if enabled else "notifications_off")
    await message.answer(
        t(language, "settings", status=status),
        reply_markup=settings_keyboard(language, enabled),
    )


@router.message(Command("settings"))
async def settings_command(message: Message) -> None:
    language = await selected_language(message)
    if language is None:
        await send_language_prompt(message)
        return
    await send_settings_message(message, language)


@router.callback_query(F.data.startswith("purchase_notify:"))
async def purchase_notifications_callback(callback: CallbackQuery) -> None:
    language = await ensure_callback_user(callback)
    if language not in LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    action = (callback.data or "").split(":", maxsplit=1)[1]
    if action not in {"on", "off"}:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    enabled = action == "on"
    await get_runtime().db.set_purchase_notifications(callback.from_user.id, enabled)
    await callback.answer(t(language, "notifications_updated"))
    if callback.message is not None:
        status = t(language, "notifications_on" if enabled else "notifications_off")
        try:
            await callback.message.edit_text(
                t(language, "settings", status=status),
                reply_markup=settings_keyboard(language, enabled),
            )
        except TelegramBadRequest:
            pass


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
    if choice == "cancel":
        # Leaving the amount prompt has to be one tap. Without this the buyer is
        # stuck in the state and every message they send is read as an amount.
        await state.clear()
        await callback.answer(t(language, "top_up_cancelled"))
        if callback.message is not None:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except TelegramBadRequest:
                pass
        return
    if choice == "other":
        await state.set_state(TopUpStates.waiting_amount)
        await callback.answer()
        if callback.message is not None:
            await callback.message.answer(
                f"{top_up_prompt_text(language)}\n"
                f"{min_topup_text(language)}\n"
                f"{t(language, 'cancel_hint')}",
                reply_markup=cancel_keyboard(language),
            )
        return
    try:
        amount_cents = int(choice)
    except ValueError:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await offer_payment_methods(
            callback.message,
            callback.from_user.id,
            language,
            amount_cents,
        )


def min_topup_text(language: str) -> str:
    """"Minimum X" in the buyer's own currency."""
    rates = get_runtime().settings.currency_rates
    return t(
        language,
        "top_up_min_hint",
        minimum=format_local_price(MIN_TOPUP_CENTS, language, rates),
    )


def too_small_text(language: str) -> str:
    rates = get_runtime().settings.currency_rates
    return t(
        language,
        "top_up_too_small",
        minimum=format_local_price(MIN_TOPUP_CENTS, language, rates),
    )


async def offer_payment_methods(
    message: Message,
    user_id: int,
    language: str,
    amount_cents: int,
) -> None:
    """Ask Crypto Pay or manual transfer, unless there is nothing to choose.

    With no enabled wallet the manual route does not exist, so the buyer goes
    straight to a Crypto Pay invoice exactly as before — the choice screen only
    appears when it is a real choice.

    ``user_id`` is passed in rather than read off ``message``: when this is
    called from a callback the message was sent by the bot, so its ``from_user``
    is the bot itself.
    """
    rt = get_runtime()
    if amount_cents > 1_000_000:
        await message.answer(invalid_amount_text(language))
        return
    if amount_cents < MIN_TOPUP_CENTS:
        # Below the floor the network fee eats the top-up, so it is refused here
        # rather than after an invoice the buyer cannot usefully pay.
        await message.answer(too_small_text(language))
        return
    if not rt.settings.crypto_wallets:
        await send_topup_invoice(message, user_id, language, amount_cents)
        return
    await message.answer(
        t(
            language,
            "mpay_method",
            amount=localized_price(rt.settings, language, amount_cents),
        ),
        reply_markup=payment_method_keyboard(language, amount_cents),
    )


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
    if amount_cents > 1_000_000:
        await message.answer(invalid_amount_text(language))
        return
    if amount_cents < MIN_TOPUP_CENTS:
        await message.answer(too_small_text(language))
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


CANCEL_WORDS = {
    "/cancel",
    "cancel",
    "отмена",
    "отменить",
    "取消",
    "huỷ",
    "huy",
    "रद्द",
}


def wants_cancel(text: str | None) -> bool:
    """Whether a message typed at a prompt means "let me out".

    A state that only ends on a valid answer is a trap: the buyer who opened the
    amount prompt by mistake has no way back, and every message they send comes
    back as "enter a valid amount". The command is the documented way out; the
    plain words are here because that is what people actually type.
    """
    if not text:
        return False
    return text.strip().lstrip("/").strip().casefold() in {
        word.lstrip("/") for word in CANCEL_WORDS
    }


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext) -> None:
    """Leave whatever prompt is waiting for typed input.

    Registered before the per-state handlers so it wins over them: a state whose
    own handler swallows every message is exactly the state a buyer needs a way
    out of.
    """
    language = await selected_language(message) or "en"
    current = await state.get_state()
    await state.clear()
    if current is None:
        await message.answer(t(language, "nothing_to_cancel"))
    elif current == TopUpStates.waiting_amount.state:
        await message.answer(t(language, "top_up_cancelled"))
    else:
        await message.answer(t(language, "action_cancelled"))


@router.message(TopUpStates.waiting_amount)
async def custom_topup_amount_handler(message: Message, state: FSMContext) -> None:
    language = await selected_language(message)
    if language is None:
        await state.clear()
        await send_language_prompt(message)
        return
    if wants_cancel(message.text):
        await state.clear()
        await message.answer(t(language, "top_up_cancelled"))
        return
    amount_cents = parse_local_amount_cents(
        message.text or "",
        language,
        get_runtime().settings.currency_rates,
    )
    if amount_cents is None:
        await message.answer(
            f"{invalid_amount_text(language)}\n{t(language, 'cancel_hint')}",
            reply_markup=cancel_keyboard(language),
        )
        return
    if amount_cents < MIN_TOPUP_CENTS:
        await message.answer(
            f"{too_small_text(language)}\n{t(language, 'cancel_hint')}",
            reply_markup=cancel_keyboard(language),
        )
        return
    await state.clear()
    await offer_payment_methods(
        message,
        user_id_from_message(message),
        language,
        amount_cents,
    )


# ----------------------------------------------------------------------
# Manual crypto payment
#
# The buyer transfers straight to one of our addresses, then submits the tx
# hash. Nothing is credited until an admin has checked that hash on a block
# explorer and pressed Confirm — the bot never infers a payment from the fact
# that somebody claims to have sent one.
# ----------------------------------------------------------------------


def format_crypto_amount(value: Decimal) -> str:
    """Fixed-point with trailing zeros stripped, never scientific notation."""
    quantized = value.quantize(Decimal("0.00000001"), rounding=ROUND_UP)
    text = f"{quantized:f}".rstrip("0").rstrip(".")
    return text or "0"


def wallet_assets(wallets: tuple[Wallet, ...]) -> list[str]:
    """Unique tickers in table order, so the keyboard layout is stable."""
    seen: list[str] = []
    for wallet in wallets:
        if wallet.asset not in seen:
            seen.append(wallet.asset)
    return seen


async def quote_for_asset(asset: str, amount_cents: int) -> tuple[str | None, str | None, str | None]:
    """Convert a USD-cent amount into ``asset``.

    Returns ``(crypto_amount, rate, rate_at)``. The rate comes from Crypto Pay;
    when that call fails or has no entry for the coin, the frozen table in
    ``crypto_fallback`` is used instead and ``rate_at`` carries its capture date
    rather than a live timestamp — so a stale quote is always visibly stale.
    Everything is ``None`` only when the coin is in neither source, and callers
    must then show the fiat amount instead of substituting an estimate.
    """
    rt = get_runtime()
    rate: Decimal | None = None
    rate_at: str | None = None
    try:
        rates, fetched_at = await rt.crypto.exchange_rates("USD")
    except Exception:
        logger.exception("Could not load exchange rates for %s", asset)
    else:
        live = rates.get(asset.upper())
        if live is not None and live > 0 and fetched_at is not None:
            rate = live
            rate_at = fetched_at.strftime("%Y-%m-%d %H:%M")
    if rate is None:
        rate = fallback_rate(asset)
        if rate is None:
            return None, None, None
        rate_at = CAPTURED_AT
        logger.warning("Quoting %s from the frozen rate table (%s)", asset, CAPTURED_AT)
    crypto_amount = Decimal(amount_cents) / Decimal("100") / rate
    return (
        format_crypto_amount(crypto_amount),
        format_crypto_amount(rate),
        rate_at,
    )


@router.callback_query(F.data.startswith("cpay:"))
async def cpay_callback(callback: CallbackQuery) -> None:
    language = await ensure_callback_user(callback)
    if language not in LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    try:
        amount_cents = int((callback.data or "").split(":", maxsplit=1)[1])
    except ValueError:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await send_topup_invoice(
            callback.message,
            callback.from_user.id,
            language,
            amount_cents,
        )


@router.callback_query(F.data.startswith("mpay:assets:"))
async def mpay_assets_callback(callback: CallbackQuery) -> None:
    rt = get_runtime()
    language = await ensure_callback_user(callback)
    if language not in LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    try:
        amount_cents = int((callback.data or "").split(":", maxsplit=2)[2])
    except ValueError:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    wallets = rt.settings.crypto_wallets
    if not wallets:
        await callback.answer()
        if callback.message is not None:
            await callback.message.answer(
                t(language, "mpay_unavailable", support=support_contact(rt.settings))
            )
        return
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            t(
                language,
                "mpay_choose_asset",
                amount=localized_price(rt.settings, language, amount_cents),
            ),
            reply_markup=mpay_asset_keyboard(language, wallet_assets(wallets), amount_cents),
        )


@router.callback_query(F.data.startswith("mpay:asset:"))
async def mpay_asset_callback(callback: CallbackQuery) -> None:
    rt = get_runtime()
    language = await ensure_callback_user(callback)
    if language not in LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 4:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    asset = parts[2].upper()
    try:
        amount_cents = int(parts[3])
    except ValueError:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    options = [
        (index, wallet.network)
        for index, wallet in enumerate(rt.settings.crypto_wallets)
        if wallet.asset == asset
    ]
    if not options:
        await callback.answer(t(language, "mpay_stale"), show_alert=True)
        return
    await callback.answer()
    if callback.message is None:
        return
    if len(options) == 1:
        await start_manual_payment(
            callback.message,
            callback.from_user.id,
            language,
            options[0][0],
            asset,
            amount_cents,
        )
        return
    await callback.message.answer(
        t(language, "mpay_choose_network", asset=asset),
        reply_markup=mpay_network_keyboard(language, asset, options, amount_cents),
    )


@router.callback_query(F.data.startswith("mpay:w:"))
async def mpay_wallet_callback(callback: CallbackQuery) -> None:
    language = await ensure_callback_user(callback)
    if language not in LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 5:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    try:
        index = int(parts[2])
        amount_cents = int(parts[4])
    except ValueError:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await start_manual_payment(
            callback.message,
            callback.from_user.id,
            language,
            index,
            parts[3].upper(),
            amount_cents,
        )


async def start_manual_payment(
    message: Message,
    user_id: int,
    language: str,
    index: int,
    asset: str,
    amount_cents: int,
) -> None:
    rt = get_runtime()
    wallets = rt.settings.crypto_wallets
    # The index came from a button that may predate a restart, so never trust
    # it on its own: the asset carried alongside it must still match.
    if index < 0 or index >= len(wallets) or wallets[index].asset != asset:
        await message.answer(t(language, "mpay_stale"))
        return
    if amount_cents < 1 or amount_cents > 1_000_000:
        await message.answer(invalid_amount_text(language))
        return
    wallet = wallets[index]

    existing = await rt.db.open_manual_payment_for_user(user_id)
    if existing is not None:
        if str(existing["status"]) == "pending":
            # Hash already submitted and an admin is looking at it; a second
            # request now would just be two claims on one balance.
            await message.answer(
                t(language, "mpay_open_exists", payment_id=int(existing["id"]))
            )
            return
        # Still awaiting a hash, so the buyer simply changed their mind about
        # the coin. Drop the abandoned request and continue.
        await rt.db.cancel_manual_payment(int(existing["id"]), user_id)

    crypto_amount, rate, rate_at = await quote_for_asset(asset, amount_cents)
    payment_id = await rt.db.create_manual_payment(
        user_id=user_id,
        asset=wallet.asset,
        network=wallet.network,
        address=wallet.address,
        amount_cents=amount_cents,
        currency="USD",
        crypto_amount=crypto_amount,
        rate=rate,
        rate_at=rate_at,
    )
    fiat_amount = localized_price(rt.settings, language, amount_cents)
    hours = rt.settings.manual_crypto_note_hours
    if crypto_amount is None:
        text = t(
            language,
            "mpay_instructions_no_rate",
            payment_id=payment_id,
            asset=wallet.asset,
            network=html.escape(wallet.network),
            address=html.escape(wallet.address),
            fiat_amount=fiat_amount,
            hours=hours,
        )
    else:
        text = t(
            language,
            "mpay_instructions",
            payment_id=payment_id,
            asset=wallet.asset,
            network=html.escape(wallet.network),
            address=html.escape(wallet.address),
            crypto_amount=crypto_amount,
            fiat_amount=fiat_amount,
            rate=f"${rate}",
            rate_at=rate_at,
            hours=hours,
        )
    await message.answer(text, reply_markup=mpay_pending_keyboard(language, payment_id))


@router.callback_query(F.data.startswith("mpay:hash:"))
async def mpay_hash_callback(callback: CallbackQuery, state: FSMContext) -> None:
    rt = get_runtime()
    language = await ensure_callback_user(callback)
    if language not in LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    try:
        payment_id = int((callback.data or "").split(":", maxsplit=2)[2])
    except ValueError:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    payment = await rt.db.get_manual_payment(payment_id)
    if (
        payment is None
        or int(payment["user_id"]) != callback.from_user.id
        or str(payment["status"]) != "awaiting_hash"
    ):
        await callback.answer(t(language, "mpay_stale"), show_alert=True)
        return
    await state.set_state(ManualPaymentStates.waiting_tx_hash)
    await state.update_data(mpay_id=payment_id)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(t(language, "mpay_ask_hash"))


@router.callback_query(F.data.startswith("mpay:check:"))
async def mpay_check_callback(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    """"Check payment" — hand the request to the admins without asking for a hash.

    This is what the primary button under a transfer request now does. The
    buyer transfers, taps once, and the request moves to ``pending``; the admin
    finds the transfer by address and amount. ``mpay:hash:`` is still handled
    above for anyone who supplies a hash anyway, and the status guard inside
    ``request_manual_payment_review`` makes a double tap a no-op.
    """
    rt = get_runtime()
    language = await ensure_callback_user(callback)
    if language not in LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    try:
        payment_id = int((callback.data or "").split(":", maxsplit=2)[2])
    except ValueError:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    payment = await rt.db.request_manual_payment_review(payment_id, callback.from_user.id)
    if payment is None:
        # A second tap means the request is already in the admin queue, not
        # that the payment button suddenly became invalid.
        await callback.answer(t(language, "payment_pending"), show_alert=True)
        return
    await state.clear()
    # Keep the buyer-facing result as a compact Telegram alert. The detailed
    # request is sent privately to the admin below; the buyer is not shown an
    # instruction that says an admin will inspect the transfer.
    await callback.answer(t(language, "payment_pending"), show_alert=True)
    await notify_admins_manual_payment(bot, payment)


@router.callback_query(F.data.startswith("mpay:cancel:"))
async def mpay_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    rt = get_runtime()
    language = await ensure_callback_user(callback)
    if language not in LANGUAGES:
        await callback.answer("Choose a language first", show_alert=True)
        return
    try:
        payment_id = int((callback.data or "").split(":", maxsplit=2)[2])
    except ValueError:
        await callback.answer(t(language, "generic_error"), show_alert=True)
        return
    cancelled = await rt.db.cancel_manual_payment(payment_id, callback.from_user.id)
    if not cancelled:
        await callback.answer(t(language, "mpay_stale"), show_alert=True)
        return
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            t(
                language,
                "mpay_cancelled",
                payment_id=payment_id,
                support=support_contact(rt.settings),
            )
        )


@router.message(ManualPaymentStates.waiting_tx_hash)
async def mpay_tx_hash_handler(message: Message, state: FSMContext, bot: Bot) -> None:
    rt = get_runtime()
    language = await selected_language(message)
    if language is None:
        await state.clear()
        await send_language_prompt(message)
        return
    data = await state.get_data()
    payment_id = data.get("mpay_id")
    if not isinstance(payment_id, int):
        await state.clear()
        await message.answer(t(language, "mpay_stale"))
        return
    tx_hash = (message.text or "").strip()
    # A menu button must not be mistaken for a hash, or a buyer who has already
    # sent funds gets stuck in this state with no way out. The request stays
    # awaiting_hash, so the "I have sent it" button on the payment message keeps
    # working when they come back.
    if action_for_text(language, tx_hash) is not None:
        await state.clear()
        await message.answer(t(language, "mpay_hash_aborted"))
        return
    if not TX_HASH_RE.fullmatch(tx_hash):
        await message.answer(t(language, "mpay_hash_invalid"))
        return
    user_id = user_id_from_message(message)
    payment = await rt.db.submit_manual_payment_hash(payment_id, user_id, tx_hash)
    if payment is None:
        # Either the hash is already claimed or the request is no longer open.
        clash = await rt.db.find_manual_payment_by_hash(tx_hash)
        await state.clear()
        await message.answer(
            t(language, "mpay_hash_duplicate", support=support_contact(rt.settings))
            if clash is not None
            else t(language, "mpay_stale")
        )
        return
    await state.clear()
    await message.answer(
        t(
            language,
            "mpay_submitted",
            payment_id=payment_id,
            support=support_contact(rt.settings),
        )
    )
    await notify_admins_manual_payment(bot, payment)


def manual_payment_admin_text(row: object) -> str:
    """The admin's view of one request: who, how much, where, and the hash.

    Takes a row from either ``get_manual_payment`` or
    ``list_pending_manual_payments``; the latter also carries ``username``.
    """
    user_id = int(row["user_id"])  # type: ignore[index]
    try:
        username = row["username"]  # type: ignore[index]
    except (IndexError, KeyError):
        username = None
    label = f"@{username} ({user_id})" if username else str(user_id)
    crypto_amount = row["crypto_amount"]  # type: ignore[index]
    expected = (
        f"{crypto_amount} {row['asset']}"  # type: ignore[index]
        if crypto_amount
        # Stated plainly rather than shown as a number the bot never computed.
        else "не рассчитано — курс был недоступен"
    )
    # A buyer who taps "проверить оплату" never supplies a hash, so say so
    # instead of printing "None" and leaving the admin to guess.
    tx_hash = row["tx_hash"]  # type: ignore[index]
    hash_text = str(tx_hash) if tx_hash else "не указан — покупатель нажал «проверить оплату»"
    return t(
        "ru",
        "mpay_admin_new",
        payment_id=int(row["id"]),  # type: ignore[index]
        user=html.escape(label),
        asset=row["asset"],  # type: ignore[index]
        network=html.escape(str(row["network"])),  # type: ignore[index]
        fiat_amount=format_usd(int(row["amount_cents"])),  # type: ignore[index]
        crypto_amount=html.escape(expected),
        address=html.escape(str(row["address"])),  # type: ignore[index]
        tx_hash=html.escape(hash_text),
    )


async def notify_admins_manual_payment(bot: Bot, payment: object) -> None:
    rt = get_runtime()
    user_id = int(payment["user_id"])  # type: ignore[index]
    user = await rt.db.get_user(user_id)
    username = user["username"] if user is not None else None
    text = manual_payment_admin_text(
        {
            "id": payment["id"],  # type: ignore[index]
            "user_id": user_id,
            "username": username,
            "asset": payment["asset"],  # type: ignore[index]
            "network": payment["network"],  # type: ignore[index]
            "amount_cents": payment["amount_cents"],  # type: ignore[index]
            "crypto_amount": payment["crypto_amount"],  # type: ignore[index]
            "address": payment["address"],  # type: ignore[index]
            "tx_hash": payment["tx_hash"],  # type: ignore[index]
        }
    )
    markup = mpay_admin_keyboard(int(payment["id"]))  # type: ignore[index]
    for admin_id in rt.settings.admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=markup)
        except Exception:
            # One unreachable admin must not stop the others from being told.
            logger.exception("Could not notify admin %s about manual payment", admin_id)


@router.callback_query(F.data.startswith("mpay:ok:"))
async def mpay_admin_confirm_callback(callback: CallbackQuery, bot: Bot) -> None:
    await decide_manual_payment_from_callback(callback, bot, approve=True)


@router.callback_query(F.data.startswith("mpay:rej:"))
async def mpay_admin_reject_callback(callback: CallbackQuery, bot: Bot) -> None:
    await decide_manual_payment_from_callback(callback, bot, approve=False)


async def decide_manual_payment_from_callback(
    callback: CallbackQuery,
    bot: Bot,
    approve: bool,
) -> None:
    if not await admin_only_callback(callback):
        return
    rt = get_runtime()
    try:
        payment_id = int((callback.data or "").split(":", maxsplit=2)[2])
    except ValueError:
        await callback.answer("Некорректный запрос", show_alert=True)
        return
    payment = await rt.db.decide_manual_payment(payment_id, callback.from_user.id, approve)
    if payment is None:
        # Guarded UPDATE matched nothing: another admin already ruled on it.
        await callback.answer(t("ru", "mpay_admin_already", payment_id=payment_id), show_alert=True)
        return
    user_id = int(payment["user_id"])
    amount_cents = int(payment["amount_cents"])
    user = await rt.db.get_user(user_id)
    username = user["username"] if user is not None else None
    label = f"@{username} ({user_id})" if username else str(user_id)
    await callback.answer()
    if callback.message is not None:
        summary = (
            t(
                "ru",
                "mpay_admin_confirmed",
                payment_id=payment_id,
                user=html.escape(label),
                amount=format_usd(amount_cents),
            )
            if approve
            else t("ru", "mpay_admin_rejected", payment_id=payment_id)
        )
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
        await callback.message.answer(summary)

    language = await rt.db.get_language(user_id) or "en"
    try:
        if approve:
            balance = await rt.db.get_balance_cents(user_id)
            await bot.send_message(
                user_id,
                t(
                    language,
                    "mpay_confirmed",
                    payment_id=payment_id,
                    amount=localized_price(rt.settings, language, amount_cents),
                    balance=localized_price(rt.settings, language, balance),
                ),
            )
        else:
            await bot.send_message(
                user_id,
                t(
                    language,
                    "mpay_rejected",
                    payment_id=payment_id,
                    support=support_contact(rt.settings),
                ),
            )
    except Exception:
        # The decision already stands in the database; a blocked buyer must not
        # roll it back.
        logger.exception("Could not tell user %s about manual payment %s", user_id, payment_id)


@router.message(Command("pending"))
async def pending_manual_payments_command(message: Message) -> None:
    if not is_admin(user_id_from_message(message)):
        return
    rows = await get_runtime().db.list_pending_manual_payments()
    if not rows:
        await message.answer(t("ru", "mpay_admin_none_pending"))
        return
    for row in rows:
        await message.answer(
            manual_payment_admin_text(row),
            reply_markup=mpay_admin_keyboard(int(row["id"])),
        )


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
    balance_amount_cents = discounted_product_usd_cents(product) * quantity
    fiat = currency_for_language(language)
    balance_cents = await rt.db.get_balance_cents(buyer_id)
    await rt.db.track_event(buyer_id, "checkout", product.key)
    await rt.db.track_event(buyer_id, "pay_cryptobot", product.key)
    try:
        order_id, invoice = await create_payment_for_order(
            user_id=buyer_id,
            product_key=product.key,
            amount_cents=total_cents,
            description=(
                f"{product_label(product, language)} x{quantity} - "
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
        product=product_label(product, language),
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
            quantity_prompt(language, product_label(product, language), available)
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
    balance_amount_cents = discounted_product_usd_cents(product) * quantity
    balance_cents = await rt.db.get_balance_cents(callback.from_user.id)
    product_name = product_label(product, language)
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

    await rt.db.track_event(callback.from_user.id, "pay_balance", str(order["product_key"]))

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
    await broadcast_purchase_notification(bot, settlement)
    await credit_referral_for_order(bot, settlement)
    if settlement["delivery_status"] == "waiting_stock":
        await bot.send_message(callback.from_user.id, preorder_notice(language))
        await notify_admins_waiting_stock(bot, settlement)
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
            await callback.answer(preorder_notice(language), show_alert=True)
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
    await message.answer(
        "🔐 Админ-панель",
        reply_markup=admin_panel_keyboard(
            await get_runtime().db.count_pending_manual_payments()
        ),
    )


@router.callback_query(F.data == "admin:home")
async def admin_home_callback(callback: CallbackQuery) -> None:
    if not await admin_only_callback(callback):
        return
    await callback.answer()
    await edit_admin_message(
        callback,
        "🔐 Админ-панель",
        admin_panel_keyboard(await get_runtime().db.count_pending_manual_payments()),
    )


@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    await state.set_state(AdminBroadcastStates.waiting_message)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "📢 <b>Новая рассылка</b>\n\n"
            "Отправь текст, который получат все пользователи, открывшие бота.\n"
            "Сообщение будет отправлено обычным текстом — ссылки, эмодзи и символы "
            "<code>&lt; &gt;</code> не сломают рассылку.\n\n"
            "Максимум: 4000 символов. Для отмены отправь /cancel."
        )


@router.message(AdminBroadcastStates.waiting_message)
async def admin_broadcast_message_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(user_id_from_message(message)):
        await state.clear()
        await message.answer(t("en", "admin_only"))
        return
    body = (message.text or "").strip()
    if body.lower() == "/cancel":
        await state.clear()
        await message.answer(
            "Рассылка отменена.",
            reply_markup=admin_panel_keyboard(
                await get_runtime().db.count_pending_manual_payments()
            ),
        )
        return
    if not body:
        await message.answer("Отправь текстовое сообщение или /cancel для отмены.")
        return
    if len(body) > MAX_BROADCAST_LENGTH:
        await message.answer(
            f"Сообщение слишком длинное: {len(body)} символов. "
            f"Максимум — {MAX_BROADCAST_LENGTH}."
        )
        return

    recipients = len(await get_runtime().db.list_users_for_broadcast())
    preview = body if len(body) <= 3000 else body[:3000] + "\n…"
    await state.update_data(broadcast_text=body)
    await state.set_state(AdminBroadcastStates.waiting_confirmation)
    await message.answer(
        "📢 Предпросмотр рассылки\n\n"
        f"{preview}\n\n"
        f"Получателей: {recipients}\n"
        "Отправить сообщение всем?",
        parse_mode=None,
        reply_markup=admin_broadcast_confirm_keyboard(),
    )


@router.message(AdminBroadcastStates.waiting_confirmation)
async def admin_broadcast_confirmation_message_handler(
    message: Message,
    state: FSMContext,
) -> None:
    if not is_admin(user_id_from_message(message)):
        await state.clear()
        await message.answer(t("en", "admin_only"))
        return
    if (message.text or "").strip().lower() == "/cancel":
        await state.clear()
        await message.answer(
            "Рассылка отменена.",
            reply_markup=admin_panel_keyboard(
                await get_runtime().db.count_pending_manual_payments()
            ),
        )
        return
    await message.answer(
        "Предпросмотр уже готов. Нажми «Отправить всем» или отправь /cancel."
    )


@router.callback_query(F.data == "admin:broadcast:cancel")
async def admin_broadcast_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    await state.clear()
    await callback.answer("Рассылка отменена")
    await edit_admin_message(
        callback,
        "🔐 Админ-панель",
        admin_panel_keyboard(await get_runtime().db.count_pending_manual_payments()),
    )


@router.callback_query(F.data == "admin:broadcast:go")
async def admin_broadcast_send_callback(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
) -> None:
    if not await admin_only_callback(callback):
        return
    data = await state.get_data()
    body = str(data.get("broadcast_text", "")).strip()
    if not body:
        await state.clear()
        await callback.answer("Рассылка устарела. Создай её заново.", show_alert=True)
        return
    await state.clear()
    await callback.answer("Рассылка началась")
    sent, failed = await broadcast_custom_message(bot, body)
    await edit_admin_message(
        callback,
        "📢 <b>Рассылка завершена</b>\n\n"
        f"Отправлено: <b>{sent}</b>\n"
        f"Не доставлено: <b>{failed}</b>",
        admin_panel_keyboard(await get_runtime().db.count_pending_manual_payments()),
    )


@router.callback_query(F.data.startswith("admin:tickets"))
async def admin_tickets_callback(callback: CallbackQuery) -> None:
    if not await admin_only_callback(callback):
        return
    parts = (callback.data or "").split(":")
    try:
        page = max(0, int(parts[2])) if len(parts) > 2 else 0
    except ValueError:
        page = 0
    total = await get_runtime().db.count_support_tickets("open")
    rows = await get_runtime().db.list_support_tickets(
        status="open",
        limit=10,
        offset=page * 10,
    )
    lines = [
        "🎫 <b>Тикеты поддержки</b>",
        "",
        f"Открытых обращений: <b>{total}</b>",
        "",
    ]
    if not rows:
        lines.append("Новых открытых тикетов нет.")
    else:
        lines.append("Выбери обращение:")
    await callback.answer()
    await edit_admin_message(
        callback,
        "\n".join(lines),
        admin_tickets_keyboard(rows, page, total),
    )


@router.callback_query(F.data.startswith("admin:ticket:card:"))
async def admin_ticket_card_callback(callback: CallbackQuery) -> None:
    if not await admin_only_callback(callback):
        return
    try:
        ticket_id = int((callback.data or "").split(":", maxsplit=3)[-1])
    except ValueError:
        await callback.answer("Некорректный тикет", show_alert=True)
        return
    ticket = await get_runtime().db.get_support_ticket(ticket_id)
    text = await admin_support_ticket_text(ticket_id)
    if ticket is None or text is None:
        await callback.answer("Тикет не найден", show_alert=True)
        return
    await callback.answer()
    await edit_admin_message(
        callback,
        text,
        admin_ticket_card_keyboard(ticket_id, str(ticket["status"]) == "closed"),
    )


@router.callback_query(F.data.startswith("admin:ticket:reply:"))
async def admin_ticket_reply_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    if not await admin_only_callback(callback):
        return
    try:
        ticket_id = int((callback.data or "").split(":", maxsplit=3)[-1])
    except ValueError:
        await callback.answer("Некорректный тикет", show_alert=True)
        return
    ticket = await get_runtime().db.get_support_ticket(ticket_id)
    if ticket is None or str(ticket["status"]) != "open":
        await callback.answer("Тикет уже закрыт или не найден", show_alert=True)
        return
    await state.set_state(AdminTicketStates.waiting_reply)
    await state.update_data(ticket_id=ticket_id)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            f"Ответ для тикета #{ticket_id}. Отправь текст одним сообщением.\n"
            "Для отмены отправь /cancel."
        )


@router.message(AdminTicketStates.waiting_reply)
async def admin_ticket_reply_handler(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    if not is_admin(user_id_from_message(message)):
        await state.clear()
        await message.answer(t("en", "admin_only"))
        return
    body = (message.text or "").strip()
    if body.lower() == "/cancel":
        await state.clear()
        await message.answer("Ответ отменён.")
        return
    if not body:
        await message.answer("Отправь текст ответа или /cancel.")
        return
    if len(body) > MAX_BROADCAST_LENGTH:
        await message.answer(f"Ответ слишком длинный. Максимум — {MAX_BROADCAST_LENGTH} символов.")
        return
    data = await state.get_data()
    try:
        ticket_id = int(data.get("ticket_id"))
    except (TypeError, ValueError):
        await state.clear()
        await message.answer("Тикет устарел.")
        return
    db = get_runtime().db
    ticket = await db.get_support_ticket(ticket_id)
    if ticket is None or str(ticket["status"]) != "open":
        await state.clear()
        await message.answer("Тикет уже закрыт или не найден.")
        return
    if not await db.add_support_message(
        ticket_id,
        "admin",
        user_id_from_message(message),
        body,
    ):
        await state.clear()
        await message.answer("Не удалось добавить ответ. Тикет уже закрыт.")
        return
    await state.clear()
    language = await db.get_language(int(ticket["user_id"])) or "en"
    try:
        await bot.send_message(
            int(ticket["user_id"]),
            t(
                language,
                "support_ticket_reply",
                ticket_id=ticket_id,
                body=html.escape(body),
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=t(language, "support_ticket_reply_button"),
                            callback_data=f"shop:ticket:reply:{ticket_id}",
                        )
                    ]
                ]
            ),
        )
    except Exception:
        logger.exception("Could not send support reply for ticket %s", ticket_id)
        await message.answer("Ответ записан, но пользователь недоступен.")
        return
    await message.answer(
        f"✅ Ответ по тикету #{ticket_id} отправлен.",
        reply_markup=admin_ticket_card_keyboard(ticket_id),
    )


@router.callback_query(F.data.startswith("admin:ticket:close:"))
async def admin_ticket_close_callback(callback: CallbackQuery, bot: Bot) -> None:
    if not await admin_only_callback(callback):
        return
    try:
        ticket_id = int((callback.data or "").split(":", maxsplit=3)[-1])
    except ValueError:
        await callback.answer("Некорректный тикет", show_alert=True)
        return
    db = get_runtime().db
    closed = await db.close_support_ticket(ticket_id)
    if closed is None:
        await callback.answer("Тикет уже закрыт или не найден", show_alert=True)
        return
    user_id = int(closed["user_id"])
    language = await db.get_language(user_id) or "en"
    try:
        await bot.send_message(
            user_id,
            t(language, "support_ticket_closed", ticket_id=ticket_id),
        )
    except Exception:
        logger.exception("Could not notify user about closed support ticket %s", ticket_id)
    text = await admin_support_ticket_text(ticket_id)
    await callback.answer("Тикет закрыт")
    if text is not None:
        await edit_admin_message(
            callback,
            text,
            admin_ticket_card_keyboard(ticket_id, closed=True),
        )


@router.callback_query(F.data == "admin:manual")
async def admin_manual_callback(callback: CallbackQuery) -> None:
    if not await admin_only_callback(callback):
        return
    rt = get_runtime()
    rows = await rt.db.list_pending_manual_payments()
    await callback.answer()
    if callback.message is None:
        return
    if not rows:
        await callback.message.answer(t("ru", "mpay_admin_none_pending"))
        return
    for row in rows:
        await callback.message.answer(
            manual_payment_admin_text(row),
            reply_markup=mpay_admin_keyboard(int(row["id"])),
        )


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
            "Введите получателя и сумму в USD через пробел.\n"
            "Получатель — Telegram ID или @username.\n\n"
            "Примеры:\n"
            "<code>123456789 10.50</code>\n"
            "<code>@durov 10.50</code>\n\n"
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
            "Формат: получатель сумма в USD\n"
            "Получатель — Telegram ID или @username.\n"
            "Примеры: <code>123456789 10.50</code> или <code>@durov 10.50</code>\n"
            "Для отмены: /cancel"
        )
        return

    recipient, raw_amount = parts
    rt = get_runtime()
    if recipient.lstrip("-").isdigit():
        target_user_id = int(recipient)
        if target_user_id <= 0:
            await message.answer("Telegram ID должен быть положительным числом.")
            return
        target_label = f"<code>{target_user_id}</code>"
    else:
        row = await rt.db.find_user_by_username(recipient)
        if row is None:
            await message.answer(
                f"Пользователь {html.escape(recipient)} не найден в базе.\n"
                "Он должен сначала открыть бота через /start, "
                "либо укажи числовой Telegram ID."
            )
            return
        target_user_id = int(row["user_id"])
        stored = row["username"]
        target_label = (
            f"@{html.escape(str(stored))} (<code>{target_user_id}</code>)"
            if stored
            else f"<code>{target_user_id}</code>"
        )

    amount_cents = parse_amount_cents(raw_amount)
    if amount_cents is None:
        await message.answer("Введите положительную сумму в USD, например 10.50.")
        return

    new_balance_cents = await rt.db.add_balance_cents(target_user_id, amount_cents)
    if new_balance_cents is None:
        await message.answer(
            "Пользователь не найден в базе. Сначала он должен открыть бота через /start."
        )
        return

    await state.clear()
    await message.answer(
        "Баланс пополнен.\n"
        f"Пользователь: {target_label}\n"
        f"Зачислено: <b>{format_usd(amount_cents)}</b>\n"
        f"Новый баланс: <b>{format_usd(new_balance_cents)}</b>\n\n"
        "Уведомление пользователю не отправлялось.",
        reply_markup=admin_panel_keyboard(
            await get_runtime().db.count_pending_manual_payments()
        ),
    )


@router.callback_query(F.data == "admin:stock")
async def admin_stock_callback(callback: CallbackQuery) -> None:
    if not await admin_only_callback(callback):
        return
    await callback.answer()
    await edit_admin_message(callback, await admin_stock_text(), await admin_stock_keyboard())


@router.callback_query(F.data == "admin:stock:announce")
async def admin_stock_announce_callback(callback: CallbackQuery) -> None:
    """Ask before broadcasting a restock, and say how many people it reaches."""
    if not await admin_only_callback(callback):
        return
    recipients = len(await get_runtime().db.list_users_for_broadcast())
    await callback.answer()
    await edit_admin_message(
        callback,
        "📣 Объявление о поступлении\n\n"
        f"Сообщение «Новое поступление» получат: <b>{recipients}</b>\n"
        "Какие именно товары пришли — не указывается.\n\n"
        "Отправлять только после реального пополнения склада или счётчика.",
        admin_announce_confirm_keyboard(),
    )


@router.callback_query(F.data == "admin:stock:announce:go")
async def admin_stock_announce_send_callback(callback: CallbackQuery, bot: Bot) -> None:
    if not await admin_only_callback(callback):
        return
    await callback.answer("Рассылка началась")
    await broadcast_stock_replenished(bot)
    # The waitlist message names a product and says it can be bought now, so it
    # only goes out for products that are genuinely on offer.
    offered = await get_runtime().db.available_stock()
    for product_key in get_runtime().settings.products:
        if offered.get(product_key, 0) > 0:
            await notify_waitlist_for_product(bot, product_key)
    await deliver_pending_orders(bot)
    await edit_admin_message(callback, await admin_stock_text(), await admin_stock_keyboard())


@router.callback_query(F.data.startswith("admin:stock:payload:"))
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
async def admin_stock_payload_handler(message: Message, state: FSMContext, bot: Bot) -> None:
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
        reply_markup=await admin_stock_keyboard(),
    )
    await notify_waitlist_for_product(bot, product_key)
    await broadcast_stock_replenished(bot)
    await deliver_pending_orders(bot)


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
        reply_markup=await admin_stock_keyboard(),
    )


@router.callback_query(F.data == "admin:products")
async def admin_products_callback(callback: CallbackQuery) -> None:
    if not await admin_only_callback(callback):
        return
    await callback.answer()
    await edit_admin_message(callback, await admin_products_text(), admin_products_keyboard())


@router.callback_query(F.data.startswith("admin:product:price:"))
async def admin_product_price_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    product_key = (callback.data or "").split(":", maxsplit=3)[-1]
    rt = get_runtime()
    if product_key not in rt.settings.products:
        await callback.answer("Неизвестный товар", show_alert=True)
        return
    await state.set_state(AdminProductStates.waiting_prices)
    await state.update_data(mode="edit", product_key=product_key)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            f"Товар: <code>{html.escape(product_key)}</code>\n"
            f"Базовая цена: <b>{product.price_cents / 100:.2f} USD</b>\n"
            f"Скидка: <b>{int(product.discount_percent)}%</b>\n"
            f"Цена сейчас: <b>{discounted_product_usd_cents(product) / 100:.2f} USD</b>\n\n"
            "Отправь новую цену только в USD. Остальные валюты пересчитаются "
            "автоматически по курсам из настроек.\n"
            "Пример: <code>1.63</code>\n\n"
            "Для отмены отправь /cancel."
        )


@router.callback_query(F.data.startswith("admin:product:discount:"))
async def admin_product_discount_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    product_key = (callback.data or "").split(":", maxsplit=3)[-1]
    product = get_runtime().settings.products.get(product_key)
    if product is None:
        await callback.answer("Неизвестный товар", show_alert=True)
        return
    await state.set_state(AdminProductStates.waiting_discount)
    await state.update_data(product_key=product_key)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            f"Товар: <code>{html.escape(product_key)}</code>\n"
            f"Текущая скидка: <b>{int(product.discount_percent)}%</b>\n\n"
            "Отправь скидку целым числом от 0 до 99.\n"
            "0 — убрать скидку. Например: <code>15</code> или <code>15%</code>.\n\n"
            "Для отмены отправь /cancel."
        )


@router.message(AdminProductStates.waiting_discount)
async def admin_product_discount_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(user_id_from_message(message)):
        await state.clear()
        await message.answer(t("en", "admin_only"))
        return
    raw_text = (message.text or "").strip()
    if raw_text.lower() == "/cancel":
        await state.clear()
        await message.answer("Изменение скидки отменено.")
        return
    normalized = raw_text.rstrip("%").strip()
    if not normalized.isdigit() or not 0 <= int(normalized) <= 99:
        await message.answer("Введи целое число от 0 до 99, например 15. Для отмены: /cancel")
        return
    product_key = str((await state.get_data()).get("product_key", ""))
    try:
        updated = await get_runtime().db.update_product_discount(product_key, int(normalized))
    except ValueError as exc:
        await message.answer(str(exc))
        return
    if not updated:
        await state.clear()
        await message.answer("Товар не найден или отключён.")
        return
    await sync_runtime_products()
    product = get_runtime().settings.products.get(product_key)
    await state.clear()
    discount = int(normalized)
    price = (
        f"{discounted_product_usd_cents(product) / 100:.2f} USD"
        if product is not None
        else "—"
    )
    await message.answer(
        f"✅ Скидка обновлена: <code>{html.escape(product_key)}</code>\n"
        f"Скидка: <b>{discount}%</b>\n"
        f"Цена после скидки: <b>{price}</b>",
        reply_markup=admin_products_keyboard(),
    )


@router.callback_query(F.data == "admin:product:new")
async def admin_product_new_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    await state.set_state(AdminProductStates.waiting_definition)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Отправь описание товара одной строкой через <code>|</code>:\n"
            "<code>key | category | title_ru | title_en | title_zh</code>\n\n"
            "Пример:\n"
            "<code>gpt_team_nw | plus | GPT Team NW | GPT Team NW | GPT Team NW</code>\n\n"
            f"key: только {PRODUCT_KEY_HINT}\n"
            "После этого бот попросит цены.\n\n"
            "Для отмены отправь /cancel."
        )


@router.message(AdminProductStates.waiting_definition)
async def admin_product_definition_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(user_id_from_message(message)):
        await state.clear()
        await message.answer(t("en", "admin_only"))
        return
    raw_text = (message.text or "").strip()
    if raw_text.lower() == "/cancel":
        await state.clear()
        await message.answer("Создание товара отменено.")
        return
    parts = [part.strip() for part in raw_text.split("|")]
    if len(parts) != 5:
        await message.answer(
            "Нужно ровно 5 полей через <code>|</code>:\n"
            "<code>key | category | title_ru | title_en | title_zh</code>"
        )
        return
    product_key, category, title_ru, title_en, title_zh = parts
    if not PRODUCT_KEY_RE.fullmatch(product_key):
        await message.answer(f"Некорректный key. Разрешено: {PRODUCT_KEY_HINT}")
        return
    if product_key in get_runtime().settings.products:
        await message.answer("Товар с таким key уже существует.")
        return
    if not category or len(category) > 40:
        await message.answer("Категория обязательна и не длиннее 40 символов.")
        return
    if not (title_ru and title_en and title_zh):
        await message.answer("Все три названия обязательны.")
        return
    if max(len(title_ru), len(title_en), len(title_zh)) > 80:
        await message.answer("Название не длиннее 80 символов.")
        return
    await state.set_state(AdminProductStates.waiting_prices)
    await state.update_data(
        mode="new",
        product_key=product_key,
        category=category,
        title_ru=title_ru,
        title_en=title_en,
        title_zh=title_zh,
    )
    await message.answer(
        f"Товар <code>{html.escape(product_key)}</code> принят.\n\n"
        "Теперь отправь цену только в USD. Остальные валюты бот пересчитает "
        "автоматически по курсам.\n"
        "Пример: <code>1.63</code>\n\n"
        "Для отмены отправь /cancel."
    )


@router.message(AdminProductStates.waiting_prices)
async def admin_product_prices_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(user_id_from_message(message)):
        await state.clear()
        await message.answer(t("en", "admin_only"))
        return
    raw_text = (message.text or "").strip()
    if raw_text.lower() == "/cancel":
        await state.clear()
        await message.answer("Изменение цен отменено.")
        return
    parts = raw_text.split()
    if len(parts) != 1:
        await message.answer(
            "Нужно одно число — цена в USD.\nПример: <code>1.63</code>"
        )
        return
    price_usd = parse_price_cents(parts[0])
    if price_usd is None:
        await message.answer(
            "Цена должна быть положительным числом не больше 1 000 000 USD."
        )
        return

    data = await state.get_data()
    mode = str(data.get("mode", "edit"))
    product_key = str(data.get("product_key", ""))
    rt = get_runtime()
    if mode == "new":
        # The legacy schema keeps RUB/CNY columns for old databases, but the
        # admin enters one authoritative USD price. Store derived values only
        # for backwards compatibility; runtime pricing is rebuilt from USD.
        price_rub = convert_usd_cents(price_usd, rt.settings.currency_rates["ru"])
        price_cny = convert_usd_cents(price_usd, rt.settings.currency_rates["zh"])
        try:
            created = await rt.db.create_product(
                product_key,
                str(data.get("category", "catalog")),
                str(data.get("title_ru", product_key)),
                str(data.get("title_en", product_key)),
                str(data.get("title_zh", product_key)),
                price_usd,
                price_rub,
                price_cny,
            )
        except ValueError as exc:
            await message.answer(f"Не удалось создать товар: {exc}")
            return
        if not created:
            await state.clear()
            await message.answer("Товар с таким key уже существует.")
            return
        await sync_runtime_products()
        await state.clear()
        await message.answer(
            f"✅ Товар создан: <code>{html.escape(product_key)}</code>\n"
            f"Цена-источник: <b>{price_usd / 100:.2f} USD</b>\n"
            "Цены для остальных валют пересчитаны автоматически.\n\n"
            "Наличие — 0. Измени его в разделе «Остатки» или добавь данные товара.",
            reply_markup=admin_products_keyboard(),
        )
        return

    if product_key not in rt.settings.products:
        await state.clear()
        await message.answer("Товар не найден.")
        return
    try:
        updated = await rt.db.update_product_usd_price(product_key, price_usd)
    except ValueError as exc:
        await message.answer(f"Не удалось обновить цены: {exc}")
        return
    if not updated:
        await state.clear()
        await message.answer("Товар не найден или отключён.")
        return
    await sync_runtime_products()
    await state.clear()
    await message.answer(
        f"✅ Цены обновлены: <code>{html.escape(product_key)}</code>\n"
        f"Цена-источник: <b>{price_usd / 100:.2f} USD</b>\n"
        "Цены для остальных валют пересчитаны автоматически.",
        reply_markup=admin_products_keyboard(),
    )


# ----------------------------------------------------------------------
# Product card: rename, move between categories, take off sale
# ----------------------------------------------------------------------


async def show_product_card(callback: CallbackQuery, product_key: str) -> bool:
    text = await admin_product_card_text(product_key)
    if text is None:
        await callback.answer("Товар не найден", show_alert=True)
        await edit_admin_message(callback, await admin_products_text(), admin_products_keyboard())
        return False
    await edit_admin_message(callback, text, admin_product_card_keyboard(product_key))
    return True


@router.callback_query(F.data.startswith("admin:product:card:"))
async def admin_product_card_callback(callback: CallbackQuery) -> None:
    if not await admin_only_callback(callback):
        return
    await callback.answer()
    await show_product_card(callback, (callback.data or "").split(":", maxsplit=3)[-1])


@router.callback_query(F.data.startswith("admin:product:rename:"))
async def admin_product_rename_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    product_key = (callback.data or "").split(":", maxsplit=3)[-1]
    product = get_runtime().settings.products.get(product_key)
    if product is None:
        await callback.answer("Неизвестный товар", show_alert=True)
        return
    await state.set_state(AdminProductStates.waiting_title)
    await state.update_data(product_key=product_key)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            f"Товар: <code>{html.escape(product_key)}</code>\n"
            f"Сейчас: <b>{html.escape(product_label(product))}</b>\n\n"
            "Отправь новое название. Оно будет одинаковым во всех языках — "
            "название товара это марка, а не перевод.\n\n"
            "Для отмены отправь /cancel."
        )


@router.message(AdminProductStates.waiting_title)
async def admin_product_title_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(user_id_from_message(message)):
        await state.clear()
        await message.answer(t("en", "admin_only"))
        return
    title = (message.text or "").strip()
    if title.lower() == "/cancel":
        await state.clear()
        await message.answer("Переименование отменено.")
        return
    if not title or len(title) > 80:
        await message.answer("Название обязательно и не длиннее 80 символов.")
        return
    product_key = str((await state.get_data()).get("product_key", ""))
    if not await get_runtime().db.rename_product(product_key, title):
        await state.clear()
        await message.answer("Товар не найден или отключён.")
        return
    await sync_runtime_products()
    await state.clear()
    await message.answer(
        f"✅ Новое название: <b>{html.escape(title)}</b>\n"
        f"Товар: <code>{html.escape(product_key)}</code>",
        reply_markup=admin_products_keyboard(),
    )


@router.callback_query(F.data.startswith("admin:product:del:go:"))
async def admin_product_delete_confirmed_callback(callback: CallbackQuery) -> None:
    if not await admin_only_callback(callback):
        return
    product_key = (callback.data or "").split(":", maxsplit=4)[-1]
    if not await get_runtime().db.delete_product(product_key):
        await callback.answer("Товар уже снят с продажи", show_alert=True)
    else:
        await callback.answer("Снято с продажи")
    await sync_runtime_products()
    await edit_admin_message(callback, await admin_products_text(), admin_products_keyboard())


@router.callback_query(F.data.startswith("admin:product:del:"))
async def admin_product_delete_callback(callback: CallbackQuery) -> None:
    if not await admin_only_callback(callback):
        return
    product_key = (callback.data or "").split(":", maxsplit=3)[-1]
    rt = get_runtime()
    product = rt.settings.products.get(product_key)
    if product is None:
        await callback.answer("Неизвестный товар", show_alert=True)
        return
    await callback.answer()
    await edit_admin_message(
        callback,
        f"🗑 Снять с продажи: <b>{html.escape(product_label(product))}</b>\n"
        f"<code>{html.escape(product_key)}</code>\n\n"
        "Товар пропадёт из каталога, а его наличие станет 0.\n"
        "Прошлые заказы и чеки сохранятся — история не стирается.\n\n"
        "Отменить это из панели нельзя: чтобы вернуть товар, придётся создать его заново.",
        admin_confirm_keyboard(
            f"admin:product:del:go:{product_key}",
            f"admin:product:card:{product_key}",
            "🗑 Снять с продажи",
        ),
    )


@router.callback_query(F.data.startswith("admin:product:cat:"))
async def admin_product_category_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    product_key = (callback.data or "").split(":", maxsplit=3)[-1]
    rt = get_runtime()
    product = rt.settings.products.get(product_key)
    if product is None:
        await callback.answer("Неизвестный товар", show_alert=True)
        return
    categories = [
        (str(row["slug"]), str(row["title"]))
        for row in await rt.db.list_categories()
        if str(row["slug"]) != product.category
    ]
    if not categories:
        await callback.answer("Других категорий нет — создай её сначала", show_alert=True)
        return
    await state.update_data(cat_product_key=product_key)
    await callback.answer()
    await edit_admin_message(
        callback,
        f"🗂 Куда перенести <b>{html.escape(product_label(product))}</b>?\n"
        f"Сейчас: <code>{html.escape(product.category)}</code>",
        admin_pick_category_keyboard(product_key, categories),
    )


async def apply_product_category(
    callback: CallbackQuery,
    product_key: str,
    slug: str,
) -> None:
    """Move one product into one category and show the result."""
    rt = get_runtime()
    if product_key not in rt.settings.products:
        await callback.answer("Неизвестный товар", show_alert=True)
        return
    if not await rt.db.set_product_category(product_key, slug):
        await callback.answer("Не удалось перенести", show_alert=True)
        return
    await sync_runtime_products()
    await callback.answer("Перенесено")


@router.callback_query(F.data.startswith("admin:setcat:"))
async def admin_set_category_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    slug = (callback.data or "").split(":", maxsplit=2)[-1]
    product_key = str((await state.get_data()).get("cat_product_key", ""))
    if not product_key:
        await callback.answer("Выбор устарел, начни заново", show_alert=True)
        await edit_admin_message(callback, await admin_products_text(), admin_products_keyboard())
        return
    await apply_product_category(callback, product_key, slug)
    await state.update_data(cat_product_key=None)
    await show_product_card(callback, product_key)


@router.callback_query(F.data.startswith("admin:setprod:"))
async def admin_set_product_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    product_key = (callback.data or "").split(":", maxsplit=2)[-1]
    slug = str((await state.get_data()).get("cat_slug", ""))
    if not slug:
        await callback.answer("Выбор устарел, начни заново", show_alert=True)
        await edit_admin_message(callback, await admin_categories_text(), await admin_categories_keyboard())
        return
    await apply_product_category(callback, product_key, slug)
    await state.update_data(cat_slug=None)
    await edit_admin_message(callback, await admin_categories_text(), await admin_categories_keyboard())


# ----------------------------------------------------------------------
# Categories
# ----------------------------------------------------------------------


@router.callback_query(F.data == "admin:cats")
async def admin_categories_callback(callback: CallbackQuery) -> None:
    if not await admin_only_callback(callback):
        return
    await callback.answer()
    await edit_admin_message(
        callback, await admin_categories_text(), await admin_categories_keyboard()
    )


@router.callback_query(F.data.startswith("admin:cat:card:"))
async def admin_category_card_callback(callback: CallbackQuery) -> None:
    if not await admin_only_callback(callback):
        return
    slug = (callback.data or "").split(":", maxsplit=3)[-1]
    rt = get_runtime()
    row = next((item for item in await rt.db.list_categories() if str(item["slug"]) == slug), None)
    if row is None:
        await callback.answer("Категория не найдена", show_alert=True)
        await edit_admin_message(
            callback, await admin_categories_text(), await admin_categories_keyboard()
        )
        return
    names = [
        product_label(product)
        for product in rt.settings.products.values()
        if product.category == slug
    ]
    body = html.escape(", ".join(names)) if names else "<i>пока пусто</i>"
    await callback.answer()
    await edit_admin_message(
        callback,
        f"🗂 <b>{html.escape(str(row['title']))}</b>\n"
        f"<code>{html.escape(slug)}</code>\n\n"
        f"Товаров: <b>{len(names)}</b>\n{body}",
        admin_category_card_keyboard(slug),
    )


@router.callback_query(F.data == "admin:cat:new")
async def admin_category_new_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    await state.set_state(AdminCategoryStates.waiting_definition)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Отправь категорию одной строкой через <code>|</code>:\n"
            "<code>slug | название</code>\n\n"
            "Пример:\n<code>plus | ChatGPT Plus</code>\n\n"
            f"slug: {CATEGORY_SLUG_HINT}\n"
            "Название видит покупатель, slug — только ты.\n\n"
            "Для отмены отправь /cancel."
        )


@router.message(AdminCategoryStates.waiting_definition)
async def admin_category_definition_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(user_id_from_message(message)):
        await state.clear()
        await message.answer(t("en", "admin_only"))
        return
    raw_text = (message.text or "").strip()
    if raw_text.lower() == "/cancel":
        await state.clear()
        await message.answer("Создание категории отменено.")
        return
    parts = [part.strip() for part in raw_text.split("|")]
    if len(parts) != 2:
        await message.answer("Нужно два поля через <code>|</code>: <code>slug | название</code>")
        return
    slug, title = parts
    if not CATEGORY_SLUG_RE.fullmatch(slug):
        await message.answer(f"Некорректный slug. Разрешено: {CATEGORY_SLUG_HINT}")
        return
    if not title or len(title) > 60:
        await message.answer("Название обязательно и не длиннее 60 символов.")
        return
    if not await get_runtime().db.create_category(slug, title):
        await message.answer("Категория с таким slug уже есть.")
        return
    await sync_category_titles()
    await state.clear()
    await message.answer(
        f"✅ Категория создана: <b>{html.escape(title)}</b> (<code>{html.escape(slug)}</code>)",
        reply_markup=await admin_categories_keyboard(),
    )


@router.callback_query(F.data.startswith("admin:cat:rename:"))
async def admin_category_rename_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    slug = (callback.data or "").split(":", maxsplit=3)[-1]
    await state.set_state(AdminCategoryStates.waiting_title)
    await state.update_data(slug=slug)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            f"Категория: <code>{html.escape(slug)}</code>\n\n"
            "Отправь новое название. slug не меняется — товары останутся на месте.\n\n"
            "Для отмены отправь /cancel."
        )


@router.message(AdminCategoryStates.waiting_title)
async def admin_category_title_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(user_id_from_message(message)):
        await state.clear()
        await message.answer(t("en", "admin_only"))
        return
    title = (message.text or "").strip()
    if title.lower() == "/cancel":
        await state.clear()
        await message.answer("Переименование отменено.")
        return
    if not title or len(title) > 60:
        await message.answer("Название обязательно и не длиннее 60 символов.")
        return
    slug = str((await state.get_data()).get("slug", ""))
    if not await get_runtime().db.rename_category(slug, title):
        await state.clear()
        await message.answer("Категория не найдена.")
        return
    await sync_category_titles()
    await state.clear()
    await message.answer(
        f"✅ Новое название: <b>{html.escape(title)}</b>",
        reply_markup=await admin_categories_keyboard(),
    )


@router.callback_query(F.data.startswith("admin:cat:add:"))
async def admin_category_add_product_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    slug = (callback.data or "").split(":", maxsplit=3)[-1]
    keyboard = admin_pick_product_keyboard(exclude=slug)
    if len(keyboard.inline_keyboard) == 1:
        await callback.answer("Все товары уже в этой категории", show_alert=True)
        return
    await state.update_data(cat_slug=slug)
    await callback.answer()
    await edit_admin_message(
        callback,
        f"➕ Какой товар перенести в <code>{html.escape(slug)}</code>?",
        keyboard,
    )


@router.callback_query(F.data.startswith("admin:cdg:"))
async def admin_category_delete_confirmed_callback(callback: CallbackQuery) -> None:
    """Apply a confirmed category deletion.

    The payload is deliberately short (``admin:cdg:slug:destination``) because
    two slugs plus a readable prefix would not fit in Telegram's 64-byte
    callback data.
    """
    if not await admin_only_callback(callback):
        return
    parts = (callback.data or "").split(":", maxsplit=3)
    if len(parts) != 4:
        await callback.answer("Некорректная кнопка", show_alert=True)
        return
    slug, move_to = parts[2], parts[3]
    try:
        moved = await get_runtime().db.delete_category(slug, None if move_to == "-" else move_to)
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await sync_runtime_products()
    await callback.answer(f"Удалено. Перенесено товаров: {moved}")
    await edit_admin_message(
        callback, await admin_categories_text(), await admin_categories_keyboard()
    )


@router.callback_query(F.data.startswith("admin:cat:del:"))
async def admin_category_delete_callback(callback: CallbackQuery) -> None:
    if not await admin_only_callback(callback):
        return
    slug = (callback.data or "").split(":", maxsplit=3)[-1]
    rt = get_runtime()
    rows = await rt.db.list_categories()
    row = next((item for item in rows if str(item["slug"]) == slug), None)
    if row is None:
        await callback.answer("Категория не найдена", show_alert=True)
        return
    occupied = sum(
        1 for product in rt.settings.products.values() if product.category == slug
    )
    # Products are moved, not deleted — a category is a shelf, and removing the
    # shelf must not throw away the goods on it. They need somewhere to go.
    move_to = next((str(item["slug"]) for item in rows if str(item["slug"]) != slug), None)
    if occupied and move_to is None:
        await callback.answer(
            "Некуда переносить товары: создай ещё одну категорию", show_alert=True
        )
        return
    destination = move_to if occupied else (move_to or "-")
    await callback.answer()
    await edit_admin_message(
        callback,
        f"🗑 Удалить категорию <b>{html.escape(str(row['title']))}</b>?\n"
        f"<code>{html.escape(slug)}</code>\n\n"
        + (
            f"Товаров внутри: <b>{occupied}</b> — они переедут в "
            f"<code>{html.escape(destination)}</code>, а не удалятся.\n\n"
            if occupied
            else "Категория пустая.\n\n"
        )
        + "Сам раздел исчезнет из каталога.",
        admin_confirm_keyboard(
            f"admin:cdg:{slug}:{destination}",
            f"admin:cat:card:{slug}",
            "🗑 Удалить",
        ),
    )


@router.callback_query(F.data.startswith("admin:stock:adjust:"))
async def admin_stock_adjust_callback(callback: CallbackQuery, bot: Bot) -> None:
    if not await admin_only_callback(callback):
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 5:
        await callback.answer("Некорректная кнопка", show_alert=True)
        return
    product_key = parts[3]
    try:
        delta = int(parts[4])
    except ValueError:
        await callback.answer("Некорректное значение", show_alert=True)
        return
    result = await get_runtime().db.adjust_display_stock(product_key, delta)
    if result is None:
        await callback.answer("Неизвестный товар", show_alert=True)
        return
    old_value, new_value = result
    await callback.answer(f"Остаток: {old_value} → {new_value}")
    await edit_admin_message(callback, await admin_stock_text(), await admin_stock_keyboard())
    if old_value == 0 and new_value > 0:
        # This is the moment the product went back on sale, so it is the moment
        # the people who asked to be told about it should hear.
        await notify_waitlist_for_product(bot, product_key)
        await deliver_pending_orders(bot)


@router.callback_query(F.data.startswith("admin:stock:set:"))
async def admin_stock_set_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not await admin_only_callback(callback):
        return
    product_key = (callback.data or "").split(":", maxsplit=3)[-1]
    if product_key not in get_runtime().settings.products:
        await callback.answer("Неизвестный товар", show_alert=True)
        return
    await state.set_state(AdminStockStates.waiting_quantity)
    await state.update_data(product_key=product_key)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            f"Товар: <code>{html.escape(product_key)}</code>\n\n"
            "Отправь новый остаток — целое число от 0.\n"
            "Это и есть то число, которое видит покупатель и которое уменьшается при продаже.\n\n"
            "Для отмены отправь /cancel."
        )


@router.message(AdminStockStates.waiting_quantity)
async def admin_stock_quantity_handler(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(user_id_from_message(message)):
        await state.clear()
        await message.answer(t("en", "admin_only"))
        return
    raw_text = (message.text or "").strip()
    if raw_text.lower() == "/cancel":
        await state.clear()
        await message.answer("Изменение остатка отменено.")
        return
    if not raw_text.isdigit():
        await message.answer("Отправь неотрицательное целое число, например 10.")
        return
    value = int(raw_text)
    if value > 100_000:
        await message.answer("Слишком большое значение. Максимум 100000.")
        return
    data = await state.get_data()
    product_key = str(data.get("product_key", ""))
    try:
        result = await get_runtime().db.set_display_stock(product_key, value)
    except ValueError as exc:
        await message.answer(f"Не удалось изменить остаток: {exc}")
        return
    if result is None:
        await state.clear()
        await message.answer("Товар не найден.")
        return
    old_value, new_value = result
    await state.clear()
    await message.answer(
        f"✅ Остаток обновлён: {old_value} → {new_value}\n"
        f"Товар: <code>{html.escape(product_key)}</code>",
        reply_markup=await admin_stock_keyboard(),
    )
    if old_value == 0 and new_value > 0:
        await notify_waitlist_for_product(bot, product_key)
        await deliver_pending_orders(bot)


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
            reply_markup=plus_keyboard(
                language,
                product_price_labels(rt.settings, language),
                stock=await rt.db.available_stock(),
            ),
        )
        return
    if action == "pro":
        await message.answer(
            t(language, "choose_pro_plan"),
            reply_markup=pro_keyboard(
                language,
                product_price_labels(rt.settings, language),
                stock=await rt.db.available_stock(),
            ),
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
        if not rt.settings.products:
            await message.answer(t(language, "catalog_empty"), reply_markup=main_keyboard(language))
            return
        lines = []
        for key, product in rt.settings.products.items():
            count = stock.get(key, 0)
            marker = "🟢" if count > 0 else "🔴"
            lines.append(f"{marker} {html.escape(product_label(product, language))}: {count}")
        await message.answer(
            t(language, "stock_list", items="\n".join(lines)),
            reply_markup=main_keyboard(language),
        )
        return
    if action == "catalog":
        stock = await rt.db.available_stock()
        items = [
            (
                key,
                product_label(product, language),
                product_price(rt.settings, product, language),
                stock.get(key, 0),
            )
            for key, product in rt.settings.products.items()
        ]
        if not items:
            await message.answer(t(language, "catalog_empty"), reply_markup=main_keyboard(language))
            return
        await message.answer(
            t(language, "catalog_title"),
            reply_markup=catalog_keyboard(language, items),
        )
        return
    if action == "settings":
        await send_settings_message(message, language)
        return
    if action == "queue":
        await message.answer(
            t(language, "queue"),
            reply_markup=queue_keyboard(
                language,
                product_price_labels(rt.settings, language),
                stock=await rt.db.available_stock(),
            ),
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
    await db.ensure_product_catalog(
        settings.products,
        settings.regional_prices,
        settings.stock_display,
    )
    crypto = CryptoPayClient(
        token=settings.crypto_pay_token,
        base_url=settings.crypto_pay_base_url,
        accepted_assets=settings.accepted_assets,
    )
    await crypto.start()
    runtime = Runtime(settings=settings, db=db, crypto=crypto)
    await sync_runtime_products()

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
