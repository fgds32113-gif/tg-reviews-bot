import asyncio
import os
import threading
import html
from flask import Flask
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton
)

import database as db

# ---------- НАСТРОЙКИ ----------
TG_TOKEN      = os.getenv("TG_TOKEN")
ADMIN_ID      = int(os.getenv("ADMIN_ID", "0"))
REVIEWS_CHAT  = int(os.getenv("REVIEWS_CHAT", "0"))
SUPPORT_URL   = os.getenv("SUPPORT_URL", "https://t.me/vodcheats")

REVIEW_COOLDOWN_DAYS = 30

# ---------- ВАРИАНТЫ ----------
CHEATS = {
    "cry4me": "🔫 Cry4me",
    "zolvs":  "⚡ Zolvs",
}

PERIODS = {
    "2w":  "🗓 2 недели",
    "1m":  "🗓 1 месяц",
    "inf": "♾ Пожизненно",
}

STARS = {
    1: "⭐",
    2: "⭐⭐",
    3: "⭐⭐⭐",
    4: "⭐⭐⭐⭐",
    5: "⭐⭐⭐⭐⭐",
}


# ---------- FSM ----------
class ReviewForm(StatesGroup):
    cheat   = State()
    period  = State()
    rating  = State()
    comment = State()


# ---------- ИНИЦИАЛИЗАЦИЯ ----------
bot = Bot(token=TG_TOKEN)
dp = Dispatcher()
app = Flask(__name__)


@app.route("/")
def health():
    return "OK", 200


def run_flask():
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# ---------- КЛАВИАТУРЫ ----------
def kb_cheats():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"cheat_{key}")]
        for key, name in CHEATS.items()
    ])


def kb_periods():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=name, callback_data=f"period_{key}")]
        for key, name in PERIODS.items()
    ])


def kb_rating():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1⭐", callback_data="rate_1"),
            InlineKeyboardButton(text="2⭐", callback_data="rate_2"),
            InlineKeyboardButton(text="3⭐", callback_data="rate_3"),
            InlineKeyboardButton(text="4⭐", callback_data="rate_4"),
            InlineKeyboardButton(text="5⭐", callback_data="rate_5"),
        ],
    ])


def kb_skip_comment():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_comment")],
    ])


def kb_admin(review_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"pub_ok_{review_id}"),
            InlineKeyboardButton(text="❌ Отклонить",    callback_data=f"pub_no_{review_id}"),
        ]
    ])


# ---------- ХЕЛПЕРЫ ----------
def display_name(user: types.User) -> str:
    """Имя пользователя (не username). Если пусто — 'Покупатель'."""
    name = (user.first_name or "").strip()
    if not name:
        name = (user.username or "").strip()
    return name or "Покупатель"


def format_review(data: dict, global_index: int = None) -> str:
    cheat_name = CHEATS.get(data["cheat"], data["cheat"])
    period_name = PERIODS.get(data["period"], data["period"])
    stars = STARS.get(data["rating"], "")
    comment = (data.get("comment") or "").strip()
    comment_line = f"\n💬 <i>{html.escape(comment)}</i>" if comment else ""

    name = html.escape((data.get("first_name") or "Покупатель").strip() or "Покупатель")
    header = f"<b>📝 Отзыв #{global_index}</b>" if global_index else "<b>📝 Отзыв</b>"

    return (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎮 Чит: <b>{cheat_name}</b>\n"
        f"📅 Срок: <b>{period_name}</b>\n"
        f"⭐ Оценка: <b>{stars} ({data['rating']}/5)</b>"
        f"{comment_line}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 {name}"
    )


# ---------- /start и /cancel ----------
@dp.message(Command("start"))
async def start(msg: types.Message, state: FSMContext):
    await state.clear()
    await msg.answer(
        "👋 Привет! Здесь ты можешь оставить отзыв о нашем сервисе.\n\n"
        "Нажми <b>Оставить отзыв</b>, чтобы начать.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Оставить отзыв", callback_data="start_review")],
            [InlineKeyboardButton(text="📋 Мои отзывы", callback_data="my_reviews")],
        ]),
        parse_mode="HTML"
    )


