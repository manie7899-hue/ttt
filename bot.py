import os
import re
from datetime import datetime, timezone
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


GOOGLE_FINANCE_URL = "https://www.google.com/finance/quote/USD-{code}"
API_URL = "https://cdn.moneyconvert.net/api/latest.json"
API_FALLBACK_URL = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json"

# Валюты, которые загружаем с Google Finance (курсы как в Google)
GOOGLE_CURRENCIES = ["EUR", "GBP", "PLN", "UAH", "BAM", "RUB", "BYN", "KZT", "CHF", "JPY", "TRY", "CNY", "CAD", "AUD"]
ADMINS_FILE = Path(__file__).resolve().parent / "admins.txt"
USERS_FILE = Path(__file__).resolve().parent / "users.txt"

# Оффлайн‑значения (актуальные курсы к USD, как в Google — март 2025)
FALLBACK_RATES: Dict[str, float] = {
    "AED": 3.6725, "AFN": 63.43, "ALL": 82.69, "AMD": 377.36, "ANG": 1.797, "AOA": 929.28,
    "ARS": 1417.0, "AUD": 1.422, "AWG": 1.79, "AZN": 1.701, "BAM": 1.6834, "BBD": 2.0,
    "BDT": 122.44, "BGN": 1.6834, "BHD": 0.376, "BIF": 2967.0, "BMD": 1.0, "BND": 1.279,
    "BOB": 6.908, "BRL": 5.258, "BSD": 1.0, "BTN": 91.96, "BWP": 13.52, "BYN": 2.935,
    "BZD": 2.015, "CAD": 1.357, "CDF": 2214.0, "CHF": 0.777, "CLP": 911.8, "CNY": 6.902,
    "COP": 3776.0, "CRC": 477.6, "CUP": 23.87, "CVE": 94.91, "CZK": 20.99, "DJF": 177.65,
    "DKK": 6.438, "DOP": 60.2, "DZD": 131.4, "EGP": 50.27, "ERN": 15.0, "ETB": 156.1,
    "EUR": 0.8607, "FJD": 2.21, "FKP": 0.746, "FOK": 6.438, "GBP": 0.746, "GEL": 2.729,
    "GGP": 0.746, "GHS": 10.77, "GIP": 0.746, "GMD": 73.67, "GNF": 8774.0, "GTQ": 7.665,
    "GYD": 209.1, "HKD": 7.822, "HNL": 26.53, "HRK": 6.485, "HTG": 131.9, "HUF": 337.8,
    "IDR": 16915.0, "ILS": 3.09, "IMP": 0.746, "INR": 91.96, "IQD": 1310.3, "IRR": 1318642.0,
    "ISK": 124.9, "JEP": 0.746, "JMD": 156.3, "JOD": 0.709, "JPY": 157.77, "KES": 129.2,
    "KGS": 87.45, "KHR": 4008.0, "KMF": 423.4, "KRW": 1480.3, "KWD": 0.3074,
    "KYD": 0.821, "KZT": 494.0, "LAK": 21370.0, "LBP": 89370.0, "LKR": 311.0, "LRD": 183.0,
    "LSL": 16.56, "LYD": 6.349, "MAD": 9.304, "MDL": 17.23, "MGA": 4174.0, "MKD": 53.03,
    "MMK": 2100.1, "MNT": 3569.0, "MOP": 8.057, "MRU": 40.01, "MUR": 47.38, "MVR": 15.46,
    "MWK": 1735.1, "MXN": 17.79, "MYR": 3.946, "MZN": 63.78, "NAD": 16.56, "NGN": 1391.4,
    "NIO": 36.66, "NOK": 9.585, "NPR": 147.2, "NZD": 1.696, "OMR": 0.3852, "PAB": 1.0,
    "PEN": 3.481, "PGK": 4.295, "PHP": 59.05, "PKR": 279.6, "PLN": 3.675, "PYG": 6541.0,
    "QAR": 3.64, "RON": 4.384, "RSD": 100.99, "RUB": 79.095, "RWF": 1458.0, "SAR": 3.75,
    "SBD": 8.046, "SCR": 14.71, "SDG": 600.2, "SEK": 9.182, "SGD": 1.279, "SHP": 0.746,
    "SLE": 24.39, "SOS": 571.2, "SRD": 37.70, "SSP": 4537.0, "STN": 21.27, "SYP": 110.62,
    "SZL": 16.56, "THB": 31.78, "TJS": 9.585, "TMT": 3.502, "TND": 2.909, "TOP": 2.371,
    "TRY": 44.05, "TTD": 6.727, "TWD": 31.82, "TZS": 2568.0, "UAH": 43.81, "UGX": 3679.3,
    "UYU": 40.16, "UZS": 12190.0, "VES": 431.9, "VND": 26196.0, "VUV": 118.9,
    "WST": 2.74, "XAF": 564.6, "XCD": 2.70, "XOF": 564.6, "XPF": 102.7, "YER": 238.4,
    "ZAR": 16.56, "ZMW": 19.38, "ZWL": 64360.0,
    "BTC": 0.0000148, "ETH": 0.000507, "DOGE": 11.09,
}

