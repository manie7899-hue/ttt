"""
Telegram бот: Калькулятор + BIN Checker.
Команды: /start, /calc, /bin, /help
"""
import os
import re
import sys
from pathlib import Path
from typing import Optional

# Подключаем bin_checker
_root = Path(__file__).resolve().parent
sys.path.insert(0, str(_root / "bin_checker"))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bin_lookup import BinChecker


BIN_CHECKER = BinChecker(use_online=True)

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("🔢 Калькулятор"), KeyboardButton("💳 BIN Checker")],
        [KeyboardButton("❓ Помощь")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


def _calc_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("7", callback_data="calc_7"),
            InlineKeyboardButton("8", callback_data="calc_8"),
            InlineKeyboardButton("9", callback_data="calc_9"),
            InlineKeyboardButton("÷", callback_data="calc_/"),
        ],
        [
            InlineKeyboardButton("4", callback_data="calc_4"),
            InlineKeyboardButton("5", callback_data="calc_5"),
            InlineKeyboardButton("6", callback_data="calc_6"),
            InlineKeyboardButton("×", callback_data="calc_*"),
        ],
        [
            InlineKeyboardButton("1", callback_data="calc_1"),
            InlineKeyboardButton("2", callback_data="calc_2"),
            InlineKeyboardButton("3", callback_data="calc_3"),
            InlineKeyboardButton("−", callback_data="calc_-"),
        ],
        [
            InlineKeyboardButton("0", callback_data="calc_0"),
            InlineKeyboardButton(".", callback_data="calc_."),
            InlineKeyboardButton("=", callback_data="calc_="),
            InlineKeyboardButton("+", callback_data="calc_+"),
        ],
        [
            InlineKeyboardButton("⌫", callback_data="calc_back"),
            InlineKeyboardButton("C", callback_data="calc_C"),
        ],
    ])


def _safe_calc(expr: str) -> Optional[str]:
    clean = expr.replace("×", "*").replace("÷", "/").replace("−", "-")
    if not re.match(r'^[\d\+\-\*/\.\s]+$', clean):
        return None
    try:
        result = eval(clean)  # noqa: S307
        if isinstance(result, float):
            if result == int(result) and abs(result) < 1e15:
                return str(int(result))
            return f"{result:.10g}"
        return str(result)
    except Exception:
        return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Привет!\n\n"
        "🔢 Калькулятор — кнопка или /calc\n"
        "💳 BIN Checker — /bin 457105\n\n"
        "Или используй кнопки ниже 👇"
    )
    await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "/calc — калькулятор или кнопка 🔢\n"
        "/bin <6-8 цифр> — проверка BIN карты\n"
        "Пример: /bin 457105"
    )
    await update.message.reply_text(text)


async def calc_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.args and len(context.args) == 3:
        a_text, op, b_text = context.args
        try:
            a, b = float(a_text.replace(",", ".")), float(b_text.replace(",", "."))
            if op == "+": result = a + b
            elif op == "-": result = a - b
            elif op == "*": result = a * b
            elif op == "/": result = a / b if b != 0 else None
            else: result = None
            if result is not None:
                await update.message.reply_text(f"{a} {op} {b} = {result}")
                return
        except (ValueError, ZeroDivisionError):
            pass
    context.user_data["calc_expr"] = "0"
    await update.message.reply_text(
        "🔢 Калькулятор\n\n📟 0",
        reply_markup=_calc_keyboard(),
    )


async def bin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "Использование: /bin <6-8 цифр>\n"
            "Пример: /bin 457105\n"
            "Или несколько: /bin 457105 541275 411111"
        )
        return

    results = []
    for arg in context.args:
        bin_val = "".join(c for c in arg if c.isdigit())[:8]
        if len(bin_val) < 6:
            results.append(f"{arg} — минимум 6 цифр")
            continue
        info = BIN_CHECKER.lookup(bin_val)
        if info:
            results.append(
                f"BIN: {info.bin}\n"
                f"Scheme: {info.scheme.upper() or '—'}\n"
                f"Type: {info.card_type or '—'}\n"
                f"Country: {info.country or '—'}\n"
                f"Bank: {info.bank_name or '—'}"
            )
        else:
            results.append(f"{bin_val[:6]} — не найден")

    text = "\n\n".join(results)
    if len(text) > 4000:
        text = text[:3997] + "..."
    await update.message.reply_text(text)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    cb = (query.data or "").strip()
    await query.answer()

    if cb.startswith("calc_"):
        key = cb[5:]
        expr = context.user_data.get("calc_expr", "0")
        display_map = {"/": "÷", "*": "×", "-": "−"}

        if key == "C":
            expr = "0"
        elif key == "back":
            expr = expr[:-1] if len(expr) > 1 else "0"
        elif key == "=":
            result = _safe_calc(expr)
            expr = result if result is not None else "Ошибка"
        else:
            char = display_map.get(key, key)
            if expr == "0" and key.isdigit():
                expr = key
            elif expr == "Ошибка":
                expr = key if key.isdigit() or key == "." else "0"
            else:
                expr += char

        context.user_data["calc_expr"] = expr
        display = expr if len(expr) <= 30 else "…" + expr[-27:]
        try:
            await query.edit_message_text(
                f"🔢 Калькулятор\n\n📟 {display}",
                reply_markup=_calc_keyboard(),
            )
        except Exception:
            pass


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    if text.startswith("/"):
        return

    if text == "🔢 Калькулятор":
        context.user_data["calc_expr"] = "0"
        await update.message.reply_text(
            "🔢 Калькулятор\n\n📟 0",
            reply_markup=_calc_keyboard(),
        )
        return
    if text == "💳 BIN Checker":
        await update.message.reply_text(
            "Введите BIN (6–8 цифр) или используй /bin 457105"
        )
        return
    if text == "❓ Помощь":
        await help_command(update, context)
        return

    # Проверка: может это BIN?
    digits = "".join(c for c in text if c.isdigit())
    if len(digits) >= 6 and len(digits) <= 8 and len(text.strip()) <= 12:
        info = BIN_CHECKER.lookup(digits)
        if info:
            await update.message.reply_text(
                f"BIN: {info.bin}\n"
                f"Scheme: {info.scheme.upper() or '—'}\n"
                f"Type: {info.card_type or '—'}\n"
                f"Country: {info.country or '—'}\n"
                f"Bank: {info.bank_name or '—'}"
            )
            return


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Задайте TELEGRAM_BOT_TOKEN.")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("calc", calc_command))
    app.add_handler(CommandHandler("bin", bin_command))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^calc_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    print("Бот запущен.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
