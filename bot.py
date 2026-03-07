"""
Telegram бот: Калькулятор + BIN Checker.
Команды: /start, /calc, /bin, /help
"""
import asyncio
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


def _extract_bin(text: str) -> str | None:
    """Берёт только первые 6 цифр. Пробелы игнорируются. 4432 6440 1636 7695 -> 443264"""
    digits = "".join(c for c in text if c.isdigit())
    if len(digits) < 6:
        return None
    return digits[:6]


def _country_flag(code: str) -> str:
    """Флаг страны из кода US, DE, RU и т.д."""
    if not code or len(code) != 2:
        return "🌍"
    a, b = code.upper()[0], code.upper()[1]
    if "A" <= a <= "Z" and "A" <= b <= "Z":
        return chr(0x1F1E6 + ord(a) - ord("A")) + chr(0x1F1E6 + ord(b) - ord("A"))
    return "🌍"


SCHEME_EMOJI = {
    "visa": "💳", "mastercard": "💎", "master": "💎", "amex": "🃏",
    "maestro": "💵", "mir": "🔷", "unionpay": "🇨🇳", "discover": "🔍",
    "diners": "🍽", "jcb": "🇯🇵", "elo": "🃏",
}
TYPE_EMOJI = {"credit": "💳", "debit": "💵", "prepaid": "🎫", "charge": "⚡"}


def _format_bin_card(info) -> str:
    """Красивая карточка BIN с флагами и эмодзи"""
    scheme = (info.scheme or "").lower()
    scheme_emoji = SCHEME_EMOJI.get(scheme, "💳")
    scheme_display = (info.scheme or "—").upper()

    card_type = (info.card_type or "").lower()
    type_emoji = TYPE_EMOJI.get(card_type, "💳")
    type_display = (info.card_type or "—").capitalize()

    flag = _country_flag(info.country or "")
    country = info.country or "—"
    bank = info.bank_name or "—"

    return (
        f"{scheme_emoji} <b>BIN {info.bin}</b>\n"
        f"├ {scheme_emoji} Схема: {scheme_display}\n"
        f"├ {type_emoji} Тип: {type_display}\n"
        f"├ {flag} Страна: {country}\n"
        f"└ 🏦 Банк: {bank}"
    )


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
        "👋 <b>Привет!</b>\n\n"
        "🔢 <b>Калькулятор</b> — кнопка или /calc\n"
        "💳 <b>BIN Checker</b> — /bin 457105 или просто 4165 98\n\n"
        "👇 Используй кнопки ниже"
    )
    await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD, parse_mode="HTML")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🔢 <b>/calc</b> — калькулятор (кнопка)\n"
        "💳 <b>/bin</b> — проверка BIN карты\n\n"
        "BIN можно вводить с пробелами:\n"
        "• /bin 457105\n"
        "• /bin 4165 98\n"
        "• или просто: 4165 98"
    )
    await update.message.reply_text(text, parse_mode="HTML")


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
                await update.message.reply_text(f"🔢 {a} {op} {b} = <b>{result}</b>", parse_mode="HTML")
                return
        except (ValueError, ZeroDivisionError):
            pass
    context.user_data["calc_expr"] = "0"
    await update.message.reply_text(
        "🔢 Калькулятор\n\n📟 0",
        reply_markup=_calc_keyboard(),
    )


async def bin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raw = " ".join(context.args) if context.args else ""
    bin_val = _extract_bin(raw)
    if not bin_val:
        await update.message.reply_text(
            "💳 <b>BIN Checker</b>\n\n"
            "Введи минимум 6 цифр (пробелы игнорируются):\n"
            "• /bin 457105\n"
            "• /bin 4432 64",
            parse_mode="HTML",
        )
        return

    info = BIN_CHECKER.lookup(bin_val)
    if info:
        await update.message.reply_text(_format_bin_card(info), parse_mode="HTML")
    else:
        await update.message.reply_text(f"❌ <b>{bin_val}</b> — не найден 🔍", parse_mode="HTML")


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
            "💳 Введи BIN (6+ цифр). Пробелы можно: <code>4165 98</code>",
            parse_mode="HTML",
        )
        return
    if text == "❓ Помощь":
        await help_command(update, context)
        return

    # Проверка: может это BIN? (первые 6 цифр)
    bin_val = _extract_bin(text)
    if bin_val:
        clean = text.replace(" ", "").replace("-", "")
        if clean.isdigit() and len(clean) <= 24:
            info = BIN_CHECKER.lookup(bin_val)
            if info:
                await update.message.reply_text(
                    _format_bin_card(info),
                    parse_mode="HTML",
                )


async def _run_bot() -> None:
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

    async with app:
        await app.start()
        await app.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )
        print("Бот запущен.")
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await app.updater.stop()
            await app.stop()


def main() -> None:
    asyncio.run(_run_bot())


if __name__ == "__main__":
    main()
