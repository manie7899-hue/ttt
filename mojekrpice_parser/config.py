# Конфигурация парсера MOJEKRPICE
# https://www.mojekrpice.rs - сербский маркетплейс одежды и аксессуаров

import os

BASE_URL = "https://mojekrpice.rs"

# Прокси (формат: ip:port:user:password)
# Задайте через MOJEKRPICE_PROXY или укажите здесь:
PROXY_RAW = os.getenv("MOJEKRPICE_PROXY", "89.31.121.13:12706:modeler_PXGC9Z:xLszYkY1VQZd")


def parse_proxy(raw: str) -> dict | None:
    """Преобразует ip:port:user:password в формат для requests"""
    if not raw or not raw.strip():
        return None
    parts = raw.strip().split(":")
    if len(parts) >= 4:
        ip, port, user, password = parts[0], parts[1], parts[2], ":".join(parts[3:])
        proxy_url = f"http://{user}:{password}@{ip}:{port}"
        return {"http": proxy_url, "https": proxy_url}
    return None


PROXY = parse_proxy(PROXY_RAW)

# Основные категории (можно расширить)
# Формат: "название": "URL путь"
CATEGORIES = {
    "zene": "zene",                    # Женщины
    "zene_odeca": "zene/odeca",         # Женская одежда
    "zene_haljine": "zene/odeca/haljine",      # Платья
    "zene_duksevi": "zene/odeca/duksevi_i_dzemperi",  # Свитера
    "zene_pantalone": "zene/odeca/pantalone_i_helanke",  # Брюки
    "zene_obuca": "zene/obuca",         # Женская обувь
    "muskarci": "muskarci",             # Мужчины
    "deca": "deca",                     # Дети
}

# Задержка между запросами (секунды) - чтобы не перегружать сайт
REQUEST_DELAY = 2

# Максимум страниц в категории для парсинга (0 = все)
MAX_PAGES_PER_CATEGORY = 10
