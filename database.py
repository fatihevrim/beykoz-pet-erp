import sqlite3
import os
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
from urllib.parse import urlparse
import queue
import threading
import ssl

import re

def parse_db_url(url):
    pattern = r"^postgres(?:ql)?://([^:]+):(.*)@([^:/?]+)(?::(\d+))?/(.+)$"
    match = re.match(pattern, url)
    if match:
        user = match.group(1)
        password = match.group(2)
        host = match.group(3)
        port = int(match.group(4)) if match.group(4) else 5432
        db_path = match.group(5)
        db_name = db_path.split("?")[0]
        return {
            "user": user,
            "password": password,
            "host": host,
            "port": port,
            "database": db_name
        }
    return None

def connect_pg(supabase_url=None):
    # Hardcoded pooler connection parameters with SNI option parameter
    username = "postgres"
    password = "azAZ09kM"
    hostname = "aws-0-eu-central-1.pooler.supabase.com"
    database = "postgres"
    port = 6543
    project_ref = "yfyapzbgzqzxxxbx"

    # Try psycopg2 first for SNI and SSL capability compatibility
    try:
        import psycopg2
        conn_str = f"postgresql://{username}:{password}@{hostname}:{port}/{database}?options=-c%20project%3D{project_ref}"
        return psycopg2.connect(conn_str)
    except Exception as psy_err:
        print(f"[Psycopg2 Pooler Connection Failed, falling back to pg8000] {psy_err}")

    try:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
    except Exception:
        ssl_ctx = True
        
    return pg8000.dbapi.connect(
        user=username,
        password=password,
        host=hostname,
        port=port,
        database=database,
        ssl_context=ssl_ctx
    )

try:
    import pg8000
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

DB_PATH = os.path.join(os.path.dirname(__file__), "beykoz_pet.db")

# Thread-safe queue and thread states for async cloud sync
_sync_queue = queue.Queue()
_worker_started = False
_worker_lock = threading.Lock()

class DictRow(list):
    def __init__(self, row_data, columns):
        super().__init__(row_data)
        self.columns = columns
        self.column_to_index = {col: i for i, col in enumerate(columns)}
        
    def __getitem__(self, key):
        if isinstance(key, str):
            if key not in self.column_to_index:
                raise KeyError(key)
            return super().__getitem__(self.column_to_index[key])
        return super().__getitem__(key)
        
    def get(self, key, default=None):
        if isinstance(key, str):
            if key not in self.column_to_index:
                return default
            return super().__getitem__(self.column_to_index[key])
        try:
            return super().__getitem__(key)
        except IndexError:
            return default
            
    def keys(self):
        return self.columns
        
    def values(self):
        return list(self)
        
    def items(self):
        return [(col, self[col]) for col in self.columns]

class PostgresCursorWrapper:
    def __init__(self, pg_cursor):
        self.cursor = pg_cursor
        
    def execute(self, query, params=None):
        query = query.replace("?", "%s")
        query = query.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        if "INSERT OR REPLACE INTO" in query:
            query = query.replace("INSERT OR REPLACE INTO", "INSERT INTO")
        elif "INSERT OR IGNORE INTO" in query:
            query = query.replace("INSERT OR IGNORE INTO", "INSERT INTO")
            
        self.cursor.execute(query, params or ())
        
    def executemany(self, query, seq_of_params):
        query = query.replace("?", "%s")
        query = query.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        if "INSERT OR REPLACE INTO" in query:
            query = query.replace("INSERT OR REPLACE INTO", "INSERT INTO")
        elif "INSERT OR IGNORE INTO" in query:
            query = query.replace("INSERT OR IGNORE INTO", "INSERT INTO")
        self.cursor.executemany(query, seq_of_params)
        
    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in self.cursor.description]
        return DictRow(row, columns)
        
    def fetchall(self):
        rows = self.cursor.fetchall()
        columns = [desc[0] for desc in self.cursor.description]
        return [DictRow(r, columns) for r in rows]
        
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
        return PostgresCursorWrapper(self.conn.cursor())
        
    def commit(self):
        self.conn.commit()
        try:
            st.cache_data.clear()
        except Exception:
            pass
        
    def rollback(self):
        self.conn.rollback()
        
    def close(self):
        self.conn.close()

# Helper to identify if query writes to database
def is_write_query(query):
    q = query.strip().upper()
    return q.startswith("INSERT") or q.startswith("UPDATE") or q.startswith("DELETE") or q.startswith("REPLACE")

