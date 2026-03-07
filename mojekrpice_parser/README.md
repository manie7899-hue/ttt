# Парсер MOJEKRPICE.rs

Парсер объявлений с сербского маркетплейса [mojekrpice.rs](https://mojekrpice.rs) с фильтрацией по:
- **Категории** — одежда, обувь, аксессуары и т.д.
- **Продавцам без репутации** — только объявления от пользователей с нулевыми отзывами, лайками, дизлайками и рейтингом

## Установка

```bash
pip install -r requirements.txt
```

## Использование

### Миниприложение (GUI)

```bash
python app.py
```

Или двойной клик по `run_app.bat`

В окне можно указать:
- **Категорию** — из выпадающего списка
- **Количество страниц** — сколько страниц категории парсить (0 = все)
- **Задержку** — пауза между запросами в секундах
- **Файл вывода** — куда сохранить результат (JSON)
- **Прокси** — при необходимости (формат: ip:port:user:password)

### Командная строка

```bash
# Парсинг категории "Платья" (zene_haljine), сохранить в listings.json
python parser.py zene_haljine -o listings.json

# Парсинг с ограничением в 5 страниц
python parser.py zene_haljine -o output.json -p 5

# Список доступных категорий
python parser.py --help
```

### Из Python

```python
from parser import MojekrpiceParser
from config import CATEGORIES

parser = MojekrpiceParser(delay=2)
listings = parser.parse_category("zene_haljine", max_pages=3, output_file="result.json")
print(f"Найдено {len(listings)} объявлений от продавцов без отзывов")
```

## Категории

| Ключ | Описание |
|------|----------|
| `zene` | Женщины (всё) |
| `zene_odeca` | Женская одежда |
| `zene_haljine` | Платья |
| `zene_duksevi` | Свитера и джемперы |
| `zene_pantalone` | Брюки |
| `zene_obuca` | Женская обувь |
| `muskarci` | Мужчины |
| `deca` | Дети |

Добавить категорию можно в `config.py`.

## Важно: Cloudflare

Сайт защищён Cloudflare. Если основной парсер получает 403:

1. **Selenium-вариант** (рекомендуется):
   ```bash
   pip install selenium webdriver-manager
   python parser_selenium.py zene_haljine
   ```

2. Увеличьте `REQUEST_DELAY` в `config.py`

3. Используйте VPN или другой IP

## Структура результата

```json
[
  {
    "title": "Crvena haljina S veličina",
    "url": "https://mojekrpice.rs/items/zene/13250983/...",
    "price": "2000 RSD",
    "item_id": "13250983",
    "category": "zene",
    "seller_username": "mundijal-12345",
    "seller_profile_url": "https://mojekrpice.rs/mundijal-12345/",
    "city": "Sremski Karlovci"
  }
]
```
