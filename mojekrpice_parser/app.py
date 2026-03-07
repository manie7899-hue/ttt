"""
Миниприложение MOJEKRPICE Parser
GUI для удобной настройки и запуска парсера.
"""

import json
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from config import CATEGORIES, REQUEST_DELAY, PROXY_RAW, parse_proxy
from parser import MojekrpiceParser


# Человекочитаемые названия категорий
CATEGORY_NAMES = {
    "zene": "Женщины (всё)",
    "zene_odeca": "Женская одежда",
    "zene_haljine": "Платья",
    "zene_duksevi": "Свитера и джемперы",
    "zene_pantalone": "Брюки",
    "zene_obuca": "Женская обувь",
    "muskarci": "Мужчины",
    "deca": "Дети",
}


class ParserApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MOJEKRPICE Parser")
        self.root.geometry("580x620")
        self.root.minsize(500, 550)

        self.parser = None
        self.is_running = False
        self.stop_requested = False

        self._build_ui()

    def _build_ui(self):
        # Основной фрейм
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        # === Настройки ===
        settings_frame = ttk.LabelFrame(main, text="Настройки парсинга", padding=10)
        settings_frame.pack(fill=tk.X, pady=(0, 10))

        # Категория
        ttk.Label(settings_frame, text="Категория:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.category_var = tk.StringVar(value="zene_haljine")
        cat_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.category_var,
            values=list(CATEGORY_NAMES.values()),
            state="readonly",
            width=35,
        )
        cat_combo.grid(row=0, column=1, sticky=tk.EW, padx=(8, 0), pady=2)
        cat_combo.current(2)  # Платья по умолчанию

        # Страницы
        ttk.Label(settings_frame, text="Страниц:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.pages_var = tk.StringVar(value="5")
        pages_spin = ttk.Spinbox(
            settings_frame,
            from_=1,
            to=100,
            textvariable=self.pages_var,
            width=8,
        )
        pages_spin.grid(row=1, column=1, sticky=tk.W, padx=(8, 0), pady=2)
        ttk.Label(settings_frame, text="(0 = все страницы)").grid(row=1, column=2, sticky=tk.W, padx=4)

        # Задержка
        ttk.Label(settings_frame, text="Задержка (сек):").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.delay_var = tk.StringVar(value="2")
        ttk.Spinbox(
            settings_frame,
            from_=1,
            to=10,
            textvariable=self.delay_var,
            width=8,
        ).grid(row=2, column=1, sticky=tk.W, padx=(8, 0), pady=2)

        # Файл вывода
        ttk.Label(settings_frame, text="Сохранить в:").grid(row=3, column=0, sticky=tk.W, pady=2)
        file_frame = ttk.Frame(settings_frame)
        file_frame.grid(row=3, column=1, columnspan=2, sticky=tk.EW, padx=(8, 0), pady=2)
        self.output_var = tk.StringVar(value=os.path.abspath("listings.json"))
        ttk.Entry(file_frame, textvariable=self.output_var, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ttk.Button(file_frame, text="Обзор...", command=self._browse_output).pack(side=tk.LEFT)

        settings_frame.columnconfigure(1, weight=1)

        # === Прокси ===
        proxy_frame = ttk.LabelFrame(main, text="Прокси (ip:port:user:password)", padding=10)
        proxy_frame.pack(fill=tk.X, pady=(0, 10))

        self.proxy_var = tk.StringVar(value=PROXY_RAW or "")
        proxy_entry = ttk.Entry(proxy_frame, textvariable=self.proxy_var, width=60)
        proxy_entry.pack(fill=tk.X, pady=2)
        ttk.Label(proxy_frame, text="Оставьте пустым для работы без прокси", foreground="gray").pack(anchor=tk.W)

        # === Кнопки ===
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.start_btn = ttk.Button(btn_frame, text="▶ Запустить", command=self._start, width=14)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.stop_btn = ttk.Button(btn_frame, text="■ Остановить", command=self._stop, state=tk.DISABLED, width=14)
        self.stop_btn.pack(side=tk.LEFT)
        self.open_btn = ttk.Button(btn_frame, text="Открыть результат", command=self._open_result, width=18)
        self.open_btn.pack(side=tk.RIGHT)

        # === Прогресс ===
        progress_frame = ttk.LabelFrame(main, text="Прогресс", padding=10)
        progress_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(0, 6))

        self.log_text = scrolledtext.ScrolledText(
            progress_frame,
            height=14,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 9),
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Все файлы", "*.*")],
            initialfile="listings.json",
        )
        if path:
            self.output_var.set(path)

    def _get_category_key(self) -> str:
        display = self.category_var.get()
        for key, name in CATEGORY_NAMES.items():
            if name == display:
                return key
        return "zene_haljine"

    def _log(self, msg: str):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)
        self.root.update_idletasks()

    def _progress_callback(self, current: int, total: int, message: str):
        if self.stop_requested:
            return
        self.root.after(0, lambda: self._log(message))
        if total > 0:
            pct = (current / total) * 100
            self.root.after(0, lambda: self.progress_var.set(pct))

    def _start(self):
        try:
            pages = int(self.pages_var.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Укажите корректное число страниц")
            return

        try:
            delay = float(self.delay_var.get())
            if delay < 0.5:
                delay = 0.5
        except ValueError:
            delay = 2.0

        output = self.output_var.get().strip()
        if not output:
            messagebox.showerror("Ошибка", "Укажите файл для сохранения")
            return

        proxy_raw = self.proxy_var.get().strip()
        proxy = parse_proxy(proxy_raw) if proxy_raw else None

        self.is_running = True
        self.stop_requested = False
        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.progress_var.set(0)
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state=tk.DISABLED)

        category = self._get_category_key()
        self._log(f"Запуск: категория {CATEGORY_NAMES.get(category, category)}, страниц: {pages}")

        def run():
            try:
                parser = MojekrpiceParser(delay=delay, proxy=proxy)
                result = parser.parse_category(
                    category_key=category,
                    max_pages=pages,
                    output_file=output,
                    progress_callback=self._progress_callback,
                    stop_check=lambda: self.stop_requested,
                )
                self.root.after(0, lambda: self._on_done(len(result), output))
            except Exception as e:
                self.root.after(0, lambda: self._on_error(str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _stop(self):
        self.stop_requested = True
        self._log("Остановка после текущего объявления...")

    def _on_done(self, count: int, output_path: str):
        self.is_running = False
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self.progress_var.set(100)
        self._log(f"\n✓ Готово! Найдено объявлений: {count}")
        self._log(f"Сохранено в: {output_path}")
        if count > 0:
            messagebox.showinfo("Готово", f"Найдено {count} объявлений.\nСохранено в:\n{output_path}")

    def _on_error(self, err: str):
        self.is_running = False
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)
        self._log(f"\n✗ Ошибка: {err}")
        messagebox.showerror("Ошибка", err)

    def _open_result(self):
        path = self.output_var.get()
        if path and os.path.isfile(path):
            os.startfile(path)
        else:
            messagebox.showwarning("Файл не найден", "Сначала запустите парсинг и дождитесь завершения.")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ParserApp()
    app.run()
