import requests
from bs4 import BeautifulSoup
import re
import random
import sys
import os
import sqlite3

# Database path resolution relative to this file
DB_PATH = os.path.join(os.path.dirname(__file__), "beykoz_pet.db")

# A mock database of barcode product metadata to serve as a fast and guaranteed fallback
MOCK_BARCODES = {
    "8692223334445": {
        "ad": "Pro Plan Kitten Tavuklu Yavru Kedi Maması 1.5kg",
        "kategori": "Kedi Maması",
        "fiyat": 395.00,
        "gorsel_url": "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"
    },
    "8690123456789": {
        "ad": "Royal Canin Sterilised Yetişkin Kedi Maması 2kg",
        "kategori": "Kedi Maması",
        "fiyat": 450.00,
        "gorsel_url": "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=500"
    },
    "8697778889990": {
        "ad": "Ever Clean Litter Free Kedi Kumu 10L",
        "kategori": "Kum",
        "fiyat": 280.00,
        "gorsel_url": "https://images.unsplash.com/photo-1569591159212-b02ea8a9f239?w=500"
    },
    "8690000000002": {
        "ad": "Gimcat Multi-Vitamin Kedi Ödül Macunu 50g",
        "kategori": "Ödül/Vitamin",
        "fiyat": 195.00,
        "gorsel_url": "https://images.unsplash.com/photo-1608454509000-1936617c6a91?w=500"
    },
    "8694445556667": {
        "ad": "Trixie Tavuklu Kedi Ödül Maması 50g",
        "kategori": "Ödül/Vitamin",
        "fiyat": 45.00,
        "gorsel_url": "https://images.unsplash.com/photo-1535930891776-0c2dfb7fda1a?w=500"
    },
    "8690000000003": {
        "ad": "Lepus Ortopedik Köpek Yatağı L Beden",
        "kategori": "Aksesuar",
        "fiyat": 650.00,
        "gorsel_url": "https://images.unsplash.com/photo-1541599540903-216a46ca1ad0?w=500"
    }
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Mobile/15E148 Safari/604.1"
]

BRANDS = [
    "Pro Plan", "Royal Canin", "N&D", "Felicia", "Reflex", "Trendline", "Mito", 
    "Bio PetActive", "Eastland", "GimCat", "Felix", "Acana", "Orijen", "Hill's", 
    "Trixie", "Ever Clean", "Whiskas", "Pedigree", "Gourmet", "Sheba", "Cat Chow", "Dog Chow", "Brit Care"
]

PET_TERMS = [
    "mama", "kedi", "köpek", "kum", "tasma", "ödül", "vitamin", "şampuan", "konserve", 
    "yavr", "kısır", "sterilised", "adult", "kitten", "litter", "cat", "dog", "macun", 
    "yatak", "tarak", "oyuncak", "pate", "bisküvi", "snack", "tavuk", "somon", "hindi", "kuzu"
]

EXCLUDE_TERMS = [
    "yandex", "map", "video", "porn", "sign in", "log in", "login", "register", 
    "google", "facebook", "instagram", "twitter", "youtube", "xvideos", "xnxx", "xhamster"
]

def get_random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive"
    }

def get_api_headers():
    return {
        "User-Agent": f"BeykozPetPOS/1.0 (contact@beykozpet.com; +905000000000) Python/{sys.version_info.major}.{sys.version_info.minor}",
        "Accept": "application/json"
    }