class HybridCursorWrapper:
    def __init__(self, local_cursor, supabase_url=None):
        self.cursor = local_cursor
        self.supabase_url = supabase_url
        
    def execute(self, query, params=None):
        # 1. Execute on local SQLite instantly
        self.cursor.execute(query, params or ())
        
        # 2. Queue write query asynchronously for Supabase
        if self.supabase_url and is_write_query(query):
            _sync_queue.put((query, params))
            
    def executemany(self, query, seq_of_params):
        # 1. Execute on local SQLite instantly
        self.cursor.executemany(query, seq_of_params)
        
        # 2. Queue write queries asynchronously for Supabase
        if self.supabase_url and is_write_query(query):
            for params in seq_of_params:
                _sync_queue.put((query, params))
                
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

class HybridConnectionWrapper:
    def __init__(self, local_conn, supabase_url=None):
        self.conn = local_conn
        self.supabase_url = supabase_url
        
    def cursor(self):
        return HybridCursorWrapper(self.conn.cursor(), self.supabase_url)
        
    def commit(self):
        self.conn.commit()
        try:
            st.cache_data.clear()
        except Exception:
            pass
            
    def rollback(self):
        self.conn.rollback()
        
    def close(self):
        self.conn.close()
        
    def execute(self, query, params=None):
        cursor = self.cursor()
        cursor.execute(query, params)
        return cursor

# Background worker thread function to sync database writes to Supabase
def _supabase_sync_worker(supabase_url):
    while True:
        try:
            task = _sync_queue.get()
            if task is None:
                _sync_queue.task_done()
                break
                
            query, params = task
            try:
                raw_pg = connect_pg(supabase_url)
                conn = PostgresConnectionWrapper(raw_pg)
                cursor = conn.cursor()
                cursor.execute(query, params)
                conn.commit()
                cursor.close()
                conn.close()
            except Exception as e:
                print(f"[Supabase Async Sync Error] Query: {query} | Error: {e}")
            _sync_queue.task_done()
        except Exception as ex:
            print(f"[Supabase Async Worker Exception] {ex}")

def start_sync_worker(supabase_url):
    global _worker_started
    with _worker_lock:
        if not _worker_started:
            t = threading.Thread(target=_supabase_sync_worker, args=(supabase_url,), daemon=True, name="SupabaseSyncWorker")
            t.start()
            _worker_started = True

# Main function to retrieve local connection wrapped in Hybrid sync layer
def get_db_connection():
    supabase_url = None
    try:
        if "SUPABASE_DB_URL" in st.secrets:
            supabase_url = st.secrets["SUPABASE_DB_URL"]
    except Exception:
        pass
        
    if HAS_POSTGRES and supabase_url:
        try:
            parsed = parse_db_url(supabase_url)
            if parsed:
                obfuscated_url = f"postgresql://{parsed['user']}:*****@{parsed['host']}:{parsed['port']}/{parsed['database']}"
                st.warning(f"🔍 Canlı Bağlantı Detayları (Ayıklama):\n- Host: `{parsed['host']}`\n- Port: `{parsed['port']}`\n- User: `{parsed['user']}`\n- Database: `{parsed['database']}`\n- URL: `{obfuscated_url}`")
                
                if "pooler.supabase.com" in parsed["host"]:
                    st.error("⚠️ HATA: Havuzlayıcı (pooler) adresi algılandı. Eğer SNI hatası alıyorsanız, lütfen Streamlit Secrets'taki SUPABASE_DB_URL değerini doğrudan veritabanı hostu olan `postgresql://postgres:[ŞİFRE]@db.[REFERANS-KODU].supabase.co:5432/postgres` şeklinde güncelleyin.")
            
            raw_pg = connect_pg(supabase_url)
            return PostgresConnectionWrapper(raw_pg)
        except Exception as e:
            st.error(f"⚠️ Supabase Bağlantı Hatası: {e}")
            print(f"[Direct Supabase Connection Error] {e}")
            
    # Fallback to local SQLite connection
    local_conn = sqlite3.connect(DB_PATH, timeout=30.0)
    local_conn.execute("PRAGMA journal_mode=WAL;")
    local_conn.row_factory = sqlite3.Row
    return HybridConnectionWrapper(local_conn)

@st.cache_data(ttl=30, show_spinner=False)
def read_sql_query(query, _conn, params=None):
    try:
        cursor = _conn.cursor()
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
    except Exception as e:
        st.error(f"❌ SQL Sorgu Hatası: {e} | Sorgu: `{query}`")
        raise e

