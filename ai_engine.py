import os
import json
import random
import re
try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

def clean_scraped_data_with_ai(scraped_data):
    """
    Cleans raw scraped product titles and attributes.
    If an API key is available, it uses Gemini to perform natural language cleanup.
    Otherwise, it applies a rule-based text formatter.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if HAS_GENAI and api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = (
                "Sen bir petshop veri düzenleme asistanısın. Aşağıdaki ham ürün verisini al. "
                "Ürün adını gereksiz SEO kelimelerinden temizle, markasını düzgün yaz (örn: 'royal canin kedi maması' -> 'Royal Canin Kedi Maması'), "
                "kategorisini ('Kedi Maması', 'Köpek Maması', 'Kum', 'Aksesuar', 'Ödül/Vitamin', 'Oyuncak', 'Diğer') kelimelerinden biri olarak belirle. "
                "Yanıtı SADECE geçerli bir JSON olarak ver. JSON formatı: {\"ad\": \"temizlenmiş ad\", \"kategori\": \"kategori\"}\n\n"
                f"Ham Veri: {json.dumps(scraped_data, ensure_ascii=False)}"
            )
            response = model.generate_content(prompt)
            text = response.text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            cleaned_json = json.loads(text)
            scraped_data["ad"] = cleaned_json.get("ad", scraped_data["ad"])
            scraped_data["kategori"] = cleaned_json.get("kategori", scraped_data["kategori"])
            return scraped_data
        except Exception as e:
            print(f"Gemini cleaning failed, falling back to local clean-up: {e}")
            
    # Local clean-up logic (fallback)
    ad = scraped_data.get("ad", "")
    ad = re_clean_name(ad)
    
    # Fix casing for brands
    for brand in ["Pro Plan", "Royal Canin", "N&D", "Felicia", "Reflex", "Trendline", "Mito", "Bio PetActive", "GimCat", "Felix", "Trixie", "Ever Clean", "Acana", "Orijen", "Hill's"]:
        if brand.lower() in ad.lower():
            pattern = re.compile(re.escape(brand), re.IGNORECASE)
            ad = pattern.sub(brand, ad)
            
    scraped_data["ad"] = ad
    return scraped_data

def re_clean_name(name):
    # Remove e-commerce indicators
    name = re.sub(r"\b(Trendyol|n11|Hepsiburada|Çiçeksepeti|Amazon|fiyatı|fiyatları|satın al|satın|al|kapıda ödeme)\b", "", name, flags=re.IGNORECASE).strip()
    name = re.sub(r"[\s\-\|:]+$", "", name)
    name = re.sub(r"^[\s\-\|:]+", "", name)
    name = " ".join(name.split())
    words = name.split()
    capitalized_words = [w.capitalize() if not w.isupper() else w for w in words]
    return " ".join(capitalized_words)

def get_smart_recommendations(cart_items, db_products=None):
    """
    Given the current cart items, return 2-3 recommended items.
    GUARANTEE: Suggestions MUST only be selected from db_products (which only contains items with stok > 0).
    Uses the updated category system: Kedi Maması, Köpek Maması, Kum, Aksesuar, Ödül/Vitamin, Oyuncak, Diğer.
    """
    if not cart_items or not db_products:
        return []
    
    cart_barcodes = {item.get("barkod") for item in cart_items}
    cart_categories = [item.get("kategori") for item in cart_items if item.get("kategori")]
    
    available_stock = [p for p in db_products if p["barkod"] not in cart_barcodes]
    if not available_stock:
        return []
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if HAS_GENAI and api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            cart_names = [item.get("ad") for item in cart_items]
            stock_list = [{"ad": p["ad"], "kategori": p["kategori"], "barkod": p["barkod"], "fiyat": p["fiyat"]} for p in available_stock]
            
            prompt = (
                "Sen Beykoz Pet isimli petshopun AI satış asistanısın. "
                f"Müşterinin sepetindeki ürünler: {', '.join(cart_names)}. "
                f"Dükkandaki stokta olan ürünlerin listesi: {json.dumps(stock_list, ensure_ascii=False)}. "
                "Sepetteki ürünlerle birlikte en çok satılabilecek (çapraz satış) 3 adet stok ürününün BARKODLARINI seçip öner. "
                "Önerilerini JSON listesi olarak dön. Liste formatı: [\"barkod1\", \"barkod2\"]\n"
                "SADECE JSON liste çıktısı ver, başka hiçbir şey yazma."
            )
            response = model.generate_content(prompt)
            text = response.text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            
            suggested_barcodes = json.loads(text)
            
            recommendations = []
            for barcode in suggested_barcodes:
                for p in available_stock:
                    if p["barkod"] == barcode:
                        recommendations.append(p)
            if recommendations:
                return recommendations[:3]
        except Exception as e:
            print(f"Gemini recommendations failed, falling back to rule-based: {e}")

    # Fallback Smart Rule-Based recommendations matching actual stock and updated categories
    recommendations = []
    
    CROSS_SELLING_MAP = {
        "Kedi Maması": ["Ödül/Vitamin", "Oyuncak", "Kum"],
        "Köpek Maması": ["Ödül/Vitamin", "Oyuncak", "Aksesuar"],
        "Kum": ["Aksesuar", "Kedi Maması", "Oyuncak"],
        "Aksesuar": ["Kedi Maması", "Köpek Maması", "Ödül/Vitamin"],
        "Ödül/Vitamin": ["Kedi Maması", "Köpek Maması", "Oyuncak"],
        "Oyuncak": ["Ödül/Vitamin", "Kedi Maması", "Köpek Maması", "Aksesuar"]
    }
    
    target_categories = []
    for cat in cart_categories:
        if cat in CROSS_SELLING_MAP:
            target_categories.extend(CROSS_SELLING_MAP[cat])
            
    target_categories = list(dict.fromkeys(target_categories))
    
    # 1. Search for in-stock items in companion categories
    for target_cat in target_categories:
        for p in available_stock:
            if p["kategori"] == target_cat and p not in recommendations:
                recommendations.append(p)
                if len(recommendations) >= 3:
                    break
        if len(recommendations) >= 3:
            break
            
    # 2. If we still have room, add other random in-stock items
    if len(recommendations) < 3:
        for p in available_stock:
            if p not in recommendations:
                recommendations.append(p)
                if len(recommendations) >= 3:
                    break
                    
    return recommendations[:3]