@dp.message(Command("cancel"))
async def cancel(msg: types.Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ Отменено. Чтобы начать заново — /start")


# ---------- МОИ ОТЗЫВЫ ----------
@dp.callback_query(F.data == "my_reviews")
async def my_reviews(cb: types.CallbackQuery):
    user_id = cb.from_user.id
    rows = await db.get_user_reviews(user_id)

    if not rows:
        await cb.answer("У вас пока нет отзывов", show_alert=True)
        return

    text_lines = ["<b>📋 Ваши отзывы:</b>\n"]
    for r in rows:
        rid, cheat, period, rating, comment, status = r
        cheat_name = CHEATS.get(cheat, cheat)
        stars = STARS.get(rating, "")
        status_icon = {
            "pending":  "⏳ на модерации",
            "approved": "✅ опубликован",
            "rejected": "❌ отклонён",
        }.get(status, status)
        text_lines.append(
            f"<b>#{rid}</b> — {cheat_name}, {stars} ({rating}/5)\n"
            f"   Статус: {status_icon}"
        )

    await cb.message.answer("\n".join(text_lines), parse_mode="HTML")


# ---------- СТАРТ ФОРМЫ (с проверкой 30 дней) ----------
@dp.callback_query(F.data == "start_review")
async def start_review(cb: types.CallbackQuery, state: FSMContext):
    user_id = cb.from_user.id

    can, hours_left = await db.can_leave_review(user_id, REVIEW_COOLDOWN_DAYS)
    if not can:
        days_left = max(1, hours_left // 24)
        await cb.answer(
            f"❌ Вы уже оставляли отзыв. Следующий можно через "
            f"{days_left} дн.",
            show_alert=True
        )
        return

    await state.set_state(ReviewForm.cheat)
    await cb.message.answer(
        "<b>Шаг 1/4.</b> 🎮 Выбери чит, который использовал:",
        reply_markup=kb_cheats(),
        parse_mode="HTML"
    )


# ---------- ШАГ 1: ЧИТ ----------
@dp.callback_query(F.data.startswith("cheat_"), ReviewForm.cheat)
async def form_cheat(cb: types.CallbackQuery, state: FSMContext):
    cheat = cb.data.split("_", 1)[1]
    if cheat not in CHEATS:
        await cb.answer("Неизвестный чит", show_alert=True)
        return

    await state.update_data(cheat=cheat)
    await state.set_state(ReviewForm.period)

    await cb.message.edit_text(
        "<b>Шаг 2/4.</b> 📅 На какой срок брал?",
        reply_markup=kb_periods(),
        parse_mode="HTML"
    )


# ---------- ШАГ 2: СРОК ----------
@dp.callback_query(F.data.startswith("period_"), ReviewForm.period)
async def form_period(cb: types.CallbackQuery, state: FSMContext):
    period = cb.data.split("_", 1)[1]
    if period not in PERIODS:
        await cb.answer("Неизвестный период", show_alert=True)
        return

    await state.update_data(period=period)
    await state.set_state(ReviewForm.rating)

    await cb.message.edit_text(
        "<b>Шаг 3/4.</b> ⭐ Оцени от 1 до 5 звёзд:",
        reply_markup=kb_rating(),
        parse_mode="HTML"
    )


# ---------- ШАГ 3: ОЦЕНКА ----------
@dp.callback_query(F.data.startswith("rate_"), ReviewForm.rating)
async def form_rating(cb: types.CallbackQuery, state: FSMContext):
    try:
        rating = int(cb.data.split("_", 1)[1])
    except ValueError:
        await cb.answer("Ошибка оценки", show_alert=True)
        return

    if rating < 1 or rating > 5:
        await cb.answer("Оценка от 1 до 5", show_alert=True)
        return

    await state.update_data(rating=rating)
    await state.set_state(ReviewForm.comment)

    await cb.message.edit_text(
        "<b>Шаг 4/4.</b> 💬 Напиши комментарий (или нажми «Пропустить»):\n\n"
        "<i>Например: «Работает стабильно, поддержка топ»</i>",
        reply_markup=kb_skip_comment(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "skip_comment", ReviewForm.comment)
async def form_skip_comment(cb: types.CallbackQuery, state: FSMContext):
    await _finish_review(cb.from_user, "", state, cb.message, edit=True)


# ---------- ШАГ 4: КОММЕНТАРИЙ ----------
@dp.message(ReviewForm.comment, F.text)
async def form_comment(msg: types.Message, state: FSMContext):
    comment = (msg.text or "").strip()[:500]
    await _finish_review(msg.from_user, comment, state, msg)


async def _finish_review(user: types.User, comment: str, state: FSMContext,
                         target_msg, edit: bool = False):
    data = await state.get_data()
    await state.clear()

    cheat = data.get("cheat")
    period = data.get("period")
    rating = data.get("rating")

    if not cheat or not period or not rating:
        await target_msg.answer("Ошибка: данные формы потеряны. Начни заново — /start")
        return

    username = user.username or ""
    first_name = display_name(user)

    review_id = await db.add_review(
        user.id, username, first_name, cheat, period, rating, comment
    )

    total = await db.total_reviews_count()

    review_data = {
        "id": review_id,
        "user_id": user.id,
        "username": username,
        "first_name": first_name,
        "cheat": cheat,
        "period": period,
        "rating": rating,
        "comment": comment,
        "status": "pending",
    }

    # ---- Пользователю ----
    text_ok = (
        "✅ <b>Спасибо за отзыв!</b>\n\n"
        f"Номер отзыва: <b>#{total}</b>\n"
        f"👤 Имя: <b>{html.escape(first_name)}</b>\n\n"
        "Отзыв отправлен на модерацию. После проверки он появится "
        "в нашем канале отзывов. 🙏"
    )
    if edit:
        try:
            await target_msg.edit_text(text_ok, parse_mode="HTML")
        except Exception:
            await target_msg.answer(text_ok, parse_mode="HTML")
    else:
        await target_msg.answer(text_ok, parse_mode="HTML")

    # ---- Админу ----
    if ADMIN_ID:
        admin_text = (
            f"<b>🔔 Новый отзыв на модерации</b>\n\n"
            f"{format_review(review_data, global_index=total)}\n\n"
            f"<i>user_id: {user.id}</i>"
        )
        try:
            await bot.send_message(
                ADMIN_ID, admin_text,
                reply_markup=kb_admin(review_id),
                parse_mode="HTML"
            )
        except Exception as e:
            print("admin notify error:", e)


# ---------- АДМИН: ПУБЛИКАЦИЯ ----------
@dp.callback_query(F.data.startswith("pub_ok_"))
async def admin_publish(cb: types.CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("Not admin", show_alert=True)
        return

    try:
        review_id = int(cb.data.split("_")[2])
    except (ValueError, IndexError):
        await cb.answer("Bad id", show_alert=True)
        return

    r = await db.get_review(review_id)
    if not r:
        await cb.answer("Отзыв не найден", show_alert=True)
        return
    if r["status"] != "pending":
        await cb.answer("Уже обработан", show_alert=True)
        return

    await db.set_status(review_id, "approved")

    # сквозной номер = id записи
    total_index = review_id

    if REVIEWS_CHAT:
        try:
            await bot.send_message(
                REVIEWS_CHAT,
                format_review(r, global_index=total_index),
                parse_mode="HTML"
            )
        except Exception as e:
            print("publish to channel error:", e)
            await cb.answer(f"Не удалось опубликовать: {e}", show_alert=True)
            return

    try:
        await bot.send_message(
            r["user_id"],
            f"✅ Ваш отзыв <b>#{total_index}</b> опубликован в нашем канале! "
            f"Спасибо 🙏",
            parse_mode="HTML"
        )
    except Exception as e:
        print("notify user error:", e)

    try:
        await cb.message.edit_text(
            f"{cb.message.html_text}\n\n✅ Опубликован",
            parse_mode="HTML"
        )
    except Exception:
        pass


@dp.callback_query(F.data.startswith("pub_no_"))
async def admin_reject(cb: types.CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("Not admin", show_alert=True)
        return

    try:
        review_id = int(cb.data.split("_")[2])
    except (ValueError, IndexError):
        await cb.answer("Bad id", show_alert=True)
        return

    r = await db.get_review(review_id)
    if not r:
        await cb.answer("Отзыв не найден", show_alert=True)
        return
    if r["status"] != "pending":
        await cb.answer("Уже обработан", show_alert=True)
        return

    await db.set_status(review_id, "rejected")

    try:
        await bot.send_message(
            r["user_id"],
            f"❌ К сожалению, ваш отзыв <b>#{review_id}</b> не был опубликован. "
            f"Если есть вопросы — {SUPPORT_URL}",
            parse_mode="HTML"
        )
    except Exception as e:
        print("notify user error:", e)

    try:
        await cb.message.edit_text(
            f"{cb.message.html_text}\n\n❌ Отклонён",
            parse_mode="HTML"
        )
    except Exception:
        pass


# ---------- ФОЛЛБЭК ----------
@dp.message()
async def fallback(msg: types.Message):
    await msg.answer("Используй /start, чтобы оставить отзыв.")


# ---------- ЗАПУСК ----------
async def main():
    await db.init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
