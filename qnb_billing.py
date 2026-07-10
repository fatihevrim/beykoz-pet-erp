import xml.etree.ElementTree as ET
import json
from datetime import datetime, timedelta
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "beykoz_pet.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Updated mock XML e-Invoice containing Reflex Yetişkin 15kg and other items
MOCK_XML_INVOICE = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ID>QNB2026000098765</cbc:ID>
    <cbc:IssueDate>2026-07-04</cbc:IssueDate>
    <cac:AccountingSupplierParty>
        <cac:Party>
            <cac:PartyName>
                <cbc:Name>Beykoz Toptan Pet Dağıtım Ltd. Şti.</cbc:Name>
            </cac:PartyName>
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:InvoiceLine>
        <cbc:ID>1</cbc:ID>
        <cbc:InvoicedQuantity unitCode="NIU">5</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="TRY">2000.00</cbc:LineExtensionAmount>
        <cac:Item>
            <cbc:Name>Reflex Yetişkin Kedi Maması 15kg</cbc:Name>
            <cac:SellersItemIdentification>
                <cbc:ID>8691112223334</cbc:ID>
            </cac:SellersItemIdentification>
        </cac:Item>
        <cac:Price>
            <cbc:PriceAmount currencyID="TRY">400.00</cbc:PriceAmount>
        </cac:Price>
    </cac:InvoiceLine>
    <cac:InvoiceLine>
        <cbc:ID>2</cbc:ID>
        <cbc:InvoicedQuantity unitCode="NIU">10</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="TRY">4500.00</cbc:LineExtensionAmount>
        <cac:Item>
            <cbc:Name>Royal Canin Sterilised Yetişkin Kedi Maması 2kg</cbc:Name>
            <cac:SellersItemIdentification>
                <cbc:ID>8690123456789</cbc:ID>
            </cac:SellersItemIdentification>
        </cac:Item>
        <cac:Price>
            <cbc:PriceAmount currencyID="TRY">450.00</cbc:PriceAmount>
        </cac:Price>
    </cac:InvoiceLine>
    <cac:InvoiceLine>
        <cbc:ID>3</cbc:ID>
        <cbc:InvoicedQuantity unitCode="NIU">15</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="TRY">4425.00</cbc:LineExtensionAmount>
        <cac:Item>
            <cbc:Name>Ever Clean Lavender Kokulu Kedi Kumu 10L</cbc:Name>
            <cac:SellersItemIdentification>
                <cbc:ID>8697778889983</cbc:ID>
            </cac:SellersItemIdentification>
        </cac:Item>
        <cac:Price>
            <cbc:PriceAmount currencyID="TRY">295.00</cbc:PriceAmount>
        </cac:Price>
    </cac:InvoiceLine>
</Invoice>
"""

def parse_qnb_e_invoice(xml_string):
    """
    Parses QNB Finansbank XML e-Invoice (UBL-TR format)
    Returns a list of products parsed from the invoice:
    [ {barkod, ad, fiyat, miktar, kategori, skt, gorsel_url} ]
    """
    try:
        namespaces = {
            'inv': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
        }
        
        root = ET.fromstring(xml_string)
        invoice_lines = root.findall('.//cac:InvoiceLine', namespaces)
        
        parsed_products = []
        for line in invoice_lines:
            barcode_elem = line.find('.//cac:Item/cac:SellersItemIdentification/cbc:ID', namespaces)
            barcode = barcode_elem.text if barcode_elem is not None else None
            
            name_elem = line.find('.//cac:Item/cbc:Name', namespaces)
            name = name_elem.text if name_elem is not None else "Bilinmeyen Ürün"
            
            qty_elem = line.find('.//cbc:InvoicedQuantity', namespaces)
            qty = int(float(qty_elem.text)) if qty_elem is not None else 0
            
            price_elem = line.find('.//cac:Price/cbc:PriceAmount', namespaces)
            price = float(price_elem.text) if price_elem is not None else 0.0
            
            # Determine correct categories according to schema
            lower_name = name.lower()
            category = "Diğer"
            if "mama" in lower_name or "kitten" in lower_name or "sterilised" in lower_name:
                if "köpek" in lower_name:
                    category = "Köpek Maması"
                else:
                    category = "Kedi Maması"
            elif "kum" in lower_name or "litter" in lower_name:
                category = "Kum"
            elif "tasma" in lower_name or "yata" in lower_name or "kap" in lower_name or "tarak" in lower_name:
                category = "Aksesuar"
            elif "vitamin" in lower_name or "macun" in lower_name or "damla" in lower_name or "ödül" in lower_name:
                category = "Ödül/Vitamin"
            elif "oyuncak" in lower_name or "top" in lower_name:
                category = "Oyuncak"
                
            # Default Expiry date (far in the future)
            skt = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
            
            # Default image placeholder
            gorsel_url = "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"
            if "Mama" in category:
                gorsel_url = "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"
            elif category == "Kum":
                gorsel_url = "https://images.unsplash.com/photo-1569591159212-b02ea8a9f239?w=500"
                
            if barcode:
                parsed_products.append({
                    "barkod": barcode,
                    "ad": name,
                    "fiyat": price,
                    "miktar": qty,
                    "kategori": category,
                    "skt": skt,
                    "gorsel_url": gorsel_url
                })
        return parsed_products
    except Exception as e:
        print(f"Error parsing e-invoice XML: {e}")
        return []

def import_invoice_to_stock(xml_string):
    """
    Parses the invoice and updates/inserts products in:
    1. Active inventory (urunler)
    2. Catalog library (hazir_urunler) if not present
    """
    products = parse_qnb_e_invoice(xml_string)
    if not products:
        return 0, "Fatura ayrıştırılamadı veya boş."
    
    conn = get_db_connection()
    cursor = conn.cursor()
    imported_count = 0
    
    for p in products:
        # 1. Update/Insert active inventory (urunler)
        cursor.execute("SELECT stok FROM urunler WHERE barkod = ?", (p["barkod"],))
        result = cursor.fetchone()
        
        if result:
            new_stock = result["stok"] + p["miktar"]
            cursor.execute("UPDATE urunler SET stok = ?, fiyat = ? WHERE barkod = ?", 
                           (new_stock, p["fiyat"], p["barkod"]))
        else:
            cursor.execute("""
            INSERT INTO urunler (barkod, ad, kategori, fiyat, stok, kritik_stok, skt, gorsel_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (p["barkod"], p["ad"], p["kategori"], p["fiyat"], p["miktar"], 5, p["skt"], p["gorsel_url"]))
            
        # 2. Update/Insert catalog library (hazir_urunler)
        cursor.execute("SELECT 1 FROM hazir_urunler WHERE barkod = ?", (p["barkod"],))
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO hazir_urunler (barkod, ad, kategori, varsayilan_gorsel)
            VALUES (?, ?, ?, ?)
            """, (p["barkod"], p["ad"], p["kategori"], p["gorsel_url"]))
            
        imported_count += 1
        
    conn.commit()
    conn.close()
    return imported_count, f"Başarıyla {imported_count} ürün stoka eklendi/güncellendi."

if __name__ == "__main__":
    count, msg = import_invoice_to_stock(MOCK_XML_INVOICE)
    print(msg)
