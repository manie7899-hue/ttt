"""
BIN Checker — GUI приложение.
Одиночный и массовый поиск BIN.
Локальная база (безлимит) + binlist.net fallback.
"""

import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from bin_lookup import BinChecker, BinInfo


RESULT_FIELDS = [
    ("BIN", "bin"),
    ("Scheme", "scheme"),
    ("Brand", "brand"),
    ("Type", "type"),
    ("Prepaid", "prepaid"),
    ("Country", "country"),
    ("Bank", "bank"),
    ("Bank URL", "bank_url"),
    ("Phone", "bank_phone"),
    ("City", "bank_city"),
]


class BinCheckerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("BIN Checker")
        self.root.geometry("620x600")
        self.root.minsize(550, 500)

        self.checker = BinChecker(use_online=True)
        self._build_ui()

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        # === Одиночный поиск ===
        single_frame = ttk.LabelFrame(main, text="Поиск по BIN", padding=10)
        single_frame.pack(fill=tk.X, pady=(0, 10))

        input_row = ttk.Frame(single_frame)
        input_row.pack(fill=tk.X)

        ttk.Label(input_row, text="BIN (6–8 цифр):").pack(side=tk.LEFT)
        self.bin_entry = ttk.Entry(input_row, width=20, font=("Consolas", 12))
        self.bin_entry.pack(side=tk.LEFT, padx=(8, 8))
        self.bin_entry.bind("<Return>", lambda e: self._single_lookup())

        self.search_btn = ttk.Button(input_row, text="Найти", command=self._single_lookup, width=10)
        self.search_btn.pack(side=tk.LEFT)

        self.online_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(input_row, text="Онлайн fallback", variable=self.online_var).pack(side=tk.RIGHT)

        # Результат одиночного поиска — карточка
        self.card_frame = ttk.Frame(single_frame)
        self.card_frame.pack(fill=tk.X, pady=(10, 0))

        self.result_labels = {}
        for i, (label, key) in enumerate(RESULT_FIELDS):
            ttk.Label(self.card_frame, text=f"{label}:", font=("Segoe UI", 10, "bold")).grid(
                row=i, column=0, sticky=tk.W, pady=1, padx=(0, 10)
            )
            val = ttk.Label(self.card_frame, text="—", font=("Consolas", 10))
            val.grid(row=i, column=1, sticky=tk.W, pady=1)
            self.result_labels[key] = val

        self.source_label = ttk.Label(single_frame, text="", foreground="gray")
        self.source_label.pack(anchor=tk.W, pady=(6, 0))

        # === Массовый поиск ===
        bulk_frame = ttk.LabelFrame(main, text="Массовая проверка", padding=10)
        bulk_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        ttk.Label(bulk_frame, text="Введите BIN-ы (по одному на строку):").pack(anchor=tk.W)

        text_row = ttk.Frame(bulk_frame)
        text_row.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        self.bulk_input = scrolledtext.ScrolledText(text_row, height=5, width=20, font=("Consolas", 10))
        self.bulk_input.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        self.bulk_output = scrolledtext.ScrolledText(text_row, height=5, width=40, font=("Consolas", 9), state=tk.DISABLED)
        self.bulk_output.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        btn_row = ttk.Frame(bulk_frame)
        btn_row.pack(fill=tk.X, pady=(6, 0))

        self.bulk_btn = ttk.Button(btn_row, text="Проверить все", command=self._bulk_lookup, width=16)
        self.bulk_btn.pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Загрузить из файла", command=self._load_file, width=18).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_row, text="Сохранить результат", command=self._save_result, width=18).pack(side=tk.LEFT)

        self.bulk_progress = ttk.Progressbar(bulk_frame, maximum=100)
        self.bulk_progress.pack(fill=tk.X, pady=(6, 0))

        # Статус бар
        self.status_var = tk.StringVar(value=f"База: {len(self.checker.db.entries)} BIN | Онлайн: binlist.net")
        ttk.Label(main, textvariable=self.status_var, foreground="gray").pack(anchor=tk.W)

    def _single_lookup(self):
        bin_val = self.bin_entry.get().strip()
        if not bin_val or len(bin_val.replace(" ", "")) < 6:
            messagebox.showwarning("Ошибка", "Введите минимум 6 цифр BIN")
            return

        self.checker.online = None
        if self.online_var.get():
            from bin_lookup import OnlineBinLookup
            self.checker.online = OnlineBinLookup()

        # Сначала ищем в локальной БД
        local_result = self.checker.db.lookup(bin_val)
        source = "Локальная база"

        if local_result:
            result = local_result
        elif self.checker.online:
            result = self.checker.online.lookup(bin_val)
            source = "binlist.net (онлайн)"
        else:
            result = None

        if result:
            d = result.to_dict()
            for key, label_widget in self.result_labels.items():
                val = d.get(key, "—")
                if isinstance(val, bool):
                    val = "Yes" if val else "No"
                label_widget.configure(text=str(val) if val else "—")
            self.source_label.configure(text=f"Источник: {source}")
        else:
            for label_widget in self.result_labels.values():
                label_widget.configure(text="—")
            self.source_label.configure(text="Не найден")

    def _bulk_lookup(self):
        text = self.bulk_input.get("1.0", tk.END).strip()
        if not text:
            return
        bins = [line.strip() for line in text.splitlines() if line.strip()]
        if not bins:
            return

        self.bulk_btn.configure(state=tk.DISABLED)
        self.bulk_output.configure(state=tk.NORMAL)
        self.bulk_output.delete("1.0", tk.END)
        self.bulk_output.configure(state=tk.DISABLED)
        self.bulk_progress["value"] = 0

        self.checker.online = None
        if self.online_var.get():
            from bin_lookup import OnlineBinLookup
            self.checker.online = OnlineBinLookup()

        self._bulk_results = []

        def run():
            for i, b in enumerate(bins):
                result = self.checker.lookup(b)
                self._bulk_results.append((b, result))
                self.root.after(0, lambda idx=i, r=result, bn=b: self._append_bulk_result(idx, len(bins), bn, r))
            self.root.after(0, self._bulk_done)

        threading.Thread(target=run, daemon=True).start()

    def _append_bulk_result(self, idx: int, total: int, bin_val: str, info):
        self.bulk_progress["value"] = ((idx + 1) / total) * 100
        self.bulk_output.configure(state=tk.NORMAL)
        if info:
            line = f"{info.bin} | {info.scheme:12} | {info.card_type:8} | {info.country} | {info.bank_name}\n"
        else:
            line = f"{bin_val:6} | NOT FOUND\n"
        self.bulk_output.insert(tk.END, line)
        self.bulk_output.see(tk.END)
        self.bulk_output.configure(state=tk.DISABLED)

    def _bulk_done(self):
        self.bulk_btn.configure(state=tk.NORMAL)
        found = sum(1 for _, r in self._bulk_results if r)
        self.status_var.set(f"Готово: {found}/{len(self._bulk_results)} найдено")

    def _load_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("Текст", "*.txt"), ("CSV", "*.csv"), ("Все", "*.*")]
        )
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.bulk_input.delete("1.0", tk.END)
        self.bulk_input.insert("1.0", content)

    def _save_result(self):
        if not hasattr(self, "_bulk_results") or not self._bulk_results:
            messagebox.showwarning("Пусто", "Сначала выполните массовую проверку")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Текст", "*.txt"), ("CSV", "*.csv")],
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write("BIN|Scheme|Type|Prepaid|Country|Bank|URL|Phone|City\n")
            for bin_val, info in self._bulk_results:
                if info:
                    d = info.to_dict()
                    f.write(f"{d['bin']}|{d['scheme']}|{d['type']}|{d['prepaid']}|{d['country']}|{d['bank']}|{d['bank_url']}|{d['bank_phone']}|{d['bank_city']}\n")
                else:
                    f.write(f"{bin_val}|NOT FOUND\n")
        messagebox.showinfo("Сохранено", f"Результат сохранён в:\n{path}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = BinCheckerApp()
    app.run()
