"""
Telegram бот: Калькулятор + BIN Checker + Конвертер валют.
Команды: /start, /calc, /bin, /rates, /convert, /help
"""
import asyncio
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests

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

# === Конвертер валют ===
GOOGLE_FINANCE_URL = "https://www.google.com/finance/quote/USD-{code}"
API_URL = "https://cdn.moneyconvert.net/api/latest.json"
API_FALLBACK_URL = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json"
RATES_CACHE_TTL = 300
GOOGLE_CURRENCIES = ["EUR", "GBP", "PLN", "UAH", "BAM", "RUB", "BYN", "KZT", "CHF", "JPY", "TRY", "CNY", "CAD", "AUD"]

FALLBACK_RATES: Dict[str, float] = {
    "USD": 1.0, "EUR": 0.86, "GBP": 0.75, "PLN": 3.68, "UAH": 43.8, "BAM": 1.68,
    "RUB": 79.1, "BYN": 2.94, "KZT": 494, "CHF": 0.78, "JPY": 157.8, "TRY": 44,
    "CNY": 6.9, "CAD": 1.36, "AUD": 1.42,
}

RATES: Dict[str, float] = dict(FALLBACK_RATES)
LAST_RATES_UPDATE: Optional[datetime] = None
RATES_SOURCE: str = "fallback"
RATES_TARGETS = ["EUR", "GBP", "PLN", "UAH", "USD"]

CODE_META: Dict[str, str] = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "PLN": "🇵🇱", "UAH": "🇺🇦",
    "RUB": "🇷🇺", "BYN": "🇧🇾", "KZT": "🇰🇿", "BAM": "🇧🇦",
}
CURRENCY_SYMBOLS: Dict[str, str] = {
    "USD": "$", "EUR": "€", "GBP": "£", "PLN": "zł", "UAH": "₴",
    "RUB": "₽", "BYN": "Br", "KZT": "₸", "BAM": "KM",
}
SYMBOL_TO_CODE: Dict[str, str] = {
    "$": "USD", "€": "EUR", "£": "GBP", "₴": "UAH", "₽": "RUB",
    "₸": "KZT", "zł": "PLN", "zl": "PLN", "Br": "BYN", "KM": "BAM",
    "доллар": "USD", "долларов": "USD", "бакс": "USD", "баксы": "USD",
    "евро": "EUR", "euro": "EUR", "фунт": "GBP", "pound": "GBP",
    "рубль": "RUB", "рублей": "RUB", "гривна": "UAH", "грн": "UAH",
    "злотый": "PLN", "марка": "BAM", "марок": "BAM",
}

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("💱 Курсы"), KeyboardButton("🔢 Калькулятор")],
        [KeyboardButton("💳 BIN Checker"), KeyboardButton("❓ Помощь")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

RATES_BUTTONS = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("100$", callback_data="rates_100_USD"),
        InlineKeyboardButton("500$", callback_data="rates_500_USD"),
        InlineKeyboardButton("1000$", callback_data="rates_1000_USD"),
    ],
    [
        InlineKeyboardButton("100€", callback_data="rates_100_EUR"),
        InlineKeyboardButton("500€", callback_data="rates_500_EUR"),
        InlineKeyboardButton("100 BAM", callback_data="rates_100_BAM"),
    ],
    [
        InlineKeyboardButton("500 BAM", callback_data="rates_500_BAM"),
        InlineKeyboardButton("1000₴", callback_data="rates_1000_UAH"),
        InlineKeyboardButton("1000₽", callback_data="rates_1000_RUB"),
    ],
])


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


def _resolve_currency(code_or_symbol: str) -> Optional[str]:
    s = "".join(c for c in code_or_symbol if ord(c) > 32 and c not in "\u200b\u200c\u200d\ufeff").strip()
    if not s:
        return None
    s_lower = s.lower()
    if s_lower in SYMBOL_TO_CODE:
        return SYMBOL_TO_CODE[s_lower]
    if s in SYMBOL_TO_CODE:
        return SYMBOL_TO_CODE[s]
    code = s.upper()
    if code in RATES or code in FALLBACK_RATES:
        return code
    return None


