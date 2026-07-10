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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
]

BRANDS = ["Pro Plan", "Royal Canin", "N&D", "Felicia", "Reflex", "Trendline", "Mito", "Bio PetActive", "Eastland", "GimCat", "Felix", "Acana", "Orijen", "Hill's", "Trixie", "Ever Clean"]

def get_random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive"
    }

def clean_scraped_title(title):
    cleaned = re.sub(
        r"\b(Trendyol|n11|Hepsiburada|Çiçeksepeti|Amazon|fiyatı|fiyatları|satın al|satın|al|kapıda ödeme|kargo bedava)\b",
        "",
        title,
        flags=re.IGNORECASE
    ).strip()
    cleaned = re.sub(r"[\s\-\|:]+$", "", cleaned)
    cleaned = re.sub(r"^[\s\-\|:]+", "", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned

def deduce_category_from_title(title):
    lower_name = title.lower()
    if "mama" in lower_name or "konserve" in lower_name or "pate" in lower_name or "kitten" in lower_name or "sterilised" in lower_name:
        if "köpek" in lower_name:
            return "Köpek Maması"
        return "Kedi Maması"
    elif "kum" in lower_name or "litter" in lower_name:
        return "Kum"
    elif "tasma" in lower_name or "yata" in lower_name or "kap" in lower_name or "tarak" in lower_name:
        return "Aksesuar"
    elif "vitamin" in lower_name or "macun" in lower_name or "damla" in lower_name or "ödül" in lower_name:
        return "Ödül/Vitamin"
    elif "oyuncak" in lower_name or "top" in lower_name or "oltab" in lower_name:
        return "Oyuncak"
    return "Diğer"

def scrape_barcode_online(barcode):
    """
    Scrapes barcode details online (Google Search and Trendyol).
    If it succeeds: prints '[OK] İnternetten Çekildi: [Name]' and returns it.
    If it fails/blocked: prints '[BAĞLANTI/BOT ENGELİ] Yerel Kütüphaneye Soruluyor...'
    and queries the local offline catalog 'hazir_urunler' table.
    """
    # 1. Direct check in mock DB (for immediate dev matching)
    if barcode in MOCK_BARCODES:
        prod = MOCK_BARCODES[barcode]
        print(f"[OK] İnternetten Çekildi (Mock DB): {prod['ad']}")
        return prod

    # 2. Try Online Google Search
    google_success = False
    scraped_title = None
    scraped_cat = None
    
    try:
        url = f"https://www.google.com/search?q={barcode}+pet+shop"
        response = requests.get(url, headers=get_random_headers(), timeout=5)
        
        if response.status_code == 200 and "captcha" not in response.text.lower():
            soup = BeautifulSoup(response.text, "html.parser")
            h3_tags = soup.find_all("h3")
            titles = [h3.get_text() for h3 in h3_tags if len(h3.get_text()) > 5]
            
            if titles:
                best_title = None
                best_score = -1
                for t in titles:
                    score = 0
                    t_lower = t.lower()
                    for brand in BRANDS:
                        if brand.lower() in t_lower:
                            score += 10
                    for term in ["mama", "kum", "tasma", "macun", "vitamin", "oyuncak", "kitten", "yavru", "kısır", "sterilised"]:
                        if term in t_lower:
                            score += 5
                    if score > best_score:
                        best_score = score
                        best_title = t
                
                if best_title and best_score > 0:
                    scraped_title = clean_scraped_title(best_title)
                    scraped_cat = deduce_category_from_title(scraped_title)
                    google_success = True
    except Exception:
        pass

    # 3. Try Online Trendyol Fallback
    if not google_success:
        try:
            trendyol_url = f"https://www.trendyol.com/sr?q={barcode}"
            response = requests.get(trendyol_url, headers=get_random_headers(), timeout=5)
            
            if response.status_code == 200 and "captcha" not in response.text.lower():
                soup = BeautifulSoup(response.text, "html.parser")
                brand_elem = soup.find(class_="prdct-desc-cntnr-brand")
                name_elem = soup.find(class_="prdct-desc-cntnr-name")
                
                if brand_elem and name_elem:
                    full_title = f"{brand_elem.get_text().strip()} {name_elem.get_text().strip()}"
                    scraped_title = clean_scraped_title(full_title)
                    scraped_cat = deduce_category_from_title(scraped_title)
                    google_success = True
                else:
                    # Direct product page check
                    product_detail_h1 = soup.find("h1", class_="pr-new-br")
                    if product_detail_h1:
                        full_title = product_detail_h1.get_text().strip()
                        scraped_title = clean_scraped_title(full_title)
                        scraped_cat = deduce_category_from_title(scraped_title)
                        google_success = True
        except Exception:
            pass

    # 4. Handle Result or Query Local Library
    if google_success and scraped_title and len(scraped_title) >= 10:
        print(f"[OK] İnternetten Çekildi: {scraped_title}")
        return {
            "ad": scraped_title,
            "kategori": scraped_cat,
            "fiyat": round(random.uniform(95.0, 480.0), 2),
            "gorsel_url": "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"
        }
    else:
        print("[BAĞLANTI/BOT ENGELİ] Yerel Kütüphaneye Soruluyor...")
        # Query local hazir_urunler catalog
        try:
            from database import get_db_connection
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM hazir_urunler WHERE barkod = ?", (barcode,))
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
            
        print("[BİLİNMİYOR] Ürün ne internette ne de yerel kütüphanede bulunamadı.")
        return None
