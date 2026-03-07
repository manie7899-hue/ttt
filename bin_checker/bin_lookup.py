"""
Движок BIN Lookup — поиск по локальной базе + онлайн fallback.
Локальная база: ranges.csv (binlist/data с GitHub).
Онлайн: freebinchecker.com API.
"""

import csv
import os
import re
from dataclasses import dataclass
from typing import Optional

import requests


@dataclass
class BinInfo:
    bin: str
    scheme: str        # visa, mastercard, amex...
    brand: str
    card_type: str     # credit, debit, prepaid
    prepaid: bool
    country: str       # country code (US, RS, DE...)
    bank_name: str
    bank_url: str
    bank_phone: str
    bank_city: str

    def to_dict(self) -> dict:
        return {
            "bin": self.bin,
            "scheme": self.scheme,
            "brand": self.brand,
            "type": self.card_type,
            "prepaid": self.prepaid,
            "country": self.country,
            "bank": self.bank_name,
            "bank_url": self.bank_url,
            "bank_phone": self.bank_phone,
            "bank_city": self.bank_city,
        }

    def display(self) -> str:
        lines = [
            f"BIN:       {self.bin}",
            f"Scheme:    {self.scheme.upper() or '—'}",
            f"Brand:     {self.brand or '—'}",
            f"Type:      {self.card_type or '—'}",
            f"Prepaid:   {'Yes' if self.prepaid else 'No'}",
            f"Country:   {self.country or '—'}",
            f"Bank:      {self.bank_name or '—'}",
            f"Bank URL:  {self.bank_url or '—'}",
            f"Phone:     {self.bank_phone or '—'}",
            f"City:      {self.bank_city or '—'}",
        ]
        return "\n".join(lines)


class BinDatabase:
    """Локальная БД из ranges.csv (безлимит, офлайн)"""

    def __init__(self, csv_path: str = None):
        if csv_path is None:
            csv_path = os.path.join(os.path.dirname(__file__), "ranges.csv")
        self.entries: list[dict] = []
        self._load(csv_path)

    def _load(self, path: str):
        if not os.path.isfile(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.entries.append(row)

    def lookup(self, bin_number: str) -> Optional[BinInfo]:
        """Поиск BIN (6–8 цифр) в локальной базе"""
        bin_clean = re.sub(r"\D", "", bin_number)[:8]
        if len(bin_clean) < 6:
            return None

        best_match = None
        best_len = 0

        for entry in self.entries:
            start = entry.get("iin_start", "")
            end = entry.get("iin_end", "")
            if not start:
                continue

            prefix_len = len(start)
            # Дополняем BIN нулями, если start длиннее
            check = bin_clean.ljust(prefix_len, "0")[:prefix_len]

            if end:
                if start <= check <= end:
                    if prefix_len > best_len:
                        best_match = entry
                        best_len = prefix_len
            else:
                if check == start:
                    if prefix_len > best_len:
                        best_match = entry
                        best_len = prefix_len

        if not best_match:
            return None

        return BinInfo(
            bin=bin_clean[:6],
            scheme=best_match.get("scheme", ""),
            brand=best_match.get("brand", ""),
            card_type=best_match.get("type", ""),
            prepaid=best_match.get("prepaid", "").upper() == "Y",
            country=best_match.get("country", ""),
            bank_name=best_match.get("bank_name", ""),
            bank_url=best_match.get("bank_url", ""),
            bank_phone=best_match.get("bank_phone", ""),
            bank_city=best_match.get("bank_city", ""),
        )


class OnlineBinLookup:
    """Онлайн fallback через binlist.net (5 запросов/мин бесплатно)"""

    API_URL = "https://lookup.binlist.net/{bin}"

    def lookup(self, bin_number: str) -> Optional[BinInfo]:
        bin_clean = re.sub(r"\D", "", bin_number)[:8]
        if len(bin_clean) < 6:
            return None
        try:
            resp = requests.get(
                self.API_URL.format(bin=bin_clean[:6]),
                timeout=10,
                headers={"Accept-Version": "3"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            country = data.get("country") or {}
            bank = data.get("bank") or {}
            return BinInfo(
                bin=bin_clean[:6],
                scheme=data.get("scheme", "") or "",
                brand=data.get("brand", "") or "",
                card_type=data.get("type", "") or "",
                prepaid=bool(data.get("prepaid")),
                country=country.get("alpha2", ""),
                bank_name=bank.get("name", ""),
                bank_url=bank.get("url", ""),
                bank_phone=bank.get("phone", ""),
                bank_city=bank.get("city", ""),
            )
        except Exception:
            return None


class BinChecker:
    """Комбинированный чекер: локальная БД + онлайн fallback"""

    def __init__(self, csv_path: str = None, use_online: bool = True):
        self.db = BinDatabase(csv_path)
        self.online = OnlineBinLookup() if use_online else None

    def lookup(self, bin_number: str) -> Optional[BinInfo]:
        result = self.db.lookup(bin_number)
        if result:
            return result
        if self.online:
            return self.online.lookup(bin_number)
        return None

    def bulk_lookup(self, bins: list[str]) -> list[Optional[BinInfo]]:
        return [self.lookup(b) for b in bins]
