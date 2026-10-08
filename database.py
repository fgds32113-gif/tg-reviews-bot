import aiosqlite
from datetime import datetime, timedelta

DB = "reviews.db"


async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                cheat TEXT,
                period TEXT,
                rating INTEGER,
                comment TEXT,
                created_at TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)
        await db.commit()

        # миграция: добавить first_name, если её нет
        async with db.execute("PRAGMA table_info(reviews)") as cur:
            cols = [r[1] for r in await cur.fetchall()]
        if "first_name" not in cols:
            await db.execute("ALTER TABLE reviews ADD COLUMN first_name TEXT")
            await db.commit()


async def add_review(user_id: int, username: str, first_name: str,
                     cheat: str, period: str, rating: int, comment: str) -> int:
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("""
            INSERT INTO reviews
                (user_id, username, first_name, cheat, period, rating, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username, first_name, cheat, period, rating, comment,
              datetime.utcnow().isoformat()))
        await db.commit()
        return cur.lastrowid


async def get_review(review_id: int):
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT id, user_id, username, first_name, cheat, period, rating, "
            "comment, status FROM reviews WHERE id = ?", (review_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0], "user_id": row[1], "username": row[2],
                "first_name": row[3], "cheat": row[4], "period": row[5],
                "rating": row[6], "comment": row[7], "status": row[8],
            }


async def set_status(review_id: int, status: str):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "UPDATE reviews SET status = ? WHERE id = ?",
            (status, review_id)
        )
        await db.commit()


async def get_user_reviews(user_id: int, limit: int = 5):
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT id, cheat, period, rating, comment, status "
            "FROM reviews WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ) as cur:
            return await cur.fetchall()


# ---------- ЗАЩИТА ОТ ПОВТОРНЫХ ОТЗЫВОВ ----------
async def last_review_time(user_id: int):
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT created_at FROM reviews WHERE user_id = ? "
            "ORDER BY id DESC LIMIT 1", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row or not row[0]:
                return None
            try:
                return datetime.fromisoformat(row[0])
            except ValueError:
                return None


async def can_leave_review(user_id: int, days: int = 30):
    """Возвращает (можно_ли, сколько_часов_осталось)."""
    last = await last_review_time(user_id)
    if last is None:
        return True, 0

    delta = datetime.utcnow() - last
    limit = timedelta(days=days)
    if delta >= limit:
        return True, 0

    remaining = limit - delta
    return False, int(remaining.total_seconds() // 3600)


async def total_reviews_count() -> int:
    """Общее число отзывов за всё время."""
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT COUNT(*) FROM reviews") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0
