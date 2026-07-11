import sqlite3
import os
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd

try:
    import psycopg2
    import psycopg2.extras
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

DB_PATH = os.path.join(os.path.dirname(__file__), "beykoz_pet.db")

class PostgresCursorWrapper:
    def __init__(self, pg_cursor):
        self.cursor = pg_cursor
        
    def execute(self, query, params=None):
        # 1. Standardize query placeholders from ? to %s for PostgreSQL
        query = query.replace("?", "%s")
        # 2. Standardize SQLite-specific AUTOINCREMENT to PostgreSQL SERIAL
        query = query.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        # 3. Standardize SQLite-specific unique replacements to standard INSERT
        if "INSERT OR REPLACE INTO" in query:
            query = query.replace("INSERT OR REPLACE INTO", "INSERT INTO")
        elif "INSERT OR IGNORE INTO" in query:
            query = query.replace("INSERT OR IGNORE INTO", "INSERT INTO")
            
        self.cursor.execute(query, params)
        
    def executemany(self, query, seq_of_params):
        query = query.replace("?", "%s")
        query = query.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        if "INSERT OR REPLACE INTO" in query:
            query = query.replace("INSERT OR REPLACE INTO", "INSERT INTO")
        elif "INSERT OR IGNORE INTO" in query:
            query = query.replace("INSERT OR IGNORE INTO", "INSERT INTO")
        self.cursor.executemany(query, seq_of_params)
        
    def fetchone(self):
        return self.cursor.fetchone()
        
    def fetchall(self):
        return self.cursor.fetchall()
        
    @property
    def rowcount(self):
        return self.cursor.rowcount
        
    @property
    def description(self):
        return self.cursor.description
        
    def close(self):
        self.cursor.close()

class PostgresConnectionWrapper:
    def __init__(self, pg_conn):
        self.conn = pg_conn
        
    def cursor(self):
        pg_cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        return PostgresCursorWrapper(pg_cursor)
        
    def commit(self):
        self.conn.commit()
        
    def rollback(self):
        self.conn.rollback()
        
    def close(self):
        self.conn.close()
        
    def execute(self, query, params=None):
        cursor = self.cursor()
        cursor.execute(query, params)
        return cursor

def get_db_connection():
    supabase_url = None
    try:
        if "SUPABASE_DB_URL" in st.secrets:
            supabase_url = st.secrets["SUPABASE_DB_URL"]
    except Exception:
        pass
        
    if HAS_POSTGRES and supabase_url:
        try:
            conn = psycopg2.connect(supabase_url)
            return PostgresConnectionWrapper(conn)
        except Exception as e:
            # Output warning but fallback to SQLite cleanly
            print(f"[Supabase Connection Error] Falling back to SQLite. Error: {e}")
            
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn

def read_sql_query(query, conn, params=None):
    is_sqlite = isinstance(conn, sqlite3.Connection)
    if not is_sqlite:
        query = query.replace("?", "%s")
        
    cursor = conn.cursor()
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)
        
    rows = cursor.fetchall()
    if not cursor.description:
        cursor.close()
        return pd.DataFrame()
        
    columns = [desc[0] for desc in cursor.description]
    
    data_list = []
    for r in rows:
        data_list.append({columns[i]: r[i] for i in range(len(columns))})
        
    cursor.close()
    return pd.DataFrame(data_list, columns=columns)