def _fetch_google_rates() -> Optional[Dict[str, float]]:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0", "Accept-Language": "en-US,en;q=0.9"}
    rates: Dict[str, float] = {"USD": 1.0}
    for code in GOOGLE_CURRENCIES:
        try:
            url = GOOGLE_FINANCE_URL.format(code=code)
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            m = re.search(r'YMlKec fxKbKc">(\d+\.\d+)<', resp.text) or re.search(r'data-last-price="(\d+\.\d+)"', resp.text)
            if m:
                rates[code] = float(m.group(1))
        except Exception:
            continue
    return rates if len(rates) >= 3 else None


def _fetch_live_rates() -> None:
    global RATES, LAST_RATES_UPDATE, RATES_SOURCE
    if LAST_RATES_UPDATE and (datetime.now(timezone.utc) - LAST_RATES_UPDATE).total_seconds() < RATES_CACHE_TTL:
        return
    google_rates = _fetch_google_rates()
    if google_rates and len(google_rates) >= 5:
        RATES = {**dict(FALLBACK_RATES), **google_rates}
        LAST_RATES_UPDATE = datetime.now(timezone.utc)
        RATES_SOURCE = "google"
        return
    for url, parse_fn in [
        (API_URL, lambda d: (d.get("rates", {}), d.get("ts"))),
        (API_FALLBACK_URL, lambda d: (
            {k.upper(): float(v) for k, v in (d.get("usd") or {}).items() if isinstance(v, (int, float))},
            d.get("date"),
        )),
    ]:
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            api_rates, ts_raw = parse_fn(data)
            if not api_rates:
                raise ValueError("empty")
            new_rates = {k.upper() if isinstance(k, str) else k: float(v) for k, v in api_rates.items() if isinstance(v, (int, float))}
            if new_rates:
                new_rates.setdefault("USD", 1.0)
                RATES = new_rates
                RATES_SOURCE = "api"
                LAST_RATES_UPDATE = datetime.now(timezone.utc)
                return
        except Exception:
            continue
    RATES = dict(FALLBACK_RATES)
    LAST_RATES_UPDATE = datetime.now(timezone.utc)


def _format_amount(value: float, decimals: int = 2) -> str:
    return f"{value:,.{decimals}f}".replace(",", " ")


def _get_display(code: str, amount: float) -> str:
    flag = CODE_META.get(code, "")
    symbol = CURRENCY_SYMBOLS.get(code, code)
    return f"{flag} {_format_amount(amount, 2)} {symbol}" if flag else f"{amount:.2f} {code}"


async def _handle_rates(update: Update, context: ContextTypes.DEFAULT_TYPE, amount_text: str, base_code: str, reply_message=None) -> None:
    msg = reply_message or (update.message if update else None)
    if not msg:
        return
    try:
        amount = float(amount_text.replace(",", "."))
    except ValueError:
        await msg.reply_text("Ошибка: сумма должна быть числом.")
        return
    base_code = base_code.upper()
    await asyncio.get_running_loop().run_in_executor(None, _fetch_live_rates)
    if base_code not in RATES:
        await msg.reply_text("Неизвестная валюта. Примеры: USD, EUR, RUB, BAM.")
        return
    base_rate = RATES[base_code]
    try:
        amount_in_usd = amount / base_rate
    except ZeroDivisionError:
        await msg.reply_text("Ошибка: некорректные курсы.")
        return
    lines = [f"{_get_display(base_code, amount)} ="]
    for code in RATES_TARGETS:
        if code == base_code or code not in RATES:
            continue
        try:
            converted = amount_in_usd * RATES[code]
            lines.append(f" {_get_display(code, converted)}")
        except ZeroDivisionError:
            continue
    src = " (Google)" if RATES_SOURCE == "google" else ""
    time_part = f"\n\n🕐 Курсы{src}, {LAST_RATES_UPDATE.strftime('%d.%m.%Y %H:%M')} UTC" if LAST_RATES_UPDATE else "\n\n⚠️ Курсы оффлайн"
    body = "\n".join(lines) + time_part
    chat_id = msg.chat.id if msg else update.effective_chat.id
    await context.bot.send_message(chat_id=chat_id, text=body)


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
        "💱 <b>Курсы</b> — 500 BAM, 100 $, /rates\n"
        "🔢 <b>Калькулятор</b> — /calc\n"
        "💳 <b>BIN Checker</b> — /bin 457105\n\n"
        "👇 Используй кнопки ниже"
    )
    await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD, parse_mode="HTML")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "💱 <b>/rates</b> &lt;сумма&gt; &lt;валюта&gt; — курсы\n"
        "💱 <b>/convert</b> &lt;сумма&gt; &lt;из&gt; &lt;в&gt; — конвертер\n"
        "🔢 <b>/calc</b> — калькулятор\n"
        "💳 <b>/bin</b> — проверка BIN\n\n"
        "Или просто: 500 BAM, 100 $"
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