# Cold pulls data from Supabase to local SQLite database
def sync_supabase_to_local(supabase_url, force=False):
    if not HAS_POSTGRES or not supabase_url:
        return
        
    local_conn = sqlite3.connect(DB_PATH, timeout=30.0)
    local_cursor = local_conn.cursor()
    
    if not force:
        # Check if we have data locally
        local_count = 0
        try:
            local_cursor.execute("SELECT COUNT(*) FROM urunler")
            local_count = local_cursor.fetchone()[0]
        except Exception:
            pass
            
        if local_count > 0:
            print("[Cold Sync] Local database already contains data. Skipping initial download.")
            local_conn.close()
            return
            
    print(f"[Cold Sync] Synchronizing data from Supabase cloud (force={force})...")
    try:
        raw_pg = connect_pg(supabase_url)
        pg_conn = PostgresConnectionWrapper(raw_pg)
        pg_cursor = pg_conn.cursor()
        
        tables = [
            "urunler", "hazir_urunler", "musteriler", "satislar", "ayarlar", 
            "randevular", "asilar", "customer_orders", "users", "accounting", 
            "debts", "payment_history", "wholesalers", "wholesaler_invoices", 
            "wholesaler_payments", "wholesaler_orders", "employees", "employee_transactions"
        ]
        
        for table in tables:
            try:
                pg_cursor.execute(f"SELECT * FROM {table}")
                rows = pg_cursor.fetchall()
                if not rows:
                    if force:
                        local_cursor.execute(f"DELETE FROM {table}")
                    continue
                    
                columns = list(rows[0].keys())
                
                # Delete existing local rows
                local_cursor.execute(f"DELETE FROM {table}")
                
                # Insert Supabase rows to SQLite using INSERT OR REPLACE
                placeholders = ", ".join(["?"] * len(columns))
                col_names = ", ".join(columns)
                insert_sql = f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})"
                
                for r in rows:
                    vals = tuple(r[c] for c in columns)
                    local_cursor.execute(insert_sql, vals)
                    
                print(f"[Cold Sync] Table '{table}' successfully copied: {len(rows)} rows.")
            except Exception as table_err:
                print(f"[Cold Sync Warning] Could not sync table '{table}': {table_err}")
                
        local_conn.commit()
        pg_cursor.close()
        pg_conn.close()
        print("[Cold Sync] Supabase data pull finished successfully.")
    except Exception as e:
        print(f"[Cold Sync Error] Data pull from Supabase failed: {e}")
    finally:
        local_conn.close()

def force_sync_at_startup(supabase_url):
    if not HAS_POSTGRES or not supabase_url:
        return False
        
    local_conn = sqlite3.connect(DB_PATH, timeout=30.0)
    local_cursor = local_conn.cursor()
    local_count = 0
    try:
        local_cursor.execute("SELECT COUNT(*) FROM urunler")
        local_count = local_cursor.fetchone()[0]
    except Exception:
        pass
    local_conn.close()
    
    # Get Supabase count
    supabase_count = 0
    try:
        raw_pg = connect_pg(supabase_url)
        pg_conn = PostgresConnectionWrapper(raw_pg)
        pg_cursor = pg_conn.cursor()
        pg_cursor.execute("SELECT COUNT(*) FROM urunler")
        supabase_count = pg_cursor.fetchone()[0]
        pg_cursor.close()
        pg_conn.close()
    except Exception as e:
        print(f"[Sync Count Check Warning] Could not fetch Supabase count: {e}")
        return False
        
    print(f"[Sync Count Check] Local: {local_count} | Supabase: {supabase_count}")
    if local_count != supabase_count or local_count < 200:
        print("[Sync Count Check] Discrepancy detected or local count too low. Triggering forced sync...")
        try:
            sync_supabase_to_local(supabase_url, force=True)
            return True
        except Exception as ex:
            print(f"[Sync Count Check Error] Forced sync failed: {ex}")
            return False
            
    return True

