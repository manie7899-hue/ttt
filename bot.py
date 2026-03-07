"""
Telegram бот UT Exchange + BIN Checker.
Команды: /start, /bin <6-8 цифр>, /help
"""
import os
import sys
from pathlib import Path

# Подключаем bin_checker
_root = Path(__file__).resolve().parent
sys.path.insert(0, str(_root / "bin_checker"))

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from bin_lookup import BinChecker


BIN_CHECKER = BinChecker(use_online=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Привет!\n\n"
        "BIN Checker — проверка первых 6–8 цифр карты:\n"
        "/bin 457105 — одиночный поиск\n"
        "/bin 457105 541275 — несколько BIN через пробел\n\n"
        "/help — справка"
    )
    await update.message.reply_text(text)


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


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "/bin <6-8 цифр> — проверка BIN (Visa, Mastercard и др.)\n"
        "Пример: /bin 457105"
    )


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Задайте TELEGRAM_BOT_TOKEN.")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bin", bin_command))
    app.add_handler(CommandHandler("help", help_command))
    print("Бот запущен.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
