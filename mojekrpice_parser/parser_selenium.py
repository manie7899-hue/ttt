"""
Альтернативный парсер MOJEKRPICE с использованием Selenium.
Используйте этот вариант, если cloudscraper получает 403 от Cloudflare.

Установка: pip install selenium webdriver-manager selenium-wire
(selenium-wire нужен для прокси с авторизацией)
"""

import time
from urllib.parse import urljoin
from typing import Optional

from bs4 import BeautifulSoup
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

from config import BASE_URL, CATEGORIES, REQUEST_DELAY, PROXY

try:
    from seleniumwire import webdriver
    HAS_SELENIUM_WIRE = True
except ImportError:
    from selenium import webdriver
    HAS_SELENIUM_WIRE = False


def _create_driver(headless: bool) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
    )
    if HAS_SELENIUM_WIRE and PROXY:
        proxy_url = PROXY.get("http") or PROXY.get("https")
        return webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=opts,
            seleniumwire_options={"proxy": {"http": proxy_url, "https": proxy_url}},
        )
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=opts
    )


class MojekrpiceSeleniumParser:
    """Парсер через Selenium (обходит Cloudflare)"""

    def __init__(self, delay: float = REQUEST_DELAY, headless: bool = True):
        self.driver = _create_driver(headless)
        self.delay = delay

    def _get(self, url: str) -> Optional[BeautifulSoup]:
        try:
            full_url = url if url.startswith("http") else urljoin(BASE_URL, url)
            self.driver.get(full_url)
            time.sleep(self.delay + 2)  # Доп. время на загрузку JS
            return BeautifulSoup(self.driver.page_source, "html.parser")
        except Exception as e:
            print(f"[Ошибка] {url}: {e}")
            return None

    def close(self):
        self.driver.quit()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# Импорт логики из основного парсера
from parser import MojekrpiceParser


class MojekrpiceSeleniumFullParser(MojekrpiceParser):
    """Полный парсер с Selenium вместо requests (обходит Cloudflare)"""

    def __init__(self, delay: float = REQUEST_DELAY, headless: bool = True):
        self.delay = delay
        self.driver = _create_driver(headless)
        self.session = None

    def _get(self, url: str) -> Optional[BeautifulSoup]:
        try:
            full_url = url if url.startswith("http") else urljoin(BASE_URL, url)
            self.driver.get(full_url)
            time.sleep(self.delay + 2)
            return BeautifulSoup(self.driver.page_source, "html.parser")
        except Exception as e:
            print(f"[Ошибка] {url}: {e}")
            return None

    def close(self):
        self.driver.quit()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


if __name__ == "__main__":
    import sys
    category = sys.argv[1] if len(sys.argv) > 1 else "zene_haljine"
    parser = MojekrpiceSeleniumFullParser(headless=True)
    try:
        listings = parser.parse_category(category, max_pages=2, output_file="selenium_result.json")
        print(f"Найдено: {len(listings)}")
    finally:
        parser.close()
