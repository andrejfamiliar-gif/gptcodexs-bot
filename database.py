from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
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
                referrer_id INTEGER,
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

            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status, delivery_status);
            CREATE INDEX IF NOT EXISTS idx_goods_stock ON goods(product_key, status);
            CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
            CREATE INDEX IF NOT EXISTS idx_waitlist_product ON waitlist(product_key, status);
            """
        )
        order_columns = {
            str(row["name"]) for row in await self._fetchall("PRAGMA table_info(orders)")
        }
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
            SELECT user_id, username, language, balance_cents, referrer_id, created_at, updated_at
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
            SELECT user_id, username, language, balance_cents, created_at
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
        cursor = await connection.execute(
            """
            SELECT id, payload FROM goods
            WHERE product_key = ? AND status = 'available'
            ORDER BY id
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
            "SELECT product_key, COUNT(*) AS count FROM goods WHERE status = 'available' GROUP BY product_key"
        )
        return {str(row["product_key"]): int(row["count"]) for row in rows}

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
