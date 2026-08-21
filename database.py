from __future__ import annotations

import asyncio
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiosqlite


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.connection: aiosqlite.Connection | None = None
        self.lock = asyncio.Lock()

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = await aiosqlite.connect(self.path)
        self.connection.row_factory = aiosqlite.Row
        await self.connection.execute("PRAGMA foreign_keys = ON")
        await self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                language TEXT,
                balance_cents INTEGER NOT NULL DEFAULT 0,
                purchase_notifications INTEGER NOT NULL DEFAULT 1,
                referrer_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS products (
                product_key TEXT PRIMARY KEY,
                category TEXT NOT NULL DEFAULT 'catalog',
                title_ru TEXT NOT NULL,
                title_en TEXT NOT NULL,
                title_zh TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                price_usd_cents INTEGER NOT NULL,
                price_rub_cents INTEGER NOT NULL,
                price_cny_cents INTEGER NOT NULL,
                discount_percent INTEGER NOT NULL DEFAULT 0,
                display_stock INTEGER NOT NULL DEFAULT 0,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS goods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_key TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'available',
                sold_to INTEGER,
                order_id INTEGER UNIQUE,
                created_at TEXT NOT NULL,
                sold_at TEXT
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_number INTEGER UNIQUE,
                user_id INTEGER NOT NULL,
                product_key TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                balance_amount_cents INTEGER,
                quantity INTEGER NOT NULL DEFAULT 1,
                currency TEXT NOT NULL DEFAULT 'USD',
                order_type TEXT NOT NULL DEFAULT 'product',
                order_token TEXT NOT NULL UNIQUE,
                invoice_id TEXT UNIQUE,
                status TEXT NOT NULL DEFAULT 'pending',
                delivery_status TEXT NOT NULL DEFAULT 'pending',
                delivery_payload TEXT,
                product_id INTEGER,
                created_at TEXT NOT NULL,
                paid_at TEXT,
                delivered_at TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(order_id, product_id),
                FOREIGN KEY(order_id) REFERENCES orders(id),
                FOREIGN KEY(product_id) REFERENCES goods(id)
            );

            CREATE TABLE IF NOT EXISTS waitlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_key TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                UNIQUE(user_id, product_key),
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            -- Storefront sections. Products carry a category slug; this table
            -- gives the slug a title and an order, so the owner can add or
            -- rename a section without a code change.
            CREATE TABLE IF NOT EXISTS categories (
                slug TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 100,
                created_at TEXT NOT NULL
            );

            -- Funnel events, one row per step a user takes. Kept as raw rows
            -- rather than counters so a new statistic can be derived later from
            -- history that was already recorded.
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event TEXT NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL
            );

            -- Referral commission, one row per paid order. The order id is
            -- unique, which is what stops a retried settlement from paying the
            -- same commission twice.
            CREATE TABLE IF NOT EXISTS referral_payouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL UNIQUE,
                referrer_id INTEGER NOT NULL,
                buyer_id INTEGER NOT NULL,
                amount_cents INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            -- Crypto transfers made straight to one of our wallet addresses,
            -- outside Crypto Pay. Nothing here is credited automatically: a row
            -- stays 'pending' until an admin checks the tx hash on an explorer
            -- and confirms it, which is what moves it to 'confirmed'.
            CREATE TABLE IF NOT EXISTS manual_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_number INTEGER UNIQUE,
                user_id INTEGER NOT NULL,
                asset TEXT NOT NULL,
                network TEXT NOT NULL,
                address TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                crypto_amount TEXT,
                rate TEXT,
                rate_at TEXT,
                tx_hash TEXT,
                status TEXT NOT NULL DEFAULT 'awaiting_hash',
                created_at TEXT NOT NULL,
                submitted_at TEXT,
                decided_at TEXT,
                decided_by INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status, delivery_status);
            CREATE INDEX IF NOT EXISTS idx_goods_stock ON goods(product_key, status);
            CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
            CREATE INDEX IF NOT EXISTS idx_waitlist_product ON waitlist(product_key, status);
            CREATE INDEX IF NOT EXISTS idx_manual_payments_status
                ON manual_payments(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_manual_payments_user
                ON manual_payments(user_id, status);
            CREATE INDEX IF NOT EXISTS idx_events_event ON events(event, created_at);
            CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id, event);
            CREATE INDEX IF NOT EXISTS idx_referral_payouts_referrer
                ON referral_payouts(referrer_id);

            -- One extra campaign reward per referred buyer and campaign.
            CREATE TABLE IF NOT EXISTS referral_campaign_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_key TEXT NOT NULL,
                referrer_id INTEGER NOT NULL,
                buyer_id INTEGER NOT NULL,
                trigger_order_id INTEGER NOT NULL,
                amount_cents INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(campaign_key, buyer_id)
            );

            CREATE INDEX IF NOT EXISTS idx_referral_campaign_referrer
                ON referral_campaign_rewards(referrer_id);

            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_number INTEGER UNIQUE,
                user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                sender_role TEXT NOT NULL,
                sender_id INTEGER NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(ticket_id) REFERENCES support_tickets(id)
            );

            CREATE INDEX IF NOT EXISTS idx_support_tickets_status
                ON support_tickets(status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_support_messages_ticket
                ON support_messages(ticket_id, created_at);
            """
        )
        order_columns = {
            str(row["name"]) for row in await self._fetchall("PRAGMA table_info(orders)")
        }
        user_columns = {
            str(row["name"]) for row in await self._fetchall("PRAGMA table_info(users)")
        }
        product_columns = {
            str(row["name"]) for row in await self._fetchall("PRAGMA table_info(products)")
        }
        if "purchase_notifications" not in user_columns:
            await self.connection.execute(
                "ALTER TABLE users ADD COLUMN purchase_notifications INTEGER NOT NULL DEFAULT 1"
            )
        if "discount_percent" not in product_columns:
            await self.connection.execute(
                "ALTER TABLE products ADD COLUMN discount_percent INTEGER NOT NULL DEFAULT 0"
            )
        if "description" not in product_columns:
            await self.connection.execute(
                "ALTER TABLE products ADD COLUMN description TEXT NOT NULL DEFAULT ''"
            )
        if "quantity" not in order_columns:
            await self.connection.execute(
                "ALTER TABLE orders ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1"
            )
        if "balance_amount_cents" not in order_columns:
            await self.connection.execute(
                "ALTER TABLE orders ADD COLUMN balance_amount_cents INTEGER"
            )
        if "currency" not in order_columns:
            await self.connection.execute(
                "ALTER TABLE orders ADD COLUMN currency TEXT NOT NULL DEFAULT 'USD'"
            )
        if "order_type" not in order_columns:
            await self.connection.execute(
                "ALTER TABLE orders ADD COLUMN order_type TEXT NOT NULL DEFAULT 'product'"
            )
        manual_payment_columns = {
            str(row["name"]) for row in await self._fetchall("PRAGMA table_info(manual_payments)")
        }
        ticket_columns = {
            str(row["name"]) for row in await self._fetchall("PRAGMA table_info(support_tickets)")
        }
        if "public_number" not in order_columns:
            await self.connection.execute("ALTER TABLE orders ADD COLUMN public_number INTEGER")
        if "public_number" not in manual_payment_columns:
            await self.connection.execute("ALTER TABLE manual_payments ADD COLUMN public_number INTEGER")
        if "public_number" not in ticket_columns:
            await self.connection.execute("ALTER TABLE support_tickets ADD COLUMN public_number INTEGER")
        await self._backfill_public_numbers("orders")
        await self._backfill_public_numbers("manual_payments")
        await self._backfill_public_numbers("support_tickets")
        now = utc_now()
        await self.connection.execute(
            """
            INSERT OR IGNORE INTO app_settings(key, value, updated_at)
            VALUES ('stats_reset_at', ?, ?)
            """,
            (now, now),
        )
        await self.connection.execute(
            """
            INSERT OR IGNORE INTO app_settings(key, value, updated_at)
            VALUES ('purchase_notifications_global', '1', ?)
            """,
            (now,),
        )
        await self.connection.commit()

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
            self.connection = None

    def _conn(self) -> aiosqlite.Connection:
        if self.connection is None:
            raise RuntimeError("Database is not initialized")
        return self.connection

    async def _fetchone(self, query: str, parameters: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        cursor = await self._conn().execute(query, parameters)
        try:
            return await cursor.fetchone()
        finally:
            await cursor.close()

    async def _fetchall(self, query: str, parameters: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        cursor = await self._conn().execute(query, parameters)
        try:
            return await cursor.fetchall()
        finally:
            await cursor.close()

    async def _allocate_public_number(self, table: str) -> int:
        """Return an unused five-digit number for a customer-facing reference."""
        if table not in {"orders", "manual_payments", "support_tickets"}:
            raise ValueError("unsupported public-number table")
        for _ in range(100):
            candidate = secrets.randbelow(90_000) + 10_000
            used = False
            for existing_table in ("orders", "manual_payments", "support_tickets"):
                row = await self._fetchone(
                    f"SELECT 1 FROM {existing_table} WHERE public_number = ? LIMIT 1",
                    (candidate,),
                )
                if row is not None:
                    used = True
                    break
            if not used:
                return candidate
        raise RuntimeError(f"could not allocate a public number for {table}")

    async def _backfill_public_numbers(self, table: str) -> None:
        if table not in {"orders", "manual_payments", "support_tickets"}:
            raise ValueError("unsupported public-number table")
        rows = await self._fetchall(
            f"SELECT id FROM {table} WHERE public_number IS NULL ORDER BY id"
        )
        for row in rows:
            number = await self._allocate_public_number(table)
            await self._conn().execute(
                f"UPDATE {table} SET public_number = ? WHERE id = ? AND public_number IS NULL",
                (number, int(row["id"])),
            )
        await self._conn().execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_public_number ON {table}(public_number)"
        )

    @staticmethod
    def _user_exclusion(
        column: str,
        excluded_user_ids: tuple[int, ...] = (),
    ) -> tuple[str, tuple[int, ...]]:
        ids = tuple(dict.fromkeys(int(user_id) for user_id in excluded_user_ids))
        if not ids:
            return "", ()
        placeholders = ", ".join("?" for _ in ids)
        return f" AND {column} NOT IN ({placeholders})", ids

    async def _get_app_setting(self, key: str, default: str) -> str:
        row = await self._fetchone(
            "SELECT value FROM app_settings WHERE key = ?",
            (key,),
        )
        return str(row["value"]) if row is not None else default

    async def _set_app_setting(self, key: str, value: str) -> None:
        async with self.lock:
            await self._conn().execute(
                """
                INSERT INTO app_settings(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, value, utc_now()),
            )
            await self._conn().commit()

    async def get_stats_reset_at(self) -> str | None:
        value = await self._get_app_setting("stats_reset_at", "")
        return value or None

    async def reset_statistics(self) -> str:
        now = utc_now()
        await self._set_app_setting("stats_reset_at", now)
        return now

    async def get_purchase_notifications_global(self) -> bool:
        return (await self._get_app_setting("purchase_notifications_global", "1")) == "1"

    async def set_purchase_notifications_global(self, enabled: bool) -> None:
        await self._set_app_setting("purchase_notifications_global", "1" if enabled else "0")

    async def ensure_product_catalog(
        self,
        products: dict[str, Any],
        regional_prices: dict[str, dict[str, int]],
        stock_defaults: dict[str, int] | None = None,
    ) -> None:
        """Seed built-in products without overwriting admin-managed values."""
        stock_defaults = stock_defaults or {}
        async with self.lock:
            for key, product in products.items():
                prices = regional_prices.get(key, {})
                category = str(getattr(product, "category", "catalog") or "catalog")
                await self._conn().execute(
                    """
                    INSERT OR IGNORE INTO categories(slug, title, position, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        category,
                        category.replace("_", " ").strip().title() or "Catalog",
                        100,
                        utc_now(),
                    ),
                )
                await self._conn().execute(
                    """
                    INSERT OR IGNORE INTO products(
                        product_key, category, title_ru, title_en, title_zh, description,
                        price_usd_cents, price_rub_cents, price_cny_cents,
                        display_stock, enabled, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        key,
                        category,
                        product.title.get("ru", key),
                        product.title.get("en", key),
                        product.title.get("zh", key),
                        str(getattr(product, "description", "") or "").strip(),
                        int(prices.get("en", product.price_cents)),
                        int(prices.get("ru", product.price_cents)),
                        int(prices.get("zh", product.price_cents)),
                        max(0, int(stock_defaults.get(key, 0))),
                        utc_now(),
                        utc_now(),
                    ),
                )
            await self._conn().commit()

    async def list_products(self, enabled_only: bool = True) -> list[aiosqlite.Row]:
        where = "WHERE enabled = 1" if enabled_only else ""
        return await self._fetchall(
            f"""
            SELECT product_key, category, title_ru, title_en, title_zh, description,
                   price_usd_cents, price_rub_cents, price_cny_cents,
                   discount_percent,
                   display_stock, enabled, created_at, updated_at
            FROM products
            {where}
            ORDER BY created_at, product_key
            """
        )

    async def create_product(
        self,
        product_key: str,
        category: str,
        title_ru: str,
        title_en: str,
        title_zh: str,
        price_usd_cents: int,
        price_rub_cents: int,
        price_cny_cents: int,
        description: str = "",
    ) -> bool:
        if min(price_usd_cents, price_rub_cents, price_cny_cents) <= 0:
            raise ValueError("product prices must be positive")
        description = description.strip()
        if len(description) > 2000:
            raise ValueError("product description must be 2000 characters or shorter")
        now = utc_now()
        async with self.lock:
            await self._conn().execute(
                """
                INSERT OR IGNORE INTO categories(slug, title, position, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    category,
                    category.replace("_", " ").strip().title() or "Catalog",
                    100,
                    now,
                ),
            )
            existing = await self._fetchone(
                "SELECT enabled FROM products WHERE product_key = ?",
                (product_key,),
            )
            if existing is not None and int(existing["enabled"]) == 0:
                cursor = await self._conn().execute(
                    """
                    UPDATE products
                    SET category = ?, title_ru = ?, title_en = ?, title_zh = ?,
                        description = ?,
                        price_usd_cents = ?, price_rub_cents = ?, price_cny_cents = ?,
                        discount_percent = 0, display_stock = 0, enabled = 1, updated_at = ?
                    WHERE product_key = ?
                    """,
                    (
                        category,
                        title_ru,
                        title_en,
                        title_zh,
                        description,
                        price_usd_cents,
                        price_rub_cents,
                        price_cny_cents,
                        now,
                        product_key,
                    ),
                )
                await self._conn().commit()
                return cursor.rowcount == 1
            cursor = await self._conn().execute(
                """
                INSERT OR IGNORE INTO products(
                    product_key, category, title_ru, title_en, title_zh, description,
                    price_usd_cents, price_rub_cents, price_cny_cents,
                    discount_percent, display_stock, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 1, ?, ?)
                """,
                (
                    product_key,
                    category,
                    title_ru,
                    title_en,
                    title_zh,
                    description,
                    price_usd_cents,
                    price_rub_cents,
                    price_cny_cents,
                    now,
                    now,
                ),
            )
            await self._conn().commit()
            return cursor.rowcount == 1

    async def update_product_prices(
        self,
        product_key: str,
        price_usd_cents: int,
        price_rub_cents: int,
        price_cny_cents: int,
    ) -> bool:
        if min(price_usd_cents, price_rub_cents, price_cny_cents) <= 0:
            raise ValueError("product prices must be positive")
        async with self.lock:
            cursor = await self._conn().execute(
                """
                UPDATE products
                SET price_usd_cents = ?, price_rub_cents = ?, price_cny_cents = ?, updated_at = ?
                WHERE product_key = ? AND enabled = 1
                """,
                (price_usd_cents, price_rub_cents, price_cny_cents, utc_now(), product_key),
            )
            await self._conn().commit()
            return cursor.rowcount == 1

    async def update_product_usd_price(self, product_key: str, price_usd_cents: int) -> bool:
        """Change the source price used to derive every buyer currency.

        The storefront keeps one authoritative price in USD. Regional figures
        are calculated from the configured exchange rates when the runtime
        syncs, so an admin does not have to maintain five copies of one price.
        The older ``update_product_prices`` method remains for database
        compatibility with the smoke test and older integrations.
        """
        if price_usd_cents <= 0:
            raise ValueError("product prices must be positive")
        async with self.lock:
            cursor = await self._conn().execute(
                """
                UPDATE products
                SET price_usd_cents = ?, updated_at = ?
                WHERE product_key = ? AND enabled = 1
                """,
                (price_usd_cents, utc_now(), product_key),
            )
            await self._conn().commit()
            return cursor.rowcount == 1

    async def update_product_discount(self, product_key: str, percent: int) -> bool:
        """Set the product discount, keeping at least one cent payable."""
        if percent < 0 or percent > 99:
            raise ValueError("discount must be between 0 and 99 percent")
        async with self.lock:
            cursor = await self._conn().execute(
                """
                UPDATE products
                SET discount_percent = ?, updated_at = ?
                WHERE product_key = ? AND enabled = 1
                """,
                (percent, utc_now(), product_key),
            )
            await self._conn().commit()
            return cursor.rowcount == 1

    async def update_product_description(self, product_key: str, description: str) -> bool:
        description = description.strip()
        if len(description) > 2000:
            raise ValueError("product description must be 2000 characters or shorter")
        async with self.lock:
            cursor = await self._conn().execute(
                """
                UPDATE products
                SET description = ?, updated_at = ?
                WHERE product_key = ? AND enabled = 1
                """,
                (description, utc_now(), product_key),
            )
            await self._conn().commit()
            return cursor.rowcount == 1

    async def adjust_display_stock(self, product_key: str, delta: int) -> tuple[int, int] | None:
        async with self.lock:
            row = await self._fetchone(
                "SELECT display_stock FROM products WHERE product_key = ? AND enabled = 1",
                (product_key,),
            )
            if row is None:
                return None
            old_value = max(0, int(row["display_stock"]))
            new_value = max(0, old_value + delta)
            await self._conn().execute(
                "UPDATE products SET display_stock = ?, updated_at = ? WHERE product_key = ?",
                (new_value, utc_now(), product_key),
            )
            await self._conn().commit()
            return old_value, new_value

    async def set_display_stock(self, product_key: str, value: int) -> tuple[int, int] | None:
        if value < 0:
            raise ValueError("display stock cannot be negative")
        async with self.lock:
            row = await self._fetchone(
                "SELECT display_stock FROM products WHERE product_key = ? AND enabled = 1",
                (product_key,),
            )
            if row is None:
                return None
            old_value = max(0, int(row["display_stock"]))
            await self._conn().execute(
                "UPDATE products SET display_stock = ?, updated_at = ? WHERE product_key = ?",
                (value, utc_now(), product_key),
            )
            await self._conn().commit()
            return old_value, value

    async def find_user_by_username(self, username: str) -> aiosqlite.Row | None:
        normalized = username.strip().lstrip("@").lower()
        if not normalized:
            return None
        return await self._fetchone(
            """
            SELECT user_id, username, language, balance_cents, purchase_notifications,
                   referrer_id, created_at, updated_at
            FROM users
            WHERE LOWER(REPLACE(COALESCE(username, ''), '@', '')) = ?
            LIMIT 1
            """,
            (normalized,),
        )

    async def list_purchase_notification_users(self) -> list[aiosqlite.Row]:
        if not await self.get_purchase_notifications_global():
            return []
        return await self._fetchall(
            """
            SELECT user_id, username, language
            FROM users
            WHERE purchase_notifications = 1
            ORDER BY user_id
            """
        )

    async def list_users_for_broadcast(self) -> list[aiosqlite.Row]:
        return await self._fetchall(
            "SELECT user_id, language FROM users ORDER BY user_id"
        )

    async def create_support_ticket(self, user_id: int, body: str) -> int:
        """Create an open ticket and its first user message atomically."""
        body = body.strip()
        if not body:
            raise ValueError("support ticket message cannot be empty")
        async with self.lock:
            now = utc_now()
            public_number = await self._allocate_public_number("support_tickets")
            cursor = await self._conn().execute(
                """
                INSERT INTO support_tickets(public_number, user_id, status, created_at, updated_at)
                VALUES (?, ?, 'open', ?, ?)
                """,
                (public_number, user_id, now, now),
            )
            ticket_id = int(cursor.lastrowid)
            await self._conn().execute(
                """
                INSERT INTO support_messages(ticket_id, sender_role, sender_id, body, created_at)
                VALUES (?, 'user', ?, ?, ?)
                """,
                (ticket_id, user_id, body, now),
            )
            await self._conn().commit()
            return ticket_id

    async def get_support_ticket(self, ticket_id: int) -> aiosqlite.Row | None:
        return await self._fetchone(
            """
            SELECT t.id, t.public_number, t.user_id, t.status, t.created_at, t.updated_at,
                   u.username, u.language
            FROM support_tickets t
            LEFT JOIN users u ON u.user_id = t.user_id
            WHERE t.id = ?
            """,
            (ticket_id,),
        )

    async def list_support_tickets(
        self,
        status: str = "open",
        limit: int = 20,
        offset: int = 0,
    ) -> list[aiosqlite.Row]:
        return await self._fetchall(
            """
            SELECT t.id, t.public_number, t.user_id, t.status, t.created_at, t.updated_at,
                   u.username, u.language,
                   (
                       SELECT body FROM support_messages sm
                       WHERE sm.ticket_id = t.id
                       ORDER BY sm.id DESC LIMIT 1
                   ) AS last_body
            FROM support_tickets t
            LEFT JOIN users u ON u.user_id = t.user_id
            WHERE t.status = ?
            ORDER BY t.updated_at DESC, t.id DESC
            LIMIT ? OFFSET ?
            """,
            (status, max(1, min(limit, 100)), max(0, offset)),
        )

    async def count_support_tickets(
        self,
        status: str = "open",
        since: str | None = None,
        excluded_user_ids: tuple[int, ...] = (),
    ) -> int:
        user_filter, user_params = self._user_exclusion("user_id", excluded_user_ids)
        date_filter = " AND created_at >= ?" if since else ""
        params = (status,) + user_params + ((since,) if since else ())
        row = await self._fetchone(
            f"SELECT COUNT(*) AS total FROM support_tickets WHERE status = ?{user_filter}{date_filter}",
            params,
        )
        return int(row["total"]) if row is not None else 0

    async def list_support_messages(self, ticket_id: int) -> list[aiosqlite.Row]:
        return await self._fetchall(
            """
            SELECT id, ticket_id, sender_role, sender_id, body, created_at
            FROM support_messages
            WHERE ticket_id = ?
            ORDER BY id
            """,
            (ticket_id,),
        )

    async def add_support_message(
        self,
        ticket_id: int,
        sender_role: str,
        sender_id: int,
        body: str,
    ) -> bool:
        body = body.strip()
        if not body or sender_role not in {"user", "admin"}:
            return False
        async with self.lock:
            now = utc_now()
            updated = await self._conn().execute(
                """
                UPDATE support_tickets
                SET updated_at = ?
                WHERE id = ? AND status = 'open'
                """,
                (now, ticket_id),
            )
            if updated.rowcount != 1:
                await self._conn().rollback()
                return False
            await self._conn().execute(
                """
                INSERT INTO support_messages(ticket_id, sender_role, sender_id, body, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ticket_id, sender_role, sender_id, body, now),
            )
            await self._conn().commit()
            return True

    async def close_support_ticket(self, ticket_id: int) -> aiosqlite.Row | None:
        async with self.lock:
            row = await self._fetchone(
                "SELECT id, public_number, user_id, status FROM support_tickets WHERE id = ?",
                (ticket_id,),
            )
            if row is None or str(row["status"]) == "closed":
                await self._conn().rollback()
                return None
            await self._conn().execute(
                "UPDATE support_tickets SET status = 'closed', updated_at = ? WHERE id = ?",
                (utc_now(), ticket_id),
            )
            await self._conn().commit()
            return row

    async def get_purchase_notifications(self, user_id: int) -> bool:
        row = await self._fetchone(
            "SELECT purchase_notifications FROM users WHERE user_id = ?",
            (user_id,),
        )
        return bool(row["purchase_notifications"]) if row is not None else True

    async def set_purchase_notifications(self, user_id: int, enabled: bool) -> None:
        async with self.lock:
            await self._conn().execute(
                "UPDATE users SET purchase_notifications = ?, updated_at = ? WHERE user_id = ?",
                (1 if enabled else 0, utc_now(), user_id),
            )
            await self._conn().commit()

    async def ensure_user(self, user_id: int, username: str | None, referrer_id: int | None = None) -> str | None:
        async with self.lock:
            row = await self._fetchone("SELECT language FROM users WHERE user_id = ?", (user_id,))
            now = utc_now()
            if row is None:
                if referrer_id == user_id:
                    referrer_id = None
                await self._conn().execute(
                    """
                    INSERT INTO users(user_id, username, language, referrer_id, created_at, updated_at)
                    VALUES (?, ?, NULL, ?, ?, ?)
                    """,
                    (user_id, username, referrer_id, now, now),
                )
            else:
                await self._conn().execute(
                    "UPDATE users SET username = ?, updated_at = ? WHERE user_id = ?",
                    (username, now, user_id),
                )
            await self._conn().commit()
            return row["language"] if row is not None else None

    async def get_language(self, user_id: int) -> str | None:
        row = await self._fetchone("SELECT language FROM users WHERE user_id = ?", (user_id,))
        return row["language"] if row is not None else None

    async def get_user(self, user_id: int) -> aiosqlite.Row | None:
        return await self._fetchone(
            """
            SELECT user_id, username, language, balance_cents, purchase_notifications,
                   referrer_id, created_at, updated_at
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        )

    async def count_users(
        self,
        since: str | None = None,
        excluded_user_ids: tuple[int, ...] = (),
    ) -> int:
        user_filter, user_params = self._user_exclusion("user_id", excluded_user_ids)
        date_filter = " AND created_at >= ?" if since else ""
        params = user_params + ((since,) if since else ())
        row = await self._fetchone(
            f"SELECT COUNT(*) AS count FROM users WHERE 1 = 1{user_filter}{date_filter}",
            params,
        )
        return int(row["count"]) if row is not None else 0

    async def list_users(self, limit: int, offset: int = 0) -> list[aiosqlite.Row]:
        return await self._fetchall(
            """
            SELECT user_id, username, language, balance_cents, purchase_notifications, created_at
            FROM users
            ORDER BY created_at DESC, user_id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )

    async def set_language(self, user_id: int, language: str) -> None:
        async with self.lock:
            await self._conn().execute(
                "UPDATE users SET language = ?, updated_at = ? WHERE user_id = ?",
                (language, utc_now(), user_id),
            )
            await self._conn().commit()

    async def get_balance_cents(self, user_id: int) -> int:
        row = await self._fetchone("SELECT balance_cents FROM users WHERE user_id = ?", (user_id,))
        return int(row["balance_cents"]) if row is not None else 0

    async def add_balance_cents(self, user_id: int, amount_cents: int) -> int | None:
        if amount_cents <= 0:
            raise ValueError("amount_cents must be positive")
        async with self.lock:
            cursor = await self._conn().execute(
                """
                UPDATE users
                SET balance_cents = balance_cents + ?, updated_at = ?
                WHERE user_id = ?
                """,
                (amount_cents, utc_now(), user_id),
            )
            await self._conn().commit()
            if cursor.rowcount != 1:
                return None
            return await self.get_balance_cents(user_id)

    async def create_order(
        self,
        user_id: int,
        product_key: str,
        amount_cents: int,
        order_token: str,
        invoice_id: int | str,
        quantity: int = 1,
        currency: str = "USD",
        order_type: str = "product",
        balance_amount_cents: int | None = None,
    ) -> int:
        if quantity < 1:
            raise ValueError("quantity must be at least 1")
        if balance_amount_cents is not None and balance_amount_cents < 0:
            raise ValueError("balance_amount_cents cannot be negative")
        async with self.lock:
            public_number = await self._allocate_public_number("orders")
            cursor = await self._conn().execute(
                """
                INSERT INTO orders(
                    public_number, user_id, product_key, amount_cents, balance_amount_cents,
                    quantity, currency, order_type,
                    order_token, invoice_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    public_number,
                    user_id,
                    product_key,
                    amount_cents,
                    balance_amount_cents,
                    quantity,
                    currency.upper(),
                    order_type,
                    order_token,
                    str(invoice_id),
                    utc_now(),
                ),
            )
            await self._conn().commit()
            return int(cursor.lastrowid)

    async def get_order(self, order_id: int) -> aiosqlite.Row | None:
        return await self._fetchone("SELECT * FROM orders WHERE id = ?", (order_id,))

    async def get_pending_orders(self) -> list[aiosqlite.Row]:
        return await self._fetchall(
            "SELECT * FROM orders WHERE status = 'pending' AND invoice_id IS NOT NULL ORDER BY id"
        )

    async def mark_order_expired(self, order_id: int) -> None:
        async with self.lock:
            await self._conn().execute(
                "UPDATE orders SET status = 'expired' WHERE id = ? AND status = 'pending'",
                (order_id,),
            )
            await self._conn().commit()

    async def _available_goods_for_order(
        self,
        connection: aiosqlite.Connection,
        order: aiosqlite.Row,
    ) -> list[aiosqlite.Row] | None:
        quantity = max(1, int(order["quantity"] or 1))
        # RANDOM() rather than id order: the owner loads a batch of interchangeable
        # accounts and wants them handed out in no particular order. The rows are
        # distinct by construction, so an order for three units gets three
        # different accounts, and the status guard in _reserve_goods_for_order
        # means a row handed to one buyer can never reach another.
        cursor = await connection.execute(
            """
            SELECT id, payload FROM goods
            WHERE product_key = ? AND status = 'available'
            ORDER BY RANDOM()
            LIMIT ?
            """,
            (order["product_key"], quantity),
        )
        try:
            goods = await cursor.fetchall()
        finally:
            await cursor.close()
        if len(goods) < quantity:
            return None
        return goods

    async def _reserve_goods_for_order(
        self,
        connection: aiosqlite.Connection,
        order: aiosqlite.Row,
        now: str,
    ) -> list[str] | None:
        goods = await self._available_goods_for_order(connection, order)
        if goods is None:
            return None

        payloads: list[str] = []
        for good in goods:
            update_cursor = await connection.execute(
                """
                UPDATE goods
                SET status = 'sold', sold_to = ?, order_id = NULL, sold_at = ?
                WHERE id = ? AND status = 'available'
                """,
                (order["user_id"], now, good["id"]),
            )
            if update_cursor.rowcount != 1:
                await update_cursor.close()
                raise RuntimeError("Could not reserve an available stock item")
            await update_cursor.close()
            await connection.execute(
                """
                INSERT INTO order_items(order_id, product_id, payload, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (order["id"], good["id"], str(good["payload"]), now),
            )
            payloads.append(str(good["payload"]))
        return payloads

    async def _delivery_payloads_for_order(
        self,
        connection: aiosqlite.Connection,
        order: aiosqlite.Row,
        now: str,
        decrement_stock: bool,
    ) -> list[str] | None:
        if decrement_stock:
            return await self._reserve_goods_for_order(connection, order, now)
        goods = await self._available_goods_for_order(connection, order)
        if goods is None:
            return None
        return [str(good["payload"]) for good in goods]

    async def _consume_display_stock_in_transaction(
        self,
        connection: aiosqlite.Connection,
        product_key: str,
        quantity: int,
    ) -> None:
        """Lower the one storefront stock counter as part of settlement.

        It is deliberately independent of whether a payload is immediately
        available. A paid order without a payload is a preorder, so its units
        are still reserved and must not remain advertised as available.
        """
        if quantity < 1 or product_key == "balance_topup":
            return
        await connection.execute(
            """
            UPDATE products
            SET display_stock = MAX(0, display_stock - ?), updated_at = ?
            WHERE product_key = ?
            """,
            (quantity, utc_now(), product_key),
        )

    async def settle_paid_order(
        self,
        order_id: int,
        decrement_stock: bool = True,
    ) -> dict[str, Any] | None:
        """Mark a paid invoice once and optionally reserve its items atomically."""
        async with self.lock:
            connection = self._conn()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                order = await self._fetchone("SELECT * FROM orders WHERE id = ?", (order_id,))
                if order is None or order["status"] != "pending":
                    await connection.rollback()
                    return None

                now = utc_now()
                await connection.execute(
                    "UPDATE orders SET status = 'paid', paid_at = ? WHERE id = ?",
                    (now, order_id),
                )

                if order["product_key"] == "balance_topup":
                    await connection.execute(
                        "UPDATE users SET balance_cents = balance_cents + ?, updated_at = ? WHERE user_id = ?",
                        (order["amount_cents"], now, order["user_id"]),
                    )
                    await connection.execute(
                        "UPDATE orders SET delivery_status = 'pending', delivery_payload = ? WHERE id = ?",
                        (str(order["amount_cents"]), order_id),
                    )
                    await connection.commit()
                    return {
                        "order_id": order_id,
                        "user_id": order["user_id"],
                        "product_key": order["product_key"],
                        "amount_cents": order["amount_cents"],
                        "quantity": order["quantity"],
                        "currency": order["currency"],
                        "delivery_status": "pending",
                        "payload": str(order["amount_cents"]),
                    }

                payloads = await self._delivery_payloads_for_order(
                    connection,
                    order,
                    now,
                    decrement_stock,
                )
                await self._consume_display_stock_in_transaction(
                    connection,
                    str(order["product_key"]),
                    int(order["quantity"] or 1),
                )
                if payloads is None:
                    await connection.execute(
                        "UPDATE orders SET delivery_status = 'waiting_stock' WHERE id = ?",
                        (order_id,),
                    )
                    await connection.commit()
                    return {
                        "order_id": order_id,
                        "user_id": order["user_id"],
                        "product_key": order["product_key"],
                        "amount_cents": order["amount_cents"],
                        "quantity": order["quantity"],
                        "currency": order["currency"],
                        "delivery_status": "waiting_stock",
                        "payload": None,
                    }
                await connection.execute(
                    """
                    UPDATE orders
                    SET delivery_status = 'pending', delivery_payload = ?, product_id = NULL
                    WHERE id = ?
                    """,
                    (json.dumps(payloads, ensure_ascii=False), order_id),
                )
                await connection.commit()
                return {
                    "order_id": order_id,
                    "user_id": order["user_id"],
                    "product_key": order["product_key"],
                    "amount_cents": order["amount_cents"],
                    "quantity": order["quantity"],
                    "currency": order["currency"],
                    "delivery_status": "pending",
                    "payload": payloads,
                }
            except Exception:
                await connection.rollback()
                raise

    async def pay_order_with_balance(
        self,
        order_id: int,
        user_id: int,
        decrement_stock: bool = True,
    ) -> dict[str, Any] | None:
        """Pay a pending product/queue order atomically from the buyer's balance."""
        async with self.lock:
            connection = self._conn()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                order = await self._fetchone("SELECT * FROM orders WHERE id = ?", (order_id,))
                if (
                    order is None
                    or order["status"] != "pending"
                    or int(order["user_id"]) != user_id
                    or order["product_key"] == "balance_topup"
                ):
                    await connection.rollback()
                    return None

                required_cents = int(order["balance_amount_cents"] or 0)
                if required_cents <= 0 and str(order["currency"]).upper() == "USD":
                    required_cents = int(order["amount_cents"])
                if required_cents <= 0:
                    await connection.rollback()
                    return None

                now = utc_now()
                cursor = await connection.execute(
                    """
                    UPDATE users
                    SET balance_cents = balance_cents - ?, updated_at = ?
                    WHERE user_id = ? AND balance_cents >= ?
                    """,
                    (required_cents, now, user_id, required_cents),
                )
                updated = cursor.rowcount
                await cursor.close()
                if updated != 1:
                    await connection.rollback()
                    return {
                        "status": "insufficient",
                        "order_id": order_id,
                        "user_id": user_id,
                        "required_cents": required_cents,
                    }

                await connection.execute(
                    "UPDATE orders SET status = 'paid', paid_at = ? WHERE id = ?",
                    (now, order_id),
                )
                payloads = await self._delivery_payloads_for_order(
                    connection,
                    order,
                    now,
                    decrement_stock,
                )
                await self._consume_display_stock_in_transaction(
                    connection,
                    str(order["product_key"]),
                    int(order["quantity"] or 1),
                )
                if payloads is None:
                    await connection.execute(
                        "UPDATE orders SET delivery_status = 'waiting_stock' WHERE id = ?",
                        (order_id,),
                    )
                    await connection.commit()
                    return {
                        "order_id": order_id,
                        "user_id": order["user_id"],
                        "product_key": order["product_key"],
                        "amount_cents": order["amount_cents"],
                        "quantity": order["quantity"],
                        "currency": order["currency"],
                        "delivery_status": "waiting_stock",
                        "payload": None,
                        "payment_method": "balance",
                    }

                await connection.execute(
                    """
                    UPDATE orders
                    SET delivery_status = 'pending', delivery_payload = ?, product_id = NULL
                    WHERE id = ?
                    """,
                    (json.dumps(payloads, ensure_ascii=False), order_id),
                )
                await connection.commit()
                return {
                    "order_id": order_id,
                    "user_id": order["user_id"],
                    "product_key": order["product_key"],
                    "amount_cents": order["amount_cents"],
                    "quantity": order["quantity"],
                    "currency": order["currency"],
                    "delivery_status": "pending",
                    "payload": payloads,
                    "payment_method": "balance",
                }
            except Exception:
                await connection.rollback()
                raise

    async def get_waiting_stock_orders(self) -> list[aiosqlite.Row]:
        return await self._fetchall(
            """
            SELECT * FROM orders
            WHERE status = 'paid' AND delivery_status = 'waiting_stock'
            ORDER BY id
            """
        )

    async def try_fulfill_waiting_order(self, order_id: int, decrement_stock: bool = True) -> bool:
        async with self.lock:
            connection = self._conn()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                order = await self._fetchone("SELECT * FROM orders WHERE id = ?", (order_id,))
                if order is None or order["status"] != "paid" or order["delivery_status"] != "waiting_stock":
                    await connection.rollback()
                    return False
                now = utc_now()
                payloads = await self._delivery_payloads_for_order(
                    connection,
                    order,
                    now,
                    decrement_stock,
                )
                if payloads is None:
                    await connection.rollback()
                    return False
                await connection.execute(
                    """
                    UPDATE orders
                    SET delivery_status = 'pending', delivery_payload = ?, product_id = NULL
                    WHERE id = ?
                    """,
                    (json.dumps(payloads, ensure_ascii=False), order_id),
                )
                await connection.commit()
                return True
            except Exception:
                await connection.rollback()
                raise

    async def get_pending_deliveries(self) -> list[aiosqlite.Row]:
        return await self._fetchall(
            "SELECT * FROM orders WHERE status = 'paid' AND delivery_status = 'pending' ORDER BY id"
        )

    async def claim_delivery(self, order_id: int) -> aiosqlite.Row | None:
        async with self.lock:
            connection = self._conn()
            cursor = await connection.execute(
                """
                UPDATE orders SET delivery_status = 'sending'
                WHERE id = ? AND status = 'paid' AND delivery_status = 'pending'
                """,
                (order_id,),
            )
            if cursor.rowcount != 1:
                await connection.commit()
                return None
            await connection.commit()
            return await self._fetchone("SELECT * FROM orders WHERE id = ?", (order_id,))

    async def mark_delivery_sent(self, order_id: int) -> None:
        async with self.lock:
            await self._conn().execute(
                """
                UPDATE orders
                SET delivery_status = 'sent', delivered_at = ?
                WHERE id = ? AND delivery_status = 'sending'
                """,
                (utc_now(), order_id),
            )
            await self._conn().commit()

    async def reset_delivery(self, order_id: int) -> None:
        async with self.lock:
            await self._conn().execute(
                "UPDATE orders SET delivery_status = 'pending' WHERE id = ? AND delivery_status = 'sending'",
                (order_id,),
            )
            await self._conn().commit()

    async def add_good(self, product_key: str, payload: str) -> int:
        """Load one account and raise the storefront counter with it.

        The counter is the single stock figure, so accounts arriving have to move
        it: otherwise the owner would load ten accounts, the shop would keep
        offering none, and the ten would sit unsold.
        """
        async with self.lock:
            cursor = await self._conn().execute(
                "INSERT INTO goods(product_key, payload, created_at) VALUES (?, ?, ?)",
                (product_key, payload, utc_now()),
            )
            await self._conn().execute(
                """
                UPDATE products
                SET display_stock = MAX(0, display_stock) + 1, updated_at = ?
                WHERE product_key = ?
                """,
                (utc_now(), product_key),
            )
            await self._conn().commit()
            return int(cursor.lastrowid)

    async def list_available_goods(self, limit: int = 200) -> list[aiosqlite.Row]:
        return await self._fetchall(
            """
            SELECT id, product_key, created_at
            FROM goods
            WHERE status = 'available'
            ORDER BY product_key, id
            LIMIT ?
            """,
            (limit,),
        )

    async def remove_good(self, good_id: int) -> bool:
        async with self.lock:
            good = await self._fetchone(
                "SELECT product_key FROM goods WHERE id = ? AND status = 'available'",
                (good_id,),
            )
            if good is None:
                await self._conn().commit()
                return False
            cursor = await self._conn().execute(
                "UPDATE goods SET status = 'removed' WHERE id = ? AND status = 'available'",
                (good_id,),
            )
            if cursor.rowcount == 1:
                await self._conn().execute(
                    """
                    UPDATE products
                    SET display_stock = MAX(0, display_stock - 1), updated_at = ?
                    WHERE product_key = ?
                    """,
                    (utc_now(), str(good["product_key"])),
                )
            await self._conn().commit()
            return cursor.rowcount == 1

    async def available_stock(self) -> dict[str, int]:
        """What the storefront offers, one number per product.

        That number is the counter the owner sets in the admin panel and nothing
        else. Loading accounts raises it, a sale lowers it, and the owner can
        overrule both — so there is a single figure to reason about instead of a
        display value and a real value that can disagree. Whether an order can be
        handed over immediately is a separate question, answered by the goods
        table at delivery time.
        """
        rows = await self._fetchall(
            "SELECT product_key, display_stock FROM products WHERE enabled = 1"
        )
        return {str(row["product_key"]): max(0, int(row["display_stock"])) for row in rows}

    async def actual_stock(self) -> dict[str, int]:
        rows = await self._fetchall(
            """
            SELECT product_key, COUNT(*) AS count
            FROM goods
            WHERE status = 'available'
            GROUP BY product_key
            """
        )
        return {str(row["product_key"]): int(row["count"]) for row in rows}

    async def display_stock(self) -> dict[str, int]:
        rows = await self._fetchall(
            "SELECT product_key, display_stock FROM products WHERE enabled = 1"
        )
        return {str(row["product_key"]): int(row["display_stock"]) for row in rows}

    async def add_waitlist_entry(self, user_id: int, product_key: str) -> bool:
        """Subscribe to "back in stock", or re-subscribe after a past notice.

        ``INSERT OR IGNORE`` alone left an already-notified row in place, so a
        buyer who used the button once was never told again — the second tap
        silently did nothing. Re-activating on conflict is what makes the button
        work every time.
        """
        async with self.lock:
            cursor = await self._conn().execute(
                """
                INSERT INTO waitlist(user_id, product_key, status, created_at)
                VALUES (?, ?, 'active', ?)
                ON CONFLICT(user_id, product_key) DO UPDATE
                SET status = 'active', created_at = excluded.created_at
                WHERE waitlist.status <> 'active'
                """,
                (user_id, product_key, utc_now()),
            )
            await self._conn().commit()
            return cursor.rowcount == 1

    async def get_waitlist_users(self, product_key: str) -> list[aiosqlite.Row]:
        return await self._fetchall(
            """
            SELECT user_id FROM waitlist
            WHERE product_key = ? AND status = 'active'
            ORDER BY id
            """,
            (product_key,),
        )

    async def mark_waitlist_notified(self, user_id: int, product_key: str) -> None:
        async with self.lock:
            await self._conn().execute(
                """
                UPDATE waitlist SET status = 'notified'
                WHERE user_id = ? AND product_key = ? AND status = 'active'
                """,
                (user_id, product_key),
            )
            await self._conn().commit()

    # ------------------------------------------------------------------
    # Manual crypto payments
    #
    # Lifecycle: awaiting_hash -> pending -> confirmed | rejected, plus
    # cancelled from either of the first two. Every transition is a guarded
    # UPDATE that also names the expected current status, so a double-tapped
    # button or a retried callback can never apply the same step twice — the
    # second attempt updates zero rows and the caller gets None.
    # ------------------------------------------------------------------

    async def create_manual_payment(
        self,
        user_id: int,
        asset: str,
        network: str,
        address: str,
        amount_cents: int,
        currency: str = "USD",
        crypto_amount: str | None = None,
        rate: str | None = None,
        rate_at: str | None = None,
    ) -> int:
        if amount_cents <= 0:
            raise ValueError("amount_cents must be positive")
        async with self.lock:
            public_number = await self._allocate_public_number("manual_payments")
            cursor = await self._conn().execute(
                """
                INSERT INTO manual_payments(
                    public_number, user_id, asset, network, address, amount_cents, currency,
                    crypto_amount, rate, rate_at, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'awaiting_hash', ?)
                """,
                (
                    public_number,
                    user_id,
                    asset,
                    network,
                    address,
                    amount_cents,
                    currency,
                    crypto_amount,
                    rate,
                    rate_at,
                    utc_now(),
                ),
            )
            await self._conn().commit()
            return int(cursor.lastrowid)

    async def get_manual_payment(self, payment_id: int) -> aiosqlite.Row | None:
        return await self._fetchone(
            "SELECT * FROM manual_payments WHERE id = ?",
            (payment_id,),
        )

    async def find_manual_payment_by_hash(self, tx_hash: str) -> aiosqlite.Row | None:
        """Look up a hash across all users.

        Used to reject a hash that has already been claimed, including by
        somebody else — a public explorer makes anyone's tx hash copyable, so
        without this check one real transfer could be claimed repeatedly.
        """
        return await self._fetchone(
            """
            SELECT * FROM manual_payments
            WHERE tx_hash IS NOT NULL
              AND lower(tx_hash) = lower(?)
              AND status IN ('pending', 'confirmed')
            ORDER BY id
            LIMIT 1
            """,
            (tx_hash.strip(),),
        )

    async def submit_manual_payment_hash(
        self,
        payment_id: int,
        user_id: int,
        tx_hash: str,
    ) -> aiosqlite.Row | None:
        tx_hash = tx_hash.strip()
        if not tx_hash:
            raise ValueError("tx_hash cannot be empty")
        async with self.lock:
            connection = self._conn()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                duplicate = await self._fetchone(
                    """
                    SELECT id FROM manual_payments
                    WHERE lower(tx_hash) = lower(?)
                      AND status IN ('pending', 'confirmed')
                      AND id != ?
                    LIMIT 1
                    """,
                    (tx_hash, payment_id),
                )
                if duplicate is not None:
                    await connection.rollback()
                    return None
                now = utc_now()
                cursor = await connection.execute(
                    """
                    UPDATE manual_payments
                    SET tx_hash = ?, status = 'pending', submitted_at = ?
                    WHERE id = ? AND user_id = ? AND status = 'awaiting_hash'
                    """,
                    (tx_hash, now, payment_id, user_id),
                )
                if cursor.rowcount != 1:
                    await connection.rollback()
                    return None
                row = await self._fetchone(
                    "SELECT * FROM manual_payments WHERE id = ?",
                    (payment_id,),
                )
                await connection.commit()
                return row
            except Exception:
                await connection.rollback()
                raise

    async def request_manual_payment_review(
        self,
        payment_id: int,
        user_id: int,
    ) -> aiosqlite.Row | None:
        """Hand a transfer to the admins without asking the buyer for a hash.

        The buyer taps "check payment" and the request moves straight to
        ``pending``. There is no hash to de-duplicate against, so the admin has
        to locate the transfer by address and amount — that is the trade-off for
        not making the buyer copy a hash out of their wallet. The guard on
        ``status = 'awaiting_hash'`` still makes a double tap harmless.
        """
        async with self.lock:
            connection = self._conn()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = await connection.execute(
                    """
                    UPDATE manual_payments
                    SET status = 'pending', submitted_at = ?
                    WHERE id = ? AND user_id = ? AND status = 'awaiting_hash'
                    """,
                    (utc_now(), payment_id, user_id),
                )
                if cursor.rowcount != 1:
                    await connection.rollback()
                    return None
                row = await self._fetchone(
                    "SELECT * FROM manual_payments WHERE id = ?",
                    (payment_id,),
                )
                await connection.commit()
                return row
            except Exception:
                await connection.rollback()
                raise

    async def decide_manual_payment(
        self,
        payment_id: int,
        admin_id: int,
        approve: bool,
    ) -> aiosqlite.Row | None:
        """Confirm or reject a pending payment.

        On approval the balance is credited in the same transaction as the
        status change, so the two can never disagree. The balance UPDATE is
        written inline rather than through ``add_balance_cents`` because that
        method takes ``self.lock``, which is not reentrant.
        """
        async with self.lock:
            connection = self._conn()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                now = utc_now()
                cursor = await connection.execute(
                    """
                    UPDATE manual_payments
                    SET status = ?, decided_at = ?, decided_by = ?
                    WHERE id = ? AND status = 'pending'
                    """,
                    ("confirmed" if approve else "rejected", now, admin_id, payment_id),
                )
                if cursor.rowcount != 1:
                    await connection.rollback()
                    return None
                row = await self._fetchone(
                    "SELECT * FROM manual_payments WHERE id = ?",
                    (payment_id,),
                )
                if row is None:
                    await connection.rollback()
                    return None
                if approve:
                    credited = await connection.execute(
                        """
                        UPDATE users
                        SET balance_cents = balance_cents + ?, updated_at = ?
                        WHERE user_id = ?
                        """,
                        (int(row["amount_cents"]), now, int(row["user_id"])),
                    )
                    if credited.rowcount != 1:
                        # No such user: refuse the whole decision rather than
                        # mark a payment confirmed that credited nobody.
                        await connection.rollback()
                        return None
                await connection.commit()
                return row
            except Exception:
                await connection.rollback()
                raise

    async def cancel_manual_payment(self, payment_id: int, user_id: int) -> bool:
        """Let a buyer drop their own request before an admin has ruled on it."""
        async with self.lock:
            cursor = await self._conn().execute(
                """
                UPDATE manual_payments
                SET status = 'cancelled', decided_at = ?
                WHERE id = ? AND user_id = ? AND status IN ('awaiting_hash', 'pending')
                """,
                (utc_now(), payment_id, user_id),
            )
            await self._conn().commit()
            return cursor.rowcount == 1

    async def expire_stale_manual_payments(self, older_than_hours: int) -> int:
        """Drop requests where the buyer never sent a hash.

        Only ``awaiting_hash`` rows are touched. A ``pending`` row is waiting on
        an admin, not on the buyer, and must never be timed out — the money may
        already be on-chain.
        """
        if older_than_hours < 1:
            raise ValueError("older_than_hours must be at least 1")
        cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
        async with self.lock:
            cursor = await self._conn().execute(
                """
                UPDATE manual_payments
                SET status = 'expired', decided_at = ?
                WHERE status = 'awaiting_hash' AND created_at < ?
                """,
                (utc_now(), cutoff.isoformat()),
            )
            await self._conn().commit()
            return cursor.rowcount

    async def list_pending_manual_payments(self, limit: int = 20) -> list[aiosqlite.Row]:
        return await self._fetchall(
            """
            SELECT m.*, u.username
            FROM manual_payments m
            LEFT JOIN users u ON u.user_id = m.user_id
            WHERE m.status = 'pending'
            ORDER BY m.id
            LIMIT ?
            """,
            (limit,),
        )

    async def count_pending_manual_payments(self) -> int:
        row = await self._fetchone(
            "SELECT COUNT(*) AS total FROM manual_payments WHERE status = 'pending'"
        )
        return int(row["total"]) if row is not None else 0

    async def open_manual_payment_for_user(self, user_id: int) -> aiosqlite.Row | None:
        """The buyer's most recent request that is still in play, if any."""
        return await self._fetchone(
            """
            SELECT * FROM manual_payments
            WHERE user_id = ? AND status IN ('awaiting_hash', 'pending')
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,),
        )

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------

    async def list_categories(self) -> list[aiosqlite.Row]:
        return await self._fetchall(
            "SELECT slug, title, position FROM categories ORDER BY position, title"
        )

    async def create_category(self, slug: str, title: str, position: int = 100) -> bool:
        async with self.lock:
            cursor = await self._conn().execute(
                """
                INSERT OR IGNORE INTO categories(slug, title, position, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (slug, title, position, utc_now()),
            )
            await self._conn().commit()
            return cursor.rowcount == 1

    async def rename_category(self, slug: str, title: str) -> bool:
        async with self.lock:
            cursor = await self._conn().execute(
                "UPDATE categories SET title = ? WHERE slug = ?",
                (title, slug),
            )
            await self._conn().commit()
            return cursor.rowcount == 1

    async def delete_category(self, slug: str, move_to: str | None = "catalog") -> int:
        """Drop a section and move whatever was in it somewhere else.

        Products are moved rather than deleted: a category is a shelf, and
        removing the shelf must not throw away the goods on it. ``move_to`` may
        be ``None`` only for an empty section — there is then nothing to move,
        and demanding a destination would block deleting the last category.
        """
        if slug == move_to:
            raise ValueError("cannot move products into the category being deleted")
        async with self.lock:
            await self._conn().execute("BEGIN IMMEDIATE")
            try:
                occupied = await self._fetchone(
                    "SELECT COUNT(*) AS total FROM products WHERE category = ?", (slug,)
                )
                if occupied is not None and int(occupied["total"]) and move_to is None:
                    raise ValueError("this category still holds products; give a destination")
                moved = 0
                if move_to is not None:
                    cursor = await self._conn().execute(
                        "UPDATE products SET category = ?, updated_at = ? WHERE category = ?",
                        (move_to, utc_now(), slug),
                    )
                    moved = cursor.rowcount
                await self._conn().execute("DELETE FROM categories WHERE slug = ?", (slug,))
            except Exception:
                await self._conn().rollback()
                raise
            await self._conn().commit()
            return moved

    async def set_product_category(self, product_key: str, category: str) -> bool:
        async with self.lock:
            cursor = await self._conn().execute(
                "UPDATE products SET category = ?, updated_at = ? WHERE product_key = ?",
                (category, utc_now(), product_key),
            )
            await self._conn().commit()
            return cursor.rowcount == 1

    async def count_products_in_category(self, slug: str) -> int:
        row = await self._fetchone(
            "SELECT COUNT(*) AS total FROM products WHERE enabled = 1 AND category = ?",
            (slug,),
        )
        return int(row["total"]) if row is not None else 0

    # ------------------------------------------------------------------
    # Product management
    # ------------------------------------------------------------------

    async def rename_product(self, product_key: str, title: str) -> bool:
        """One title for every language: a product name is a brand name."""
        async with self.lock:
            cursor = await self._conn().execute(
                """
                UPDATE products
                SET title_ru = ?, title_en = ?, title_zh = ?, updated_at = ?
                WHERE product_key = ?
                """,
                (title, title, title, utc_now(), product_key),
            )
            await self._conn().commit()
            return cursor.rowcount == 1

    async def delete_product(self, product_key: str) -> bool:
        """Take a product off sale without erasing its history.

        The row is disabled rather than deleted, because past orders point at it
        and a buyer's receipt should not turn into a bare product key. Unsold
        accounts are withdrawn with it, and the counter goes to zero.
        """
        async with self.lock:
            cursor = await self._conn().execute(
                """
                UPDATE products
                SET enabled = 0, display_stock = 0, updated_at = ?
                WHERE product_key = ? AND enabled = 1
                """,
                (utc_now(), product_key),
            )
            if cursor.rowcount != 1:
                await self._conn().commit()
                return False
            await self._conn().execute(
                "UPDATE goods SET status = 'removed' WHERE product_key = ? AND status = 'available'",
                (product_key,),
            )
            await self._conn().commit()
            return True

    async def consume_display_stock(self, product_key: str, quantity: int) -> None:
        """Lower the storefront counter after a sale, never below zero."""
        if quantity < 1:
            return
        async with self.lock:
            await self._conn().execute(
                """
                UPDATE products
                SET display_stock = MAX(0, display_stock - ?), updated_at = ?
                WHERE product_key = ?
                """,
                (quantity, utc_now(), product_key),
            )
            await self._conn().commit()

    # ------------------------------------------------------------------
    # Funnel events and statistics
    # ------------------------------------------------------------------

    async def track_event(self, user_id: int, event: str, detail: str | None = None) -> None:
        """Record one funnel step. Never raises: a lost statistic is not worth
        breaking the handler a buyer is standing in."""
        try:
            async with self.lock:
                await self._conn().execute(
                    "INSERT INTO events(user_id, event, detail, created_at) VALUES (?, ?, ?, ?)",
                    (user_id, event, detail, utc_now()),
                )
                await self._conn().commit()
        except Exception:
            pass

    async def event_counts(
        self,
        since: str | None = None,
        excluded_user_ids: tuple[int, ...] = (),
    ) -> dict[str, tuple[int, int]]:
        """Per event: how many times it happened and how many distinct people."""
        user_filter, user_params = self._user_exclusion("user_id", excluded_user_ids)
        date_filter = " AND created_at >= ?" if since else ""
        where = "WHERE 1 = 1" + user_filter + date_filter
        params = user_params + ((since,) if since else ())
        rows = await self._fetchall(
            f"""
            SELECT event, COUNT(*) AS total, COUNT(DISTINCT user_id) AS people
            FROM events
            {where}
            GROUP BY event
            """,
            params,
        )
        return {str(row["event"]): (int(row["total"]), int(row["people"])) for row in rows}

    async def order_stats(
        self,
        since: str | None = None,
        excluded_user_ids: tuple[int, ...] = (),
    ) -> dict[str, int]:
        """Paid orders, units and revenue in USD cents, plus what is waiting."""
        user_filter, user_params = self._user_exclusion("user_id", excluded_user_ids)
        paid_filter = " AND paid_at >= ?" if since else ""
        paid_params = user_params + ((since,) if since else ())
        row = await self._fetchone(
            f"""
            SELECT
                COUNT(*) AS paid_orders,
                COALESCE(SUM(quantity), 0) AS units,
                COALESCE(SUM(COALESCE(balance_amount_cents, amount_cents)), 0) AS revenue,
                COUNT(DISTINCT user_id) AS buyers
            FROM orders
            WHERE status = 'paid' AND order_type = 'product'{user_filter}{paid_filter}
            """,
            paid_params,
        )
        waiting = await self._fetchone(
            f"""
            SELECT COUNT(*) AS total FROM orders
            WHERE status = 'paid' AND delivery_status = 'waiting_stock'{user_filter}{paid_filter}
            """,
            paid_params,
        )
        topups = await self._fetchone(
            f"""
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(amount_cents), 0) AS amount
            FROM orders
            WHERE status = 'paid' AND product_key = 'balance_topup'{user_filter}{paid_filter}
            """,
            paid_params,
        )
        return {
            "paid_orders": int(row["paid_orders"]) if row else 0,
            "units": int(row["units"]) if row else 0,
            "revenue_cents": int(row["revenue"]) if row else 0,
            "buyers": int(row["buyers"]) if row else 0,
            "waiting_stock": int(waiting["total"]) if waiting else 0,
            "topup_orders": int(topups["total"]) if topups else 0,
            "topup_cents": int(topups["amount"]) if topups else 0,
        }

    async def paid_orders_by_product(
        self,
        limit: int = 10,
        since: str | None = None,
        excluded_user_ids: tuple[int, ...] = (),
    ) -> list[aiosqlite.Row]:
        user_filter, user_params = self._user_exclusion("user_id", excluded_user_ids)
        date_filter = " AND paid_at >= ?" if since else ""
        params = user_params + ((since,) if since else ()) + (limit,)
        return await self._fetchall(
            f"""
            SELECT product_key,
                   COUNT(*) AS orders,
                   COALESCE(SUM(quantity), 0) AS units
            FROM orders
            WHERE status = 'paid' AND order_type = 'product'{user_filter}{date_filter}
            GROUP BY product_key
            ORDER BY units DESC, orders DESC
            LIMIT ?
            """,
            params,
        )

    async def manual_payment_stats(
        self,
        since: str | None = None,
        excluded_user_ids: tuple[int, ...] = (),
    ) -> dict[str, int]:
        user_filter, user_params = self._user_exclusion("user_id", excluded_user_ids)
        date_filter = " AND created_at >= ?" if since else ""
        params = user_params + ((since,) if since else ())
        rows = await self._fetchall(
            f"SELECT status, COUNT(*) AS total FROM manual_payments WHERE 1 = 1{user_filter}{date_filter} GROUP BY status",
            params,
        )
        return {str(row["status"]): int(row["total"]) for row in rows}

    async def count_users_since(
        self,
        since: str,
        excluded_user_ids: tuple[int, ...] = (),
    ) -> int:
        return await self.count_users(since, excluded_user_ids)

    async def users_by_language(
        self,
        since: str | None = None,
        excluded_user_ids: tuple[int, ...] = (),
    ) -> dict[str, int]:
        user_filter, user_params = self._user_exclusion("user_id", excluded_user_ids)
        date_filter = " AND created_at >= ?" if since else ""
        params = user_params + ((since,) if since else ())
        rows = await self._fetchall(
            f"""
            SELECT COALESCE(language, '—') AS language, COUNT(*) AS total
            FROM users
            WHERE 1 = 1{user_filter}{date_filter}
            GROUP BY COALESCE(language, '—')
            ORDER BY total DESC
            """,
            params,
        )
        return {str(row["language"]): int(row["total"]) for row in rows}

    async def waitlist_counts(
        self,
        since: str | None = None,
        excluded_user_ids: tuple[int, ...] = (),
    ) -> dict[str, int]:
        user_filter, user_params = self._user_exclusion("user_id", excluded_user_ids)
        date_filter = " AND created_at >= ?" if since else ""
        params = user_params + ((since,) if since else ())
        rows = await self._fetchall(
            f"""
            SELECT product_key, COUNT(*) AS total
            FROM waitlist
            WHERE status = 'active'{user_filter}{date_filter}
            GROUP BY product_key
            """,
            params,
        )
        return {str(row["product_key"]): int(row["total"]) for row in rows}

    async def balance_total_cents(self, excluded_user_ids: tuple[int, ...] = ()) -> int:
        user_filter, user_params = self._user_exclusion("user_id", excluded_user_ids)
        row = await self._fetchone(
            f"SELECT COALESCE(SUM(balance_cents), 0) AS total FROM users WHERE 1 = 1{user_filter}",
            user_params,
        )
        return int(row["total"]) if row is not None else 0

    # ------------------------------------------------------------------
    # Referral commission
    # ------------------------------------------------------------------

    async def credit_referral(
        self,
        order_id: int,
        buyer_id: int,
        amount_cents: int,
        percent: int,
    ) -> dict[str, int] | None:
        """Pay the inviter their cut of one order, at most once.

        Returns ``None`` when there is nothing to pay: no inviter, a
        self-referral, a commission that rounds to zero, or an order that has
        already paid out. The unique index on ``order_id`` is what makes a
        retried settlement safe — the second attempt loses the insert and the
        balance is left alone.
        """
        if amount_cents <= 0 or percent <= 0:
            return None
        async with self.lock:
            buyer = await self._fetchone(
                "SELECT referrer_id FROM users WHERE user_id = ?",
                (buyer_id,),
            )
            if buyer is None or buyer["referrer_id"] is None:
                return None
            referrer_id = int(buyer["referrer_id"])
            if referrer_id == buyer_id:
                return None
            referrer = await self._fetchone(
                "SELECT user_id FROM users WHERE user_id = ?",
                (referrer_id,),
            )
            if referrer is None:
                return None
            bonus = amount_cents * percent // 100
            if bonus <= 0:
                return None
            connection = self._conn()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = await connection.execute(
                    """
                    INSERT OR IGNORE INTO referral_payouts(
                        order_id, referrer_id, buyer_id, amount_cents, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (order_id, referrer_id, buyer_id, bonus, utc_now()),
                )
                if cursor.rowcount != 1:
                    await connection.rollback()
                    return None
                await connection.execute(
                    """
                    UPDATE users
                    SET balance_cents = balance_cents + ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (bonus, utc_now(), referrer_id),
                )
                balance = await self._fetchone(
                    "SELECT balance_cents FROM users WHERE user_id = ?",
                    (referrer_id,),
                )
                await connection.commit()
            except Exception:
                await connection.rollback()
                raise
            return {
                "referrer_id": referrer_id,
                "bonus_cents": bonus,
                "balance_cents": int(balance["balance_cents"]) if balance else bonus,
            }

    async def referral_summary(self, user_id: int) -> dict[str, int]:
        invited = await self._fetchone(
            "SELECT COUNT(*) AS total FROM users WHERE referrer_id = ?",
            (user_id,),
        )
        earned = await self._fetchone(
            """
            SELECT COUNT(*) AS orders, COALESCE(SUM(amount_cents), 0) AS total
            FROM referral_payouts
            WHERE referrer_id = ?
            """,
            (user_id,),
        )
        return {
            "invited": int(invited["total"]) if invited else 0,
            "paid_orders": int(earned["orders"]) if earned else 0,
            "earned_cents": int(earned["total"]) if earned else 0,
        }

    async def referral_totals(
        self,
        since: str | None = None,
        excluded_user_ids: tuple[int, ...] = (),
    ) -> dict[str, int]:
        ids = tuple(dict.fromkeys(int(user_id) for user_id in excluded_user_ids))
        payout_conditions: list[str] = []
        payout_params: tuple[Any, ...] = ()
        invited_conditions: list[str] = ["referrer_id IS NOT NULL"]
        invited_params: tuple[Any, ...] = ()
        if ids:
            placeholders = ", ".join("?" for _ in ids)
            payout_conditions.extend(
                [
                    f"referrer_id NOT IN ({placeholders})",
                    f"buyer_id NOT IN ({placeholders})",
                ]
            )
            payout_params += ids + ids
            invited_conditions.extend(
                [
                    f"user_id NOT IN ({placeholders})",
                    f"referrer_id NOT IN ({placeholders})",
                ]
            )
            invited_params += ids + ids
        if since:
            payout_conditions.append("created_at >= ?")
            payout_params += (since,)
            invited_conditions.append("created_at >= ?")
            invited_params += (since,)
        payout_where = "WHERE " + " AND ".join(payout_conditions) if payout_conditions else ""
        invited_where = "WHERE " + " AND ".join(invited_conditions)
        row = await self._fetchone(
            f"""
            SELECT COUNT(*) AS payouts,
                   COALESCE(SUM(amount_cents), 0) AS total,
                   COUNT(DISTINCT referrer_id) AS earners
            FROM referral_payouts
            {payout_where}
            """,
            payout_params,
        )
        invited = await self._fetchone(
            f"SELECT COUNT(*) AS total FROM users {invited_where}",
            invited_params,
        )
        return {
            "payouts": int(row["payouts"]) if row else 0,
            "total_cents": int(row["total"]) if row else 0,
            "earners": int(row["earners"]) if row else 0,
            "invited_users": int(invited["total"]) if invited else 0,
        }

    async def credit_referral_campaign(
        self,
        campaign_key: str,
        order_id: int,
        buyer_id: int,
        threshold_cents: int,
        bonus_cents: int,
        starts_at: str,
        ends_at: str,
    ) -> dict[str, int] | None:
        """Pay one cumulative referral campaign reward, at most once.

        The qualifying total is calculated from settled product orders whose
        canonical USD amount is known and whose payment happened before the
        campaign deadline. The unique campaign/buyer key makes retries safe.
        """
        if threshold_cents <= 0 or bonus_cents <= 0:
            return None
        async with self.lock:
            connection = self._conn()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                buyer = await self._fetchone(
                    "SELECT referrer_id FROM users WHERE user_id = ?",
                    (buyer_id,),
                )
                if buyer is None or buyer["referrer_id"] is None:
                    await connection.rollback()
                    return None
                referrer_id = int(buyer["referrer_id"])
                if referrer_id == buyer_id:
                    await connection.rollback()
                    return None
                referrer = await self._fetchone(
                    "SELECT user_id FROM users WHERE user_id = ?",
                    (referrer_id,),
                )
                current = await self._fetchone(
                    "SELECT status, paid_at FROM orders WHERE id = ? AND user_id = ?",
                    (order_id, buyer_id),
                )
                if (
                    referrer is None
                    or current is None
                    or str(current["status"]) != "paid"
                    or not current["paid_at"]
                    or str(current["paid_at"]) < starts_at
                    or str(current["paid_at"]) > ends_at
                ):
                    await connection.rollback()
                    return None

                total_row = await self._fetchone(
                    """
                    SELECT COALESCE(SUM(COALESCE(balance_amount_cents, amount_cents)), 0) AS total
                    FROM orders
                    WHERE user_id = ?
                      AND status = 'paid'
                      AND order_type = 'product'
                      AND paid_at IS NOT NULL
                      AND paid_at >= ?
                      AND paid_at <= ?
                    """,
                    (buyer_id, starts_at, ends_at),
                )
                total_cents = int(total_row["total"]) if total_row else 0
                if total_cents < threshold_cents:
                    await connection.rollback()
                    return None

                cursor = await connection.execute(
                    """
                    INSERT OR IGNORE INTO referral_campaign_rewards(
                        campaign_key, referrer_id, buyer_id, trigger_order_id,
                        amount_cents, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (campaign_key, referrer_id, buyer_id, order_id, bonus_cents, utc_now()),
                )
                if cursor.rowcount != 1:
                    await connection.rollback()
                    return None
                await connection.execute(
                    """
                    UPDATE users
                    SET balance_cents = balance_cents + ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (bonus_cents, utc_now(), referrer_id),
                )
                balance = await self._fetchone(
                    "SELECT balance_cents FROM users WHERE user_id = ?",
                    (referrer_id,),
                )
                await connection.commit()
                return {
                    "referrer_id": referrer_id,
                    "buyer_id": buyer_id,
                    "bonus_cents": bonus_cents,
                    "total_cents": total_cents,
                    "balance_cents": int(balance["balance_cents"]) if balance else bonus_cents,
                }
            except Exception:
                await connection.rollback()
                raise