def init_db():
    supabase_url = None
    try:
        if "SUPABASE_DB_URL" in st.secrets:
            supabase_url = st.secrets["SUPABASE_DB_URL"]
    except Exception:
        pass

    is_postgres = (HAS_POSTGRES and supabase_url is not None)
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Identify if new/empty database dynamically
    is_new_db = False
    if is_postgres:
        try:
            cursor.execute("SELECT COUNT(*) FROM users")
            is_new_db = (cursor.fetchone()[0] == 0)
        except Exception:
            is_new_db = True
    else:
        is_new_db = not os.path.exists(DB_PATH)
    
    # 1. Shop Active Inventory Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS urunler (
        barkod TEXT PRIMARY KEY,
        ad TEXT NOT NULL,
        kategori TEXT NOT NULL,
        fiyat REAL NOT NULL,
        stok INTEGER NOT NULL,
        kritik_stok INTEGER DEFAULT 5,
        skt TEXT,
        gorsel_url TEXT,
        gelis_fiyati REAL DEFAULT 0.0,
        hizli_kasa_kisayol INTEGER DEFAULT 0
    )
    """)
    
    # 2. Local Catalog Library Table (Offline Barcode Database)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS hazir_urunler (
        barkod TEXT PRIMARY KEY,
        ad TEXT NOT NULL,
        kategori TEXT NOT NULL,
        varsayilan_gorsel TEXT
    )
    """)
    
    # 3. Customers Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS musteriler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        isim TEXT NOT NULL,
        telefon TEXT,
        hayvan_turu TEXT,
        irk_detay TEXT,
        yas TEXT,
        kisir TEXT,
        kilo REAL,
        boyut TEXT,
        ekipman_detay TEXT,
        saglik_detay TEXT,
        ozel_notlar TEXT,
        son_alinan_mama TEXT,
        tahmini_mama_bitis_tarihi TEXT,
        dogum_gunu TEXT,
        iskonto_orani REAL DEFAULT 0.0
    )
    """)
    
    # 4. Sales Records Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS satislar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarih TEXT NOT NULL,
        barkod TEXT,
        urun_ad TEXT,
        miktar INTEGER,
        toplam_tutar REAL,
        odeme_yontemi TEXT,
        musteri_id INTEGER,
        FOREIGN KEY(musteri_id) REFERENCES musteriler(id)
    )
    """)
    
    # 5. API Settings Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ayarlar (
        anahtar TEXT PRIMARY KEY,
        deger TEXT NOT NULL
    )
    """)

    # 6. Pet Grooming Appointments Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS randevular (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        musteri_id INTEGER,
        hayvan_ad TEXT NOT NULL,
        islem TEXT NOT NULL,
        tarih TEXT NOT NULL,
        saat TEXT NOT NULL,
        durum TEXT DEFAULT 'Bekliyor',
        tamamlandi_tarih TEXT,
        FOREIGN KEY(musteri_id) REFERENCES musteriler(id)
    )
    """)

    # 7. Vaccinations Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS asilar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        musteri_id INTEGER,
        hayvan_ad TEXT NOT NULL,
        asi_adi TEXT NOT NULL,
        uygulama_tarih TEXT NOT NULL,
        gelecek_doz_tarih TEXT NOT NULL,
        FOREIGN KEY(musteri_id) REFERENCES musteriler(id)
    )
    """)

    # 8. Customer Custom Product Orders Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS customer_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        musteri_id INTEGER,
        urun_detay TEXT NOT NULL,
        miktar INTEGER DEFAULT 1,
        siparis_tarihi TEXT NOT NULL,
        durum TEXT DEFAULT 'Beklemede',
        FOREIGN KEY(musteri_id) REFERENCES musteriler(id)
    )
    """)

    # 9. Users Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    )
    """)

    # 10. Accounting Ledger Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounting (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarih TEXT NOT NULL,
        tip TEXT NOT NULL,
        kategori TEXT NOT NULL,
        tutar REAL NOT NULL,
        aciklama TEXT
    )
    """)
    
    # 11. Debts Table (Veresiye)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS debts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        amount REAL NOT NULL,
        product_details TEXT NOT NULL,
        purchase_date TEXT NOT NULL,
        due_date TEXT NOT NULL,
        status TEXT DEFAULT 'Ödenmedi',
        FOREIGN KEY(customer_id) REFERENCES musteriler(id)
    )
    """)
    
    # 12. Payment History Table (Veresiye Ödeme Geçmişi)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payment_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        debt_id INTEGER,
        amount_paid REAL NOT NULL,
        payment_date TEXT NOT NULL,
        payment_type TEXT NOT NULL,
        FOREIGN KEY(debt_id) REFERENCES debts(id)
    )
    """)
    
    # 13. Wholesalers Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS wholesalers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        balance REAL DEFAULT 0.0
    )
    """)

    # 14. Wholesaler Invoices Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS wholesaler_invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wholesaler_id INTEGER,
        product_details TEXT,
        total_amount REAL NOT NULL,
        invoice_date TEXT NOT NULL,
        FOREIGN KEY(wholesaler_id) REFERENCES wholesalers(id)
    )
    """)

    # 15. Wholesaler Payments Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS wholesaler_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wholesaler_id INTEGER,
        amount_paid REAL NOT NULL,
        payment_date TEXT NOT NULL,
        FOREIGN KEY(wholesaler_id) REFERENCES wholesalers(id)
    )
    """)

    # 16. Wholesaler Orders Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS wholesaler_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wholesaler_id INTEGER,
        order_notes TEXT NOT NULL,
        status TEXT DEFAULT 'Beklemede',
        FOREIGN KEY(wholesaler_id) REFERENCES wholesalers(id)
    )
    """)
    
    # 17. Employees Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        base_salary REAL NOT NULL,
        current_balance REAL DEFAULT 0.0
    )
    """)

    # 18. Employee Transactions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS employee_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_id INTEGER,
        type TEXT NOT NULL,
        amount REAL NOT NULL,
        description TEXT,
        date TEXT NOT NULL,
        FOREIGN KEY(employee_id) REFERENCES employees(id)
    )
    """)
    
    # Seed default users
    try:
        cursor.execute("DELETE FROM users WHERE username IN ('patron', 'eleman', 'beykozpet', 'kasa')")
        cursor.execute("INSERT INTO users (username, password, role) VALUES ('beykozpet', 'beykozpet56', 'Patron')")
        cursor.execute("INSERT INTO users (username, password, role) VALUES ('kasa', '5656', 'Satış Elemanı')")
    except Exception:
        pass
    
    conn.commit()
    
    # Veritabanı Şeması Güncelleme / Migrations
    def add_column_if_not_exists(table_name, column_name, column_def):
        exists = False
        try:
            cursor.execute(f"SELECT {column_name} FROM {table_name} LIMIT 1")
            exists = True
        except Exception:
            # Clear Postgres transaction aborted state
            try:
                if hasattr(conn, 'conn'):
                    conn.conn.rollback()
                elif hasattr(conn, 'rollback'):
                    conn.rollback()
            except Exception:
                pass
                
        if not exists:
            try:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")
                conn.commit()
            except Exception as e:
                print(f"[MIGRATION WARNING] Failed to add {column_name} to {table_name}: {e}")
                try:
                    if hasattr(conn, 'conn'):
                        conn.conn.rollback()
                    elif hasattr(conn, 'rollback'):
                        conn.rollback()
                except Exception:
                    pass

    add_column_if_not_exists("urunler", "gelis_fiyati", "REAL DEFAULT 0.0")
    add_column_if_not_exists("urunler", "hizli_kasa_kisayol", "INTEGER DEFAULT 0")
    
    try:
        cursor.execute("UPDATE urunler SET hizli_kasa_kisayol = 1 WHERE barkod LIKE 'custom_%'")
        conn.commit()
    except Exception:
        pass
        
    add_column_if_not_exists("randevular", "durum", "TEXT DEFAULT 'Bekliyor'")
    add_column_if_not_exists("randevular", "tamamlandi_tarih", "TEXT")
    
    add_column_if_not_exists("satislar", "odeme_yontemi", "TEXT")
    add_column_if_not_exists("satislar", "musteri_id", "INTEGER")
    
    # Müşteri Tablosu Şeması Güncelleme / Migrations
    yeni_kolonlar = [
        ("hayvan_turu", "TEXT"),
        ("irk_detay", "TEXT"),
        ("yas", "TEXT"),
        ("kisir", "TEXT"),
        ("kilo", "TEXT"),
        ("boyut", "TEXT"),
        ("ekipman_detay", "TEXT"),
        ("saglik_detay", "TEXT"),
        ("ozel_notlar", "TEXT"),
        ("son_alinan_mama", "TEXT"),
        ("tahmini_mama_bitis_tarihi", "TEXT"),
        ("dogum_gunu", "TEXT"),
        ("iskonto_orani", "REAL DEFAULT 0.0")
    ]
    for kolon_adi, kolon_tipi in yeni_kolonlar:
        add_column_if_not_exists("musteriler", kolon_adi, kolon_tipi)
        
    conn.commit()
    
    # Seeding Active Inventory Table (urunler) - Seed only on first DB file creation
    if is_new_db:
        cursor.execute("SELECT COUNT(*) FROM urunler")
        if cursor.fetchone()[0] == 0:
            today = datetime.now()
            skt_near = (today + timedelta(days=3)).strftime("%Y-%m-%d")
            skt_expired = (today - timedelta(days=5)).strftime("%Y-%m-%d")
            skt_far = (today + timedelta(days=365)).strftime("%Y-%m-%d")
            
            products = [
                ("7613035123456", "Pro Plan Kitten Tavuklu Yavru Kedi Maması 1.5kg", "Kedi Maması", 395.00, 15, 5, skt_far, "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("3182550702222", "Royal Canin Sterilised Yetişkin Kedi Maması 2kg", "Kedi Maması", 450.00, 12, 5, skt_far, "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=500"),
                ("8697778889990", "Ever Clean Litter Free Kedi Kumu 10L", "Kum", 280.00, 3, 5, skt_far, "https://images.unsplash.com/photo-1569591159212-b02ea8a9f239?w=500"),
                ("4002064123456", "Gimcat Multi-Vitamin Kedi Ödül Macunu 50g", "Ödül/Vitamin", 195.00, 18, 5, skt_near, "https://images.unsplash.com/photo-1608454509000-1936617c6a91?w=500"),
                ("4011905055555", "Trixie Tavuklu Kedi Ödül Maması 50g", "Ödül/Vitamin", 45.00, 8, 4, skt_expired, "https://images.unsplash.com/photo-1535930891776-0c2dfb7fda1a?w=500")
            ]
            cursor.executemany("""
            INSERT INTO urunler (barkod, ad, kategori, fiyat, stok, kritik_stok, skt, gorsel_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, products)
            
    # Seeding Local Catalog Library (hazir_urunler) - Seed only on first DB file creation
    if is_new_db:
        cursor.execute("SELECT COUNT(*) FROM hazir_urunler")
        if cursor.fetchone()[0] == 0:
            catalog = [
                # 1. Pro Plan Products (EAN prefix starting 761303...)
                ("7613035123456", "Pro Plan Kitten Tavuklu Yavru Kedi Maması 1.5kg", "Kedi Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("7613035123463", "Pro Plan Sterilised Somonlu Kısırlaştırılmış Kedi Maması 1.5kg", "Kedi Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("7613035123470", "Pro Plan Sterilised Hindili Kısırlaştırılmış Kedi Maması 1.5kg", "Kedi Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("7613035123487", "Pro Plan LiveClear Sterilised Kedi Maması 1.4kg", "Kedi Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("7613035123494", "Pro Plan Housecat Hindi & Pirinçli Kedi Maması 1.5kg", "Kedi Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("7613035123500", "Pro Plan Derma Plus Saç Yumağı Önleyici Kedi Maması 1.5kg", "Kedi Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("7613035123517", "Pro Plan Delicate Sensitive Hindi Etli Kedi Maması 1.5kg", "Kedi Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("7613035123524", "Pro Plan Medium Adult Kuzu Etli Yetişkin Köpek Maması 14kg", "Köpek Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("7613035123531", "Pro Plan Medium Puppy Tavuklu Yavru Köpek Maması 12kg", "Köpek Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("7613035123548", "Pro Plan Large Athletic Yetişkin Köpek Maması 14kg", "Köpek Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                
                # 2. Royal Canin Products (EAN prefix starting 318255...)
                ("3182550702222", "Royal Canin Sterilised Yetişkin Kedi Maması 2kg", "Kedi Maması", "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=500"),
                ("3182550702338", "Royal Canin Kitten Yavru Kedi Maması 2kg", "Kedi Maması", "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=500"),
                ("3182550702444", "Royal Canin Mother & Babycat Kedi Maması 400g", "Kedi Maması", "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=500"),
                ("3182550702550", "Royal Canin Fit 32 Yetişkin Kedi Maması 2kg", "Kedi Maması", "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=500"),
                ("3182550702666", "Royal Canin Sensible Hassas Sindirim Kedi Maması 2kg", "Kedi Maması", "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=500"),
                ("3182550702772", "Royal Canin Hairball Care Saç Yumağı Karşıtı Kedi Maması 2kg", "Kedi Maması", "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=500"),
                ("3182550702888", "Royal Canin Pug Yetişkin Köpek Maması 3kg", "Köpek Maması", "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=500"),
                ("3182550702994", "Royal Canin Golden Retriever Yetişkin Köpek Maması 12kg", "Köpek Maması", "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=500"),
                ("3182550703007", "Royal Canin Medium Adult Yetişkin Köpek Maması 15kg", "Köpek Maması", "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=500"),
                ("3182550703113", "Royal Canin Mini Starter Yavru Köpek Maması 3kg", "Köpek Maması", "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=500"),
                
                # 3. N&D Products (EAN prefix starting 802222...)
                ("8022221234561", "N&D Prime Tavuklu ve Narlı Kısırlaştırılmış Kedi Maması 1.5kg", "Kedi Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("8022221234578", "N&D Pumpkin Bıldırcınlı ve Balkabaklı Kısır Kedi Maması 1.5kg", "Kedi Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("8022221234585", "N&D Prime Kuzu Etli ve Yaban Mersinli Kedi Maması 1.5kg", "Kedi Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("8022221234592", "N&D Quinoa Urinary İdrar Yolu Sağlığı Kedi Maması 1.5kg", "Kedi Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("8022221234608", "N&D Ocean Morina Balıklı ve Portakallı Kedi Maması 1.5kg", "Kedi Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("8022221234615", "N&D Pumpkin Kuzu Etli ve Balkabaklı Yavru Köpek Maması 12kg", "Köpek Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("8022221234622", "N&D Ocean Somonlu ve Morina Balıklı Köpek Maması 12kg", "Köpek Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                
                # 4. Felicia & Reflex (Turkish Brands EAN starting 869...)
                ("8698745632145", "Felicia Kitten Düşük Tahıllı Yavru Kedi Maması 2kg", "Kedi Maması", "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"),
                ("8698745632152", "Felicia Sterilised Somonlu Kısır Kedi Maması 2kg", "Kedi Maması", "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"),
                ("8698745632169", "Felicia Sterilised Tavuklu Kısır Kedi Maması 2kg", "Kedi Maması", "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"),
                ("8698745632176", "Felicia Hypoallergenic Somonlu Yetişkin Kedi Maması 2kg", "Kedi Maması", "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"),
                ("8698745632183", "Felicia Medium Puppy Tavuklu Yavru Köpek Maması 3kg", "Köpek Maması", "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"),
                ("8690526081111", "Reflex Sterilised Somonlu Kısırlaştırılmış Kedi Maması 1.5kg", "Kedi Maması", "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"),
                ("8690526082222", "Reflex Plus Kitten Tavuklu Yavru Kedi Maması 1.5kg", "Kedi Maması", "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"),
                ("8690526083333", "Reflex Plus Adult Somonlu Yetişkin Kedi Maması 1.5kg", "Kedi Maması", "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"),
                ("8690526084444", "Reflex Plus Medium Adult Kuzu Etli Köpek Maması 3kg", "Köpek Maması", "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"),
                
                # 5. Ever Clean & Litter brands (Kum)
                ("8697778889990", "Ever Clean Litter Free Kedi Kumu 10L", "Kum", "https://images.unsplash.com/photo-1569591159212-b02ea8a9f239?w=500"),
                ("8697778889983", "Ever Clean Lavender Kokulu Kedi Kumu 10L", "Kum", "https://images.unsplash.com/photo-1569591159212-b02ea8a9f239?w=500"),
                ("8697778889976", "Ever Clean Extra Strong Kokusuz Kedi Kumu 10L", "Kum", "https://images.unsplash.com/photo-1569591159212-b02ea8a9f239?w=500"),
                ("8697778889969", "Ever Clean Fast Acting Koku Kontrollü Kum 10L", "Kum", "https://images.unsplash.com/photo-1569591159212-b02ea8a9f239?w=500"),
                ("8690123412345", "Bento Premium Kokusuz Doğal Kedi Kumu 10L", "Kum", "https://images.unsplash.com/photo-1569591159212-b02ea8a9f239?w=500"),
                ("8690123412352", "VanCat Marsilya Sabunlu İnce Kedi Kumu 10L", "Kum", "https://images.unsplash.com/photo-1569591159212-b02ea8a9f239?w=500"),
                ("8690123412369", "Pro Line Lavanta Kokulu Bentonit Kedi Kumu 10L", "Kum", "https://images.unsplash.com/photo-1569591159212-b02ea8a9f239?w=500"),
                
                # 6. Treats & Vitamins (Gimcat / Trixie / Bio PetActive)
                ("4002064123456", "Gimcat Multi-Vitamin Kedi Ödül Macunu 50g", "Ödül/Vitamin", "https://images.unsplash.com/photo-1608454509000-1936617c6a91?w=500"),
                ("4002064123463", "Gimcat Malt-Soft Extra Tüy Yumağı Karşıtı Macun 50g", "Ödül/Vitamin", "https://images.unsplash.com/photo-1608454509000-1936617c6a91?w=500"),
                ("4002064123470", "Gimcat Kitten Paste Yavru Kedi Vitamin Macunu 50g", "Ödül/Vitamin", "https://images.unsplash.com/photo-1608454509000-1936617c6a91?w=500"),
                ("4011905055555", "Trixie Tavuklu Kedi Ödül Maması 50g", "Ödül/Vitamin", "https://images.unsplash.com/photo-1535930891776-0c2dfb7fda1a?w=500"),
                ("4011905055562", "Trixie Ciğerli Tüp Kedi Ödülü 75g", "Ödül/Vitamin", "https://images.unsplash.com/photo-1535930891776-0c2dfb7fda1a?w=500"),
                ("8698945621458", "Bio PetActive Biodent Hexidine Köpek Ağız Sağlığı 250ml", "Ödül/Vitamin", "https://images.unsplash.com/photo-1608454509000-1936617c6a91?w=500"),
                ("8698945621465", "Bio PetActive Somon Yağı Deri ve Tüy Sağlığı 250ml", "Ödül/Vitamin", "https://images.unsplash.com/photo-1608454509000-1936617c6a91?w=500"),
                
                # 7. Toys & Accessories
                ("8690000000003", "Lepus Ortopedik Köpek Yatağı L Beden", "Aksesuar", "https://images.unsplash.com/photo-1541599540903-216a46ca1ad0?w=500"),
                ("4011905022222", "Trixie Göğüs Tasması M Beden Kırmızı", "Aksesuar", "https://images.unsplash.com/photo-1541599540903-216a46ca1ad0?w=500"),
                ("4011905022239", "Trixie Çelik Kedi Mama Kabı 0.2L", "Aksesuar", "https://images.unsplash.com/photo-1541599540903-216a46ca1ad0?w=500"),
                ("4011905022246", "Kong Classic Dayanıklı Kauçuk Isırma Topu L", "Oyuncak", "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?w=500"),
                ("4011905022253", "Trixie Peluş Hışırtılı Fare Kedi Oyuncağı", "Oyuncak", "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?w=500"),
                ("4011905022260", "Eastland Kedi Oyun Oltası Kuşlu", "Oyuncak", "https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?w=500")
            ]
            cursor.executemany("""
            INSERT INTO hazir_urunler (barkod, ad, kategori, varsayilan_gorsel)
            VALUES (?, ?, ?, ?)
            """, catalog)
            
    # Seeding Customers - Seed only on first DB file creation
    if is_new_db:
        cursor.execute("SELECT COUNT(*) FROM musteriler")
        if cursor.fetchone()[0] == 0:
            customers = [
                ("Ahmet Yılmaz", "05321234567", "Kedi", "Tekir", "2 Yaşında", "Evet", 4.2, "", "Bentonit", "Alerjisi yok", "Mırnav"),
                ("Zeynep Kaya", "05439876543", "Köpek", "Golden Retriever", "3 Yaşında", "Hayır", 28.5, "Büyük Irk", "", "Hassas cilt", "Dobby"),
                ("Mehmet Demir", "05051112233", "Kuş", "Muhabbet Kuşu", "1 Yaşında", "Belirtilmedi", 0.0, "Standart", "", "Kalamar kemiği sever", "Maviş")
            ]
            cursor.executemany("""
            INSERT INTO musteriler (isim, telefon, hayvan_turu, irk_detay, yas, kisir, kilo, boyut, ekipman_detay, saglik_detay, ozel_notlar)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, customers)
        
    # Seed shortcut/custom products if they do not exist
    shortcut_products = [
        ("custom_beta_baligi", "Beta Balığı", "Canlı Balık", 120.00, 40.00, 100, 5, "-"),
        ("custom_japon_baligi", "Japon Balığı", "Canlı Balık", 80.00, 25.00, 100, 5, "-"),
        ("custom_lepistes", "Lepistes", "Canlı Balık", 50.00, 15.00, 200, 5, "-"),
        ("custom_acik_kedi_1kg", "Açık Kedi Maması (1 KG)", "Açık Mama", 150.00, 90.00, 100, 5, "-"),
        ("custom_acik_kopek_1kg", "Açık Köpek Maması (1 KG)", "Açık Mama", 140.00, 80.00, 100, 5, "-"),
        ("custom_3d_dekor", "3D Akvaryum Dekoru", "Akvaryum / Dekor", 250.00, 120.00, 50, 5, "-"),
        ("custom_fanus_bitki", "Fanus Yapay Bitki", "Akvaryum / Dekor", 75.00, 30.00, 80, 5, "-")
    ]
    for bc, name, cat, price, cost, stock, crit, skt in shortcut_products:
        cursor.execute("SELECT COUNT(*) FROM urunler WHERE barkod = ?", (bc,))
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO urunler (barkod, ad, kategori, fiyat, gelis_fiyati, stok, kritik_stok, skt, hizli_kasa_kisayol)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (bc, name, cat, price, cost, stock, crit, skt))
            
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully with fresh high-fidelity seed data and hazir_urunler catalog.")