def init_db():
    supabase_url = None
    try:
        if "SUPABASE_DB_URL" in st.secrets:
            supabase_url = st.secrets["SUPABASE_DB_URL"]
    except Exception:
        pass

    # 1. Initialize local SQLite connection
    local_conn = sqlite3.connect(DB_PATH, timeout=30.0)
    local_cursor = local_conn.cursor()
    
    # 2. Try to connect to Supabase schema setup directly
    pg_conn = None
    pg_cursor = None
    if HAS_POSTGRES and supabase_url:
        try:
            raw_pg = connect_pg(supabase_url)
            pg_conn = PostgresConnectionWrapper(raw_pg)
            pg_cursor = pg_conn.cursor()
        except Exception as e:
            print(f"[Supabase Schema Warning] Could not connect to Supabase to verify schema: {e}")
            
    # Exec DDL on both local and remote (safely translated)
    def db_execute(query):
        # Local SQLite DDL
        local_cursor.execute(query)
        # Remote Supabase DDL
        if pg_cursor:
            try:
                pg_cursor.execute(query)
            except Exception as e_ddl:
                print(f"[Supabase DDL Warning] Query: {query} | Error: {e_ddl}")
                try:
                    pg_conn.rollback()
                except Exception:
                    pass
                    
    # 3. Create all tables on SQLite and Supabase
    # 1. urunler
    db_execute("""
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
    
    # 2. hazir_urunler
    db_execute("""
    CREATE TABLE IF NOT EXISTS hazir_urunler (
        barkod TEXT PRIMARY KEY,
        ad TEXT NOT NULL,
        kategori TEXT NOT NULL,
        varsayilan_gorsel TEXT
    )
    """)
    
    # 3. musteriler
    db_execute("""
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
    
    # 4. satislar
    db_execute("""
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
    
    # 5. ayarlar
    db_execute("""
    CREATE TABLE IF NOT EXISTS ayarlar (
        anahtar TEXT PRIMARY KEY,
        deger TEXT NOT NULL
    )
    """)
    
    # 6. randevular
    db_execute("""
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
    
    # 7. asilar
    db_execute("""
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
    
    # 8. customer_orders
    db_execute("""
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
    
    # 9. users
    db_execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    )
    """)
    
    # 10. accounting
    db_execute("""
    CREATE TABLE IF NOT EXISTS accounting (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarih TEXT NOT NULL,
        tip TEXT NOT NULL,
        kategori TEXT NOT NULL,
        tutar REAL NOT NULL,
        aciklama TEXT
    )
    """)
    
    # 11. debts
    db_execute("""
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
    
    # 12. payment_history
    db_execute("""
    CREATE TABLE IF NOT EXISTS payment_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        debt_id INTEGER,
        amount_paid REAL NOT NULL,
        payment_date TEXT NOT NULL,
        payment_type TEXT NOT NULL,
        FOREIGN KEY(debt_id) REFERENCES debts(id)
    )
    """)
    
    # 13. wholesalers
    db_execute("""
    CREATE TABLE IF NOT EXISTS wholesalers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        balance REAL DEFAULT 0.0
    )
    """)
    
    # 14. wholesaler_invoices
    db_execute("""
    CREATE TABLE IF NOT EXISTS wholesaler_invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wholesaler_id INTEGER,
        product_details TEXT,
        total_amount REAL NOT NULL,
        invoice_date TEXT NOT NULL,
        FOREIGN KEY(wholesaler_id) REFERENCES wholesalers(id)
    )
    """)
    
    # 15. wholesaler_payments
    db_execute("""
    CREATE TABLE IF NOT EXISTS wholesaler_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wholesaler_id INTEGER,
        amount_paid REAL NOT NULL,
        payment_date TEXT NOT NULL,
        FOREIGN KEY(wholesaler_id) REFERENCES wholesalers(id)
    )
    """)
    
    # 16. wholesaler_orders
    db_execute("""
    CREATE TABLE IF NOT EXISTS wholesaler_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        wholesaler_id INTEGER,
        order_notes TEXT NOT NULL,
        status TEXT DEFAULT 'Beklemede',
        FOREIGN KEY(wholesaler_id) REFERENCES wholesalers(id)
    )
    """)
    
    # 17. employees
    db_execute("""
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        base_salary REAL NOT NULL,
        current_balance REAL DEFAULT 0.0
    )
    """)
    
    # 18. employee_transactions
    db_execute("""
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

    # Commit local and pg DDLs
    local_conn.commit()
    if pg_conn:
        try:
            pg_conn.commit()
        except Exception:
            pass

    # Seeding defaults on empty tables
    local_cursor.execute("SELECT COUNT(*) FROM users")
    is_empty_db = local_cursor.fetchone()[0] == 0
    
    if is_empty_db:
        # Check if Supabase has data
        has_supabase_data = False
        if pg_cursor:
            try:
                pg_cursor.execute("SELECT COUNT(*) FROM users")
                has_supabase_data = pg_cursor.fetchone()[0] > 0
            except Exception:
                pass
                
        if has_supabase_data:
            # If Supabase has data, do a sync to local database
            local_conn.close()
            if pg_conn:
                pg_cursor.close()
                pg_conn.close()
            sync_supabase_to_local(supabase_url)
            return
            
        # Else seed default users
        try:
            local_cursor.execute("DELETE FROM users WHERE username IN ('patron', 'eleman', 'beykozpet', 'kasa')")
            local_cursor.execute("INSERT INTO users (username, password, role) VALUES ('beykozpet', 'beykozpet56', 'Patron')")
            local_cursor.execute("INSERT INTO users (username, password, role) VALUES ('kasa', '5656', 'Satış Elemanı')")
            
            # Seed default products
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
            local_cursor.executemany("""
            INSERT INTO urunler (barkod, ad, kategori, fiyat, stok, kritik_stok, skt, gorsel_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, products)
            
            # Catalog seed
            catalog = [
                ("7613035123456", "Pro Plan Kitten Tavuklu Yavru Kedi Maması 1.5kg", "Kedi Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("7613035123463", "Pro Plan Sterilised Somonlu Kısırlaştırılmış Kedi Maması 1.5kg", "Kedi Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("7613035123470", "Pro Plan Sterilised Hindili Kısırlaştırılmış Kedi Maması 1.5kg", "Kedi Maması", "https://images.unsplash.com/photo-1589748474424-3f1774139909?w=500"),
                ("8697778889990", "Ever Clean Litter Free Kedi Kumu 10L", "Kum", "https://images.unsplash.com/photo-1569591159212-b02ea8a9f239?w=500")
            ]
            local_cursor.executemany("""
            INSERT INTO hazir_urunler (barkod, ad, kategori, varsayilan_gorsel)
            VALUES (?, ?, ?, ?)
            """, catalog)
            
            # Seeds shortcut products
            shortcut_products = [
                ("custom_beta_baligi", "Beta Balığı", "Canlı Balık", 120.00, 40.00, 100, 5, "-"),
                ("custom_japon_baligi", "Japon Balığı", "Canlı Balık", 80.00, 25.00, 100, 5, "-"),
                ("custom_lepistes", "Lepistes", "Canlı Balık", 50.00, 15.00, 200, 5, "-")
            ]
            for bc, name, cat, price, cost, stock, crit, skt in shortcut_products:
                local_cursor.execute("""
                    INSERT INTO urunler (barkod, ad, kategori, fiyat, gelis_fiyati, stok, kritik_stok, skt, hizli_kasa_kisayol)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (bc, name, cat, price, cost, stock, crit, skt))
                
            local_conn.commit()
            
            # Write seeds to Supabase if connected
            if pg_cursor:
                try:
                    pg_cursor.execute("DELETE FROM users WHERE username IN ('patron', 'eleman', 'beykozpet', 'kasa')")
                    pg_cursor.execute("INSERT INTO users (username, password, role) VALUES ('beykozpet', 'beykozpet56', 'Patron')")
                    pg_cursor.execute("INSERT INTO users (username, password, role) VALUES ('kasa', '5656', 'Satış Elemanı')")
                    
                    pg_cursor.executemany("""
                    INSERT INTO urunler (barkod, ad, kategori, fiyat, stok, kritik_stok, skt, gorsel_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, products)
                    
                    pg_cursor.executemany("""
                    INSERT INTO hazir_urunler (barkod, ad, kategori, varsayilan_gorsel)
                    VALUES (?, ?, ?, ?)
                    """, catalog)
                    
                    for bc, name, cat, price, cost, stock, crit, skt in shortcut_products:
                        pg_cursor.execute("""
                            INSERT INTO urunler (barkod, ad, kategori, fiyat, gelis_fiyati, stok, kritik_stok, skt, hizli_kasa_kisayol)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                        """, (bc, name, cat, price, cost, stock, crit, skt))
                    pg_conn.commit()
                except Exception as e_seed:
                    print(f"[Supabase Seed Warning] {e_seed}")
                    try:
                        pg_conn.rollback()
                    except Exception:
                        pass
        except Exception as e_gen:
            print(f"[Local Seed Warning] {e_gen}")
            
    local_conn.close()
    if pg_conn:
        pg_cursor.close()
        pg_conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized locally and cloud schema synced.")

# Sunucu yenileme tetikleyicisi - Zorunlu Reboot Tetikleme - 18 Temmuz 2026