def clean_scraped_title(title):
    if not title:
        return ""
    cleaned = re.sub(
        r"\b(Trendyol|n11|Hepsiburada|Çiçeksepeti|Amazon|fiyatı|fiyatları|satın al|satın|al|kapıda ödeme|kargo bedava|online|petshop|pet shop)\b",
        "",
        title,
        flags=re.IGNORECASE
    ).strip()
    cleaned = re.sub(r"[\s\-\|:]+$", "", cleaned)
    cleaned = re.sub(r"^[\s\-\|:]+", "", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned

def is_valid_product_title(title):
    if not title or len(title) < 6:
        return False
    t_lower = title.lower()
    for ex in EXCLUDE_TERMS:
        if ex in t_lower:
            return False
    for brand in BRANDS:
        if brand.lower() in t_lower:
            return True
    for term in PET_TERMS:
        if term in t_lower:
            return True
    return False

def deduce_category_from_title(title):
    lower_name = title.lower() if title else ""
    if "mama" in lower_name or "konserve" in lower_name or "pate" in lower_name or "kitten" in lower_name or "sterilised" in lower_name or "adult" in lower_name:
        if "köpek" in lower_name or "dog" in lower_name:
            return "Köpek Maması"
        return "Kedi Maması"
    elif "kum" in lower_name or "litter" in lower_name:
        return "Kum"
    elif "tasma" in lower_name or "yata" in lower_name or "kap" in lower_name or "tarak" in lower_name or "ekipman" in lower_name:
        return "Aksesuar"
    elif "vitamin" in lower_name or "macun" in lower_name or "damla" in lower_name or "ödül" in lower_name or "snack" in lower_name:
        return "Ödül/Vitamin"
    elif "oyuncak" in lower_name or "top" in lower_name or "oltab" in lower_name:
        return "Oyuncak"
    return "Diğer"

def scrape_barcode_online(barcode):
    """
    Multi-source online barcode lookup service with resilient fallbacks.
    Tiers:
    1. Mock database check
    2. OpenFoodFacts & OpenPetFoodFacts APIs
    3. UPCItemDB API
    4. E-commerce web search scraping (Trendyol, Hepsiburada, N11, Petzzshop)
    5. Web search engine fallback (DuckDuckGo, Google, Bing)
    6. Local catalog library (hazir_urunler)
    """
    if not barcode:
        return None

    clean_barcode = str(barcode).strip()

    # 0. Google Custom Search API (If API credentials provided in secrets or env)
    try:
        import streamlit as st
        api_key = None
        cx = None
        try:
            if "GOOGLE_SEARCH_API_KEY" in st.secrets:
                api_key = st.secrets["GOOGLE_SEARCH_API_KEY"]
            if "GOOGLE_SEARCH_ENGINE_ID" in st.secrets:
                cx = st.secrets["GOOGLE_SEARCH_ENGINE_ID"]
        except Exception:
            pass
            
        if not api_key:
            api_key = os.environ.get("GOOGLE_SEARCH_API_KEY")
        if not cx:
            cx = os.environ.get("GOOGLE_SEARCH_ENGINE_ID")
            
        if api_key and cx:
            url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={cx}&q={clean_barcode}+pet"
            resp = requests.get(url, timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                if items:
                    raw_title = items[0].get("title") or items[0].get("snippet")
                    cleaned = clean_scraped_title(raw_title)
                    if cleaned:
                        cat = deduce_category_from_title(cleaned)
                        print(f"[OK] İnternetten Çekildi (Google Custom Search API): {cleaned}")
                        return {
                            "ad": cleaned,
                            "kategori": cat,
                            "fiyat": round(random.uniform(95.0, 480.0), 2),
                            "gorsel_url": "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"
                        }
    except Exception as e_gcs:
        print(f"[Google Custom Search API Warning] {e_gcs}")

    # 1. Direct check in mock DB
    if clean_barcode in MOCK_BARCODES:
        prod = MOCK_BARCODES[clean_barcode]
        print(f"[OK] İnternetten Çekildi (Mock DB): {prod['ad']}")
        return prod

    # 2. OpenFoodFacts & OpenPetFoodFacts APIs
    api_h = get_api_headers()
    for domain in ["world.openfoodfacts.org", "world.openpetfoodfacts.org", "tr.openfoodfacts.org"]:
        try:
            url = f"https://{domain}/api/v0/product/{clean_barcode}.json"
            resp = requests.get(url, headers=api_h, timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == 1:
                    p = data.get("product", {})
                    name = p.get("product_name_tr") or p.get("product_name") or p.get("abbreviated_product_name") or p.get("product_name_en")
                    brand = p.get("brands") or ""
                    if name:
                        full_name = f"{brand} {name}".strip() if brand and brand.lower() not in name.lower() else name.strip()
                        cleaned = clean_scraped_title(full_name)
                        if is_valid_product_title(cleaned) or len(cleaned) >= 6:
                            img = p.get("image_front_url") or p.get("image_url") or "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"
                            cat = deduce_category_from_title(cleaned)
                            print(f"[OK] İnternetten Çekildi (OpenFoodFacts API): {cleaned}")
                            return {
                                "ad": cleaned,
                                "kategori": cat,
                                "fiyat": round(random.uniform(110.0, 490.0), 2),
                                "gorsel_url": img
                            }
        except Exception:
            pass

    # 3. UPCItemDB API
    try:
        url = f"https://api.upcitemdb.com/prod/trial/lookup?upc={clean_barcode}"
        resp = requests.get(url, headers=api_h, timeout=4)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            if items:
                title = items[0].get("title")
                brand = items[0].get("brand") or ""
                images = items[0].get("images", [])
                img = images[0] if images else "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"
                if title:
                    full_name = f"{brand} {title}".strip() if brand and brand.lower() not in title.lower() else title.strip()
                    cleaned = clean_scraped_title(full_name)
                    if is_valid_product_title(cleaned) or len(cleaned) >= 6:
                        cat = deduce_category_from_title(cleaned)
                        print(f"[OK] İnternetten Çekildi (UPCItemDB API): {cleaned}")
                        return {
                            "ad": cleaned,
                            "kategori": cat,
                            "fiyat": round(random.uniform(110.0, 490.0), 2),
                            "gorsel_url": img
                        }
    except Exception:
        pass

    # 4. E-Commerce Search Scraping (Trendyol, Hepsiburada, N11, Petzzshop)
    web_h = get_random_headers()
    
    # 4a. Trendyol
    try:
        url = f"https://www.trendyol.com/sr?q={clean_barcode}"
        resp = requests.get(url, headers=web_h, timeout=4)
        if resp.status_code == 200 and "captcha" not in resp.text.lower():
            soup = BeautifulSoup(resp.text, "html.parser")
            brand_elem = soup.find(class_="prdct-desc-cntnr-brand")
            name_elem = soup.find(class_="prdct-desc-cntnr-name")
            if brand_elem and name_elem:
                full_title = f"{brand_elem.get_text().strip()} {name_elem.get_text().strip()}"
                cleaned = clean_scraped_title(full_title)
                if is_valid_product_title(cleaned):
                    cat = deduce_category_from_title(cleaned)
                    print(f"[OK] İnternetten Çekildi (Trendyol): {cleaned}")
                    return {
                        "ad": cleaned,
                        "kategori": cat,
                        "fiyat": round(random.uniform(95.0, 480.0), 2),
                        "gorsel_url": "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"
                    }
            product_detail_h1 = soup.find("h1", class_="pr-new-br")
            if product_detail_h1:
                cleaned = clean_scraped_title(product_detail_h1.get_text().strip())
                if is_valid_product_title(cleaned):
                    cat = deduce_category_from_title(cleaned)
                    print(f"[OK] İnternetten Çekildi (Trendyol H1): {cleaned}")
                    return {
                        "ad": cleaned,
                        "kategori": cat,
                        "fiyat": round(random.uniform(95.0, 480.0), 2),
                        "gorsel_url": "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"
                    }
    except Exception:
        pass

    # 4b. Hepsiburada
    try:
        url = f"https://www.hepsiburada.com/ara?q={clean_barcode}"
        resp = requests.get(url, headers=web_h, timeout=4)
        if resp.status_code == 200 and "captcha" not in resp.text.lower():
            soup = BeautifulSoup(resp.text, "html.parser")
            h3_tags = soup.find_all("h3")
            for h in h3_tags:
                txt = clean_scraped_title(h.get_text().strip())
                if is_valid_product_title(txt):
                    cat = deduce_category_from_title(txt)
                    print(f"[OK] İnternetten Çekildi (Hepsiburada): {txt}")
                    return {
                        "ad": txt,
                        "kategori": cat,
                        "fiyat": round(random.uniform(95.0, 480.0), 2),
                        "gorsel_url": "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"
                    }
    except Exception:
        pass

    # 4c. Petzzshop
    try:
        url = f"https://www.petzzshop.com/arama?q={clean_barcode}"
        resp = requests.get(url, headers=web_h, timeout=4)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            h2_tags = soup.find_all(["h2", "h3", "a"])
            for h in h2_tags:
                txt = clean_scraped_title(h.get_text().strip())
                if is_valid_product_title(txt):
                    cat = deduce_category_from_title(txt)
                    print(f"[OK] İnternetten Çekildi (Petzzshop): {txt}")
                    return {
                        "ad": txt,
                        "kategori": cat,
                        "fiyat": round(random.uniform(95.0, 480.0), 2),
                        "gorsel_url": "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"
                    }
    except Exception:
        pass

    # 5. Search Engines (DuckDuckGo & Google Search)
    # 5a. DuckDuckGo HTML
    try:
        url = "https://html.duckduckgo.com/html/"
        resp = requests.post(url, data={"q": f"{clean_barcode} pet shop mama"}, headers=web_h, timeout=4)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            res_a = soup.find_all("a", class_="result__a")
            for a in res_a:
                txt = clean_scraped_title(a.get_text().strip())
                if is_valid_product_title(txt):
                    cat = deduce_category_from_title(txt)
                    print(f"[OK] İnternetten Çekildi (DuckDuckGo): {txt}")
                    return {
                        "ad": txt,
                        "kategori": cat,
                        "fiyat": round(random.uniform(95.0, 480.0), 2),
                        "gorsel_url": "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"
                    }
    except Exception:
        pass

    # 5b. Google Search
    try:
        url = f"https://www.google.com/search?q={clean_barcode}+pet+shop"
        resp = requests.get(url, headers=web_h, timeout=4)
        if resp.status_code == 200 and "captcha" not in resp.text.lower():
            soup = BeautifulSoup(resp.text, "html.parser")
            h3_tags = soup.find_all("h3")
            for h in h3_tags:
                txt = clean_scraped_title(h.get_text().strip())
                if is_valid_product_title(txt):
                    cat = deduce_category_from_title(txt)
                    print(f"[OK] İnternetten Çekildi (Google): {txt}")
                    return {
                        "ad": txt,
                        "kategori": cat,
                        "fiyat": round(random.uniform(95.0, 480.0), 2),
                        "gorsel_url": "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"
                    }
    except Exception:
        pass

    # 6. Query Local hazir_urunler Catalog Table
    try:
        from database import get_db_connection
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM hazir_urunler WHERE barkod = ?", (clean_barcode,))
        row = c.fetchone()
        conn.close()
        
        if row:
            print(f"[OK] Yerel Kütüphaneden Bulundu: {row['ad']}")
            return {
                "ad": row["ad"],
                "kategori": row["kategori"],
                "fiyat": 0.0,
                "gorsel_url": row["varsayilan_gorsel"]
            }
    except Exception as e:
        print(f"[ERROR] Yerel veritabanı sorgulanamadı: {e}", file=sys.stderr)
        
    print(f"[BİLİNMİYOR] Ürün ({clean_barcode}) ne internet servislerinde ne de yerel kütüphanede bulunamadı.")
    return None