async def rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 2:
        await update.message.reply_text("Использование: /rates <сумма> <валюта>\nПримеры: /rates 500 BAM, /rates 100 $")
        return
    amount_text, code_or_symbol = context.args
    base_code = _resolve_currency(code_or_symbol)
    if not base_code:
        await update.message.reply_text("Неизвестная валюта.")
        return
    await _handle_rates(update, context, amount_text, base_code)


async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 3:
        await update.message.reply_text("Использование: /convert <сумма> <из> <в>\nПример: /convert 100 USD RUB")
        return
    amount_text, from_curr, to_curr = context.args
    try:
        amount = float(amount_text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Ошибка: сумма должна быть числом.")
        return
    from_curr = _resolve_currency(from_curr) or from_curr.upper()
    to_curr = _resolve_currency(to_curr) or to_curr.upper()
    await asyncio.get_running_loop().run_in_executor(None, _fetch_live_rates)
    if from_curr not in RATES or to_curr not in RATES:
        await update.message.reply_text("Неизвестная валюта. Примеры: USD, EUR, RUB.")
        return
    try:
        result = amount / RATES[from_curr] * RATES[to_curr]
    except ZeroDivisionError:
        await update.message.reply_text("Ошибка: некорректные курсы.")
        return
    time_part = f" (🕐 {LAST_RATES_UPDATE.strftime('%d.%m.%Y %H:%M')} UTC)" if LAST_RATES_UPDATE else ""
    await update.message.reply_text(f"{amount:.2f} {from_curr} = {result:.2f} {to_curr}{time_part}")


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

    if cb.startswith("rates_"):
        parts = cb.split("_")
        if len(parts) >= 3:
            amount_text, base_code = parts[1], parts[2]
            await _handle_rates(update, context, amount_text, base_code, reply_message=query.message)


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    if text.startswith("/"):
        return

    if text == "💱 Курсы":
        await update.message.reply_text("Выбери сумму и валюту:", reply_markup=RATES_BUTTONS)
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

    # Проверка: валюта (500 BAM, 100 $, 1000₴)
    parts = [p.strip() for p in text.split()]
    if len(parts) == 2:
        a, b = parts
        base_code = _resolve_currency(b)
        if base_code:
            try:
                float(a.replace(",", "."))
                await _handle_rates(update, context, a, base_code)
                return
            except ValueError:
                pass
        base_code = _resolve_currency(a)
        if base_code:
            try:
                float(b.replace(",", "."))
                await _handle_rates(update, context, b, base_code)
                return
            except ValueError:
                pass
    if len(parts) == 1:
        s = text.strip()
        for sym in sorted(SYMBOL_TO_CODE.keys(), key=len, reverse=True):
            if s.endswith(sym):
                amount_text = s[:-len(sym)].strip()
                try:
                    float(amount_text.replace(",", "."))
                    await _handle_rates(update, context, amount_text, SYMBOL_TO_CODE[sym])
                    return
                except ValueError:
                    break

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
    app.add_handler(CommandHandler("rates", rates_command))
    app.add_handler(CommandHandler("convert", convert_command))
    app.add_handler(CommandHandler("bin", bin_command))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^(calc_|rates_)"))
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
