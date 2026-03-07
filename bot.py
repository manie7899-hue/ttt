import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Set

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


API_URL = "https://cdn.moneyconvert.net/api/latest.json"
ADMINS_FILE = Path(__file__).resolve().parent / "admins.txt"
USERS_FILE = Path(__file__).resolve().parent / "users.txt"

# Оффлайн‑значения на случай недоступности API (примерные курсы к USD)
FALLBACK_RATES: Dict[str, float] = {
    "AED": 3.67, "AFN": 72.0, "ALL": 95.0, "AMD": 405.0, "ANG": 1.79, "AOA": 930.0,
    "ARS": 1100.0, "AUD": 1.52, "AWG": 1.79, "AZN": 1.70, "BAM": 1.68, "BBD": 2.0,
    "BDT": 117.0, "BGN": 1.68, "BHD": 0.376, "BIF": 2850.0, "BMD": 1.0, "BND": 1.34,
    "BOB": 6.91, "BRL": 5.25, "BSD": 1.0, "BTN": 83.0, "BWP": 13.5, "BYN": 3.25,
    "BZD": 2.0, "CAD": 1.36, "CDF": 2750.0, "CHF": 0.88, "CLP": 950.0, "CNY": 7.24,
    "COP": 3950.0, "CRC": 530.0, "CUP": 24.0, "CVE": 102.0, "CZK": 22.5, "DJF": 178.0,
    "DKK": 6.9, "DOP": 58.0, "DZD": 134.0, "EGP": 49.0, "ERN": 15.0, "ETB": 56.0,
    "EUR": 0.92, "FJD": 2.25, "FKP": 0.79, "FOK": 6.9, "GBP": 0.79, "GEL": 2.65,
    "GGP": 0.79, "GHS": 12.5, "GIP": 0.79, "GMD": 67.0, "GNF": 8600.0, "GTQ": 7.85,
    "GYD": 209.0, "HKD": 7.82, "HNL": 24.7, "HRK": 6.95, "HTG": 132.0, "HUF": 355.0,
    "IDR": 15700.0, "ILS": 3.68, "IMP": 0.79, "INR": 83.0, "IQD": 1310.0, "IRR": 42000.0,
    "ISK": 138.0, "JEP": 0.79, "JMD": 155.0, "JOD": 0.709, "JPY": 149.0, "KES": 129.0,
    "KGS": 89.0, "KHR": 4100.0, "KID": 1.52, "KMF": 453.0, "KRW": 1320.0, "KWD": 0.307,
    "KYD": 0.833, "KZT": 450.0, "LAK": 20500.0, "LBP": 89500.0, "LKR": 325.0, "LRD": 192.0,
    "LSL": 18.5, "LYD": 4.85, "MAD": 10.0, "MDL": 17.8, "MGA": 4500.0, "MKD": 56.0,
    "MMK": 2100.0, "MNT": 3450.0, "MOP": 8.05, "MRU": 40.0, "MUR": 45.0, "MVR": 15.4,
    "MWK": 1750.0, "MXN": 17.1, "MYR": 4.72, "MZN": 63.8, "NAD": 18.5, "NGN": 1550.0,
    "NIO": 36.5, "NOK": 10.8, "NPR": 133.0, "NZD": 1.64, "OMR": 0.385, "PAB": 1.0,
    "PEN": 3.75, "PGK": 3.75, "PHP": 56.0, "PKR": 278.0, "PLN": 3.95, "PYG": 7280.0,
    "QAR": 3.64, "RON": 4.55, "RSD": 108.0, "RUB": 92.0, "RWF": 1280.0, "SAR": 3.75,
    "SBD": 8.45, "SCR": 13.5, "SDG": 600.0, "SEK": 10.4, "SGD": 1.34, "SHP": 0.79,
    "SLE": 22.0, "SOS": 571.0, "SRD": 32.0, "SSP": 1300.0, "STN": 22.5, "SYP": 13000.0,
    "SZL": 18.5, "THB": 35.5, "TJS": 10.9, "TMT": 3.5, "TND": 3.1, "TOP": 2.35,
    "TRY": 32.0, "TTD": 6.78, "TWD": 31.5, "TZS": 2580.0, "UAH": 41.0, "UGX": 3780.0,
    "UYU": 39.0, "UZS": 12400.0, "VES": 36.0, "VND": 24500.0, "VUV": 119.0,
    "WST": 2.75, "XAF": 605.0, "XCD": 2.7, "XOF": 605.0, "XPF": 110.0, "YER": 250.0,
    "ZAR": 18.5, "ZMW": 27.0, "ZWL": 5800.0,
    # Крипта
    "BTC": 0.000023, "ETH": 0.00042, "DOGE": 8.5,
}

