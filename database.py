from __future__ import annotations

import asyncio
import json
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

            CREATE TABLE IF NOT EXISTS products (
                product_key TEXT PRIMARY KEY,
                category TEXT NOT NULL DEFAULT 'catalog',
                title_ru TEXT NOT NULL,
                title_en TEXT NOT NULL,
                title_zh TEXT NOT NULL,
                price_usd_cents INTEGER NOT NULL,
                price_rub_cents INTEGER NOT NULL,
                price_cny_cents INTEGER NOT NULL,
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

            -- Crypto transfers made straight to one of our wallet addresses,
            -- outside Crypto Pay. Nothing here is credited automatically: a row
            -- stays 'pending' until an admin checks the tx hash on an explorer
            -- and confirms it, which is what moves it to 'confirmed'.
            CREATE TABLE IF NOT EXISTS manual_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            """
        )
        order_columns = {
            str(row["name"]) for row in await self._fetchall("PRAGMA table_info(orders)")
        }
        user_columns = {
            str(row["name"]) for row in await self._fetchall("PRAGMA table_info(users)")
        }
        if "purchase_notifications" not in user_columns:
            await self.connection.execute(
                "ALTER TABLE users ADD COLUMN purchase_notifications INTEGER NOT NULL DEFAULT 1"
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
                await self._conn().execute(
                    """
                    INSERT OR IGNORE INTO products(
                        product_key, category, title_ru, title_en, title_zh,
                        price_usd_cents, price_rub_cents, price_cny_cents,
                        display_stock, enabled, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        key,
                        getattr(product, "category", "catalog"),
                        product.title.get("ru", key),
                        product.title.get("en", key),
                        product.title.get("zh", key),
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
            SELECT product_key, category, title_ru, title_en, title_zh,
                   price_usd_cents, price_rub_cents, price_cny_cents,
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
    ) -> bool:
        if min(price_usd_cents, price_rub_cents, price_cny_cents) <= 0:
            raise ValueError("product prices must be positive")
        now = utc_now()
        async with self.lock:
            cursor = await self._conn().execute(
                """
                INSERT OR IGNORE INTO products(
                    product_key, category, title_ru, title_en, title_zh,
                    price_usd_cents, price_rub_cents, price_cny_cents,
                    display_stock, enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?, ?)
                """,
                (
                    product_key,
                    category,
                    title_ru,
                    title_en,
                    title_zh,
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

    async def count_users(self) -> int:
        row = await self._fetchone("SELECT COUNT(*) AS count FROM users")
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
            cursor = await self._conn().execute(
                """
                INSERT INTO orders(
                    user_id, product_key, amount_cents, balance_amount_cents,
                    quantity, currency, order_type,
                    order_token, invoice_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
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
        async with self.lock:
            cursor = await self._conn().execute(
                "INSERT INTO goods(product_key, payload, created_at) VALUES (?, ?, ?)",
                (product_key, payload, utc_now()),
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
            cursor = await self._conn().execute(
                "UPDATE goods SET status = 'removed' WHERE id = ? AND status = 'available'",
                (good_id,),
            )
            await self._conn().commit()
            return cursor.rowcount == 1

    async def available_stock(self) -> dict[str, int]:
        rows = await self._fetchall(
            """
            SELECT p.product_key,
                   p.display_stock,
                   COUNT(g.id) AS real_stock
            FROM products p
            LEFT JOIN goods g
              ON g.product_key = p.product_key AND g.status = 'available'
            WHERE p.enabled = 1
            GROUP BY p.product_key, p.display_stock
            """
        )
        return {
            str(row["product_key"]): max(int(row["display_stock"]), int(row["real_stock"]))
            for row in rows
        }

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
        async with self.lock:
            cursor = await self._conn().execute(
                """
                INSERT OR IGNORE INTO waitlist(user_id, product_key, status, created_at)
                VALUES (?, ?, 'active', ?)
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
            cursor = await self._conn().execute(
                """
                INSERT INTO manual_payments(
                    user_id, asset, network, address, amount_cents, currency,
                    crypto_amount, rate, rate_at, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'awaiting_hash', ?)
                """,
                (
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