RATES: Dict[str, float] = dict(FALLBACK_RATES)
LAST_RATES_UPDATE: Optional[datetime] = None
RATES_SOURCE: str = "fallback"  # "google" | "api" | "fallback"

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
    # Убираем невидимые символы (zero-width, BOM и т.п.)
    s = "".join(c for c in code_or_symbol if ord(c) > 32 and c not in "\u200b\u200c\u200d\ufeff").strip()
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


def _fetch_google_rates() -> Optional[Dict[str, float]]:
    """Загружает курсы с Google Finance (как в поиске Google)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    rates: Dict[str, float] = {"USD": 1.0}
    for code in GOOGLE_CURRENCIES:
        try:
            url = GOOGLE_FINANCE_URL.format(code=code)
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            text = resp.text
            m = (
                re.search(r'YMlKec fxKbKc">(\d+\.\d+)<', text)
                or re.search(r'data-last-price="(\d+\.\d+)"', text)
                or re.search(r'Share\s+(\d+\.\d+)\s+Mar', text)
                or re.search(r'USD / ' + code + r'[^>]*>[\s\S]*?(\d+\.\d+)\s+Mar', text)
                or re.search(r'>(\d+\.\d{4})<\s*</div>\s*<div[^>]*>\s*Mar', text)
            )
            if m:
                rates[code] = float(m.group(1))
        except Exception:
            continue
    if len(rates) < 3:
        return None
    return rates


def _fetch_live_rates() -> None:
    global RATES, LAST_RATES_UPDATE, RATES_SOURCE
    # 1. Сначала пробуем Google Finance (курсы как в Google)
    google_rates = _fetch_google_rates()
    if google_rates and len(google_rates) >= 5:
        RATES = {**dict(FALLBACK_RATES), **google_rates}
        LAST_RATES_UPDATE = datetime.now(timezone.utc)
        RATES_SOURCE = "google"
        return
    # 2. Пробуем API
    for url, parse_fn in [
        (API_URL, lambda d: (d.get("rates", {}), d.get("ts"))),
        (API_FALLBACK_URL, lambda d: (
            {k.upper(): float(v) for k, v in (d.get("usd") or {}).items() if isinstance(v, (int, float))},
            d.get("date"),
        )),
    ]:
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            api_rates, ts_raw = parse_fn(data)
            if not api_rates:
                raise ValueError("empty rates")
            new_rates: Dict[str, float] = {}
            for code, value in api_rates.items():
                try:
                    new_rates[code.upper() if isinstance(code, str) else code] = float(value)
                except (TypeError, ValueError):
                    continue
            if not new_rates:
                raise ValueError("could not parse any rates")
            new_rates.setdefault("USD", 1.0)
            RATES = new_rates
            RATES_SOURCE = "api"
            if isinstance(ts_raw, str) and "T" in ts_raw:
                try:
                    LAST_RATES_UPDATE = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                except ValueError:
                    LAST_RATES_UPDATE = datetime.now(timezone.utc)
            elif isinstance(ts_raw, str):
                try:
                    LAST_RATES_UPDATE = datetime.strptime(ts_raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    LAST_RATES_UPDATE = datetime.now(timezone.utc)
            else:
                LAST_RATES_UPDATE = datetime.now(timezone.utc)
            return
        except Exception:
            continue
    # Оба API недоступны — используем запасные курсы
    RATES_SOURCE = "fallback"
    if not RATES:
        RATES = dict(FALLBACK_RATES)
    LAST_RATES_UPDATE = datetime.now(timezone.utc)


def _job_fetch_rates(context) -> None:
    """Периодическое обновление курсов (вызывается job_queue)."""
    _fetch_live_rates()


async def _post_init(application) -> None:
    """Запуск при старте: первое обновление курсов и планирование периодических."""
    _fetch_live_rates()
    if application.job_queue:
        application.job_queue.run_repeating(_job_fetch_rates, interval=1800, first=10)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is not None:
        _add_user(user_id)
    text = (
        "Всем салам от братвы\n\n"
        "Напиши сумму и валюту (курсы как в Google):\n"
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
    if LAST_RATES_UPDATE is not None:
        time_part = " (🕐 " + LAST_RATES_UPDATE.strftime("%d.%m.%Y %H:%M") + " UTC)"
    else:
        time_part = " (⚠️ оффлайн)"
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
        src = " (Google Finance)" if RATES_SOURCE == "google" else ""
        time_part = "\n\n🕐 Курсы" + src + ", обновлено " + LAST_RATES_UPDATE.strftime("%d.%m.%Y %H:%M") + " UTC"
    else:
        time_part = "\n\n⚠️ Курсы оффлайн (без даты обновления)"
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
    parts = [p.strip() for p in text.split()]
    if len(parts) == 2:
        a, b = parts
        # Вариант 1: "1 $" — сумма первая, валюта вторая
        base_code = _resolve_currency(b)
        if base_code:
            try:
                float(a.replace(",", "."))
                await _handle_rates(update, a, base_code)
                return
            except ValueError:
                pass
        # Вариант 2: "$ 1" — валюта первая, сумма вторая
        base_code = _resolve_currency(a)
        if base_code:
            try:
                float(b.replace(",", "."))
                await _handle_rates(update, b, base_code)
                return
            except ValueError:
                pass
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
    app = ApplicationBuilder().token(token).post_init(_post_init).build()
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
