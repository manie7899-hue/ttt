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

# Оффлайн‑значения на случай недоступности интернета / сервиса
FALLBACK_RATES: Dict[str, float] = {
    "USD": 1.0,
    "EUR": 0.9,
    "RUB": 80.0,
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

# Мини‑справочник по валютам: флаг по коду
CODE_META: Dict[str, str] = {
    "USD": "🇺🇸",
    "EUR": "🇪🇺",
    "GBP": "🇬🇧",
    "PLN": "🇵🇱",
    "UAH": "🇺🇦",
    "RUB": "🇷🇺",
    "BYN": "🇧🇾",
    "KZT": "🇰🇿",
    "BAM": "🇧🇦",
}

RATES_TARGETS = ["UAH", "EUR", "USD"]


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
        "Напиши сумму и валюту, например: 500 BAM\n\n"
        "Команды: /calc, /convert, /rates, /help\n"
        "Админам: /admin — админ-панель"
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "/calc <a> <операция> <b> — калькулятор\n"
        "/convert <сумма> <из> <в> — конвертер\n"
        "/rates <сумма> <валюта> — курсы в нескольких валютах\n\n"
        "Или просто: 500 BAM"
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
    lines.append("🔁 Currencies")
    lines.append("")
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
        label = _code_to_label(code)
        lines.append(f"{label} {_format_amount(converted, 2)}")
    time_part = ""
    if LAST_RATES_UPDATE is not None:
        time_part = "\n\nКурсы обновлены " + LAST_RATES_UPDATE.strftime("%d.%m.%Y %H:%M") + " по UTC"
    footer = "\n\nUltra БАТЯ ЕБЕТ МАМАШ ВАШИХ"
    body = "\n".join(lines) + time_part + footer
    await update.message.reply_text(body)


async def rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 2:
        await update.message.reply_text("Использование: /rates <сумма> <валюта>\nПример: /rates 500 BAM")
        return
    amount_text, base_code = context.args
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
        amount_text, base_code = parts
        await _handle_rates(update, amount_text, base_code)
        return
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