RATES: Dict[str, float] = dict(FALLBACK_RATES)
LAST_RATES_UPDATE: Optional[datetime] = None

# Множество ID админов (загружается из файла и env)
ADMIN_IDS: Set[int] = set()
# ID пользователей, которые когда-либо писали /start
USER_IDS: Set[int] = set()


# ---------- Админка ----------

def _load_admins() -> None:
    """Загружает список админов из файла и из переменной окружения TELEGRAM_ADMIN_IDS."""
    global ADMIN_IDS
    ADMIN_IDS = set()
    # Сначала из env (через запятую)
    env_ids = os.getenv("TELEGRAM_ADMIN_IDS", "").strip()
    if env_ids:
        for s in env_ids.split(","):
            s = s.strip()
            if s.isdigit():
                ADMIN_IDS.add(int(s))
    # Затем из файла
    if ADMINS_FILE.exists():
        with open(ADMINS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.isdigit():
                    ADMIN_IDS.add(int(line))
    # Если никого нет — сохраняем пустой файл
    if not ADMIN_IDS and env_ids:
        _save_admins()


def _save_admins() -> None:
    """Сохраняет список админов в файл."""
    with open(ADMINS_FILE, "w", encoding="utf-8") as f:
        for uid in sorted(ADMIN_IDS):
            f.write(f"{uid}\n")


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def _load_users() -> None:
    """Загружает список пользователей (кто писал /start) из файла."""
    global USER_IDS
    USER_IDS = set()
    if USERS_FILE.exists():
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.isdigit():
                    USER_IDS.add(int(line))


def _save_users() -> None:
    """Сохраняет список пользователей в файл."""
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        for uid in sorted(USER_IDS):
            f.write(f"{uid}\n")


def _add_user(user_id: int) -> None:
    """Добавляет пользователя в список (если ещё нет) и сохраняет."""
    if user_id not in USER_IDS:
        USER_IDS.add(user_id)
        _save_users()


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /admin — админ-панель (только для админов)."""
    user_id = update.effective_user.id if update.effective_user else 0
    if not _is_admin(user_id):
        await update.message.reply_text("Доступ запрещён. Нужен статус Админ.")
        return
    text = (
        "👑 Админ-панель\n\n"
        "Команды:\n"
        "/addadmin <user_id> — выдать статус Админ\n"
        "/listadmins — список админов\n"
        "/removeadmin <user_id> — забрать статус админа\n"
        "/all — рассылка всем, кто писал /start"
    )
    keyboard = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton("📢 Рассылка", callback_data="broadcast_start")
    )
    await update.message.reply_text(text, reply_markup=keyboard)


async def addadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /addadmin <user_id> — добавить админа (только для админов)."""
    user_id = update.effective_user.id if update.effective_user else 0
    if not _is_admin(user_id):
        await update.message.reply_text("Доступ запрещён. Нужен статус Админ.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Использование: /addadmin <user_id>\nПример: /addadmin 123456789")
        return
    try:
        new_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("user_id должен быть числом.")
        return
    ADMIN_IDS.add(new_id)
    _save_admins()
    await update.message.reply_text(f"Пользователь {new_id} получил статус Админ и доступ к админ-панели.")


async def listadmins_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /listadmins — список админов (только для админов)."""
    user_id = update.effective_user.id if update.effective_user else 0
    if not _is_admin(user_id):
        await update.message.reply_text("Доступ запрещён. Нужен статус Админ.")
        return
    if not ADMIN_IDS:
        await update.message.reply_text("Список админов пуст.")
        return
    lines = ["Список админов (user_id):"] + [str(uid) for uid in sorted(ADMIN_IDS)]
    await update.message.reply_text("\n".join(lines))


async def removeadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /removeadmin <user_id> — убрать админа (только для админов)."""
    user_id = update.effective_user.id if update.effective_user else 0
    if not _is_admin(user_id):
        await update.message.reply_text("Доступ запрещён. Нужен статус Админ.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("Использование: /removeadmin <user_id>")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("user_id должен быть числом.")
        return
    if target_id not in ADMIN_IDS:
        await update.message.reply_text("Этот пользователь не в списке админов.")
        return
    if len(ADMIN_IDS) == 1:
        await update.message.reply_text("Нельзя удалить последнего админа.")
        return
    ADMIN_IDS.discard(target_id)
    _save_admins()
    await update.message.reply_text(f"Пользователь {target_id} больше не админ.")


async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /all — запуск рассылки (только для админов)."""
    user_id = update.effective_user.id if update.effective_user else 0
    if not _is_admin(user_id):
        await update.message.reply_text("Доступ запрещён. Нужен статус Админ.")
        return
    context.user_data["awaiting_broadcast"] = True
    await update.message.reply_text("Отправьте текст рассылки. Он будет отправлен всем, кто писал /start.")


async def broadcast_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Кнопка «Рассылка» — запуск рассылки."""
    query = update.callback_query
    if not query:
        return
    user_id = update.effective_user.id if update.effective_user else 0
    if not _is_admin(user_id):
        await query.answer("Доступ запрещён.", show_alert=True)
        return
    await query.answer()
    context.user_data["awaiting_broadcast"] = True
    await query.edit_message_text("Отправьте текст рассылки. Он будет отправлен всем, кто писал /start.")


async def broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает текст рассылки от админа (когда awaiting_broadcast)."""
    if not update.message or not update.message.text:
        return
    user_id = update.effective_user.id if update.effective_user else 0
    if not _is_admin(user_id):
        return
    if not context.user_data.pop("awaiting_broadcast", False):
        return
    text = update.message.text
    # Рассылаем всем, кроме админов (чтобы админы не получали дубли)
    targets = USER_IDS - ADMIN_IDS
    sent = 0
    failed = 0
    for uid in targets:
        try:
            await context.bot.send_message(chat_id=uid, text=text)
            sent += 1
        except Exception:
            failed += 1
    report = (
        f"📢 Рассылка завершена\n\n"
        f"✅ Получили: {sent}\n"
        f"❌ Не доставлено: {failed}\n"
        f"📊 Всего в базе: {len(USER_IDS)}"
    )
    await update.message.reply_text(report)


# ---------- Курсы и калькулятор ----------

# Флаг и символ валюты для красивого вывода
CODE_META: Dict[str, str] = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧", "PLN": "🇵🇱", "UAH": "🇺🇦",
    "RUB": "🇷🇺", "BYN": "🇧🇾", "KZT": "🇰🇿", "BAM": "🇧🇦",
}
CURRENCY_SYMBOLS: Dict[str, str] = {
    "USD": "$", "EUR": "€", "GBP": "£", "PLN": "zł", "UAH": "₴",
    "RUB": "₽", "BYN": "Br", "KZT": "₸", "BAM": "KM",
}
# Обратный маппинг: символ/название -> код валюты
SYMBOL_TO_CODE: Dict[str, str] = {
    "$": "USD", "€": "EUR", "£": "GBP", "₴": "UAH", "₽": "RUB",
    "₸": "KZT", "zł": "PLN", "zl": "PLN", "Br": "BYN", "KM": "BAM",
    # Русские названия
    "доллар": "USD", "долларов": "USD", "доллара": "USD", "dollar": "USD", "dollars": "USD",
    "евро": "EUR", "euro": "EUR", "euros": "EUR",
    "фунт": "GBP", "фунтов": "GBP", "pound": "GBP", "pounds": "GBP",
    "рубль": "RUB", "рублей": "RUB", "рубля": "RUB", "ruble": "RUB", "rubles": "RUB",
    "гривна": "UAH", "гривен": "UAH", "гривны": "UAH", "hryvnia": "UAH",
    "злотый": "PLN", "злотых": "PLN", "zloty": "PLN",
}

RATES_TARGETS = ["EUR", "GBP", "PLN", "UAH", "USD"]


def _resolve_currency(code_or_symbol: str) -> Optional[str]:
    """Преобразует символ ($, €), название (доллар) или код (USD) в код валюты."""
    s = code_or_symbol.strip()
    if not s:
        return None
    # Символ или название (без учёта регистра)
    s_lower = s.lower()
    if s_lower in SYMBOL_TO_CODE:
        return SYMBOL_TO_CODE[s_lower]
    if s in SYMBOL_TO_CODE:
        return SYMBOL_TO_CODE[s]
    # Код валюты
    code = s.upper()
    if code in RATES or code in FALLBACK_RATES:
        return code
    return None


def _calculate(a: float, b: float, op: str) -> float:
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        if b == 0:
            raise ZeroDivisionError("division by zero")
        return a / b
    raise ValueError("unknown operation")


def _fetch_live_rates() -> None:
    global RATES, LAST_RATES_UPDATE
    try:
        response = requests.get(API_URL, timeout=8)
        response.raise_for_status()
        data = response.json()
        api_rates = data.get("rates", {})
        if not api_rates:
            raise ValueError("empty rates in API response")
        new_rates: Dict[str, float] = {}
        for code, value in api_rates.items():
            try:
                new_rates[code] = float(value)
            except (TypeError, ValueError):
                continue
        if not new_rates:
            raise ValueError("could not parse any rates")
        # API часто возвращает курсы с базой USD и не включает USD в rates — добавляем
        new_rates.setdefault("USD", 1.0)
        RATES = new_rates
        ts = data.get("ts")
        if isinstance(ts, str):
            try:
                LAST_RATES_UPDATE = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                LAST_RATES_UPDATE = None
    except Exception:
        if not RATES:
            RATES = dict(FALLBACK_RATES)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is not None:
        _add_user(user_id)
    text = (
        "Всем салам от братвы\n\n"
        "Напиши сумму и валюту:\n"
        "• 500 BAM или 500 $\n"
        "• 100 €, 50 £, 1000 ₴\n\n"
        "Команды: /calc, /convert, /rates, /help\n"
        "Админам: /admin — админ-панель"
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "/calc <a> <операция> <b> — калькулятор\n"
        "/convert <сумма> <из> <в> — конвертер\n"
        "/rates <сумма> <валюта> — курсы\n\n"
        "Или просто: 500 BAM, 100 $, 50 €, 1000 ₴"
    )
    await update.message.reply_text(text)


async def calc_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 3:
        await update.message.reply_text("Использование: /calc <a> <операция> <b>\nПример: /calc 2 + 3")
        return
    a_text, op, b_text = context.args
    try:
        a = float(a_text.replace(",", "."))
        b = float(b_text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Ошибка: a и b должны быть числами.")
        return
    try:
        result = _calculate(a, b, op)
    except ZeroDivisionError:
        await update.message.reply_text("Ошибка: деление на ноль.")
        return
    except ValueError:
        await update.message.reply_text("Ошибка: неизвестная операция. Используйте +, -, *, /.")
        return
    await update.message.reply_text(f"{a} {op} {b} = {result}")


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
    from_curr = from_curr.upper()
    to_curr = to_curr.upper()
    _fetch_live_rates()
    if from_curr not in RATES or to_curr not in RATES:
        await update.message.reply_text("Неизвестная валюта. Примеры: USD, EUR, RUB и т.д.")
        return
    from_rate = RATES[from_curr]
    to_rate = RATES[to_curr]
    try:
        amount_in_usd = amount / from_rate
        result = amount_in_usd * to_rate
    except ZeroDivisionError:
        await update.message.reply_text("Ошибка: некорректные курсы валют.")
        return
    time_part = ""
    if LAST_RATES_UPDATE is not None:
        time_part = " (обновлено " + LAST_RATES_UPDATE.strftime("%d.%m.%Y %H:%M") + " по UTC)"
    await update.message.reply_text(f"{amount:.2f} {from_curr} = {result:.2f} {to_curr}{time_part}")


def _format_amount(value: float, decimals: int = 2) -> str:
    fmt = f"{{:,.{decimals}f}}".format(value)
    return fmt.replace(",", " ")


def _code_to_label(code: str) -> str:
    flag = CODE_META.get(code)
    return f"{flag} {code}" if flag else code


def _get_display(code: str, amount: float) -> str:
    """Формат: флаг + сумма + символ (например: 🇪🇺 431.45 €)."""
    flag = CODE_META.get(code, "")
    symbol = CURRENCY_SYMBOLS.get(code, code)
    return f"{flag} {_format_amount(amount, 2)} {symbol}" if flag else f"{amount:.2f} {code}"


async def _handle_rates(update: Update, amount_text: str, base_code: str) -> None:
    try:
        amount = float(amount_text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Ошибка: сумма должна быть числом.")
        return
    base_code = base_code.upper()
    _fetch_live_rates()
    if base_code not in RATES:
        await update.message.reply_text("Неизвестная валюта. Примеры: USD, EUR, RUB, BAM и т.д.")
        return
    base_rate = RATES[base_code]
    try:
        amount_in_usd = amount / base_rate
    except ZeroDivisionError:
        await update.message.reply_text("Ошибка: некорректные курсы валют.")
        return
    lines: list[str] = []
    # Первая строка: базовая валюта (флаг + сумма + символ =)
    base_display = _get_display(base_code, amount)
    lines.append(f"{base_display} =")
    # Целевые валюты с отступом
    for code in RATES_TARGETS:
        if code == base_code:
            continue
        if code not in RATES:
            continue
        target_rate = RATES[code]
        try:
            converted = amount_in_usd * target_rate
        except ZeroDivisionError:
            continue
        lines.append(f" {_get_display(code, converted)}")
    time_part = ""
    if LAST_RATES_UPDATE is not None:
        time_part = "\n\nКурсы обновлены " + LAST_RATES_UPDATE.strftime("%d.%m.%Y %H:%M") + " по UTC"
    footer = "\n\nUltra БАТЯ ЕБЕТ МАМАШ ВАШИХ"
    body = "\n".join(lines) + time_part + footer
    await update.message.reply_text(body)


async def rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 2:
        await update.message.reply_text(
            "Использование: /rates <сумма> <валюта>\n"
            "Примеры: /rates 500 BAM, /rates 100 $, /rates 50 €"
        )
        return
    amount_text, code_or_symbol = context.args
    base_code = _resolve_currency(code_or_symbol)
    if not base_code:
        await update.message.reply_text("Неизвестная валюта. Используйте код (USD, EUR) или символ ($, €, £).")
        return
    await _handle_rates(update, amount_text, base_code)


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    # Сначала проверяем рассылку (админ отправил текст для broadcast)
    user_id = update.effective_user.id if update.effective_user else 0
    if _is_admin(user_id) and context.user_data.get("awaiting_broadcast"):
        await broadcast_message_handler(update, context)
        return
    text = update.message.text.strip()
    if text.startswith("/"):
        return
    parts = text.split()
    if len(parts) == 2:
        amount_text, code_or_symbol = parts
        base_code = _resolve_currency(code_or_symbol)
        if base_code:
            await _handle_rates(update, amount_text, base_code)
            return
    if len(parts) == 1:
        # Формат без пробела: "500$", "100€", "50£"
        s = text.strip()
        for sym in sorted(SYMBOL_TO_CODE.keys(), key=len, reverse=True):
            if s.endswith(sym):
                amount_text = s[: -len(sym)].strip()
                try:
                    float(amount_text.replace(",", "."))
                    await _handle_rates(update, amount_text, SYMBOL_TO_CODE[sym])
                    return
                except ValueError:
                    break
    # Продублировать сообщение (только для не-админов)
    if not _is_admin(user_id):
        await update.message.reply_text(text)


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "8649012078:AAGPGx8UZkS7sSIGOzGDoAcpYPOKf9ENkc8")
    if not token:
        raise RuntimeError("Задайте переменную окружения TELEGRAM_BOT_TOKEN.")
    _load_admins()
    _load_users()
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("calc", calc_command))
    app.add_handler(CommandHandler("convert", convert_command))
    app.add_handler(CommandHandler("rates", rates_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("all", all_command))
    app.add_handler(CommandHandler("addadmin", addadmin_command))
    app.add_handler(CommandHandler("listadmins", listadmins_command))
    app.add_handler(CommandHandler("removeadmin", removeadmin_command))
    app.add_handler(CallbackQueryHandler(broadcast_start_callback, pattern="^broadcast_start$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    print("Бот запущен. Нажмите Ctrl+C для остановки.")
    app.run_polling()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Ошибка: {e}")
        input("Нажмите Enter для выхода...")
