from __future__ import annotations

import asyncio
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
            CREATE INDEX IF NOT EXISTS idx_waitlist_product ON waitlist(product_key, status);
            """
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

    async def create_order(
        self,
        user_id: int,
        product_key: str,
        amount_cents: int,
        order_token: str,
        invoice_id: int | str,
    ) -> int:
        async with self.lock:
            cursor = await self._conn().execute(
                """
                INSERT INTO orders(user_id, product_key, amount_cents, order_token, invoice_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, product_key, amount_cents, order_token, str(invoice_id), utc_now()),
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

    async def settle_paid_order(
        self,
        order_id: int,
        decrement_stock: bool = True,
    ) -> dict[str, Any] | None:
        """Mark a paid invoice once and optionally reserve one item atomically."""
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
                        "delivery_status": "pending",
                        "payload": str(order["amount_cents"]),
                    }

                if not decrement_stock:
                    await connection.execute(
                        "UPDATE orders SET delivery_status = 'test_paid' WHERE id = ?",
                        (order_id,),
                    )
                    await connection.commit()
                    return {
                        "order_id": order_id,
                        "user_id": order["user_id"],
                        "product_key": order["product_key"],
                        "amount_cents": order["amount_cents"],
                        "delivery_status": "test_paid",
                        "payload": None,
                    }

                good = await self._fetchone(
                    """
                    SELECT id, payload FROM goods
                    WHERE product_key = ? AND status = 'available'
                    ORDER BY id LIMIT 1
                    """,
                    (order["product_key"],),
                )
                if good is None:
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
                        "delivery_status": "waiting_stock",
                        "payload": None,
                    }

                await connection.execute(
                    """
                    UPDATE goods
                    SET status = 'sold', sold_to = ?, order_id = ?, sold_at = ?
                    WHERE id = ? AND status = 'available'
                    """,
                    (order["user_id"], order_id, now, good["id"]),
                )
                await connection.execute(
                    """
                    UPDATE orders
                    SET delivery_status = 'pending', delivery_payload = ?, product_id = ?
                    WHERE id = ?
                    """,
                    (good["payload"], good["id"], order_id),
                )
                await connection.commit()
                return {
                    "order_id": order_id,
                    "user_id": order["user_id"],
                    "product_key": order["product_key"],
                    "amount_cents": order["amount_cents"],
                    "delivery_status": "pending",
                    "payload": good["payload"],
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

    async def try_fulfill_waiting_order(self, order_id: int) -> bool:
        async with self.lock:
            connection = self._conn()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                order = await self._fetchone("SELECT * FROM orders WHERE id = ?", (order_id,))
                if order is None or order["status"] != "paid" or order["delivery_status"] != "waiting_stock":
                    await connection.rollback()
                    return False
                good = await self._fetchone(
                    """
                    SELECT id, payload FROM goods
                    WHERE product_key = ? AND status = 'available'
                    ORDER BY id LIMIT 1
                    """,
                    (order["product_key"],),
                )
                if good is None:
                    await connection.rollback()
                    return False
                now = utc_now()
                await connection.execute(
                    """
                    UPDATE goods
                    SET status = 'sold', sold_to = ?, order_id = ?, sold_at = ?
                    WHERE id = ? AND status = 'available'
                    """,
                    (order["user_id"], order_id, now, good["id"]),
                )
                await connection.execute(
                    """
                    UPDATE orders
                    SET delivery_status = 'pending', delivery_payload = ?, product_id = ?
                    WHERE id = ?
                    """,
                    (good["payload"], good["id"], order_id),
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
