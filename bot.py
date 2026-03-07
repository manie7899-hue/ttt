import asyncio
import os
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
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
RANDOMUSER_URL = "https://randomuser.me/api/?nat={code}&results=1"
GEMINI_MODEL = "gemini-1.5-flash"
RATES_CACHE_TTL = 300

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton("💱 Курсы"), KeyboardButton("🔢 Калькулятор")],
        [KeyboardButton("📋 Фейк данные"), KeyboardButton("❓ Помощь")],
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
        InlineKeyboardButton("1000€", callback_data="rates_1000_EUR"),
    ],
    [
        InlineKeyboardButton("100 BAM", callback_data="rates_100_BAM"),
        InlineKeyboardButton("500 BAM", callback_data="rates_500_BAM"),
        InlineKeyboardButton("1000 BAM", callback_data="rates_1000_BAM"),
    ],
    [
        InlineKeyboardButton("1000₴", callback_data="rates_1000_UAH"),
        InlineKeyboardButton("1000£", callback_data="rates_1000_GBP"),
        InlineKeyboardButton("1000₽", callback_data="rates_1000_RUB"),
    ],
])

FAKE_BUTTONS = InlineKeyboardMarkup([
    [InlineKeyboardButton("🇩🇪 Германия", callback_data="fake_DE"), InlineKeyboardButton("🇺🇸 США", callback_data="fake_US")],
    [InlineKeyboardButton("🇬🇧 UK", callback_data="fake_GB"), InlineKeyboardButton("🇧🇦 Босния", callback_data="fake_BA")],
    [InlineKeyboardButton("🇫🇷 Франция", callback_data="fake_FR"), InlineKeyboardButton("🇺🇦 Украина", callback_data="fake_UA")],
    [InlineKeyboardButton("🇵🇱 Польша", callback_data="fake_PL"), InlineKeyboardButton("🇮🇹 Италия", callback_data="fake_IT")],
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

GOOGLE_CURRENCIES = ["EUR", "GBP", "PLN", "UAH", "BAM", "RUB", "BYN", "KZT", "CHF", "JPY", "TRY", "CNY", "CAD", "AUD"]
ADMINS_FILE = Path(__file__).resolve().parent / "admins.txt"
USERS_FILE = Path(__file__).resolve().parent / "users.txt"
FAKE_COUNTRY_MAP: Dict[str, str] = {"UK": "GB", "RU": "RS", "BAM": "BA"}

# randomuser.me поддерживает только эти коды
RANDOMUSER_SUPPORTED: Set[str] = {"AU", "BR", "CA", "CH", "DE", "DK", "ES", "FI", "FR", "GB", "IE", "IN", "IR", "MX", "NL", "NO", "NZ", "RS", "TR", "UA", "US"}

# Faker: код страны -> локаль (для стран без randomuser)
FAKER_LOCALES: Dict[str, str] = {
    "BA": "sl_SI", "BAM": "sl_SI", "HR": "hr_HR", "SI": "sl_SI", "MK": "mk_MK", "ME": "sl_SI",
    "AL": "sq_AL", "BG": "bg_BG", "RO": "ro_RO", "HU": "hu_HU", "SK": "sk_SK",
    "CZ": "cs_CZ", "PL": "pl_PL", "AT": "de_AT", "IT": "it_IT", "GR": "el_GR",
    "PT": "pt_PT", "BE": "nl_BE", "JP": "ja_JP", "KR": "ko_KR", "CN": "zh_CN",
    "TH": "th_TH", "VN": "vi_VN", "ID": "id_ID", "MY": "ms_MY", "PH": "en_PH",
    "SA": "ar_SA", "AE": "ar_AE", "EG": "ar_EG", "NG": "en_NG", "ZA": "en_ZA",
}
BA_CITIES = ["Sarajevo", "Banja Luka", "Tuzla", "Zenica", "Mostar", "Bihać", "Brčko", "Prijedor", "Doboj", "Cazin"]
BA_STREETS = ["Marsala Tita", "Zmaja od Bosne", "Kralja Tvrtka", "Obala Kulina bana", "Ferhadija", "Mehmeda Spahe", "Mustafe Hukića", "Ante Starčevića", "Kneza Branimira", "Trg slobode"]
COUNTRY_NAMES: Dict[str, str] = {
    "BA": "Bosnia and Herzegovina", "BAM": "Bosnia and Herzegovina", "HR": "Croatia", "SI": "Slovenia", "MK": "North Macedonia",
    "ME": "Montenegro", "AL": "Albania", "BG": "Bulgaria", "RO": "Romania", "HU": "Hungary",
    "SK": "Slovakia", "CZ": "Czech Republic", "PL": "Poland", "AT": "Austria", "IT": "Italy",
    "GR": "Greece", "PT": "Portugal", "BE": "Belgium", "JP": "Japan", "KR": "South Korea",
    "CN": "China", "TH": "Thailand", "VN": "Vietnam", "ID": "Indonesia", "MY": "Malaysia",
    "PH": "Philippines", "SA": "Saudi Arabia", "AE": "UAE", "EG": "Egypt", "NG": "Nigeria",
    "ZA": "South Africa",
}


def _ask_gemini(prompt: str) -> Optional[str]:
    """Отправляет запрос в Gemini API (бесплатный тариф)."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt[:8000])
        if response and response.text:
            return response.text.strip()
    except Exception:
        pass
    return None


def _country_flag(code: str) -> str:
    """Флаг страны из 2-буквенного кода (DE, US, GB и т.д.)."""
    if not code or len(code) != 2:
        return "🌍"
    a, b = code.upper()[0], code.upper()[1]
    if not ("A" <= a <= "Z" and "A" <= b <= "Z"):
        return "🌍"
    return chr(0x1F1E6 + ord(a) - ord("A")) + chr(0x1F1E6 + ord(b) - ord("A"))

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
RATES_SOURCE: str = "fallback"
ADMIN_IDS: Set[int] = set()
USER_IDS: Set[int] = set()


def _load_admins() -> None:
    global ADMIN_IDS
    ADMIN_IDS = set()
    env_ids = os.getenv("TELEGRAM_ADMIN_IDS", "").strip()
    if env_ids:
        for s in env_ids.split(","):
            if s.strip().isdigit():
                ADMIN_IDS.add(int(s.strip()))
    if ADMINS_FILE.exists():
        with open(ADMINS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().isdigit():
                    ADMIN_IDS.add(int(line.strip()))


def _load_users() -> None:
    global USER_IDS
    USER_IDS = set()
    if USERS_FILE.exists():
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().isdigit():
                    USER_IDS.add(int(line.strip()))


def _add_user(user_id: int) -> None:
    if user_id not in USER_IDS:
        USER_IDS.add(user_id)
        with open(USERS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{user_id}\n")


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


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
    "доллар": "USD", "долларов": "USD", "доллара": "USD", "dollar": "USD", "dollars": "USD",
    "бакс": "USD", "баксы": "USD", "баксов": "USD", "бакса": "USD",
    "зелёные": "USD", "зеленые": "USD", "зелёный": "USD", "зеленый": "USD",
    "евро": "EUR", "euro": "EUR", "euros": "EUR", "еврики": "EUR",
    "фунт": "GBP", "фунтов": "GBP", "pound": "GBP", "pounds": "GBP", "стерлингов": "GBP",
    "рубль": "RUB", "рублей": "RUB", "рубля": "RUB", "ruble": "RUB", "rubles": "RUB",
    "гривна": "UAH", "гривен": "UAH", "гривны": "UAH", "грн": "UAH", "hryvnia": "UAH", "гривенка": "UAH",
    "злотый": "PLN", "злотых": "PLN", "zloty": "PLN",
    "марка": "BAM", "марок": "BAM", "марки": "BAM",
    "франк": "CHF", "франков": "CHF", "franc": "CHF", "francs": "CHF",
    "йена": "JPY", "йен": "JPY", "yen": "JPY", "yens": "JPY",
    "юань": "CNY", "юаней": "CNY", "yuan": "CNY",
    "лира": "TRY", "лир": "TRY", "lira": "TRY",
    "крона": "SEK", "крон": "SEK", "crown": "SEK",
    "тенге": "KZT", "тенгов": "KZT", "tenge": "KZT",
    "лев": "BGN", "лева": "BGN", "левов": "BGN",
}
RATES_TARGETS = ["EUR", "GBP", "PLN", "UAH", "USD"]


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
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
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
            )
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
    RATES_SOURCE = "fallback"
    if not RATES:
        RATES = dict(FALLBACK_RATES)
    LAST_RATES_UPDATE = datetime.now(timezone.utc)


def _fetch_fake_data_randomuser(code: str) -> Optional[Dict[str, Any]]:
    """Данные с randomuser.me (только для поддерживаемых стран)."""
    try:
        r = requests.get(RANDOMUSER_URL.format(code=code.lower()), timeout=10)
        r.raise_for_status()
        data = r.json()
        res = data.get("results", [{}])[0]
        nat = res.get("nat", "").upper()
        if nat != code.upper():
            return None
        name_obj = res.get("name", {})
        name = " ".join(filter(None, [
            name_obj.get("title"),
            name_obj.get("first"),
            name_obj.get("last"),
        ])).strip()
        loc = res.get("location", {})
        street = loc.get("street", {}) or {}
        street_str = f"{street.get('number', '')} {street.get('name', '')}".strip() or "—"
        return {
            "name": name or "—",
            "street": street_str,
            "city": loc.get("city", "—"),
            "state": loc.get("state", "—"),
            "postcode": str(loc.get("postcode", "—")),
            "country": loc.get("country", "—"),
            "nat": nat,
        }
    except Exception:
        return None


def _fetch_fake_data_faker(code: str) -> Optional[Dict[str, Any]]:
    """Данные через Faker (для BA, HR, PL и др. стран без randomuser)."""
    try:
        from faker import Faker
        locale = FAKER_LOCALES.get(code, "en_US")
        fake = Faker(locale)
        country = COUNTRY_NAMES.get(code, getattr(fake, "current_country", lambda: "—")())
        state = "—"
        if hasattr(fake, "administrative_unit"):
            state = fake.administrative_unit()
        elif hasattr(fake, "state"):
            state = fake.state()
        postcode = "—"
        if hasattr(fake, "postcode"):
            postcode = fake.postcode()
        elif hasattr(fake, "zipcode"):
            postcode = fake.zipcode()
        return {
            "name": fake.name(),
            "street": fake.street_address(),
            "city": fake.city(),
            "state": state,
            "postcode": str(postcode),
            "country": country,
            "nat": code,
        }
    except Exception:
        return None


def _fetch_fake_data_bosnia() -> Dict[str, Any]:
    """Данные для Боснии и Герцеговины (BA)."""
    from faker import Faker
    fake = Faker()
    return {
        "name": fake.name(),
        "street": f"{random.choice(BA_STREETS)} {random.randint(1, 150)}",
        "city": random.choice(BA_CITIES),
        "state": random.choice(["Federacija BiH", "Republika Srpska", "Brčko Distrikt"]),
        "postcode": str(random.randint(71000, 78000)),
        "country": "Bosnia and Herzegovina",
        "nat": "BA",
    }


def _fetch_fakexy_data(country_code: str) -> Optional[Dict[str, Any]]:
    code = country_code.upper().strip()[:2]
    code = FAKE_COUNTRY_MAP.get(code, code)
    if code == "BA":
        return _fetch_fake_data_bosnia()
    if code in RANDOMUSER_SUPPORTED:
        data = _fetch_fake_data_randomuser(code)
        if data:
            return data
    if code in FAKER_LOCALES or code in COUNTRY_NAMES:
        return _fetch_fake_data_faker(code)
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is not None:
        _add_user(user_id)
    text = (
        "Всем салам от братвы\n\n"
        "Напиши сумму и валюту (курсы как в Google):\n"
        "• 500 BAM или 500 $\n"
        "• 100 €, 50 £, 1000 ₴\n\n"
        "Или используй кнопки ниже 👇\n"
        "Или задай любой вопрос — отвечу через Gemini AI\n"
        "Админам: /admin — админ-панель"
    )
    await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "/calc <a> <операция> <b> — калькулятор\n"
        "/convert <сумма> <из> <в> — конвертер\n"
        "/rates <сумма> <валюта> — курсы\n"
        "/fake <код> — фейковые данные (DE, US, UK, BA)\n\n"
        "Или: 500 BAM, 100 $ — и любой вопрос (Gemini AI)"
    )
    await update.message.reply_text(text)


async def calc_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 3:
        await update.message.reply_text("Использование: /calc <a> <операция> <b>\nПример: /calc 2 + 3")
        return
    a_text, op, b_text = context.args
    try:
        a, b = float(a_text.replace(",", ".")), float(b_text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Ошибка: a и b должны быть числами.")
        return
    try:
        if op == "+": result = a + b
        elif op == "-": result = a - b
        elif op == "*": result = a * b
        elif op == "/":
            if b == 0:
                await update.message.reply_text("Ошибка: деление на ноль.")
                return
            result = a / b
        else:
            await update.message.reply_text("Неизвестная операция. Используйте +, -, *, /")
            return
        await update.message.reply_text(f"{a} {op} {b} = {result}")
    except ValueError:
        await update.message.reply_text("Ошибка в вычислении.")


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
    from_curr, to_curr = from_curr.upper(), to_curr.upper()
    await asyncio.get_event_loop().run_in_executor(None, _fetch_live_rates)
    if from_curr not in RATES or to_curr not in RATES:
        await update.message.reply_text("Неизвестная валюта. Примеры: USD, EUR, RUB.")
        return
    try:
        result = amount / RATES[from_curr] * RATES[to_curr]
    except ZeroDivisionError:
        await update.message.reply_text("Ошибка: некорректные курсы.")
        return
    time_part = f" (🕐 {LAST_RATES_UPDATE.strftime('%d.%m.%Y %H:%M')} UTC)" if LAST_RATES_UPDATE else " (⚠️ оффлайн)"
    await update.message.reply_text(f"{amount:.2f} {from_curr} = {result:.2f} {to_curr}{time_part}")


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
    await asyncio.get_event_loop().run_in_executor(None, _fetch_live_rates)
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
    src = " (Google Finance)" if RATES_SOURCE == "google" else ""
    time_part = f"\n\n🕐 Курсы{src}, обновлено {LAST_RATES_UPDATE.strftime('%d.%m.%Y %H:%M')} UTC" if LAST_RATES_UPDATE else "\n\n⚠️ Курсы оффлайн"
    footer = "\n\nUltra БАТЯ ЕБЕТ МАМАШ ВАШИХ"
    body = "\n".join(lines) + time_part + footer
    chat_id = msg.chat.id if msg else update.effective_chat.id
    await context.bot.send_message(chat_id=chat_id, text=body)


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


async def fake_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Использование: /fake <код страны>\nПримеры: /fake DE, /fake US, /fake UK")
        return
    country = context.args[0].strip()
    if len(country) < 2:
        await update.message.reply_text("Укажите код страны (2 буквы): DE, US, UK.")
        return
    msg = await update.message.reply_text("Загрузка данных...")
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, _fetch_fakexy_data, country)
    except Exception:
        data = None
    if not data:
        await msg.edit_text("Не удалось получить данные. Попробуйте DE, US, GB, FR, BA.")
        return
    text = (
        f"👤 Name: {data['name']}\n"
        f"🏠 Street: {data['street']}\n"
        f"🌆 City: {data['city']}\n"
        f"📍 State: {data['state']}\n"
        f"📮 Postal Code: {data['postcode']}\n"
        f"{_country_flag(data.get('nat', ''))} Country: {data['country']}"
    )
    await msg.edit_text(text)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else 0
    if not _is_admin(user_id):
        await update.message.reply_text("Доступ запрещён.")
        return
    keyboard = [[InlineKeyboardButton("Рассылка", callback_data="broadcast_start")]]
    await update.message.reply_text("Админ-панель:", reply_markup=InlineKeyboardMarkup(keyboard))


async def broadcast_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not _is_admin(update.effective_user.id if update.effective_user else 0):
        return
    await query.answer()
    context.user_data["awaiting_broadcast"] = True
    await query.edit_message_text("Отправьте текст рассылки.")


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
        return

    if cb.startswith("rates_"):
        parts = cb.split("_")
        if len(parts) >= 3:
            amount_text, base_code = parts[1], parts[2]
            await _handle_rates(update, context, amount_text, base_code, reply_message=query.message)
        return

    if cb.startswith("fake_"):
        country = cb[5:7] if len(cb) >= 7 else cb[5:]
        if not country:
            return
        try:
            await query.edit_message_text("⏳ Загрузка данных...")
        except Exception:
            pass
        try:
            data_obj = await asyncio.get_event_loop().run_in_executor(None, _fetch_fakexy_data, country)
        except Exception:
            data_obj = None
        if not data_obj:
            await query.edit_message_text("Не удалось получить данные. Попробуйте DE, US, GB, FR, BA.")
            return
        text = (
            f"👤 Name: {data_obj['name']}\n"
            f"🏠 Street: {data_obj['street']}\n"
            f"🌆 City: {data_obj['city']}\n"
            f"📍 State: {data_obj['state']}\n"
            f"📮 Postal Code: {data_obj['postcode']}\n"
            f"{_country_flag(data_obj.get('nat', ''))} Country: {data_obj['country']}"
        )
        refresh_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Ещё", callback_data=f"fake_{country}"),
                InlineKeyboardButton("🔙 Страны", callback_data="fake_menu"),
            ]
        ])
        await query.edit_message_text(text, reply_markup=refresh_kb)
        return

    if cb == "fake_menu":
        await query.edit_message_text("Выбери страну:", reply_markup=FAKE_BUTTONS)
        return


async def broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text or not _is_admin(update.effective_user.id if update.effective_user else 0):
        return
    if not context.user_data.pop("awaiting_broadcast", False):
        return
    text = update.message.text
    targets = USER_IDS - ADMIN_IDS
    sent = failed = 0
    for uid in targets:
        try:
            await context.bot.send_message(chat_id=uid, text=text)
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(f"📢 Рассылка: ✅ {sent}, ❌ {failed}")


async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id if update.effective_user else 0):
        await update.message.reply_text("Доступ запрещён.")
        return
    context.user_data["awaiting_broadcast"] = True
    await update.message.reply_text("Отправьте текст рассылки.")


async def addadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id if update.effective_user else 0):
        await update.message.reply_text("Доступ запрещён.")
        return
    if len(context.args) < 1:
        await update.message.reply_text("Использование: /addadmin <user_id>")
        return
    try:
        target_id = int(context.args[0])
        ADMIN_IDS.add(target_id)
        with open(ADMINS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{target_id}\n")
        await update.message.reply_text(f"Пользователь {target_id} добавлен в админы.")
    except ValueError:
        await update.message.reply_text("Ошибка: укажите числовой ID.")


async def listadmins_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id if update.effective_user else 0):
        await update.message.reply_text("Доступ запрещён.")
        return
    await update.message.reply_text("Админы: " + ", ".join(map(str, sorted(ADMIN_IDS))))


async def removeadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id if update.effective_user else 0):
        await update.message.reply_text("Доступ запрещён.")
        return
    if len(context.args) < 1:
        await update.message.reply_text("Использование: /removeadmin <user_id>")
        return
    try:
        target_id = int(context.args[0])
        ADMIN_IDS.discard(target_id)
        if ADMINS_FILE.exists():
            with open(ADMINS_FILE, "w", encoding="utf-8") as f:
                for uid in sorted(ADMIN_IDS):
                    f.write(f"{uid}\n")
        await update.message.reply_text(f"Пользователь {target_id} удалён из админов.")
    except ValueError:
        await update.message.reply_text("Ошибка: укажите числовой ID.")


async def text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    user_id = update.effective_user.id if update.effective_user else 0
    if _is_admin(user_id) and context.user_data.get("awaiting_broadcast"):
        await broadcast_message_handler(update, context)
        return
    text = update.message.text.strip()
    if text.startswith("/"):
        return
    # Обработка кнопок главного меню
    if text == "💱 Курсы":
        await update.message.reply_text("Выбери сумму и валюту:", reply_markup=RATES_BUTTONS)
        return
    if text == "📋 Фейк данные":
        await update.message.reply_text("Выбери страну:", reply_markup=FAKE_BUTTONS)
        return
    if text == "🔢 Калькулятор":
        context.user_data["calc_expr"] = "0"
        await update.message.reply_text(
            "🔢 Калькулятор\n\n📟 0",
            reply_markup=_calc_keyboard(),
        )
        return
    if text == "❓ Помощь":
        await help_command(update, context)
        return
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
    # Сообщение не о валюте — отправляем в Gemini
    reply = await asyncio.get_event_loop().run_in_executor(None, _ask_gemini, text)
    if reply:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=reply[:4000])
    elif os.getenv("GEMINI_API_KEY", "").strip():
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Не удалось получить ответ от AI.")


async def _job_fetch_rates(context) -> None:
    await asyncio.get_event_loop().run_in_executor(None, _fetch_live_rates_force)


def _fetch_live_rates_force() -> None:
    global LAST_RATES_UPDATE
    saved = LAST_RATES_UPDATE
    LAST_RATES_UPDATE = None
    try:
        _fetch_live_rates()
    except Exception:
        LAST_RATES_UPDATE = saved


async def _post_init(application) -> None:
    await asyncio.get_event_loop().run_in_executor(None, _fetch_live_rates)
    if application.job_queue:
        application.job_queue.run_repeating(_job_fetch_rates, interval=1800, first=10)


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Задайте TELEGRAM_BOT_TOKEN.")
    _load_admins()
    _load_users()
    app = ApplicationBuilder().token(token).post_init(_post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("calc", calc_command))
    app.add_handler(CommandHandler("convert", convert_command))
    app.add_handler(CommandHandler("rates", rates_command))
    app.add_handler(CommandHandler("fake", fake_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("all", all_command))
    app.add_handler(CommandHandler("addadmin", addadmin_command))
    app.add_handler(CommandHandler("listadmins", listadmins_command))
    app.add_handler(CommandHandler("removeadmin", removeadmin_command))
    app.add_handler(CallbackQueryHandler(broadcast_start_callback, pattern="^broadcast_start$"))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^(rates_|fake_|calc_)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message))
    print("Бот запущен.")
    app.run_polling()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import sys
        print(f"Ошибка запуска: {e}", file=sys.stderr)
        raise
