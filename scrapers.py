"""
scrapers.py — Vinted · Vestiaire Collective · eBay · Leboncoin
Chaque scraper retourne une liste de dicts :
{
    title, price, url, image_url, brand, size, platform, description
}
"""

import re
import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from config import ALL_BRANDS, SIZES_MEN, SIZES_WOMEN

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "application/json, text/html, */*",
}

ALL_SIZES = SIZES_MEN + SIZES_WOMEN


def _sleep(): 
    time.sleep(random.uniform(1.2, 2.5))


def _parse_price(text: str) -> float | None:
    """Extrait un float depuis '455,00 €' ou '455.00'."""
    cleaned = re.sub(r"[^\d.,]", "", text).replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


# ─────────────────────────────────────────────────────────────────
#  VINTED
# ─────────────────────────────────────────────────────────────────

_vinted_session = None

def _get_vinted_session():
    global _vinted_session
    if _vinted_session is None:
        _vinted_session = requests.Session()
        _vinted_session.headers.update(HEADERS)
        try:
            _vinted_session.get("https://www.vinted.fr", timeout=10)
        except Exception:
            pass
    return _vinted_session


def scrape_vinted(brand: str, max_price: int = 2000) -> list[dict]:
    session = _get_vinted_session()
    results = []
    try:
        url = "https://www.vinted.fr/api/v2/catalog/items"
        params = {
            "search_text": brand,
            "per_page": 24,
            "page": 1,
            "order": "newest_first",
            "price_to": max_price,
        }
        resp = session.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            log.warning(f"Vinted {brand}: HTTP {resp.status_code}")
            return []

        data = resp.json()
        for item in data.get("items", []):
            price_raw = item.get("price", {})
            price = float(price_raw.get("amount", 0)) if isinstance(price_raw, dict) else 0.0
            if price <= 0:
                continue

            photos = item.get("photos", [])
            image_url = photos[0].get("url", "") if photos else ""

            results.append({
                "title":       item.get("title", ""),
                "price":       price,
                "url":         f"https://www.vinted.fr/items/{item['id']}",
                "image_url":   image_url,
                "brand":       item.get("brand_title", brand),
                "size":        item.get("size_title", ""),
                "description": item.get("description", ""),
                "platform":    "Vinted",
            })
    except Exception as e:
        log.error(f"Vinted scraper error ({brand}): {e}")
    _sleep()
    return results


# ─────────────────────────────────────────────────────────────────
#  VESTIAIRE COLLECTIVE
# ─────────────────────────────────────────────────────────────────

def scrape_vestiaire(brand: str, max_price: int = 2000) -> list[dict]:
    results = []
    try:
        url = "https://www.vestiairecollective.com/search/"
        params = {
            "q": brand,
            "priceMax": max_price,
            "order": "new",
        }
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        for card in soup.select("article[data-testid='product-card']")[:20]:
            title_el  = card.select_one("[data-testid='product-card-title']")
            price_el  = card.select_one("[data-testid='product-card-price']")
            link_el   = card.select_one("a[href]")
            img_el    = card.select_one("img")

            if not title_el or not price_el or not link_el:
                continue

            price = _parse_price(price_el.text)
            if not price:
                continue

            href = link_el["href"]
            full_url = href if href.startswith("http") else f"https://www.vestiairecollective.com{href}"
            image_url = img_el.get("src") or img_el.get("data-src", "") if img_el else ""

            results.append({
                "title":       title_el.text.strip(),
                "price":       price,
                "url":         full_url,
                "image_url":   image_url,
                "brand":       brand,
                "size":        "",
                "description": "",
                "platform":    "Vestiaire Collective",
            })
    except Exception as e:
        log.error(f"Vestiaire scraper error ({brand}): {e}")
    _sleep()
    return results


# ─────────────────────────────────────────────────────────────────
#  EBAY FRANCE
# ─────────────────────────────────────────────────────────────────

def scrape_ebay(brand: str, max_price: int = 2000) -> list[dict]:
    results = []
    try:
        url = "https://www.ebay.fr/sch/i.html"
        params = {
            "_nkw":   brand,
            "_sacat": "0",
            "_udhi":  max_price,
            "LH_ItemCondition": "1000|1500|2000|2500",  # neuf / très bon état
            "_sop":   "10",   # tri : nouveautés
        }
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        for item in soup.select(".s-item")[:20]:
            title_el = item.select_one(".s-item__title")
            price_el = item.select_one(".s-item__price")
            link_el  = item.select_one("a.s-item__link")
            img_el   = item.select_one("img.s-item__image-img")

            if not title_el or not price_el or not link_el:
                continue
            if "Shop on eBay" in title_el.text:
                continue

            price = _parse_price(price_el.text)
            if not price:
                continue

            image_url = img_el.get("src") or img_el.get("data-src", "") if img_el else ""

            results.append({
                "title":       title_el.text.strip(),
                "price":       price,
                "url":         link_el["href"],
                "image_url":   image_url,
                "brand":       brand,
                "size":        "",
                "description": title_el.text.strip(),
                "platform":    "eBay",
            })
    except Exception as e:
        log.error(f"eBay scraper error ({brand}): {e}")
    _sleep()
    return results


# ─────────────────────────────────────────────────────────────────
#  LEBONCOIN
# ─────────────────────────────────────────────────────────────────

def scrape_leboncoin(brand: str, max_price: int = 2000) -> list[dict]:
    results = []
    try:
        url = "https://www.leboncoin.fr/recherche"
        params = {
            "text":     brand,
            "category": "2",       # vêtements
            "price":    f"0-{max_price}",
            "shippable": "1",
        }
        headers = {**HEADERS, "Accept": "text/html,application/xhtml+xml,*/*"}
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        for card in soup.select("a[data-test-id='ad']")[:20]:
            title_el = card.select_one("[data-test-id='ad-title']")
            price_el = card.select_one("[data-test-id='price']")
            img_el   = card.select_one("img")

            if not title_el or not price_el:
                continue

            price = _parse_price(price_el.text)
            if not price:
                continue

            href = card.get("href", "")
            full_url = href if href.startswith("http") else f"https://www.leboncoin.fr{href}"
            image_url = img_el.get("src") or img_el.get("data-src", "") if img_el else ""

            results.append({
                "title":       title_el.text.strip(),
                "price":       price,
                "url":         full_url,
                "image_url":   image_url,
                "brand":       brand,
                "size":        "",
                "description": title_el.text.strip(),
                "platform":    "Leboncoin",
            })
    except Exception as e:
        log.error(f"Leboncoin scraper error ({brand}): {e}")
    _sleep()
    return results


# ─────────────────────────────────────────────────────────────────
#  DISPATCHER GLOBAL
# ─────────────────────────────────────────────────────────────────

def scrape_all(brand: str, max_price: int = 2000) -> list[dict]:
    results = []
    results += scrape_vinted(brand, max_price)
    results += scrape_vestiaire(brand, max_price)
    results += scrape_ebay(brand, max_price)
    results += scrape_leboncoin(brand, max_price)
    return results
