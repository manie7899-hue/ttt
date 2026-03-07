#!/usr/bin/env python3
"""
Скрипт запуска парсера MOJEKRPICE.
Пример: python run.py zene_haljine
"""

import sys
from parser import MojekrpiceParser
from config import CATEGORIES

def main():
    if len(sys.argv) < 2:
        print("Использование: python run.py <категория> [output.json]")
        print("\nДоступные категории:")
        for k, v in CATEGORIES.items():
            print(f"  {k}: {v}")
        sys.exit(1)

    category = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else "listings.json"

    if category not in CATEGORIES:
        print(f"Неизвестная категория: {category}")
        sys.exit(1)

    parser = MojekrpiceParser(delay=2)
    listings = parser.parse_category(category, max_pages=5, output_file=output)
    print(f"\nГотово. Найдено объявлений от продавцов без отзывов: {len(listings)}")

if __name__ == "__main__":
    main()
