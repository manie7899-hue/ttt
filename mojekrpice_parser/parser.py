"""
Парсер MOJEKRPICE.rs
Собирает объявления от продавцов БЕЗ отзывов, лайков, дизлайков и рейтинга.
Фильтрация по категориям.
"""

import re
import time
import json
from urllib.parse import urljoin
from dataclasses import dataclass, asdict
from typing import Optional, Callable

import cloudscraper
from bs4 import BeautifulSoup

from config import BASE_URL, CATEGORIES, REQUEST_DELAY, MAX_PAGES_PER_CATEGORY, PROXY


@dataclass
class Listing:
    """Объявление с MOJEKRPICE"""
    title: str
    url: str
    price: str
    item_id: str
    category: str
    seller_username: str
    seller_profile_url: str
    city: str
    added_date: str = ""


@dataclass 
class SellerStats:
    """Статистика продавца"""
    positive_feedback: int
    negative_feedback: int
    followers: int
    following: int
    has_rating: bool = False  # Есть ли рейтинг/отзывы


class MojekrpiceParser:
    """Парсер маркетплейса MOJEKRPICE"""
    
    def __init__(self, delay: float = REQUEST_DELAY, proxy: dict | None = None):
        self.scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "desktop": True}
        )
        self.delay = delay
        self.session = self.scraper
        self.proxy = proxy if proxy is not None else PROXY
        
    def _get(self, url: str) -> Optional[BeautifulSoup]:
        """GET запрос с задержкой и парсингом HTML"""
        try:
            full_url = url if url.startswith("http") else urljoin(BASE_URL, url)
            kwargs = {
                "timeout": 30,
                "headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "sr,en;q=0.9",
                },
            }
            if self.proxy:
                kwargs["proxies"] = self.proxy
            resp = self.session.get(full_url, **kwargs)
            resp.raise_for_status()
            time.sleep(self.delay)
            return BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            print(f"[Ошибка] {url}: {e}")
            return None
    
    def _extract_feedback_numbers(self, text: str) -> tuple[int, int]:
        """Извлекает пару (положительные, отрицательные) отзывы из текста"""
        # На странице feedback: [12] [0] - два числа
        numbers = re.findall(r'\d+', text)
        if len(numbers) >= 2:
            return int(numbers[0]), int(numbers[1])
        if len(numbers) == 1:
            return int(numbers[0]), 0
        return 0, 0
    
    def get_seller_stats(self, profile_url: str) -> Optional[SellerStats]:
        """
        Проверяет страницу отзывов продавца.
        Возвращает SellerStats или None при ошибке.
        """
        # Страница feedback: /username-id/feedback
        if not profile_url.endswith("/feedback"):
            profile_url = profile_url.rstrip("/") + "/feedback"
            
        soup = self._get(profile_url)
        if not soup:
            return None
            
        # Ищем блок с отзывами - обычно два числа [положительные] [отрицательные]
        # Селекторы могут потребовать корректировки под актуальный HTML
        feedback_section = soup.find(class_=re.compile(r"feedback|utisci|rating", re.I))
        if not feedback_section:
            feedback_section = soup
            
        text = feedback_section.get_text()
        pos, neg = self._extract_feedback_numbers(text)
        
        # Подсчёт followers/following
        followers = 0
        following = 0
        for match in re.finditer(r'(\d+)\s*(?:sledbenik|follower|follow)', text, re.I):
            if "follow" in text[max(0, match.start()-50):match.start()].lower():
                following = int(match.group(1))
            else:
                followers = int(match.group(1))
                
        # "27 sledbenika" "19 follovs" - из контента страницы
        sledbenik = re.search(r'(\d+)\s*sledbenik', text, re.I)
        if sledbenik:
            followers = int(sledbenik.group(1))
        follov = re.search(r'(\d+)\s*follov', text, re.I)
        if follov:
            following = int(follov.group(1))
        
        has_rating = (pos > 0 or neg > 0 or followers > 0)
        
        return SellerStats(
            positive_feedback=pos,
            negative_feedback=neg,
            followers=followers,
            following=following,
            has_rating=has_rating
        )
    
    def is_clean_seller(self, stats: SellerStats, strict: bool = False) -> bool:
        """
        Продавец без отзывов, дизлайков, рейтинга.
        Учитываются: followers (подписчики), отзывы.
        strict=True: также требует 0 following.
        """
        if strict:
            return (
                stats.positive_feedback == 0 and
                stats.negative_feedback == 0 and
                stats.followers == 0 and
                stats.following == 0
            )
        return (
            stats.positive_feedback == 0 and
            stats.negative_feedback == 0 and
            stats.followers == 0
        )
    
    def get_item_listings(self, category_path: str, max_pages: int = MAX_PAGES_PER_CATEGORY) -> list[dict]:
        """Получает список объявлений со страниц категории"""
        listings = []
        page = 1
        
        while True:
            url = f"{BASE_URL}/{category_path}"
            if page > 1:
                url += f"?page={page}"
                
            soup = self._get(url)
            if not soup:
                break
                
            # Ссылки на объявления: /items/zene/13250983/crvena-haljina-s-velicina
            item_links = soup.find_all("a", href=re.compile(r"/items/[^/]+/\d+/"))
            if not item_links:
                break
                
            seen_ids = set()
            for a in item_links:
                href = a.get("href", "")
                match = re.search(r"/items/([^/]+)/(\d+)/", href)
                if not match:
                    continue
                item_id = match.group(2)
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
                
                title = (a.get_text(strip=True) or "").split("\n")[0]
                # Цена обычно в соседнем элементе
                parent = a.find_parent(["div", "li", "article"])
                price = ""
                if parent:
                    price_elem = parent.find(string=re.compile(r"\d+\s*RSD"))
                    if price_elem:
                        price = price_elem.strip()
                
                listings.append({
                    "url": urljoin(BASE_URL, href),
                    "title": title,
                    "item_id": item_id,
                    "price": price,
                    "category": match.group(1),
                })
            
            if max_pages and page >= max_pages:
                break
            page += 1
            # Проверка наличия следующей страницы
            next_link = soup.find("a", href=re.compile(rf"page={page}"))
            if not next_link:
                break
                
        return listings
    
    def get_listing_details(self, item_url: str) -> Optional[dict]:
        """
        Получает детали объявления: продавец, город, ссылка на профиль.
        """
        soup = self._get(item_url)
        if not soup:
            return None
            
        # Ищем ссылку на профиль продавца (формат: /username-12345/ — типичный для MOJEKRPICE)
        EXCLUDED_PATHS = ("members", "login", "register", "conversations", "forum", "items", "search", "help", "about", "services", "logout")

        def is_seller_profile(href: str) -> bool:
            if not href or not href.startswith("/"):
                return False
            part = href.strip("/").split("/")[0]
            if not part or part.lower() in EXCLUDED_PATHS:
                return False
            # Профиль продавца: username-12345 (цифры в конце)
            return bool(re.match(r"^[a-zA-Z0-9_-]+-\d+$", part))

        seller_link = None
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if is_seller_profile(href):
                seller_link = a
                break

        seller_username = ""
        seller_profile_url = ""
        if seller_link:
            href = seller_link.get("href", "")
            seller_username = href.strip("/").split("/")[0]
            seller_profile_url = urljoin(BASE_URL, href)
                            
        # Город
        city = ""
        city_elem = soup.find(string=re.compile(r"^(Belgrade|Novi Sad|Niš|Sremski|Beograd|[A-Za-zćčžšđ\s]+)$"))
        if city_elem:
            city = city_elem.strip()
        for s in soup.find_all(string=re.compile(r"Grad:|City:")):
            next_sib = s.find_next_sibling() or s.find_next()
            if next_sib:
                city = next_sib.get_text(strip=True) if hasattr(next_sib, "get_text") else str(next_sib)
                break

        # Лайки/избранное на объявлении (ссылка /items/.../favorites)
        item_favorites = 0
        fav_link = soup.find("a", href=re.compile(r"/items/.*/favorites"))
        if fav_link:
            fav_text = fav_link.get_text(strip=True)
            if fav_text.isdigit():
                item_favorites = int(fav_text)
                
        return {
            "seller_username": seller_username,
            "seller_profile_url": seller_profile_url,
            "city": city,
            "item_favorites": item_favorites,
        }
    
    def parse_category(
        self,
        category_key: str,
        max_pages: int = MAX_PAGES_PER_CATEGORY,
        output_file: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        stop_check: Optional[Callable[[], bool]] = None,
    ) -> list[dict]:
        """
        Парсит категорию и возвращает только объявления от «чистых» продавцов
        (без отзывов, лайков, дизлайков, рейтинга).
        progress_callback(current, total, message) — опционально для GUI.
        """
        def log(msg: str):
            if progress_callback:
                progress_callback(0, 0, msg)
            else:
                print(msg)

        if category_key not in CATEGORIES:
            log(f"Категория '{category_key}' не найдена. Доступные: {list(CATEGORIES.keys())}")
            return []
            
        category_path = CATEGORIES[category_key]
        log(f"Парсинг категории: {category_key} ({category_path})")
        
        listings = self.get_item_listings(category_path, max_pages)
        log(f"Найдено объявлений: {len(listings)}")
        
        clean_listings = []
        checked_sellers = {}  # username -> is_clean
        
        for i, item in enumerate(listings):
            if stop_check and stop_check():
                log("Остановлено пользователем")
                break
            msg = f"[{i+1}/{len(listings)}] {item['title'][:50]}..."
            if progress_callback:
                progress_callback(i + 1, len(listings), msg)
            else:
                print(msg)
            
            details = self.get_listing_details(item["url"])
            if not details or not details["seller_profile_url"]:
                if progress_callback:
                    progress_callback(i + 1, len(listings), msg + " → пропуск (нет данных продавца)")
                else:
                    print("    -> Не удалось получить данные продавца, пропуск")
                continue
                
            # Лайки на объявлении — пропускаем, если есть
            if details.get("item_favorites", 0) > 0:
                if progress_callback:
                    progress_callback(i + 1, len(listings), msg + " → пропуск (есть лайки)")
                else:
                    print("    -> Пропуск: есть лайки на объявлении")
                continue

            username = details["seller_username"]
            if username in checked_sellers:
                if not checked_sellers[username]:
                    continue
            else:
                stats = self.get_seller_stats(details["seller_profile_url"])
                if not stats:
                    if progress_callback:
                        progress_callback(i + 1, len(listings), msg + " → пропуск (ошибка проверки)")
                    else:
                        print("    -> Не удалось проверить продавца, пропуск")
                    continue
                is_clean = self.is_clean_seller(stats)
                checked_sellers[username] = is_clean
                if not is_clean:
                    continue
                    
            listing = {
                **item,
                **details,
                "seller_positive": 0,
                "seller_negative": 0,
                "seller_followers": 0,
                "seller_following": 0,
            }
            clean_listings.append(listing)
            if progress_callback:
                progress_callback(i + 1, len(listings), msg + " ✓ OK")
            else:
                print(f"    -> OK (продавец без отзывов)")
            
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(clean_listings, f, ensure_ascii=False, indent=2)
            done_msg = f"Сохранено в {output_file}: {len(clean_listings)} объявлений"
            if progress_callback:
                progress_callback(len(listings), len(listings), done_msg)
            else:
                print(f"\n{done_msg}")
            
        return clean_listings


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Парсер MOJEKRPICE - объявления от продавцов без отзывов")
    parser.add_argument("category", choices=list(CATEGORIES.keys()), help="Ключ категории")
    parser.add_argument("-o", "--output", default="listings.json", help="Файл для сохранения")
    parser.add_argument("-p", "--pages", type=int, default=3, help="Макс. страниц в категории")
    args = parser.parse_args()
    
    p = MojekrpiceParser()
    p.parse_category(args.category, max_pages=args.pages, output_file=args.output)


if __name__ == "__main__":
    main()
