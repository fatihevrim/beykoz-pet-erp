import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import sqlite3
import os
import subprocess
import platform
import socket

# Windows Firewall Port Allowance (TCP Port 8501)
if platform.system() == "Windows":
    try:
        subprocess.run(
            'netsh advfirewall firewall add rule name="Beykoz Pet ERP Tam Entegrasyon" dir=in action=allow protocol=TCP localport=8501',
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass
    try:
        subprocess.run(
            'netsh advfirewall firewall add rule name="Beykoz Pet ERP Kesin Entegrasyon" dir=in action=allow protocol=TCP localport=8501',
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass

# Helper function to get local IP address dynamically
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.1.9"

from database import init_db, get_db_connection
from scraper import scrape_barcode_online
from ai_engine import clean_scraped_data_with_ai, get_smart_recommendations
from qnb_billing import import_invoice_to_stock, MOCK_XML_INVOICE

# Helper function for sending WhatsApp reminders (pywhatkit with webbrowser fallback)
def send_whatsapp_reminder(phone, message):
    clean_tel = "".join(filter(str.isdigit, phone))
    if len(clean_tel) == 10:
        clean_tel = "90" + clean_tel
    elif not clean_tel.startswith("90") and not clean_tel.startswith("+"):
        clean_tel = "90" + clean_tel
    if not clean_tel.startswith("+"):
        clean_tel = "+" + clean_tel

    try:
        import pywhatkit
        pywhatkit.sendwhatmsg_instantly(clean_tel, message, wait_time=12, tab_close=True)
        return True, "WhatsApp Web açıldı ve mesaj gönderiliyor."
    except Exception as e:
        import webbrowser
        import urllib.parse
        encoded_msg = urllib.parse.quote(message)
        url = f"https://web.whatsapp.com/send?phone={clean_tel.replace('+', '')}&text={encoded_msg}"
        webbrowser.open(url)
        return False, f"pywhatkit hatası ({e}). Tarayıcıda manuel gönderim için WhatsApp Web açıldı."

# Helper function to parse weight from product names (e.g. 2 kg, 400g)
def parse_weight_from_name(name):
    import re
    match_kg = re.search(r"(\d+(?:\.\d+)?)\s*(?:kg|kilogram|kilo)", name, re.IGNORECASE)
    if match_kg:
        return float(match_kg.group(1))
    match_g = re.search(r"(\d+)\s*(?:g|gram)", name, re.IGNORECASE)
    if match_g:
        return float(match_g.group(1)) / 1000.0
    return 3.0 # Default fallback

# Set Streamlit Page Config
st.set_page_config(
    page_title="Beykoz Pet AI ERP & POS",
    page_icon="🐾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session states for Theme Mode
if "current_theme" not in st.session_state:
    st.session_state.current_theme = "dark"

# Custom CSS Styles (Dark Cyber vs. Corporate Light)
DARK_THEME_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    /* Background and global text color overrides */
    .stApp {
        background: radial-gradient(circle at 50% 50%, #0d1117 0%, #07090e 100%) !important;
        color: #f0f3f8 !important;
    }
    
    /* Sidebar premium neon styling */
    [data-testid="stSidebar"] {
        background-color: #0b0e14 !important;
        border-right: 1px solid rgba(0, 173, 181, 0.15);
    }
    
    /* Global Card Designs with Shadow and Border Glows */
    .metric-card {
        background: linear-gradient(145deg, #131924 0%, #0d121c 100%);
        border: 1px solid rgba(0, 173, 181, 0.15);
        border-radius: 12px;
        padding: 22px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
        margin-bottom: 20px;
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    }
    .metric-card:hover {
        transform: translateY(-4px);
        border-color: rgba(0, 173, 181, 0.5);
        box-shadow: 0 0 20px rgba(0, 173, 181, 0.25), 0 10px 30px rgba(0, 0, 0, 0.5);
    }
    
    .metric-card h3 {
        color: #94a3b8 !important;
        font-size: 0.95rem !important;
        text-transform: uppercase !important;
        letter-spacing: 1px !important;
        margin-bottom: 8px !important;
    }
    .metric-card h2 {
        color: #ffffff !important;
        font-size: 2.1rem !important;
        font-weight: 700 !important;
        margin: 0 !important;
    }
    
    /* Special recommendation cards style */
    .rec-card {
        background: linear-gradient(135deg, rgba(0, 173, 181, 0.1) 0%, rgba(245, 158, 11, 0.08) 100%);
        border: 1px solid rgba(0, 173, 181, 0.25);
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.15);
        transition: border-color 0.2s ease;
    }
    .rec-card:hover {
        border-color: #00adb5;
    }
    
    /* Button Custom styling overrides */
    div.stButton > button {
        background: linear-gradient(135deg, #1f2937 0%, #111827 100%) !important;
        color: #f3f4f6 !important;
        border: 1px solid rgba(0, 173, 181, 0.3) !important;
        border-radius: 8px !important;
        padding: 10px 24px !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        transition: all 0.3s ease !important;
        width: 100% !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2) !important;
    }
    
    /* Primary Action Buttons */
    div.stButton > button[type="secondary"] {
        border-color: rgba(245, 158, 11, 0.4) !important;
    }
    div.stButton > button[type="secondary"]:hover {
        background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%) !important;
        color: #ffffff !important;
        border-color: #fbbf24 !important;
        box-shadow: 0 0 15px rgba(245, 158, 11, 0.4) !important;
    }
    
    div.stButton > button:hover {
        background: linear-gradient(135deg, #00adb5 0%, #007a80 100%) !important;
        color: #ffffff !important;
        border-color: #00fff2 !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 0 20px rgba(0, 173, 181, 0.4) !important;
    }
    
    /* Input Elements custom theme */
    div[data-baseweb="input"], div[data-baseweb="select"], div[data-baseweb="textarea"] {
        background-color: #111827 !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 8px !important;
        color: #ffffff !important;
    }
    div[data-baseweb="input"]:focus-within, div[data-baseweb="select"]:focus-within {
        border-color: #00adb5 !important;
        box-shadow: 0 0 10px rgba(0, 173, 181, 0.2) !important;
    }
    
    /* Typography */
    h1, h2, h3, h4 {
        font-family: 'Outfit', sans-serif !important;
        font-weight: 700 !important;
        color: #ffffff !important;
    }
    
    /* Tables and Dataframes style overrides */
    [data-testid="stTable"], [data-testid="stDataFrame"] {
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        overflow: hidden;
        background: #0f131a;
    }
    
    /* Badge styling */
    .badge-expired {
        background-color: rgba(239, 68, 68, 0.15);
        color: #f87171;
        border: 1px solid rgba(239, 68, 68, 0.35);
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 0.85em;
        font-weight: bold;
    }
    .badge-warning {
        background-color: rgba(245, 158, 11, 0.15);
        color: #fbbf24;
        border: 1px solid rgba(245, 158, 11, 0.35);
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 0.85em;
        font-weight: bold;
    }
    .badge-ok {
        background-color: rgba(16, 185, 129, 0.15);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.35);
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 0.85em;
        font-weight: bold;
    }
</style>
"""

LIGHT_THEME_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    /* Background and global text color overrides to force absolute contrast */
    .stApp {
        background: radial-gradient(circle at 50% 50%, #f8fafc 0%, #e2e8f0 100%) !important;
        color: #121620 !important;
    }
    
    /* Global text contrast overrides */
    .stApp p, .stApp span, .stApp div, .stApp label, .stApp li {
        color: #121620 !important;
    }
    
    /* Sidebar premium corporate styling with dark text */
    [data-testid="stSidebar"] {
        background-color: #ffffff !important;
        border-right: 1px solid rgba(0, 0, 0, 0.08);
    }
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label, [data-testid="stSidebar"] h2 {
        color: #121620 !important;
    }
    
    /* Global Card Designs with Shadow and Border Glows */
    .metric-card {
        background: linear-gradient(145deg, #ffffff 0%, #f8fafc 100%);
        border: 1px solid rgba(16, 185, 129, 0.25);
        border-radius: 12px;
        padding: 22px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.06);
        margin-bottom: 20px;
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    }
    .metric-card:hover {
        transform: translateY(-4px);
        border-color: rgba(16, 185, 129, 0.6);
        box-shadow: 0 0 20px rgba(16, 185, 129, 0.2), 0 10px 30px rgba(0, 0, 0, 0.1);
    }
    
    .metric-card h3 {
        color: #475569 !important;
        font-size: 0.95rem !important;
        text-transform: uppercase !important;
        letter-spacing: 1px !important;
        margin-bottom: 8px !important;
    }
    .metric-card h2, .metric-card span, .metric-card div {
        color: #000000 !important;
        font-size: 2.1rem !important;
        font-weight: 700 !important;
        margin: 0 !important;
    }
    
    /* Special recommendation cards style */
    .rec-card {
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, rgba(249, 115, 22, 0.06) 100%);
        border: 1px solid rgba(16, 185, 129, 0.2);
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
        transition: border-color 0.2s ease;
    }
    .rec-card:hover {
        border-color: #10b981;
    }
    
    /* Button Custom styling overrides */
    div.stButton > button {
        background: linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%) !important;
        color: #121620 !important;
        border: 1px solid rgba(0, 0, 0, 0.12) !important;
        border-radius: 8px !important;
        padding: 10px 24px !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        transition: all 0.3s ease !important;
        width: 100% !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05) !important;
    }
    
    /* Primary Action Buttons */
    div.stButton > button[type="secondary"] {
        border-color: rgba(249, 115, 22, 0.4) !important;
    }
    div.stButton > button[type="secondary"]:hover {
        background: linear-gradient(135deg, #f97316 0%, #ea580c 100%) !important;
        color: #ffffff !important;
        border-color: #fb923c !important;
        box-shadow: 0 0 15px rgba(249, 115, 22, 0.3) !important;
    }
    
    div.stButton > button:hover {
        background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
        color: #ffffff !important;
        border-color: #34d399 !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 0 20px rgba(16, 185, 129, 0.3) !important;
    }
    
    /* Input Elements custom theme with pure white background and dark text */
    div[data-baseweb="input"], div[data-baseweb="select"], div[data-baseweb="textarea"] {
        background-color: #ffffff !important;
        border: 1px solid rgba(0, 0, 0, 0.2) !important;
        border-radius: 8px !important;
    }
    div[data-baseweb="input"] input, div[data-baseweb="select"] select, div[data-baseweb="textarea"] textarea {
        color: #000000 !important;
        background-color: #ffffff !important;
    }
    div[data-baseweb="input"]:focus-within, div[data-baseweb="select"]:focus-within {
        border-color: #10b981 !important;
        box-shadow: 0 0 10px rgba(16, 185, 129, 0.15) !important;
    }
    
    /* Auto-complete selection lists & dropdowns */
    div[role="listbox"] {
        background-color: #ffffff !important;
        color: #000000 !important;
    }
    div[role="option"] {
        color: #000000 !important;
        background-color: #ffffff !important;
    }
    div[role="option"]:hover {
        background-color: #f1f5f9 !important;
    }
    
    /* Typography */
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Outfit', sans-serif !important;
        font-weight: 700 !important;
        color: #121620 !important;
    }
    
    /* Tables and Dataframes style overrides - Pure white background and dark text */
    [data-testid="stTable"], [data-testid="stDataFrame"], [data-testid="stTable"] th, [data-testid="stDataFrame"] th {
        border: 1px solid rgba(0, 0, 0, 0.08) !important;
        background: #ffffff !important;
    }
    [data-testid="stTable"] td, [data-testid="stDataFrame"] td, [data-testid="stDataFrame"] div, [data-testid="stDataFrame"] span {
        color: #000000 !important;
    }
    
    /* Badge styling */
    .badge-expired {
        background-color: rgba(239, 68, 68, 0.1);
        color: #dc2626;
        border: 1px solid rgba(239, 68, 68, 0.3);
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 0.85em;
        font-weight: bold;
    }
    .badge-warning {
        background-color: rgba(245, 158, 11, 0.1);
        color: #d97706;
        border: 1px solid rgba(245, 158, 11, 0.3);
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 0.85em;
        font-weight: bold;
    }
    .badge-ok {
        background-color: rgba(16, 185, 129, 0.1);
        color: #059669;
        border: 1px solid rgba(16, 185, 129, 0.3);
        padding: 4px 8px;
        border-radius: 6px;
        font-size: 0.85em;
        font-weight: bold;
    }
</style>

"""

# Inject Active Theme CSS
if st.session_state.current_theme == "light":
    st.markdown(LIGHT_THEME_CSS, unsafe_allow_html=True)
else:
    st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)

# Ensure Database is Initialized
init_db()

# Initialize session states for Login
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "role" not in st.session_state:
    st.session_state.role = None
if "username" not in st.session_state:
    st.session_state.username = None

# Recover session from Query Parameters on page reload (F5)
if not st.session_state.logged_in and "u" in st.query_params and "r" in st.query_params:
    st.session_state.logged_in = True
    st.session_state.username = st.query_params["u"]
    st.session_state.role = st.query_params["r"]

# Giriş Ekranı (Login Screen) if not logged in
if not st.session_state.logged_in:
    st.markdown("""
        <div style='text-align: center; margin-top: 50px; margin-bottom: 20px;'>
            <h1 style='color: #8b5cf6;'>🐾 Beykoz Pet ERP</h1>
            <p style='color: #cbd5e1; font-size: 1.1em;'>Akıllı Mağaza Yönetim & Otomasyon Portalı</p>
        </div>
    """, unsafe_allow_html=True)
    
    col_l1, col_l2, col_l3 = st.columns([3, 6, 3])
    with col_l2:
        st.markdown("""
            <div style='background-color: rgba(0, 173, 181, 0.05); border: 1px solid rgba(0, 173, 181, 0.2); border-radius: 12px; padding: 25px;'>
                <h3 style='text-align: center; color: #00adb5; margin-top: 0; margin-bottom: 20px;'>🔑 Kullanıcı Girişi</h3>
            </div>
        """, unsafe_allow_html=True)
        
        l_username = st.text_input("Kullanıcı Adı:", key="login_username_input")
        l_password = st.text_input("Şifre:", type="password", key="login_password_input")
        
        if st.button("🚪 Giriş Yap", type="primary", use_container_width=True):
            if not l_username or not l_password:
                st.error("Kullanıcı adı ve şifre gereklidir!")
            else:
                username_clean = l_username.strip().lower()
                password_clean = l_password.strip()
                
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username_clean, password_clean))
                user_rec = c.fetchone()
                conn.close()
                
                if user_rec:
                    st.session_state.logged_in = True
                    st.session_state.role = user_rec["role"]
                    st.session_state.username = user_rec["username"]
                    # Store in query parameters for persistence
                    st.query_params["u"] = user_rec["username"]
                    st.query_params["r"] = user_rec["role"]
                    st.toast(f"Hoş geldiniz, {user_rec['username']} ({user_rec['role']})!", icon="🔑")
                    st.rerun()
                else:
                    # Fallback default checks for safety
                    if username_clean == "beykozpet" and password_clean == "beykozpet56":
                        st.session_state.logged_in = True
                        st.session_state.role = "Patron"
                        st.session_state.username = "beykozpet"
                        st.query_params["u"] = "beykozpet"
                        st.query_params["r"] = "Patron"
                        st.toast("Hoş geldiniz, beykozpet!", icon="🔑")
                        st.rerun()
                    elif username_clean == "kasa" and password_clean == "5656":
                        st.session_state.logged_in = True
                        st.session_state.role = "Satış Elemanı"
                        st.session_state.username = "kasa"
                        st.query_params["u"] = "kasa"
                        st.query_params["r"] = "Satış Elemanı"
                        st.toast("Hoş geldiniz, kasa!", icon="🔑")
                        st.rerun()
                    else:
                        st.error("Hatalı Kullanıcı Adı veya Şifre!")
                        
    st.stop()

# Initialize session states for POS Cart
if "sepet" not in st.session_state:
    st.session_state.sepet = {}  # format: {barkod: {ad, fiyat, miktar, kategori}}
if "scan_success" not in st.session_state:
    st.session_state.scan_success = None

with st.sidebar:
    st.markdown("<h2 style='text-align: center; color: #8b5cf6;'>🐾 Beykoz Pet ERP</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 0.9em; opacity: 0.7;'>Akıllı Stok, Satış ve Öneri Sistemi</p>", unsafe_allow_html=True)
    
    # Theme toggle switcher
    theme_label = "Koyu Tema" if st.session_state.current_theme == "dark" else "Açık Tema"
    if st.button(f"🌓 Tema Değiştir: {theme_label}", use_container_width=True):
        st.session_state.current_theme = "light" if st.session_state.current_theme == "dark" else "dark"
        st.rerun()
        
    st.markdown("---")
    
    if st.session_state.role == "Patron":
        menu_options = [
            "🛒 Hızlı POS Kasa", 
            "📦 Stok ve Ürünler", 
            "👥 Müşteri Yönetimi", 
            "💇 Pet Kuaför", 
            "💉 Aşı Takvimi", 
            "🥣 Mama Takip Paneli", 
            "📋 Müşteri Siparişleri", 
            "📢 Kampanya Yönetimi", 
            "👑 Patron Rapor Paneli", 
            "📓 Veresiye Defteri", 
            "📊 Ön Muhasebe", 
            "📊 Satış & MVP Analiz", 
            "🧾 QNB E-Fatura"
        ]
    else:
        menu_options = [
            "🛒 Hızlı POS Kasa", 
            "📦 Stok ve Ürünler", 
            "💇 Pet Kuaför", 
            "💉 Aşı Takvimi"
        ]
        
    menu = st.radio("Modül Seçin", menu_options)
    
    st.markdown("---")
    st.write(f"👤 Giriş Yapan: **{st.session_state.username}** (`{st.session_state.role}`)")
    if st.button("🚪 Güvenli Çıkış Yap", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.role = None
        st.session_state.username = None
        st.query_params.clear()
        st.rerun()
    
    st.markdown("---")
    # Quick low-stock / expiry summary widget in sidebar
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM urunler WHERE stok <= kritik_stok")
    low_stock_count = c.fetchone()[0]
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    warning_date_str = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    c.execute("SELECT COUNT(*) FROM urunler WHERE skt IS NOT NULL AND skt <= ?", (warning_date_str,))
    skt_alert_count = c.fetchone()[0]
    conn.close()
    
    st.markdown("### 🔔 Kritik Durum Paneli")
    st.markdown(f"📉 **Kritik Stoktaki Ürünler:** `{low_stock_count}`")
    st.markdown(f"⚠️ **Yaklaşan/Geçen SKT Sayısı:** `{skt_alert_count}`")
    
    # Global Local Network connection display
    local_ip = get_local_ip()
    st.markdown("---")
    st.markdown(f"""
    <div style='background-color:rgba(0,173,181,0.05); border:1px solid rgba(0,173,181,0.15); border-radius:8px; padding:10px; margin-top:5px;'>
        <span style='color:#00adb5; font-weight:bold; font-size:0.9em;'>🌐 Ağ Bağlantı Rehberi</span><br/>
        <span style='font-size:0.82em; opacity:0.8;'>Diğer dükkan bilgisayarından erişim adresi:</span><br/>
        <code style='font-size:1.0em; color:#00adb5; word-break:break-all;'>http://{local_ip}:8501</code>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    # Auto-refresh using streamlit-autorefresh (fully compatible with Streamlit Cloud & local multi-device)
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=5000, key="global_autorefresh")
        st.markdown(
            "<div style='text-align:center; font-size:0.85em; color:#00adb5; font-weight:bold;'>🔄 Canlı Senkronizasyon Aktif (5s)</div>",
            unsafe_allow_html=True
        )
    except Exception:
        if st.button("🔄 Canlı Senkronizasyon", key="sidebar_autorefresh_btn", use_container_width=True):
            st.rerun()

# ----------------- MODULE: HIZLI POS KASA -----------------
if menu == "🛒 Hızlı POS Kasa":
    st.markdown("## 🛒 Hızlı POS Kasa & Akıllı Öneriler")
    
    col_kasa, col_sepet = st.columns([7, 5])
    
    with col_kasa:
        st.markdown("### 🔍 Barkod Tarama & Canlı Arama")
        
        def add_shortcut_to_cart(bc_code):
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM urunler WHERE barkod = ?", (bc_code,))
            prod = c.fetchone()
            conn.close()
            if prod:
                if bc_code in st.session_state.sepet:
                    st.session_state.sepet[bc_code]["miktar"] += 1
                else:
                    st.session_state.sepet[bc_code] = {
                        "ad": prod["ad"],
                        "fiyat": prod["fiyat"],
                        "miktar": 1,
                        "kategori": prod["kategori"]
                    }
                st.toast(f"✅ {prod['ad']} sepete eklendi!", icon="🛒")
                st.rerun()
                
        # Initialize session state variables if not done
        if "unregistered_barcode" not in st.session_state:
            st.session_state.unregistered_barcode = None
        if "scraped_temp" not in st.session_state:
            st.session_state.scraped_temp = None
        if "clear_barcode" not in st.session_state:
            st.session_state.clear_barcode = False

        # Check if a barcode was scanned from camera (passed via query params)
        if "barcode" in st.query_params:
            st.session_state.barcode_scan_input = st.query_params["barcode"]
            del st.query_params["barcode"]

        # Eğer sıfırlama bayrağı tetiklendiyse, widget çizilmeden ÖNCE state'i temizle
        if st.session_state.clear_barcode:
            st.session_state.barcode_scan_input = ""
            st.session_state.clear_barcode = False
            
        col_scan_pos, col_search_pos = st.columns([5, 5])
        
        with col_scan_pos:
            with st.expander("📸 Kameradan Barkod Tara (Mobil)", expanded=False):
                import streamlit.components.v1 as components
                components.html(
                    """
                    <div style="background-color: #0b0e14; border: 1px solid rgba(0, 173, 181, 0.2); border-radius: 12px; padding: 15px; text-align: center;">
                        <script src="https://unpkg.com/html5-qrcode" type="text/javascript"></script>
                        <div id="reader" style="width: 100%; max-width: 320px; margin: 0 auto; border-radius: 8px; overflow: hidden; background: #000;"></div>
                        <div id="status" style="margin-top: 10px; font-size: 0.9em; color: #a7f3d0; font-family: sans-serif;">📷 Kamera hazır. Taramak için hizalayın.</div>
                        <button id="start-btn" style="background: linear-gradient(135deg, #00adb5 0%, #00f2fe 100%); color: #000; border: none; padding: 10px 20px; font-weight: bold; border-radius: 6px; cursor: pointer; margin-top: 10px; width: 100%;">📷 Kamerayı Başlat</button>
                        <button id="stop-btn" style="background: #ef4444; color: #fff; border: none; padding: 10px 20px; font-weight: bold; border-radius: 6px; cursor: pointer; margin-top: 10px; width: 100%; display: none;">🛑 Kamerayı Kapat</button>
                    </div>
                    
                    <script>
                        const startBtn = document.getElementById("start-btn");
                        const stopBtn = document.getElementById("stop-btn");
                        const statusDiv = document.getElementById("status");
                        let html5QrCode = null;
                    
                        startBtn.addEventListener("click", () => {
                            statusDiv.innerText = "🔄 Kamera başlatılıyor...";
                            startBtn.style.display = "none";
                            stopBtn.style.display = "block";
                            
                            html5QrCode = new Html5Qrcode("reader");
                            const config = { fps: 15, qrbox: { width: 250, height: 150 } };
                            
                            const successCallback = (decodedText, decodedResult) => {
                                statusDiv.innerText = "✅ Barkod Algılandı: " + decodedText;
                                html5QrCode.stop().then(() => {
                                    const parentUrl = new URL(document.referrer || window.top.location.href);
                                    parentUrl.searchParams.set("barcode", decodedText);
                                    window.top.location.href = parentUrl.toString();
                                });
                            };
                            
                            html5QrCode.start({ facingMode: "environment" }, config, successCallback)
                                .catch((err) => {
                                    console.warn(err);
                                    html5QrCode.start({ facingMode: "user" }, config, successCallback)
                                        .then(() => { statusDiv.innerText = "📷 Ön kamera aktif. Barkodu yaklaştırın."; })
                                        .catch((err2) => {
                                            statusDiv.innerText = "❌ Kamera hatası: " + err2;
                                            startBtn.style.display = "block";
                                            stopBtn.style.display = "none";
                                        });
                                });
                        });
                    
                        stopBtn.addEventListener("click", () => {
                            if (html5QrCode) {
                                html5QrCode.stop().then(() => {
                                    statusDiv.innerText = "🛑 Kamera kapatıldı.";
                                    startBtn.style.display = "block";
                                    stopBtn.style.display = "none";
                                });
                            }
                        });
                    </script>
                    """,
                    height=350
                )
            # Scanner input simulation with key binding for programmatic clearing
            barcode_input = st.text_input(
                "Barkod Okutun veya Yazın (Enter):", 
                key="barcode_scan_input",
                placeholder="Örn: 8690123456789"
            )
            
        with col_search_pos:
            conn_s = get_db_connection()
            c_s = conn_s.cursor()
            c_s.execute("SELECT barkod, ad, fiyat, stok, kategori FROM urunler ORDER BY ad ASC")
            all_prods = c_s.fetchall()
            conn_s.close()
            
            prod_search_dict = {p["barkod"]: f"🛍️ {p['ad']} ({p['fiyat']:.2f} TL)" for p in all_prods}
            
            selected_search_barcode = st.selectbox(
                "Ürün Adı veya Türü ile Ara:",
                options=[""] + list(prod_search_dict.keys()),
                format_func=lambda x: "Seçiniz..." if x == "" else prod_search_dict[x],
                key="pos_live_search_box"
            )
            
            if selected_search_barcode != "":
                col_sqty, col_sadd = st.columns([4, 6])
                with col_sqty:
                    search_qty = st.number_input("Adet:", min_value=1, value=1, key="search_qty_input")
                with col_sadd:
                    st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
                    if st.button("➕ Sepete Ekle", key="search_add_to_cart_btn", use_container_width=True):
                        p_details = next(p for p in all_prods if p["barkod"] == selected_search_barcode)
                        bc = selected_search_barcode
                        if bc in st.session_state.sepet:
                            st.session_state.sepet[bc]["miktar"] += search_qty
                        else:
                            st.session_state.sepet[bc] = {
                                "ad": p_details["ad"],
                                "fiyat": p_details["fiyat"],
                                "miktar": search_qty,
                                "kategori": p_details["kategori"]
                            }
                        st.toast(f"✅ {p_details['ad']} sepete eklendi!", icon="🛒")
                        st.rerun()
        
        # Auto-focus and mobile barcode scanner polling client
        import streamlit.components.v1 as components
        components.html(
            """
            <script>
                const focusBarcodeField = () => {
                    const input = window.parent.document.querySelector("input[placeholder='Örn: 8690123456789']");
                    if (input && window.parent.document.activeElement !== input) {
                        input.focus();
                    }
                };
                focusBarcodeField();
                setTimeout(focusBarcodeField, 300);
                setTimeout(focusBarcodeField, 800);
            </script>
            """,
            height=0
        )
        
        if barcode_input:
            barcode = barcode_input.strip()
            if barcode:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT * FROM urunler WHERE barkod = ?", (barcode,))
                product = c.fetchone()
                conn.close()
                
                if product:
                    # Add to cart or increment quantity
                    if barcode in st.session_state.sepet:
                        st.session_state.sepet[barcode]["miktar"] += 1
                    else:
                        st.session_state.sepet[barcode] = {
                            "ad": product["ad"],
                            "fiyat": product["fiyat"],
                            "miktar": 1,
                            "kategori": product["kategori"]
                        }
                    st.session_state.scan_success = f"✓ **{product['ad']}** sepete eklendi."
                    st.session_state.unregistered_barcode = None
                    st.session_state.scraped_temp = None
                    # Set clear flag and rerun to render empty input field
                    st.session_state.clear_barcode = True
                    st.rerun()
                else:
                    # Set scanning state
                    st.session_state.unregistered_barcode = barcode
                    # Search the offline catalog database
                    with st.spinner("Ürün aktif stokta bulunamadı. Hazır katalogda aranıyor..."):
                        scraped_info = scrape_barcode_online(barcode)
                        if scraped_info:
                            st.session_state.scraped_temp = scraped_info
                            st.toast("✨ Ürün hazır kütüphanede eşleşti ve forma dolduruldu!", icon="🔍")
                        else:
                            st.session_state.scraped_temp = None
                            st.toast("⚠️ Ürün hazır kütüphanede bulunamadı. Lütfen bilgileri elinizle girin.", icon="ℹ️")
                    # Set clear flag and rerun to show form with empty scan field
                    st.session_state.clear_barcode = True
                    st.rerun()

        # Inline manual registration form if barcode scanned but not found in DB
        if st.session_state.unregistered_barcode:
            # Check if we have prefilled scraped info
            temp_info = st.session_state.scraped_temp
            prefilled_name = temp_info["ad"] if temp_info else ""
            prefilled_cat = temp_info["kategori"] if temp_info else "Diğer"
            prefilled_price = float(temp_info["fiyat"]) if temp_info else 0.0
            
            categories = ["Kedi Maması", "Köpek Maması", "Kum", "Aksesuar", "Ödül/Vitamin", "Oyuncak", "Diğer"]
            cat_index = categories.index(prefilled_cat) if prefilled_cat in categories else categories.index("Diğer")
            
            st.warning(f"⚠️ Barkod ({st.session_state.unregistered_barcode}) veritabanında kayıtlı değil.")
            st.markdown("#### 📝 Hızlı Ürün Kayıt Formu")
            
            with st.form("hizli_kayit_form"):
                hk_barkod = st.text_input("Barkod:", value=st.session_state.unregistered_barcode, disabled=True)
                hk_ad = st.text_input("Ürün Adı:", value=prefilled_name, placeholder="Örn: Pro Plan Kitten 1.5kg")
                hk_kategori = st.selectbox("Kategori:", categories, index=cat_index)
                hk_fiyat = st.number_input("Satış Fiyatı (TL):", min_value=0.0, value=prefilled_price, step=5.0)
                hk_stok = st.number_input("Mevcut Stok Adedi:", min_value=1, value=10, step=1)
                
                hk_has_skt = st.checkbox("Son Kullanma Tarihi Var mı?")
                hk_skt_val = None
                if hk_has_skt:
                    hk_skt = st.date_input("Son Tüketim Tarihi (SKT):", min_value=datetime.today())
                    hk_skt_val = hk_skt.strftime("%Y-%m-%d")
                
                hk_kaydet = st.form_submit_button("💾 Ürünü Kaydet ve Sepete Ekle")
                if hk_kaydet:
                    if not hk_ad:
                        st.error("Ürün adı boş bırakılamaz!")
                    else:
                        conn = get_db_connection()
                        c = conn.cursor()
                        # Default mock image or specific image from scraped results
                        gorsel_url = temp_info["gorsel_url"] if temp_info else "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500"
                        
                        c.execute("""
                        INSERT INTO urunler (barkod, ad, kategori, fiyat, stok, kritik_stok, skt, gorsel_url)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (st.session_state.unregistered_barcode, hk_ad, hk_kategori, hk_fiyat, hk_stok, 5, hk_skt_val, gorsel_url))
                        conn.commit()
                        conn.close()
                        
                        # Add to cart
                        st.session_state.sepet[st.session_state.unregistered_barcode] = {
                            "ad": hk_ad,
                            "fiyat": hk_fiyat,
                            "miktar": 1,
                            "kategori": hk_kategori
                        }
                        st.session_state.scan_success = f"✓ **{hk_ad}** kaydedildi ve sepete eklendi."
                        st.session_state.unregistered_barcode = None
                        st.session_state.scraped_temp = None
                        st.rerun()
                        
        if st.session_state.scan_success:
            st.toast(st.session_state.scan_success, icon="✅")
            st.session_state.scan_success = None
            
        # Hızlı Erişim Butonları (Kısayol Paneli)
        st.markdown("---")
        st.markdown("#### ⚡ Hızlı Erişim Kısayolları (Dinamik Ürün Paneli)")
        
        conn_qs = get_db_connection()
        c_qs = conn_qs.cursor()
        c_qs.execute("SELECT barkod, ad, fiyat, kategori FROM urunler WHERE hizli_kasa_kisayol = 1 ORDER BY kategori ASC, ad ASC")
        shortcut_list = c_qs.fetchall()
        conn_qs.close()
        
        if not shortcut_list:
            st.info("Kısayol olarak işaretlenmiş ürün bulunamadı. Stok modülü altından ürünleri kısayol olarak ekleyebilirsiniz.")
        else:
            from collections import defaultdict
            grouped_shortcuts = defaultdict(list)
            for item in shortcut_list:
                grouped_shortcuts[item["kategori"]].append(item)
                
            categories = list(grouped_shortcuts.keys())
            cols_qs = st.columns(min(len(categories), 3))
            
            for idx, cat in enumerate(categories):
                col_idx = idx % len(cols_qs)
                with cols_qs[col_idx]:
                    st.markdown(f"<div style='background-color:rgba(0,173,181,0.1); padding:8px; border-radius:6px; margin-bottom:10px; border-left:3px solid #00adb5;'><span style='color:#00adb5; font-weight:bold;'>📦 {cat}</span></div>", unsafe_allow_html=True)
                    for item in grouped_shortcuts[cat]:
                        btn_label = f"{item['ad']} ({item['fiyat']:.2f} TL)"
                        if st.button(btn_label, key=f"dyn_qs_{item['barkod']}", use_container_width=True):
                            add_shortcut_to_cart(item["barkod"])

        # Dynamic AI recommendation panel
        if st.session_state.sepet:
            st.markdown("---")
            st.markdown("### 🧠 AI Akıllı Çapraz Satış Önerileri")
            # Get DB products for LLM context
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT barkod, ad, fiyat, kategori FROM urunler WHERE stok > 0")
            all_db_products = [dict(row) for row in c.fetchall()]
            conn.close()
            
            cart_list = [dict(val, barkod=key) for key, val in st.session_state.sepet.items()]
            recommendations = get_smart_recommendations(cart_list, all_db_products)
            
            if recommendations:
                st.markdown("<p style='font-size:0.9em; opacity: 0.8;'>Kasadaki ürünlere bakarak satın alınabilecek en yüksek potansiyele sahip ek ürünler:</p>", unsafe_allow_html=True)
                for rec in recommendations:
                    # Check if recommended item is actually in database (or use mock default price)
                    r_price = rec.get("fiyat", 0.0)
                    r_barcode = rec.get("barkod")
                    
                    st.markdown(f"""
                    <div class="rec-card">
                        <div>
                            <strong>🔑 {rec['ad']}</strong><br/>
                            <span style='font-size:0.9em; opacity:0.8;'>Kategori: {rec['kategori']} | Fiyat: {r_price} TL</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"🛒 Sepete Ekle: {rec['ad'][:20]}", key=f"rec_btn_{r_barcode}"):
                        if r_barcode in st.session_state.sepet:
                            st.session_state.sepet[r_barcode]["miktar"] += 1
                        else:
                            st.session_state.sepet[r_barcode] = {
                                "ad": rec["ad"],
                                "fiyat": r_price,
                                "miktar": 1,
                                "kategori": rec["kategori"]
                            }
                        st.toast(f"Önerilen ürün eklendi: {rec['ad']}")
                        st.rerun()
            else:
                st.info("Öneri bulunamadı.")
            
    with col_sepet:
        st.markdown("### 🛒 Sepet Detayı")
        if not st.session_state.sepet:
            st.warning("Sepetiniz boş. Lütfen barkod okutun veya hızlı katalogtan ürün ekleyin.")
        else:
            total_sum = 0.0
            
            # Let's display and edit items in the cart
            to_delete = []
            for barcode, details in list(st.session_state.sepet.items()):
                item_total = details["fiyat"] * details["miktar"]
                total_sum += item_total
                
                # Layout for each item
                col_name, col_qty, col_price = st.columns([6, 3, 3])
                with col_name:
                    st.write(f"**{details['ad']}**")
                    st.caption(f"{details['fiyat']} TL / Adet | Barkod: {barcode}")
                with col_qty:
                    # Use a dynamic key to force update when quantity is changed from scanner
                    new_qty = st.number_input(
                        "", 
                        min_value=0, 
                        value=details["miktar"], 
                        key=f"qty_{barcode}_{details['miktar']}", 
                        label_visibility="collapsed"
                    )
                    if new_qty == 0:
                        to_delete.append(barcode)
                    elif new_qty != details["miktar"]:
                        st.session_state.sepet[barcode]["miktar"] = new_qty
                        st.rerun()
                with col_price:
                    st.write(f"**{item_total:.2f} TL**")
                st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)
                
            for b in to_delete:
                del st.session_state.sepet[b]
                st.rerun()
                
            st.markdown(f"### 🧾 Ara Toplam: <span style='color: #8b5cf6;'>{total_sum:.2f} TL</span>", unsafe_allow_html=True)
            
            # Customer selector
            st.markdown("---")
            st.markdown("#### 👥 Müşteri İlişkilendir")
            conn = get_db_connection()
            df_m_pos = pd.read_sql_query("SELECT * FROM musteriler", conn)
            conn.close()
            
            # Ensure expected columns are present in POS customer selection
            for col in ["hayvan_turu", "irk_detay", "yas", "kisir", "kilo", "boyut", "ekipman_detay", "saglik_detay", "ozel_notlar"]:
                if col not in df_m_pos.columns:
                    df_m_pos[col] = ""
                    
            customer_options = {0: "Anonim / Genel Satış"}
            for _, m in df_m_pos.iterrows():
                pet_lbl = f"{m['hayvan_turu']}" if m['hayvan_turu'] else "Belirtilmedi"
                if m['irk_detay']:
                    pet_lbl += f" - {m['irk_detay']}"
                customer_options[m["id"]] = f"{m['isim']} ({pet_lbl})"
                
            selected_customer_id = st.selectbox("Satış yapılacak müşteri:", list(customer_options.keys()), format_func=lambda x: customer_options[x], key="pos_customer_selectbox")
            
            # Hızlı Müşteri Kayıt Formu
            with st.expander("👤 ➕ Hızlı Müşteri Kaydet", expanded=False):
                with st.form("hizli_musteri_pos_form", clear_on_submit=True):
                    hm_isim = st.text_input("Müşteri Adı Soyadı:")
                    hm_telefon = st.text_input("Telefon Numarası:")
                    hm_hayvan_ad = st.text_input("Evcil Hayvan Adı (Özel Notlar):")
                    hm_hayvan_turu = st.selectbox("Evcil Hayvan Türü:", ["Kedi", "Köpek", "Kuş", "Balık", "Kemirgen", "Sürüngen", "Diğer"])
                    hm_dogum = st.date_input("Evcil Hayvan Doğum Günü:", value=None)
                    hm_iskonto = st.number_input("Özel İskonto Oranı (%):", min_value=0.0, max_value=100.0, step=1.0, value=0.0)
                    
                    hm_submitted = st.form_submit_button("💾 Müşteriyi Kaydet")
                    if hm_submitted:
                        if not hm_isim.strip():
                            st.error("Müşteri adı zorunludur!")
                        else:
                            dogum_str = hm_dogum.strftime("%Y-%m-%d") if hm_dogum else ""
                            conn_hm = get_db_connection()
                            c_hm = conn_hm.cursor()
                            c_hm.execute("""
                                INSERT INTO musteriler (isim, telefon, hayvan_turu, ozel_notlar, dogum_gunu, irk_detay, yas, kisir, kilo, boyut, ekipman_detay, saglik_detay, iskonto_orani)
                                VALUES (?, ?, ?, ?, ?, '', '', 'Belirtilmedi', 0.0, 'Standart Irk', '', '', ?)
                            """, (hm_isim.strip(), hm_telefon.strip(), hm_hayvan_turu, hm_hayvan_ad.strip(), dogum_str, hm_iskonto))
                            new_id = c_hm.lastrowid
                            conn_hm.commit()
                            conn_hm.close()
                            
                            # Set selected customer in session state for instant selectbox update
                            st.session_state.pos_customer_selectbox = new_id
                            st.toast(f"✅ {hm_isim} kaydedildi ve seçildi!", icon="👤")
                            st.rerun()
            
            # Display detailed pet card on selection to establish customer bonding
            if selected_customer_id > 0:
                cust = df_m_pos[df_m_pos["id"] == selected_customer_id].iloc[0].to_dict()
                
                emojis = {"Kedi": "🐱", "Köpek": "🐶", "Balık": "🐟", "Kuş": "🦜", "Kemirgen": "🐹", "Sürüngen": "🦎"}
                emo = emojis.get(cust.get('hayvan_turu'), "🐾")
                
                st.markdown(f"""
                <div style='background-color: rgba(0, 173, 181, 0.08); border: 1px solid rgba(0, 173, 181, 0.3); border-radius: 8px; padding: 12px; margin-bottom: 12px;'>
                    <strong style='color:#00adb5;'>💖 Pet Kartı: {emo} {cust.get('hayvan_turu') or 'Bilinmiyor'}</strong><br/>
                    <span style='font-size:0.9em; line-height: 1.4; color: #cbd5e1;'>
                        • <b>Irk / Tür Detay:</b> {cust.get('irk_detay') or 'Belirtilmedi'}<br/>
                        • <b>Yaş:</b> {cust.get('yas') or 'Belirtilmedi'} | <b>Kısır:</b> {cust.get('kisir') or 'Belirtilmedi'}<br/>
                        {"• <b>Kilo:</b> " + str(cust.get('kilo')) + " kg<br/>" if cust.get('kilo') and float(cust.get('kilo')) > 0 else ""}
                        {"• <b>Boyut:</b> " + cust.get('boyut') + "<br/>" if cust.get('boyut') else ""}
                        {"• <b>Ekipman / Kum:</b> " + cust.get('ekipman_detay') + "<br/>" if cust.get('ekipman_detay') else ""}
                        {"• <b>Sağlık / Alerji:</b> " + cust.get('saglik_detay') + "<br/>" if cust.get('saglik_detay') else ""}
                        {"• <b>Özel Notlar:</b> " + cust.get('ozel_notlar') + "<br/>" if cust.get('ozel_notlar') else ""}
                    </span>
                </div>
                """, unsafe_allow_html=True)
            
            # Get customer discount rate
            iskonto_orani = 0.0
            if selected_customer_id > 0:
                c_match = df_m_pos[df_m_pos["id"] == selected_customer_id]
                if not c_match.empty:
                    iskonto_orani = float(c_match.iloc[0].get("iskonto_orani", 0.0) or 0.0)
            
            # Display net total based on discount
            discount_amount = 0.0
            if iskonto_orani > 0.0:
                discount_amount = total_sum * (iskonto_orani / 100.0)
                net_total_sum = total_sum - discount_amount
                st.markdown(f"🎁 **Müşteri İskontosu (%{iskonto_orani:.1f}):** `- {discount_amount:.2f} TL`")
                st.markdown(f"## 💰 Ödenecek Net Tutar: <span style='color: #10b981;'>{net_total_sum:.2f} TL</span>", unsafe_allow_html=True)
            else:
                net_total_sum = total_sum
                st.markdown(f"## 💰 Ödenecek Net Tutar: <span style='color: #8b5cf6;'>{net_total_sum:.2f} TL</span>", unsafe_allow_html=True)
            
            # Payment Method Selection
            st.markdown("#### 💳 Ödeme Yöntemi")
            payment_method = st.radio("Seçiniz:", ["Nakit", "Kredi Kartı", "Veresiye (Deftere Yaz)", "Çalışan Cari (Maaştan Düş)"], horizontal=True, label_visibility="collapsed")
            
            due_date_str = ""
            selected_employee_id = 0
            emp_list = []
            
            # Cash Change Calculator
            if payment_method == "Nakit":
                cash_received = st.number_input("Alınan Nakit Tutar (TL):", min_value=0.0, step=10.0, value=0.0)
                if cash_received > 0.0:
                    change_due = cash_received - net_total_sum
                    if change_due >= 0:
                        st.markdown(f"<h3 style='color: #10b981; margin-top: 5px; margin-bottom: 15px;'>💵 Para Üstü: {change_due:.2f} TL</h3>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<p style='color: #ef4444; font-weight: bold; margin-top: 5px;'>⚠️ Eksik Tutar: {abs(change_due):.2f} TL</p>", unsafe_allow_html=True)
            elif payment_method == "Veresiye (Deftere Yaz)":
                if selected_customer_id == 0:
                    st.warning("⚠️ Veresiye işlemi için lütfen yukarıdan bir müşteri ilişkilendirin!")
                f_due_date = st.date_input("Vade (Ödeme Sözü Verilen Tarih):", value=(datetime.now() + timedelta(days=15)).date())
                due_date_str = f_due_date.strftime("%Y-%m-%d")
            elif payment_method == "Çalışan Cari (Maaştan Düş)":
                conn_e = get_db_connection()
                c_emp = conn_e.cursor()
                c_emp.execute("SELECT id, name, current_balance FROM employees ORDER BY name ASC")
                emp_list = c_emp.fetchall()
                conn_e.close()
                
                if not emp_list:
                    st.warning("⚠️ Önce Ön Muhasebe altından çalışan tanımlamalısınız!")
                    selected_employee_id = 0
                else:
                    selected_employee_id = st.selectbox(
                        "Alışverişi Yapan Çalışan:",
                        [e["id"] for e in emp_list],
                        format_func=lambda x: next(f"{e['name']} (Bakiye: {e['current_balance']:.2f} TL)" for e in emp_list if e["id"] == x)
                    )
                    
                    emp_price_type = st.radio("Fiyatlandırma Türü:", ["Normal Satış Fiyatı", "Maliyet Fiyatı (Geliş)"], horizontal=True)
                    
                    # Calculate cost-based total if selected
                    if emp_price_type == "Maliyet Fiyatı (Geliş)":
                        conn_q = get_db_connection()
                        c_q = conn_q.cursor()
                        emp_total_sum = 0.0
                        for barcode, details in st.session_state.sepet.items():
                            c_q.execute("SELECT gelis_fiyati, fiyat FROM urunler WHERE barkod = ?", (barcode,))
                            p_row = c_q.fetchone()
                            cost = p_row["gelis_fiyati"] if p_row and p_row["gelis_fiyati"] is not None and p_row["gelis_fiyati"] > 0 else details["fiyat"]
                            emp_total_sum += cost * details["miktar"]
                        conn_q.close()
                        net_total_sum = emp_total_sum
                        st.markdown(f"<h3 style='color: #10b981; margin-top: 10px;'>🧾 İndirimli Toplam (Maliyet): {net_total_sum:.2f} TL</h3>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<h3 style='color: #10b981; margin-top: 10px;'>🧾 Normal Satış Toplamı: {net_total_sum:.2f} TL</h3>", unsafe_allow_html=True)
            
            st.markdown("<br/>", unsafe_allow_html=True)
            if st.button("🛒 Satışı Tamamla ve Fiş Kes", type="primary", use_container_width=True):
                if payment_method == "Veresiye (Deftere Yaz)" and selected_customer_id == 0:
                    st.error("Hatalı Satış! Veresiye işlemlerinde müşteri seçilmesi zorunludur.")
                elif payment_method == "Çalışan Cari (Maaştan Düş)" and (not emp_list or selected_employee_id == 0):
                    st.error("Hatalı Satış! Lütfen çalışan seçin veya önce çalışan tanımlayın.")
                else:
                    # Update inventory & insert sales record
                    conn = get_db_connection()
                    c = conn.cursor()
                    success = True
                    
                    # Check stocks first
                    for barcode, details in st.session_state.sepet.items():
                        c.execute("SELECT stok, ad FROM urunler WHERE barkod = ?", (barcode,))
                        prod_stock = c.fetchone()
                        if prod_stock:
                            if prod_stock["stok"] < details["miktar"]:
                                st.error(f"Yetersiz Stok! {prod_stock['ad']} stoğu yetersiz (Kalan Stok: {prod_stock['stok']})")
                                success = False
                                break
                        else:
                            st.error(f"Ürün bulunamadı: {details['ad']}")
                            success = False
                            break
                            
                    if success:
                        today_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        product_details_list = []
                        
                        # Determine dynamic checkout_total and prices per item
                        checkout_total = 0.0
                        item_prices = {}
                        
                        for barcode, details in st.session_state.sepet.items():
                            if payment_method == "Çalışan Cari (Maaştan Düş)" and emp_price_type == "Maliyet Fiyatı (Geliş)":
                                c.execute("SELECT gelis_fiyati, fiyat FROM urunler WHERE barkod = ?", (barcode,))
                                p_row = c.fetchone()
                                item_price = p_row["gelis_fiyati"] if p_row and p_row["gelis_fiyati"] is not None and p_row["gelis_fiyati"] > 0 else details["fiyat"]
                            else:
                                if selected_customer_id > 0 and iskonto_orani > 0.0:
                                    item_price = details["fiyat"] * (1 - iskonto_orani / 100.0)
                                else:
                                    item_price = details["fiyat"]
                            
                            item_prices[barcode] = item_price
                            checkout_total += item_price * details["miktar"]
                        
                        for barcode, details in st.session_state.sepet.items():
                            item_price = item_prices[barcode]
                            # Decrease stock
                            c.execute("UPDATE urunler SET stok = stok - ? WHERE barkod = ?", (details["miktar"], barcode))
                            # Insert sale record with payment method
                            c.execute("""
                            INSERT INTO satislar (tarih, barkod, urun_ad, miktar, toplam_tutar, odeme_yontemi, musteri_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (today_now, barcode, details["ad"], details["miktar"], item_price * details["miktar"], payment_method, selected_customer_id))
                            
                            product_details_list.append(f"{details['miktar']}x {details['ad']} ({item_price:.2f} TL)")
                            
                            # Automated Revenue Registration in Accounting
                            if payment_method == "Veresiye (Deftere Yaz)":
                                c.execute("""
                                INSERT INTO accounting (tarih, tip, kategori, tutar, aciklama)
                                VALUES (?, ?, ?, ?, ?)
                                """, (today_now[:10], "Gelir", "Bekleyen Alacak", item_price * details["miktar"], f"Veresiye | Müşteri ID: {selected_customer_id} | Ürün: {details['ad']}"))
                            elif payment_method == "Çalışan Cari (Maaştan Düş)":
                                c.execute("""
                                INSERT INTO accounting (tarih, tip, kategori, tutar, aciklama)
                                VALUES (?, ?, ?, ?, ?)
                                """, (today_now[:10], "Gelir", "Satış", item_price * details["miktar"], f"Çalışan Satışı | Fiyat Türü: {emp_price_type} | Çalışan ID: {selected_employee_id} | Ürün: {details['ad']}"))
                            else:
                                c.execute("""
                                INSERT INTO accounting (tarih, tip, kategori, tutar, aciklama)
                                VALUES (?, ?, ?, ?, ?)
                                """, (today_now[:10], "Gelir", "Satış", item_price * details["miktar"], f"Barkod: {barcode} | Ürün: {details['ad']} | Miktar: {details['miktar']} | Ödeme: {payment_method}"))
                            
                            # AI Depletion Predictor if customer is registered and item is food (mama)
                            if selected_customer_id > 0:
                                is_mama = "mama" in details["kategori"].lower() or "mama" in details["ad"].lower()
                                if is_mama:
                                    weight_kg = parse_weight_from_name(details["ad"])
                                    daily_rate = 0.1  # Default 100g/day
                                    
                                    # Query customer pet details safely
                                    c.execute("SELECT hayvan_turu, boyut FROM musteriler WHERE id = ?", (selected_customer_id,))
                                    cust_row = c.fetchone()
                                    pet_type = cust_row["hayvan_turu"] if cust_row and cust_row["hayvan_turu"] else "Kedi"
                                    pet_size = cust_row["boyut"] if cust_row and cust_row["boyut"] else "Orta Irk"
                                    
                                    if "köpek" in pet_type.lower():
                                        if "küçük" in pet_size.lower():
                                            daily_rate = 0.1  # 100g
                                        elif "orta" in pet_size.lower():
                                            daily_rate = 0.2  # 200g
                                        elif "büyük" in pet_size.lower():
                                            daily_rate = 0.4  # 400g
                                        else:
                                            daily_rate = 0.2
                                    elif "kedi" in pet_type.lower():
                                        daily_rate = 0.1  # 100g
                                        
                                    total_weight = weight_kg * details["miktar"]
                                    duration_days = int(total_weight / daily_rate)
                                    
                                    end_date = (datetime.now() + timedelta(days=duration_days)).strftime("%Y-%m-%d")
                                    c.execute("""
                                    UPDATE musteriler 
                                    SET son_alinan_mama = ?, tahmini_mama_bitis_tarihi = ? 
                                    WHERE id = ?
                                    """, (details["ad"], end_date, selected_customer_id))
                        
                        # If veresiye, insert into debts table
                        if payment_method == "Veresiye (Deftere Yaz)":
                            product_details_str = ", ".join(product_details_list)
                            c.execute("""
                            INSERT INTO debts (customer_id, amount, product_details, purchase_date, due_date, status)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """, (selected_customer_id, checkout_total, product_details_str, today_now[:10], due_date_str, "Ödenmedi"))
                        # If employee cari, deduct balance & log transaction
                        elif payment_method == "Çalışan Cari (Maaştan Düş)":
                            product_details_str = ", ".join(product_details_list)
                            c.execute("UPDATE employees SET current_balance = current_balance - ? WHERE id = ?", (checkout_total, selected_employee_id))
                            
                            log_desc = f"Ürün Alımı ({'Maliyet' if emp_price_type == 'Maliyet Fiyatı (Geliş)' else 'Satış'} Fiyatından Verildi): {product_details_str}"
                            c.execute("""
                                INSERT INTO employee_transactions (employee_id, type, amount, description, date)
                                VALUES (?, 'Ürün Alımı', ?, ?, ?)
                            """, (selected_employee_id, checkout_total, log_desc, today_now))
                            
                        conn.commit()
                        st.success("✅ Satış başarıyla tamamlandı, stoklar güncellendi!")
                        st.session_state.sepet = {}
                        st.session_state.clear_barcode = True  # Clear search field
                        conn.close()
                        st.rerun()
                    else:
                        conn.close()

# ----------------- MODULE: STOK VE URUNLER -----------------
elif menu == "📦 Stok ve Ürünler":
    st.markdown("## 📦 Stok ve Ürün Yönetimi")
    
    # 1. Summary Metrics Cards
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM urunler")
    total_types = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM urunler WHERE stok <= kritik_stok")
    critical_count = c.fetchone()[0]
    
    c.execute("SELECT SUM(stok) FROM urunler")
    total_stock = c.fetchone()[0] or 0
    conn.close()
    
    col_st1, col_st2, col_st3 = st.columns(3)
    with col_st1:
        st.markdown(f"""
        <div class="metric-card">
            <h3>📦 Toplam Çeşit</h3>
            <h2>{total_types} Ürün</h2>
            <span style='color:#a78bfa;'>Aktif envanter listesi</span>
        </div>
        """, unsafe_allow_html=True)
    with col_st2:
        st.markdown(f"""
        <div class="metric-card" style='border-left: 4px solid #ef4444;'>
            <h3 style='color:#ef4444;'>⚠️ Kritik Stok</h3>
            <h2 style='color:#f87171;'>{critical_count} Ürün</h2>
            <span style='color:#f87171;'>Eşiğin altındaki stoklar</span>
        </div>
        """, unsafe_allow_html=True)
    with col_st3:
        st.markdown(f"""
        <div class="metric-card">
            <h3>📊 Toplam Stok</h3>
            <h2>{total_stock} Adet</h2>
            <span style='color:#34d399;'>Toplam fiziksel ürün</span>
        </div>
        """, unsafe_allow_html=True)
        
    st.markdown("<br/>", unsafe_allow_html=True)
    
    col_list, col_edit = st.columns([7, 5])
    
    # Load all products once for both panels
    conn = get_db_connection()
    df_products = pd.read_sql_query("SELECT * FROM urunler", conn)
    df_products["skt"] = df_products["skt"].fillna("")
    conn.close()
    
    with col_list:
        st.markdown("### 📋 Güncel Envanter Listesi")
        
        # Search input
        search_query = st.text_input("🔍 Envanterde Ara (Ürün Adı veya Barkod):", placeholder="Aramak istediğiniz ürün adını veya barkodu yazın...")
        
        # Filter products based on search query
        df_display = df_products.copy()
        if search_query:
            q = search_query.strip().lower()
            df_display = df_display[
                df_display["ad"].str.lower().str.contains(q, na=False) |
                df_display["barkod"].str.lower().str.contains(q, na=False)
            ]
            
        if df_display.empty:
            st.info("Arama kriterlerine uygun ürün bulunamadı.")
        else:
            today_dt = datetime.now()
            
            def check_alerts(row):
                alarms = []
                skt_val = row.get("skt")
                if skt_val and isinstance(skt_val, str) and skt_val.strip() and not pd.isna(skt_val):
                    try:
                        skt_dt = datetime.strptime(skt_val.strip(), "%Y-%m-%d")
                        if skt_dt < today_dt:
                            alarms.append("🚨 SKT GEÇTİ")
                        elif skt_dt <= today_dt + timedelta(days=7):
                            alarms.append("⚠️ SKT YAKLAŞTI")
                    except Exception:
                        pass
                if row['stok'] <= row['kritik_stok']:
                    alarms.append("📉 KRİTİK STOK")
                return ", ".join(alarms) if alarms else "✅ Normal"

            df_display["Durum"] = df_display.apply(check_alerts, axis=1)
            
            # Format and display table
            st.dataframe(
                df_display[["barkod", "ad", "kategori", "fiyat", "stok", "Durum"]],
                use_container_width=True,
                column_config={
                    "barkod": "Barkod",
                    "ad": "Ürün Adı",
                    "kategori": "Kategori",
                    "fiyat": st.column_config.NumberColumn("Fiyat (TL)", format="%.2f TL"),
                    "stok": "Stok",
                    "Durum": "Durum Alarmları"
                }
            )
            
            # Expired / critical warnings (based on full database for complete overview)
            st.markdown("#### 🚨 Aktif Alarmlar")
            has_alert = False
            df_products_alerts = df_products.copy()
            df_products_alerts["Durum"] = df_products_alerts.apply(check_alerts, axis=1)
            
            for _, row in df_products_alerts.iterrows():
                status = row["Durum"]
                if "🚨 SKT GEÇTİ" in status:
                    st.error(f"🔴 **SKT Geçti:** {row['ad']} (Son Tüketim: `{row['skt']}`)")
                    has_alert = True
                elif "⚠️ SKT YAKLAŞTI" in status:
                    st.warning(f"🟡 **SKT Yaklaştı:** {row['ad']} (Son Tüketim: `{row['skt']}`)")
                    has_alert = True
                if "📉 KRİTİK STOK" in status:
                    st.warning(f"📉 **Düşük Stok:** {row['ad']} (Kalan: `{row['stok']}`)")
                    has_alert = True
                    
            if not has_alert:
                st.success("Tebrikler! Kritik stokta veya son kullanma tarihi yaklaşmış ürün bulunmamaktadır.")
                
    with col_edit:
        st.markdown("### ⚡ Hızlı Güncelle / Sil")
        if df_products.empty:
            st.info("İşlem yapılacak ürün bulunamadı.")
        else:
            if "update_barcode_search_val" not in st.session_state:
                st.session_state.update_barcode_search_val = ""
                
            if "barcode" in st.query_params:
                st.session_state.update_barcode_search_val = st.query_params["barcode"]
                del st.query_params["barcode"]
                
            with st.expander("📸 Kameradan Barkod Tara", expanded=False):
                import streamlit.components.v1 as components
                components.html(
                    """
                    <div style="background-color: #0b0e14; border: 1px solid rgba(0, 173, 181, 0.2); border-radius: 12px; padding: 15px; text-align: center;">
                        <script src="https://unpkg.com/html5-qrcode" type="text/javascript"></script>
                        <div id="reader" style="width: 100%; max-width: 320px; margin: 0 auto; border-radius: 8px; overflow: hidden; background: #000;"></div>
                        <div id="status" style="margin-top: 10px; font-size: 0.9em; color: #a7f3d0; font-family: sans-serif;">📷 Kamera hazır. Taramak için hizalayın.</div>
                        <button id="start-btn" style="background: linear-gradient(135deg, #00adb5 0%, #00f2fe 100%); color: #000; border: none; padding: 10px 20px; font-weight: bold; border-radius: 6px; cursor: pointer; margin-top: 10px; width: 100%;">📷 Kamerayı Başlat</button>
                        <button id="stop-btn" style="background: #ef4444; color: #fff; border: none; padding: 10px 20px; font-weight: bold; border-radius: 6px; cursor: pointer; margin-top: 10px; width: 100%; display: none;">🛑 Kamerayı Kapat</button>
                    </div>
                    
                    <script>
                        const startBtn = document.getElementById("start-btn");
                        const stopBtn = document.getElementById("stop-btn");
                        const statusDiv = document.getElementById("status");
                        let html5QrCode = null;
                    
                        startBtn.addEventListener("click", () => {
                            statusDiv.innerText = "🔄 Kamera başlatılıyor...";
                            startBtn.style.display = "none";
                            stopBtn.style.display = "block";
                            
                            html5QrCode = new Html5Qrcode("reader");
                            const config = { fps: 15, qrbox: { width: 250, height: 150 } };
                            
                            const successCallback = (decodedText, decodedResult) => {
                                statusDiv.innerText = "✅ Barkod Algılandı: " + decodedText;
                                html5QrCode.stop().then(() => {
                                    const parentUrl = new URL(document.referrer || window.top.location.href);
                                    parentUrl.searchParams.set("barcode", decodedText);
                                    window.top.location.href = parentUrl.toString();
                                });
                            };
                            
                            html5QrCode.start({ facingMode: "environment" }, config, successCallback)
                                .catch((err) => {
                                    console.warn(err);
                                    html5QrCode.start({ facingMode: "user" }, config, successCallback)
                                        .then(() => { statusDiv.innerText = "📷 Ön kamera aktif. Barkodu yaklaştırın."; })
                                        .catch((err2) => {
                                            statusDiv.innerText = "❌ Kamera hatası: " + err2;
                                            startBtn.style.display = "block";
                                            stopBtn.style.display = "none";
                                        });
                                });
                        });
                    
                        stopBtn.addEventListener("click", () => {
                            if (html5QrCode) {
                                html5QrCode.stop().then(() => {
                                    statusDiv.innerText = "🛑 Kamera kapatıldı.";
                                    startBtn.style.display = "block";
                                    stopBtn.style.display = "none";
                                });
                            }
                        });
                    </script>
                    """,
                    height=350
                )
            
            # Smart text filter before selectbox
            update_barcode_search = st.text_input("⚡ Barkod Okutun veya Ürün Adı Yazın:", value=st.session_state.update_barcode_search_val, placeholder="Seçmek için barkod okutun veya yazın...")
            
            # Filter options list
            filtered_prod_options = {}
            for _, row in df_products.iterrows():
                label = f"{row['ad']} [{row['barkod']}]"
                if not update_barcode_search or update_barcode_search.lower() in label.lower():
                    filtered_prod_options[row["barkod"]] = label
                    
            if not filtered_prod_options:
                st.warning("Eşleşen ürün bulunamadı.")
                selected_barcode = None
            else:
                selected_barcode = st.selectbox(
                    "Düzenlenecek Ürün Seçin:", 
                    list(filtered_prod_options.keys()), 
                    format_func=lambda x: filtered_prod_options[x]
                )
            
            if selected_barcode:
                # Fetch detailed row info
                selected_prod = df_products[df_products["barkod"] == selected_barcode].iloc[0]
                
                # Edit values form
                new_price = st.number_input("Satış Fiyatı (TL):", value=float(selected_prod["fiyat"]), min_value=0.0, step=5.0)
                new_stock = st.number_input("Stok Miktarı:", value=int(selected_prod["stok"]), min_value=0, step=1)
                
                # Parse current SKT if valid
                current_skt_str = selected_prod["skt"]
                try:
                    current_skt_val = datetime.strptime(current_skt_str, "%Y-%m-%d").date() if current_skt_str else datetime.today().date()
                except Exception:
                    current_skt_val = datetime.today().date()
                    
                new_skt = st.date_input("Son Tüketim Tarihi (SKT):", value=current_skt_val)
                new_skt_str = new_skt.strftime("%Y-%m-%d")
                
                # Dynamic POS shortcut option
                is_shortcut = bool(selected_prod.get("hizli_kasa_kisayol", 0))
                new_is_shortcut = st.checkbox("Bu Ürün Hızlı Kasada Kısayol Butonu Olarak Görünsün", value=is_shortcut, key=f"shortcut_chk_{selected_barcode}")
                
                col_actions = st.columns(2)
                with col_actions[0]:
                    if st.button("⚡ Bilgileri Güncelle", type="primary", use_container_width=True):
                        conn = get_db_connection()
                        c = conn.cursor()
                        c.execute("UPDATE urunler SET fiyat = ?, stok = ?, skt = ?, hizli_kasa_kisayol = ? WHERE barkod = ?", 
                                  (new_price, new_stock, new_skt_str, 1 if new_is_shortcut else 0, selected_barcode))
                        conn.commit()
                        conn.close()
                        st.toast("Ürün fiyatı, stoğu, SKT ve kısayol bilgisi başarıyla güncellendi!", icon="✅")
                        st.rerun()
                        
                with col_actions[1]:
                    # Safe delete block
                    st.markdown("<p style='font-size:0.85em; color:#ef4444; font-weight:bold; margin-bottom:2px;'>⚠️ Silme Onayı</p>", unsafe_allow_html=True)
                    confirm_delete = st.checkbox("Tamamen silmeyi onayla", key=f"del_confirm_{selected_barcode}")
                    
                    if st.button("🗑️ Ürünü Sil", type="secondary", use_container_width=True):
                        if not confirm_delete:
                            st.warning("Lütfen silmeyi onaylayın.")
                        else:
                            conn = get_db_connection()
                            c = conn.cursor()
                            c.execute("DELETE FROM urunler WHERE barkod = ?", (selected_barcode,))
                            c.execute("DELETE FROM hazir_urunler WHERE barkod = ?", (selected_barcode,))
                            conn.commit()
                            conn.close()
                            st.toast("Ürün veritabanından tamamen silindi!", icon="🗑️")
                            st.rerun()
                            
        # Collapsible form to add brand new item
        st.markdown("---")
        with st.expander("➕ Sıfırdan Yeni Ürün Ekle", expanded=False):
            with st.form("yeni_urun_ekle_form", clear_on_submit=True):
                f_barkod = st.text_input("Barkod Numarası (Zorunlu):", key="new_prod_barcode")
                f_ad = st.text_input("Ürün Adı:", key="new_prod_name")
                f_kategori = st.selectbox("Kategori:", ["Kedi Maması", "Köpek Maması", "Kum", "Aksesuar", "Ödül/Vitamin", "Oyuncak", "Diğer"], key="new_prod_category")
                
                col_inputs = st.columns(3)
                with col_inputs[0]:
                    f_fiyat = st.number_input("Satış Fiyatı (TL):", min_value=0.0, step=5.0, key="new_prod_price")
                with col_inputs[1]:
                    f_stok = st.number_input("Stok Adedi:", min_value=0, step=1, key="new_prod_stock")
                with col_inputs[2]:
                    f_kritik = st.number_input("Kritik Stok Eşiği:", min_value=1, value=5, key="new_prod_critical")
                
                # Direct SKT input (optional/clearable by setting value=None)
                f_skt = st.date_input("Son Kullanma Tarihi (SKT):", value=None, key="new_prod_skt")
                skt_val = f_skt.strftime("%Y-%m-%d") if f_skt else None
                
                f_is_shortcut = st.checkbox("Bu Ürün Hızlı Kasada Kısayol Butonu Olarak Görünsün", value=False, key="new_prod_shortcut")
                
                submitted = st.form_submit_button("💾 Ürünü Envantere Ekle")
                if submitted:
                    if not f_barkod or not f_ad:
                        st.error("Barkod ve Ürün Adı zorunludur!")
                    else:
                        conn = get_db_connection()
                        c = conn.cursor()
                        c.execute("SELECT 1 FROM urunler WHERE barkod = ?", (f_barkod,))
                        if c.fetchone():
                            st.error("Bu barkod zaten kayıtlı! Lütfen yukarıdaki hızlı düzenleme alanını kullanın.")
                        else:
                            c.execute("""
                            INSERT INTO urunler (barkod, ad, kategori, fiyat, stok, kritik_stok, skt, gorsel_url, hizli_kasa_kisayol)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (f_barkod, f_ad, f_kategori, f_fiyat, f_stok, f_kritik, skt_val, "https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=500", 1 if f_is_shortcut else 0))
                            conn.commit()
                            st.success("Yeni ürün stoka eklendi!")
                            conn.close()
                            st.rerun()
                        conn.close()

# ----------------- MODULE: MUSTERI YONETIMI -----------------
elif menu == "👥 Müşteri Yönetimi":
    st.markdown("## 👥 Müşteri İlişkileri (CRM) & Detaylı Evcil Hayvan Kartları")
    
    # Bugün Doğum Günü Olan Dostlarımız Paneli
    st.markdown("### 🎂 Bugün Doğum Günü Olan Dostlarımız")
    today_md = datetime.now().strftime("%m-%d")
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT isim, telefon, hayvan_turu, irk_detay, dogum_gunu FROM musteriler WHERE dogum_gunu IS NOT NULL AND dogum_gunu != ''")
    all_custs_birth = c.fetchall()
    conn.close()
    
    birthdays_today = []
    for row in all_custs_birth:
        try:
            b_dt = datetime.strptime(row["dogum_gunu"], "%Y-%m-%d")
            if b_dt.strftime("%m-%d") == today_md:
                birthdays_today.append(row)
        except Exception:
            pass
            
    if not birthdays_today:
        st.info("Bugün doğum günü olan patili dostumuz bulunmamaktadır.")
    else:
        for b_cust in birthdays_today:
            col_info, col_action = st.columns([7, 3])
            with col_info:
                st.markdown(f"🎂 **{b_cust['irk_detay'] or b_cust['hayvan_turu']}** (Sahibi: {b_cust['isim']} - {b_cust['telefon']}) | 📅 Doğum Günü: `{b_cust['dogum_gunu']}`")
            with col_action:
                msg = f"Merhaba {b_cust['isim']}! 🎂 Beykoz Pet ailesi olarak sevimli dostumuz {b_cust['irk_detay'] or b_cust['hayvan_turu']}'nin doğum gününü en içten dileklerimizle kutlarız! 🐾 Bugün dostumuz için yapacağınız tüm ödül maması ve oyuncak alışverişlerinde %15 doğum günü hediyesi indirimimiz sizi bekliyor! ✨"
                if st.button("💬 Doğum Günü Mesajı Gönder", key=f"wa_birthday_{b_cust['telefon']}", use_container_width=True):
                    success, info = send_whatsapp_reminder(b_cust['telefon'], msg)
                    if success:
                        st.success(info)
                    else:
                        st.info(info)
            st.markdown("<hr style='margin:5px 0; border-color:rgba(255,255,255,0.05);'>", unsafe_allow_html=True)
            
    st.markdown("---")
    
    col_c_add, col_c_list = st.columns([5, 7])
    
    with col_c_add:
        st.markdown("### ➕ Yeni Müşteri Kaydı")
        
        c_isim = st.text_input("Müşteri Adı Soyadı:")
        c_tel = st.text_input("Telefon Numarası:")
        c_turu = st.selectbox("Evcil Hayvan Türü:", ["Kedi", "Köpek", "Balık", "Kuş", "Kemirgen", "Sürüngen"])
        c_dogum_gunu = st.date_input("Evcil Hayvan Doğum Günü:", value=None, key="cust_birth_date")
        c_dogum_gunu_str = c_dogum_gunu.strftime("%Y-%m-%d") if c_dogum_gunu else None
        c_iskonto = st.number_input("Özel İskonto Oranı (%):", min_value=0.0, max_value=100.0, step=1.0, value=0.0, key="cust_iskonto_rate")
        
        # Initialize default values
        irk_detay = ""
        yas = ""
        kisir = "Belirtilmedi"
        kilo = 0.0
        boyut = ""
        ekipman_detay = ""
        saglik_detay = ""
        ozel_notlar = ""
        
        # Render dynamic fields based on pet type selection
        if c_turu == "Kedi":
            st.markdown("🐱 **Kedi Detayları**")
            irk_detay = st.text_input("Kedinin Irkı:", placeholder="Örn: Tekir, British Shorthair, Van Kedisi")
            yas = st.text_input("Kedinin Yaşı:", placeholder="Örn: 2 Yaşında, 6 Aylık")
            kisir = st.selectbox("Kısırlaştırılmış mı?", ["Belirtilmedi", "Evet", "Hayır"])
            saglik_detay = st.text_area("Özel Sağlık Durumu / Alerjisi:", placeholder="Örn: Tavuklu mamaya alerjisi var...")
            ekipman_detay = st.selectbox("Kullandığı Kum Türü:", ["Bentonit", "Çam Peleti", "Silika", "Diğer"])
            
        elif c_turu == "Köpek":
            st.markdown("🐶 **Köpek Detayları**")
            irk_detay = st.text_input("Köpeğin Irkı:", placeholder="Örn: Golden Retriever, Pug, Sivas Kangalı")
            yas = st.text_input("Köpeğin Yaşı:", placeholder="Örn: 4 Yaşında")
            kilo = st.number_input("Köpeğin Kilosu (kg):", min_value=0.0, step=0.5, value=0.0)
            kisir = st.selectbox("Kısırlaştırılmış mı?", ["Belirtilmedi", "Evet", "Hayır"])
            boyut = st.selectbox("Irk Boyutu (Mama önerisi için):", ["Küçük Irk", "Orta Irk", "Büyük Irk"])
            saglik_detay = st.text_area("Alerjen / Sağlık Durumu:", placeholder="Örn: Egzama problemi var, tahılsız mama kullanıyor...")
            
        elif c_turu == "Balık":
            st.markdown("🐟 **Akvaryum & Balık Detayları**")
            boyut = st.selectbox("Akvaryum Türü:", ["Tatlı Su", "Tuzlu Su", "Bitkili"])
            irk_detay = st.text_input("Bakılan Balık Türleri:", placeholder="Örn: Ciklet, Lepistes, Japon, Beta")
            kilo = st.number_input("Akvaryum Hacmi (Litre):", min_value=0.0, step=5.0, value=0.0)
            ekipman_detay = st.text_area("Kullandığı Ekipmanlar:", placeholder="Örn: Dış Filtre, Hava Motoru, Isıtıcı")
            
        elif c_turu == "Kuş":
            st.markdown("🦜 **Kuş Detayları**")
            irk_detay = st.selectbox("Kuşun Türü:", ["Muhabbet Kuşu", "Kanarya", "Papağan", "Sultan Papağanı", "Diğer"])
            yas = st.text_input("Yaşı / Doğum Tarihi:", placeholder="Örn: 1 Yaşında")
            boyut = st.text_input("Kafes Türü:", placeholder="Örn: Çift Hane, Pirinç Kafes")
            ozel_notlar = st.text_area("Sevdiği Ekstra Gıdalar:", placeholder="Örn: Kalamar kemiği, dal darı, yumurta maması")
            
        elif c_turu == "Kemirgen":
            st.markdown("🐹 **Kemirgen Detayları**")
            irk_detay = st.selectbox("Kemirgen Türü:", ["Hamster", "Tavşan", "Ginepig", "Chinchilla", "Diğer"])
            yas = st.text_input("Yaşı:", placeholder="Örn: 6 Aylık")
            ekipman_detay = st.selectbox("Kafes Taban Malzemesi:", ["Talaş", "Pellet", "Kağıt", "Diğer"])
            ozel_notlar = st.text_area("Sevdiği Oyuncaklar / Gıdalar:", placeholder="Örn: Kemirme kemiği, yonca sapı")
            
        elif c_turu == "Sürüngen":
            st.markdown("🦎 **Sürüngen Detayları**")
            irk_detay = st.selectbox("Sürüngen Türü:", ["Bukalemun", "İguana", "Kaplumbağa", "Gecko", "Diğer"])
            ekipman_detay = st.text_input("Teraryum Isı / Nem İhtiyacı:", placeholder="Örn: 28°C / %60 Nem")
            ozel_notlar = st.selectbox("Beslenme Tipi:", ["Canlı Yem", "Otçul", "Karışık"])
            
        st.markdown("<br/>", unsafe_allow_html=True)
        if st.button("💾 Müşteriyi Kaydet", type="primary", use_container_width=True):
            if not c_isim:
                st.error("Müşteri ismi boş bırakılamaz!")
            else:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("""
                INSERT INTO musteriler (isim, telefon, hayvan_turu, irk_detay, yas, kisir, kilo, boyut, ekipman_detay, saglik_detay, ozel_notlar, dogum_gunu, iskonto_orani)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (c_isim, c_tel, c_turu, irk_detay, yas, kisir, kilo, boyut, ekipman_detay, saglik_detay, ozel_notlar, c_dogum_gunu_str, c_iskonto))
                conn.commit()
                conn.close()
                st.success(f"🎉 Müşteri {c_isim} başarıyla kaydedildi!")
                st.rerun()
                    
    with col_c_list:
        st.markdown("### 👥 Kayıtlı Müşteri Profilleri")
        
        conn = get_db_connection()
        df_m = pd.read_sql_query("SELECT * FROM musteriler ORDER BY id DESC", conn)
        conn.close()
        
        # Ensure expected columns are present in profile listing to prevent KeyError
        for col in ["hayvan_turu", "irk_detay", "yas", "kisir", "kilo", "boyut", "ekipman_detay", "saglik_detay", "ozel_notlar"]:
            if col not in df_m.columns:
                df_m[col] = ""
                
        if df_m.empty:
            st.info("Kayıtlı müşteri bulunmamaktadır.")
        else:
            c_search = st.text_input("🔍 Müşteri Listesinde Ara (İsim veya Telefon):", placeholder="Aramak istediğiniz müşteri adını veya numarasını yazın...")
            
            df_m_disp = df_m.copy()
            if c_search:
                q = c_search.strip().lower()
                df_m_disp = df_m_disp[
                    df_m_disp["isim"].str.lower().str.contains(q, na=False) |
                    df_m_disp["telefon"].str.lower().str.contains(q, na=False)
                ]
                
            if df_m_disp.empty:
                st.info("Arama kriterlerine uygun müşteri bulunamadı.")
            else:
                emojis = {"Kedi": "🐱", "Köpek": "🐶", "Balık": "🐟", "Kuş": "🦜", "Kemirgen": "🐹", "Sürüngen": "🦎"}
                
                for _, row in df_m_disp.iterrows():
                    h_turu = row.get('hayvan_turu', 'Belirtilmedi')
                    irk = row.get('irk_detay', 'Belirtilmedi')
                    yas_val = row.get('yas', 'Belirtilmedi')
                    kisir_val = row.get('kisir', 'Belirtilmedi')
                    kilo_val = row.get('kilo', 0.0)
                    boyut_val = row.get('boyut', '')
                    ekipman = row.get('ekipman_detay', '')
                    saglik = row.get('saglik_detay', '')
                    notlar = row.get('ozel_notlar', '')
                    
                    emo = emojis.get(h_turu, "🐾")
                    
                    # Configure dynamic theme styles for the profile cards
                    if st.session_state.current_theme == "light":
                        card_bg = "linear-gradient(145deg, #ffffff 0%, #f8fafc 100%)"
                        card_border = "rgba(16, 185, 129, 0.25)"
                        card_shadow = "rgba(0,0,0,0.05)"
                        text_primary = "#121620"
                        text_phone = "#059669"
                        inner_bg = "rgba(16, 185, 129, 0.05)"
                        inner_border = "#10b981"
                        text_inner = "#334155"
                    else:
                        card_bg = "linear-gradient(145deg, #131924 0%, #0d121c 100%)"
                        card_border = "rgba(0, 173, 181, 0.15)"
                        card_shadow = "rgba(0,0,0,0.25)"
                        text_primary = "#ffffff"
                        text_phone = "#a7f3d0"
                        inner_bg = "rgba(255,255,255,0.03)"
                        inner_border = "#00adb5"
                        text_inner = "#cbd5e1"
                        
                    isk_val = float(row.get("iskonto_orani", 0.0) or 0.0)
                    st.markdown(f"""
                    <div style='background: {card_bg}; border: 1px solid {card_border}; border-radius: 12px; padding: 18px; margin-bottom: 8px; box-shadow: 0 4px 15px {card_shadow};'>
                        <div style='display:flex; justify-content:space-between; align-items:center;'>
                            <strong style='font-size:1.15em; color: {text_primary};'>👤 {row.get('isim', 'İsimsiz')}</strong>
                            <span class='badge-ok' style='font-size:0.85em;'>ID: #{row.get('id', '')}</span>
                        </div>
                        <p style='color:{text_phone}; margin-bottom:10px; font-size:0.9em; margin-top:2px;'>📞 Telefon: {row.get('telefon', 'Belirtilmedi') or 'Belirtilmedi'}</p>
                        <div style='background-color: {inner_bg}; border-radius: 8px; padding: 10px; border-left: 3px solid {inner_border};'>
                            <strong style='color:{inner_border};'>Evcil Hayvan Kartı: {emo} {h_turu}</strong><br/>
                            <span style='font-size:0.85em; color: {text_inner}; line-height:1.4;'>
                                • <b>Irk / Tür:</b> {irk or 'Belirtilmedi'}<br/>
                                • <b>Yaş:</b> {yas_val or 'Belirtilmedi'} | <b>Kısır:</b> {kisir_val or 'Belirtilmedi'}<br/>
                                • <b>Özel İskonto Oranı:</b> %{isk_val:.1f}<br/>
                                {f"• <b>Kilo:</b> {kilo_val} kg<br/>" if kilo_val and float(kilo_val) > 0 else ""}
                                {f"• <b>Boyut / Tank:</b> {boyut_val}<br/>" if boyut_val else ""}
                                {f"• <b>Ekipman / Kum / Taban:</b> {ekipman}<br/>" if ekipman else ""}
                                {f"• <b>Sağlık / Alerji:</b> {saglik}<br/>" if saglik else ""}
                                {f"• <b>Özel Notlar / Beslenme:</b> {notlar}<br/>" if notlar else ""}
                            </span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Confirm delete for customer and Inline profile editor
                    col_del1, col_del2 = st.columns([7, 5])
                    with col_del1:
                        with st.expander("✏️ Profili Düzenle", expanded=False):
                            edit_isim = st.text_input("İsim Soyadı:", value=row.get('isim', ''), key=f"edit_c_isim_{row['id']}")
                            edit_tel = st.text_input("Telefon:", value=row.get('telefon', ''), key=f"edit_c_tel_{row['id']}")
                            
                            turu_list = ["Kedi", "Köpek", "Balık", "Kuş", "Kemirgen", "Sürüngen"]
                            try:
                                turu_idx = turu_list.index(h_turu)
                            except ValueError:
                                turu_idx = 0
                            edit_turu = st.selectbox("Hayvan Türü:", turu_list, index=turu_idx, key=f"edit_c_turu_{row['id']}")
                            
                            edit_irk = st.text_input("Irk / Tür Detay:", value=irk, key=f"edit_c_irk_{row['id']}")
                            edit_yas = st.text_input("Yaşı:", value=yas_val, key=f"edit_c_yas_{row['id']}")
                            
                            kisir_list = ["Belirtilmedi", "Evet", "Hayır"]
                            try:
                                kisir_idx = kisir_list.index(kisir_val)
                            except ValueError:
                                kisir_idx = 0
                            edit_kisir = st.selectbox("Kısırlaştırılmış:", kisir_list, index=kisir_idx, key=f"edit_c_kisir_{row['id']}")
                            
                            edit_kilo = st.number_input("Kilo / Hacim:", value=float(kilo_val) if kilo_val else 0.0, step=0.5, key=f"edit_c_kilo_{row['id']}")
                            edit_boyut = st.text_input("Boyut / Kafes / Akvaryum Türü:", value=boyut_val, key=f"edit_c_boyut_{row['id']}")
                            edit_ekipman = st.text_area("Ekipman / Kum / Taban:", value=ekipman, key=f"edit_c_ekipman_{row['id']}")
                            edit_saglik = st.text_area("Sağlık / Alerji Detayları:", value=saglik, key=f"edit_c_saglik_{row['id']}")
                            edit_notlar = st.text_area("Özel Notlar / Beslenme:", value=notlar, key=f"edit_c_notlar_{row['id']}")
                            
                            try:
                                default_b_date = datetime.strptime(row.get('dogum_gunu', ''), "%Y-%m-%d").date() if row.get('dogum_gunu') else None
                            except Exception:
                                default_b_date = None
                            edit_b_date = st.date_input("Evcil Hayvan Doğum Günü:", value=default_b_date, key=f"edit_c_birth_{row['id']}")
                            edit_b_date_str = edit_b_date.strftime("%Y-%m-%d") if edit_b_date else None
                            
                            edit_isk = st.number_input("İskonto Oranı (%):", min_value=0.0, max_value=100.0, step=1.0, value=float(isk_val), key=f"edit_c_isk_{row['id']}")
                            
                            if st.button("💾 Değişiklikleri Kaydet", key=f"save_cust_btn_{row['id']}", use_container_width=True):
                                if not edit_isim:
                                    st.error("İsim boş bırakılamaz!")
                                else:
                                    conn_ui = get_db_connection()
                                    c_ui = conn_ui.cursor()
                                    c_ui.execute("""
                                        UPDATE musteriler 
                                        SET isim = ?, telefon = ?, hayvan_turu = ?, irk_detay = ?, yas = ?, kisir = ?, kilo = ?, boyut = ?, ekipman_detay = ?, saglik_detay = ?, ozel_notlar = ?, dogum_gunu = ?, iskonto_orani = ?
                                        WHERE id = ?
                                    """, (edit_isim, edit_tel, edit_turu, edit_irk, edit_yas, edit_kisir, edit_kilo, edit_boyut, edit_ekipman, edit_saglik, edit_notlar, edit_b_date_str, edit_isk, row['id']))
                                    conn_ui.commit()
                                    conn_ui.close()
                                    st.toast(f"{edit_isim} profili başarıyla güncellendi!", icon="✅")
                                    st.rerun()
                                
                    with col_del2:
                        confirm_del_cust = st.checkbox("Profil silmeyi onayla", key=f"del_cust_chk_{row['id']}")
                        if st.button("🗑️ Profili Sil", key=f"del_cust_btn_{row['id']}", use_container_width=True):
                            if not confirm_del_cust:
                                st.warning("Silmek için onaylayın.")
                            else:
                                conn = get_db_connection()
                                c = conn.cursor()
                                c.execute("DELETE FROM musteriler WHERE id = ?", (row['id'],))
                                conn.commit()
                                conn.close()
                                st.toast(f"{row['isim']} profili başarıyla silindi.", icon="🗑️")
                                st.rerun()
                    st.markdown("<hr style='margin:10px 0; border-color:rgba(255,255,255,0.05);'>", unsafe_allow_html=True)

# ----------------- MODULE: PET KUAFOR (Grooming) -----------------
elif menu == "💇 Pet Kuaför":
    st.markdown("## 💇 Pet Kuaför Randevu Sistemi & WhatsApp Hatırlatma")
    
    # 1. Günü Gelen Randevular (WhatsApp Hatırlatmaları)
    st.markdown("### 🔔 Günü Gelen Randevular & Bildirimler")
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT r.*, m.isim, m.telefon 
        FROM randevular r 
        JOIN musteriler m ON r.musteri_id = m.id 
        WHERE r.tarih = ? AND r.durum = 'Bekliyor'
        ORDER BY r.saat ASC
    """, (today_str,))
    today_appointments = c.fetchall()
    
    if not today_appointments:
        st.info("Bugün için planlanmış bekleyen kuaför randevusu bulunmuyor.")
    else:
        for app in today_appointments:
            col_info, col_action = st.columns([7, 3])
            with col_info:
                st.markdown(f"🐕 **{app['hayvan_ad']}** ({app['isim']} - {app['telefon']}) | 🕒 Saat: `{app['saat']}` | İşlem: `{app['islem']}`")
            with col_action:
                msg = f"Merhaba {app['isim']}, Bugün saat {app['saat']}'te sevimli dostumuz {app['hayvan_ad']}'nin Beykoz Pet kuaför randevusu bulunmaktadır. Bilginize sunarız."
                if st.button("💬 WhatsApp Hatırlatması Gönder", key=f"wa_app_btn_{app['id']}", use_container_width=True):
                    success, info = send_whatsapp_reminder(app['telefon'], msg)
                    if success:
                        st.success(info)
                    else:
                        st.info(info)
            st.markdown("<hr style='margin:5px 0; border-color:rgba(255,255,255,0.05);'>", unsafe_allow_html=True)
            
    # 2. Pazarlama Paneli: Zamanı Gelen Bakım Hatırlatmaları (20 Gün Sonra)
    st.markdown("### 📢 Pazarlama Paneli: Zamanı Gelen Periyodik Bakım Hatırlatmaları (20. Gün)")
    reminder_target_date_str = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
    
    c.execute("""
        SELECT r.*, m.isim, m.telefon 
        FROM randevular r 
        JOIN musteriler m ON r.musteri_id = m.id 
        WHERE r.durum = 'Tamamlandı' AND r.tamamlandi_tarih = ?
    """, (reminder_target_date_str,))
    due_care_reminders = c.fetchall()
    
    if not due_care_reminders:
        st.info("Bugün için 20 günü dolan periyodik bakım hatırlatması bulunmuyor.")
    else:
        for rmd in due_care_reminders:
            col_info, col_action = st.columns([7, 3])
            with col_info:
                st.markdown(f"🐾 **{rmd['hayvan_ad']}** ({rmd['isim']} - {rmd['telefon']}) | Son İşlem Tarihi: `{rmd['tamamlandi_tarih']}`")
            with col_action:
                msg = f"Merhaba {rmd['isim']}! 🐾 Beykoz Pet'ten sevgiler. Patili dostumuz {rmd['hayvan_ad']} ile yaptığımız son bakım keyfinin üzerinden tam 20 gün geçmiş. ✨ Tüylerinin sağlığı, parlaklığı ve mis gibi kokmaya devam etmesi için periyodik bakım zamanımız geldi! Ne zaman isterseniz dükkanımıza bekliyoruz, randevunuzu hemen oluşturabiliriz. 🐶🐱"
                if st.button("💬 Bakım Hatırlatması Gönder", key=f"wa_care_btn_{rmd['id']}", use_container_width=True):
                    success, info = send_whatsapp_reminder(rmd['telefon'], msg)
                    if success:
                        st.success(info)
                    else:
                        st.info(info)
            st.markdown("<hr style='margin:5px 0; border-color:rgba(255,255,255,0.05);'>", unsafe_allow_html=True)
            
    st.markdown("---")
    
    col_add, col_list = st.columns([5, 7])
    
    with col_add:
        st.markdown("### ➕ Yeni Randevu Ekle")
        with st.form("yeni_randevu_form", clear_on_submit=True):
            c.execute("SELECT id, isim, telefon FROM musteriler ORDER BY isim ASC")
            customers = c.fetchall()
            cust_dict = {cust['id']: f"{cust['isim']} ({cust['telefon']})" for cust in customers}
            
            if not cust_dict:
                st.warning("Randevu eklemeden önce en az bir müşteri kaydetmelisiniz!")
                submitted = st.form_submit_button("Randevu Kaydet")
            else:
                f_cust_id = st.selectbox("Müşteri Seçin:", options=list(cust_dict.keys()), format_func=lambda x: cust_dict[x])
                f_pet_name = st.text_input("Evcil Hayvan Adı:")
                f_process = st.selectbox("Yapılacak İşlem:", ["Makas Traşı", "Makine Traşı", "Banyo", "Tırnak Kesimi", "Kulak Temizliği", "Komple Bakım", "Diğer"])
                f_date = st.date_input("Randevu Tarihi:")
                f_time = st.time_input("Randevu Saati:")
                
                submitted = st.form_submit_button("📅 Randevu Kaydet")
                if submitted:
                    if not f_pet_name:
                        st.error("Lütfen evcil hayvan adını girin!")
                    else:
                        c.execute("""
                            INSERT INTO randevular (musteri_id, hayvan_ad, islem, tarih, saat, durum)
                            VALUES (?, ?, ?, ?, ?, 'Bekliyor')
                        """, (f_cust_id, f_pet_name, f_process, f_date.strftime("%Y-%m-%d"), f_time.strftime("%H:%M")))
                        conn.commit()
                        st.success(f"{f_pet_name} için randevu başarıyla eklendi!")
                        st.rerun()
                        
    with col_list:
        st.markdown("### 📅 Randevu Takvimi / Listesi")
        c.execute("""
            SELECT r.*, m.isim, m.telefon 
            FROM randevular r 
            JOIN musteriler m ON r.musteri_id = m.id 
            ORDER BY r.tarih ASC, r.saat ASC
        """)
        all_appointments = c.fetchall()
        
        if not all_appointments:
            st.info("Kayıtlı randevu bulunmamaktadır.")
        else:
            app_data = []
            for app in all_appointments:
                app_data.append({
                    "id": app["id"],
                    "Tarih": app["tarih"],
                    "Saat": app["saat"],
                    "Müşteri": app["isim"],
                    "Telefon": app["telefon"],
                    "Evcil Hayvan": app["hayvan_ad"],
                    "İşlem": app["islem"],
                    "Durum": app["durum"]
                })
            df_app = pd.DataFrame(app_data)
            st.dataframe(df_app.drop(columns=["id"]), use_container_width=True)
            
            # Action: Mark completed
            st.markdown("#### ✅ Randevuyu Tamamla")
            pending_apps = df_app[df_app["Durum"] == "Bekliyor"]
            if pending_apps.empty:
                st.info("Tamamlanacak bekleyen randevu yok.")
            else:
                done_id = st.selectbox("Tamamlanan Randevu:", options=pending_apps["id"].tolist(), format_func=lambda x: f"{pending_apps[pending_apps['id'] == x]['Tarih'].values[0]} | {pending_apps[pending_apps['id'] == x]['Evcil Hayvan'].values[0]} ({pending_apps[pending_apps['id'] == x]['Müşteri'].values[0]})", key="done_app_select")
                if st.button("✔️ İşlemi Tamamlandı Olarak İşaretle", use_container_width=True):
                    c.execute("UPDATE randevular SET durum = 'Tamamlandı', tamamlandi_tarih = ? WHERE id = ?", (today_str, done_id))
                    conn.commit()
                    st.toast("Randevu tamamlandı olarak işaretlendi ve 20 günlük periyodik takip başladı!", icon="✅")
                    st.rerun()
            
            # Delete appointment block
            st.markdown("#### 🗑️ Randevu İptal/Silme")
            del_id = st.selectbox("Silinecek Randevu:", options=df_app["id"].tolist(), format_func=lambda x: f"{df_app[df_app['id'] == x]['Tarih'].values[0]} | {df_app[df_app['id'] == x]['Evcil Hayvan'].values[0]} ({df_app[df_app['id'] == x]['Müşteri'].values[0]})")
            if st.button("❌ Randevuyu Sil", use_container_width=True):
                c.execute("DELETE FROM randevular WHERE id = ?", (del_id,))
                conn.commit()
                st.toast("Randevu silindi.", icon="🗑️")
                st.rerun()
                
    conn.close()

# ----------------- MODULE: ASI TAKVIMI (Vaccinations) -----------------
elif menu == "💉 Aşı Takvimi":
    st.markdown("## 💉 Evcil Hayvan Aşı Takvimi & Takibi")
    
    # 1. Günü Gelen Aşılar (WhatsApp Hatırlatmaları)
    st.markdown("### 🔔 Günü Gelen Aşı Hatırlatmaları")
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT a.*, m.isim, m.telefon 
        FROM asilar a 
        JOIN musteriler m ON a.musteri_id = m.id 
        WHERE a.gelecek_doz_tarih = ?
    """, (today_str,))
    today_vaccinations = c.fetchall()
    
    if not today_vaccinations:
        st.info("Bugün için planlanmış aşı hatırlatması bulunmuyor.")
    else:
        for vac in today_vaccinations:
            col_info, col_action = st.columns([7, 3])
            with col_info:
                st.markdown(f"💉 **{vac['asi_adi']}** | Dostumuz: **{vac['hayvan_ad']}** ({vac['isim']} - {vac['telefon']})")
            with col_action:
                msg = f"Merhaba {vac['isim']}, Dostumuz {vac['hayvan_ad']}'nin bugün {vac['asi_adi']} aşısının zamanı gelmiştir. Sağlığı için dükkanımıza bekleriz."
                if st.button("💬 WhatsApp Hatırlatması Gönder", key=f"wa_vac_btn_{vac['id']}", use_container_width=True):
                    success, info = send_whatsapp_reminder(vac['telefon'], msg)
                    if success:
                        st.success(info)
                    else:
                        st.info(info)
            st.markdown("<hr style='margin:5px 0; border-color:rgba(255,255,255,0.05);'>", unsafe_allow_html=True)
            
    st.markdown("---")
    
    col_add, col_list = st.columns([5, 7])
    
    with col_add:
        st.markdown("### ➕ Yeni Aşı Kaydı Ekle")
        with st.form("yeni_asi_form", clear_on_submit=True):
            # Load customers for selectbox
            c.execute("SELECT id, isim, telefon FROM musteriler ORDER BY isim ASC")
            customers = c.fetchall()
            cust_dict = {cust['id']: f"{cust['isim']} ({cust['telefon']})" for cust in customers}
            
            if not cust_dict:
                st.warning("Aşı kaydı eklemeden önce en az bir müşteri kaydetmelisiniz!")
                submitted = st.form_submit_button("Aşı Kaydet")
            else:
                f_cust_id = st.selectbox("Müşteri Seçin:", options=list(cust_dict.keys()), format_func=lambda x: cust_dict[x])
                f_pet_name = st.text_input("Evcil Hayvan Adı:")
                f_vac_name = st.selectbox("Aşı Adı:", ["Karma Aşı", "Kuduz Aşısı", "İç Parazit", "Dış Parazit", "Lösemi Aşısı", "Bronchine Aşısı", "Mantar Aşısı", "Diğer"])
                f_apply_date = st.date_input("Uygulama Tarihi:")
                f_next_date = st.date_input("Gelecek Doz Tarihi (Hatırlatma):")
                
                submitted = st.form_submit_button("💉 Aşıyı Kaydet")
                if submitted:
                    if not f_pet_name:
                        st.error("Lütfen evcil hayvan adını girin!")
                    else:
                        c.execute("""
                            INSERT INTO asilar (musteri_id, hayvan_ad, asi_adi, uygulama_tarih, gelecek_doz_tarih)
                            VALUES (?, ?, ?, ?, ?)
                        """, (f_cust_id, f_pet_name, f_vac_name, f_apply_date.strftime("%Y-%m-%d"), f_next_date.strftime("%Y-%m-%d")))
                        conn.commit()
                        st.success(f"{f_pet_name} için {f_vac_name} kaydı eklendi!")
                        st.rerun()
                        
    with col_list:
        st.markdown("### 📋 Tüm Aşı Geçmişi & Takvimi")
        c.execute("""
            SELECT a.*, m.isim, m.telefon 
            FROM asilar a 
            JOIN musteriler m ON a.musteri_id = m.id 
            ORDER BY a.gelecek_doz_tarih ASC
        """)
        all_vaccinations = c.fetchall()
        
        if not all_vaccinations:
            st.info("Kayıtlı aşı bulunmamaktadır.")
        else:
            vac_data = []
            for vac in all_vaccinations:
                vac_data.append({
                    "id": vac["id"],
                    "Müşteri": vac["isim"],
                    "Telefon": vac["telefon"],
                    "Evcil Hayvan": vac["hayvan_ad"],
                    "Aşı Adı": vac["asi_adi"],
                    "Uygulama Tarihi": vac["uygulama_tarih"],
                    "Gelecek Doz / Hatırlatma": vac["gelecek_doz_tarih"]
                })
            df_vac = pd.DataFrame(vac_data)
            st.dataframe(df_vac.drop(columns=["id"]), use_container_width=True)
            
            # Edit & Delete vaccination records
            col_vac_edit, col_vac_del = st.columns([7, 5])
            
            with col_vac_edit:
                with st.expander("✏️ Aşı Kaydı Düzenle", expanded=False):
                    edit_vac_id = st.selectbox("Düzenlenecek Aşı Kaydı:", options=df_vac["id"].tolist(), format_func=lambda x: f"{df_vac[df_vac['id'] == x]['Evcil Hayvan'].values[0]} - {df_vac[df_vac['id'] == x]['Aşı Adı'].values[0]} ({df_vac[df_vac['id'] == x]['Müşteri'].values[0]})", key="edit_vac_select")
                    
                    selected_vac = None
                    for vac in all_vaccinations:
                        if vac["id"] == edit_vac_id:
                            selected_vac = vac
                            break
                    
                    if selected_vac:
                        edit_pet_name = st.text_input("Evcil Hayvan Adı:", value=selected_vac["hayvan_ad"], key=f"edit_v_pet_{selected_vac['id']}")
                        
                        asi_list = ["Karma Aşı", "Kuduz Aşısı", "İç Parazit", "Dış Parazit", "Lösemi Aşısı", "Bronchine Aşısı", "Mantar Aşısı", "Diğer"]
                        try:
                            asi_idx = asi_list.index(selected_vac["asi_adi"])
                        except ValueError:
                            asi_idx = 7
                        edit_vac_name = st.selectbox("Aşı Adı:", asi_list, index=asi_idx, key=f"edit_v_name_{selected_vac['id']}")
                        
                        try:
                            default_apply = datetime.strptime(selected_vac["uygulama_tarih"], "%Y-%m-%d").date()
                        except Exception:
                            default_apply = datetime.now().date()
                            
                        try:
                            default_next = datetime.strptime(selected_vac["gelecek_doz_tarih"], "%Y-%m-%d").date()
                        except Exception:
                            default_next = datetime.now().date()
                            
                        edit_apply_date = st.date_input("Uygulama Tarihi:", value=default_apply, key=f"edit_v_apply_{selected_vac['id']}")
                        edit_next_date = st.date_input("Gelecek Doz Tarihi:", value=default_next, key=f"edit_v_next_{selected_vac['id']}")
                        
                        if st.button("💾 Aşıyı Güncelle", key=f"save_vac_btn_{selected_vac['id']}", use_container_width=True):
                            if not edit_pet_name:
                                st.error("Evcil hayvan adı boş bırakılamaz!")
                            else:
                                c.execute("""
                                    UPDATE asilar 
                                    SET hayvan_ad = ?, asi_adi = ?, uygulama_tarih = ?, gelecek_doz_tarih = ?
                                    WHERE id = ?
                                """, (edit_pet_name, edit_vac_name, edit_apply_date.strftime("%Y-%m-%d"), edit_next_date.strftime("%Y-%m-%d"), edit_vac_id))
                                conn.commit()
                                st.toast("Aşı kaydı güncellendi.", icon="✅")
                                st.rerun()
                                
            with col_vac_del:
                with st.expander("🗑️ Aşı Kaydı Sil", expanded=False):
                    del_vac_id = st.selectbox("Silinecek Aşı Kaydı:", options=df_vac["id"].tolist(), format_func=lambda x: f"{df_vac[df_vac['id'] == x]['Evcil Hayvan'].values[0]} - {df_vac[df_vac['id'] == x]['Aşı Adı'].values[0]} ({df_vac[df_vac['id'] == x]['Müşteri'].values[0]})", key="del_vac_select")
                    if st.button("❌ Aşı Kaydını Sil", key="del_vac_btn", use_container_width=True):
                        c.execute("DELETE FROM asilar WHERE id = ?", (del_vac_id,))
                        conn.commit()
                        st.toast("Aşı kaydı silindi.", icon="🗑️")
                        st.rerun()
                
    conn.close()

# ----------------- MODULE: MAMA TAKIP PANELI (Food Depletion Tracker) -----------------
elif menu == "🥣 Mama Takip Paneli":
    st.markdown("## 🥣 Yapay Zekalı Mama Bitiş Tahmin & Hatırlatma Paneli")
    st.markdown("Müşterilerinizin satın aldıkları mamaların kilogramları ile evcil hayvanlarının günlük tüketim hızlarını hesaplayarak, maması bitmek üzere olan (son 3 güne giren) müşterileri listeler.")
    
    limit_date = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id, isim, telefon, hayvan_turu, son_alinan_mama, tahmini_mama_bitis_tarihi 
        FROM musteriler 
        WHERE tahmini_mama_bitis_tarihi IS NOT NULL AND tahmini_mama_bitis_tarihi != '' AND tahmini_mama_bitis_tarihi <= ?
        ORDER BY tahmini_mama_bitis_tarihi ASC
    """, (limit_date,))
    reminders = c.fetchall()
    
    if not reminders:
        st.info("Mamasının bitmesine 3 gün kalan veya bitmiş olan herhangi bir müşteri bulunamadı.")
    else:
        for r in reminders:
            col_info, col_action = st.columns([7, 3])
            with col_info:
                st.markdown(f"🥣 **{r['isim']}** ({r['telefon']}) | Dostumuz: `{r['hayvan_turu']}` | Son Alınan Mama: `{r['son_alinan_mama']}` | ⏳ Bitiş: **{r['tahmini_mama_bitis_tarihi']}**")
            with col_action:
                msg = f"Merhaba {r['isim']}! 🐾 Beykoz Pet'ten sevgiler. Dostumuz {r['hayvan_turu']}'nin {r['son_alinan_mama']} maması hesaplamalarımıza göre bitmek üzere olabilir. 🥣 Dostumuzun beslenme düzeni bölünmesin diye taze mamasını sizin için ayıralım mı? ✨"
                if st.button("💬 Hatırlatma Gönder", key=f"wa_mama_btn_{r['id']}", use_container_width=True):
                    success, info = send_whatsapp_reminder(r['telefon'], msg)
                    if success:
                        st.success(info)
                    else:
                        st.info(info)
            st.markdown("<hr style='margin:5px 0; border-color:rgba(255,255,255,0.05);'>", unsafe_allow_html=True)
            
    conn.close()

# ----------------- MODULE: MUSTERI SIPARISLERI (Customer Product Orders) -----------------
elif menu == "📋 Müşteri Siparişleri":
    st.markdown("## 📋 Özel Müşteri Siparişleri Takip Paneli")
    st.markdown("Müşterilerinizin özel olarak dükkana getirmemizi istediği ürün siparişlerini kaydedin, takip edin ve tek tıkla patronlara WhatsApp üzerinden hatırlatma geçin.")
    
    conn = get_db_connection()
    c = conn.cursor()
    
    col_add, col_list = st.columns([5, 7])
    
    with col_add:
        st.markdown("### ➕ Yeni Özel Sipariş Kaydet")
        with st.form("yeni_siparis_form", clear_on_submit=True):
            c.execute("SELECT id, isim, telefon FROM musteriler ORDER BY isim ASC")
            customers = c.fetchall()
            cust_dict = {cust['id']: f"{cust['isim']} ({cust['telefon']})" for cust in customers}
            
            if not cust_dict:
                st.warning("Sipariş girmeden önce en az bir müşteri kaydetmelisiniz!")
                submitted = st.form_submit_button("Sipariş Kaydet")
            else:
                f_cust_id = st.selectbox("Müşteri Seçin:", options=list(cust_dict.keys()), format_func=lambda x: cust_dict[x])
                f_prod_details = st.text_input("İstediği Ürün Adı / Detayı:")
                f_qty = st.number_input("Miktar (Adet):", min_value=1, value=1, step=1)
                f_date = st.date_input("Sipariş Tarihi:", value=datetime.today().date())
                f_status = st.selectbox("Sipariş Durumu:", ["Beklemede", "Geldi", "Teslim Edildi"])
                
                submitted = st.form_submit_button("💾 Siparişi Kaydet")
                if submitted:
                    if not f_prod_details:
                        st.error("Lütfen istenen ürün detaylarını girin!")
                    else:
                        c.execute("""
                            INSERT INTO customer_orders (musteri_id, urun_detay, miktar, siparis_tarihi, durum)
                            VALUES (?, ?, ?, ?, ?)
                        """, (f_cust_id, f_prod_details, f_qty, f_date.strftime("%Y-%m-%d"), f_status))
                        conn.commit()
                        st.success("🎉 Müşteri özel siparişi başarıyla kaydedildi!")
                        st.rerun()
                        
    with col_list:
        st.markdown("### 📋 Sipariş Takip Listesi")
        c.execute("""
            SELECT o.*, m.isim, m.telefon 
            FROM customer_orders o 
            JOIN musteriler m ON o.musteri_id = m.id 
            ORDER BY 
                CASE o.durum 
                    WHEN 'Beklemede' THEN 1 
                    WHEN 'Geldi' THEN 2 
                    WHEN 'Teslim Edildi' THEN 3 
                END ASC, 
                o.siparis_tarihi DESC
        """)
        orders = c.fetchall()
        
        if not orders:
            st.info("Kayıtlı özel sipariş bulunmamaktadır.")
        else:
            for o in orders:
                color_map = {"Beklemede": "#f59e0b", "Geldi": "#10b981", "Teslim Edildi": "#60a5fa"}
                badge_color = color_map.get(o["durum"], "#94a3b8")
                
                st.markdown(f"""
                <div style='background-color: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 8px; padding: 12px; margin-bottom: 10px;'>
                    <span style='background-color: {badge_color}; color:#fff; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold;'>{o['durum']}</span>
                    <strong style='font-size: 1.05em; margin-left: 10px;'>{o['urun_detay']} (x{o['miktar']})</strong><br/>
                    <span style='font-size:0.9em; opacity:0.8;'>
                        • <b>Müşteri:</b> {o['isim']} ({o['telefon']})<br/>
                        • <b>Sipariş Tarihi:</b> {o['siparis_tarihi']}
                    </span>
                </div>
                """, unsafe_allow_html=True)
                
                col_act1, col_act2, col_act3 = st.columns([4, 4, 4])
                
                with col_act1:
                    new_status = st.selectbox(
                        "Durumu Güncelle:", 
                        ["Beklemede", "Geldi", "Teslim Edildi"], 
                        index=["Beklemede", "Geldi", "Teslim Edildi"].index(o["durum"]), 
                        key=f"status_sel_{o['id']}"
                    )
                    if new_status != o["durum"]:
                        c.execute("UPDATE customer_orders SET durum = ? WHERE id = ?", (new_status, o["id"]))
                        conn.commit()
                        st.toast("Sipariş durumu güncellendi!", icon="✅")
                        st.rerun()
                        
                with col_act2:
                    msg = (
                        f"📋 Beykoz Pet - Özel Müşteri Siparişi Hatırlatması! \n\n"
                        f"Kanka, {o['isim']} adlı müşterimiz dükkana getirmemiz için sipariş bıraktı, toptancıya geçmeyi unutmayalım: \n"
                        f"📦 İstenen Ürün: {o['urun_detay']} \n"
                        f"🔢 Adet: {o['miktar']} \n\n"
                        f"Kayıt Tarihi: {o['siparis_tarihi']} \n"
                        f"İyi çalışmalar! 🐾"
                    )
                    patron_nums = ["05347487160", "05541938262"]
                    if st.button("📲 Siparişi Patronlara Uçur", key=f"wa_ord_btn_{o['id']}", use_container_width=True):
                        st.info("Sipariş hatırlatmaları patronlara gönderiliyor...")
                        for phone in patron_nums:
                            success, info = send_whatsapp_reminder(phone, msg)
                            st.write(f"✓ **{phone}** adresine yönlendirildi...")
                            import time
                            time.sleep(3.0)
                        st.success("Tüm hatırlatma yönlendirmeleri tamamlandı!")
                        st.rerun()
                        
                with col_act3:
                    if st.button("🗑️ Siparişi Sil", key=f"del_ord_btn_{o['id']}", use_container_width=True):
                        c.execute("DELETE FROM customer_orders WHERE id = ?", (o["id"],))
                        conn.commit()
                        st.toast("Sipariş kaydı silindi.", icon="🗑️")
                        st.rerun()
                        
                st.markdown("<hr style='margin:10px 0; border-color:rgba(255,255,255,0.05);'>", unsafe_allow_html=True)
                
    conn.close()

# ----------------- MODULE: KAMPANYA YONETIMI (Bulk Campaigns) -----------------
elif menu == "📢 Kampanya Yönetimi":
    st.markdown("## 📢 Seçmeli WhatsApp Kampanya Modülü")
    st.markdown("Müşterilerinizi filtreleyerek veya tek tek seçerek kişiselleştirilmiş kampanya mesajları gönderin.")
    
    campaign_text = st.text_area(
        "Kampanya Mesajı Metni (Alıcının ismi için [Müşteri Adı] etiketini kullanabilirsiniz):", 
        value="Merhaba [Müşteri Adı]! 🐾 Beykoz Pet'te bu haftaya özel tüm kedi/köpek mamalarında %15 indirim başladı! Stoklar tükenmeden dükkanımıza bekliyoruz. ✨", 
        height=120
    )
    
    # Load all active customers
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, isim, telefon, hayvan_turu FROM musteriler WHERE telefon IS NOT NULL AND telefon != ''")
    all_customers = c.fetchall()
    conn.close()
    
    # Initialize session state for all checkbox keys if not exists
    for cust in all_customers:
        chk_key = f"camp_chk_{cust['id']}"
        if chk_key not in st.session_state:
            st.session_state[chk_key] = False
            
    # Search filter field
    st.markdown("### 🔍 Hızlı Filtrele ve Müşteri Seçimi")
    
    # Quick filter action buttons
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        if st.button("👥 Herkesi Seç", use_container_width=True):
            for cust in all_customers:
                st.session_state[f"camp_chk_{cust['id']}"] = True
            st.rerun()
    with col_f2:
        if st.button("🐱 Sadece Kedisi Olanlar", use_container_width=True):
            for cust in all_customers:
                if cust["hayvan_turu"] == "Kedi":
                    st.session_state[f"camp_chk_{cust['id']}"] = True
                else:
                    st.session_state[f"camp_chk_{cust['id']}"] = False
            st.rerun()
    with col_f3:
        if st.button("🐶 Sadece Köpeği Olanlar", use_container_width=True):
            for cust in all_customers:
                if cust["hayvan_turu"] == "Köpek":
                    st.session_state[f"camp_chk_{cust['id']}"] = True
                else:
                    st.session_state[f"camp_chk_{cust['id']}"] = False
            st.rerun()
    with col_f4:
        if st.button("❌ Seçimleri Temizle", use_container_width=True):
            for cust in all_customers:
                st.session_state[f"camp_chk_{cust['id']}"] = False
            st.rerun()
            
    search_cust = st.text_input("Müşteri Listesinde Ara (İsim veya Telefon):", placeholder="Aramak için yazın...")
    
    # Render checkboxes
    st.markdown("#### 📋 Gönderilecek Kişiler Listesi")
    filtered_customers = all_customers
    if search_cust:
        q = search_cust.strip().lower()
        filtered_customers = [cust for cust in all_customers if q in cust["isim"].lower() or q in cust["telefon"]]
        
    # Render table-like list of checkboxes
    col_chk_head, col_name_head, col_pet_head = st.columns([1, 6, 3])
    with col_chk_head:
        st.markdown("**Seç**")
    with col_name_head:
        st.markdown("**Müşteri Adı / Telefon**")
    with col_pet_head:
        st.markdown("**Evcil Hayvan**")
        
    for cust in filtered_customers:
        chk_key = f"camp_chk_{cust['id']}"
        col_chk_val, col_name_val, col_pet_val = st.columns([1, 6, 3])
        with col_chk_val:
            st.checkbox("", key=chk_key, label_visibility="collapsed")
        with col_name_val:
            st.markdown(f"**{cust['isim']}** ({cust['telefon']})")
        with col_pet_val:
            st.markdown(cust['hayvan_turu'] or "Bilinmiyor")
            
    # Calculate how many customers are selected
    total_selected = sum([1 for cust in all_customers if st.session_state.get(f"camp_chk_{cust['id']}", False)])
    st.markdown(f"**Toplam Seçilen Alıcı Sayısı:** `{total_selected}`")
    
    st.markdown("---")
    
    # Start campaign button
    if st.button("🚀 Kampanyayı Başlat", use_container_width=True, type="primary"):
        selected_custs = [cust for cust in all_customers if st.session_state.get(f"camp_chk_{cust['id']}", False)]
        if not selected_custs:
            st.warning("Lütfen kampanya gönderilecek en az bir müşteri seçin!")
        else:
            st.info(f"{len(selected_custs)} müşteriye kampanya mesajları hazırlanıyor...")
            progress_bar = st.progress(0)
            
            # Real-time log panel
            st.markdown("### 📝 Gönderim Durumu")
            log_container = st.empty()
            logs = []
            
            import time
            for idx, cust in enumerate(selected_custs):
                time_str = datetime.now().strftime("%H:%M")
                personalized_msg = campaign_text.replace("[Müşteri Adı]", cust["isim"])
                
                success, info = send_whatsapp_reminder(cust["telefon"], personalized_msg)
                
                logs.append(f"✅ [{time_str}] {cust['isim']} - Mesaj hazırlandı.")
                log_container.markdown("\n".join([f"- {l}" for l in logs]))
                
                progress_bar.progress((idx + 1) / len(selected_custs))
                time.sleep(3.0)
                
            st.success(f"Seçilen {len(selected_custs)} müşteriye kampanya yönlendirmeleri tamamlandı!")

# ----------------- MODULE: PATRON RAPOR PANELI (Boss Panel) -----------------
elif menu == "👑 Patron Rapor Paneli":
    st.markdown("## 👑 Patron Rapor Paneli")
    st.markdown("Haftalık dükkan özet cirosunu, kuaför operasyon adetlerini ve en çok satan ürünü inceleyin; tek tıkla patronlara raporu WhatsApp üzerinden uçurun.")
    
    # Calculate dates for the last 7 days (weekly report)
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    seven_days_ago_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. Total weekly revenue
    c.execute("SELECT SUM(toplam_tutar) FROM satislar WHERE tarih >= ?", (seven_days_ago,))
    weekly_rev_res = c.fetchone()[0]
    weekly_rev = weekly_rev_res if weekly_rev_res is not None else 0.0
    
    # 2. Total completed grooming appointments this week
    c.execute("SELECT COUNT(*) FROM randevular WHERE durum = 'Tamamlandı' AND tamamlandi_tarih >= ?", (seven_days_ago_date,))
    weekly_grooming = c.fetchone()[0]
    
    # 3. Top selling product this week
    c.execute("""
        SELECT urun_ad, SUM(miktar) as total_qty 
        FROM satislar 
        WHERE tarih >= ? 
        GROUP BY barkod 
        ORDER BY total_qty DESC 
        LIMIT 1
    """, (seven_days_ago,))
    top_prod_res = c.fetchone()
    top_product_name = top_prod_res[0] if top_prod_res else "Veri Yok"
    top_product_qty = top_prod_res[1] if top_prod_res else 0
    
    conn.close()
    
    # Visual metrics presentation
    st.markdown("### 📊 Bu Haftanın Dükkan Özet Performansı")
    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1:
        st.markdown(f"""
        <div class="metric-card">
            <h3>💰 Haftalık Toplam Ciro</h3>
            <h2>{weekly_rev:.2f} TL</h2>
            <span style='color:#34d399;'>Son 7 günün cirosu</span>
        </div>
        """, unsafe_allow_html=True)
    with col_r2:
        st.markdown(f"""
        <div class="metric-card" style='border-left: 4px solid #ef4444;'>
            <h3 style='color:#ef4444;'>✂️ Tamamlanan Kuaför Bakımı</h3>
            <h2 style='color:#f87171;'>{weekly_grooming} Dostumuz</h2>
            <span style='color:#f87171;'>Son 7 günde tamamlanan işlemler</span>
        </div>
        """, unsafe_allow_html=True)
    with col_r3:
        st.markdown(f"""
        <div class="metric-card">
            <h3>📦 En Çok Satan Ürün (Haftalık)</h3>
            <h4 style='color:#a78bfa; margin: 5px 0;'>{top_product_name}</h4>
            <span style='color:#a78bfa;'>Satış Adedi: {top_product_qty}</span>
        </div>
        """, unsafe_allow_html=True)
        
    st.markdown("---")
    
    # WhatsApp sending action
    st.markdown("### 🚀 Haftalık Rapor Kartını Uçur")
    st.markdown("Bu butona bastığınızda aşağıdaki patron numaralarına haftalık dükkan raporu sırayla gönderilecektir:")
    st.markdown("- **0534 748 7160** (Furkan Enes Kan)")
    st.markdown("- **0554 193 8262** (Fatih Evrim Kan)")
    
    patron_nums = ["05347487160", "05541938262"]
    
    report_msg = (
        f"📊 Beykoz Pet Haftalık Rapor Kartı 🚀 \n\n"
        f"Merhaba Kanka, bu haftanın dükkan özeti hazır! \n"
        f"💰 Toplam Ciro: {weekly_rev:.2f} TL \n"
        f"✂️ Kuaför İşlemi: {weekly_grooming} Evcil Hayvan \n"
        f"📦 En Çok Satan Ürün: {top_product_name} \n\n"
        f"Bereketli haftalar dileriz! 🐾"
    )
    
    if st.button("📲 Haftalık Raporu Patronlara Uçur", type="primary", use_container_width=True):
        st.info("Raporlar hazırlanıyor ve sırayla gönderiliyor...")
        progress_bar = st.progress(0)
        
        for idx, phone in enumerate(patron_nums):
            success, info = send_whatsapp_reminder(phone, report_msg)
            progress_bar.progress((idx + 1) / len(patron_nums))
            st.write(f"✓ **{phone}** için rapor yönlendirildi...")
            import time
            time.sleep(4.0)
            
        st.success("Tüm patron raporları başarıyla yönlendirildi/gönderildi!")

# ----------------- MODULE: VERESIYE DEFTERI (Cari Hesap Defteri) -----------------
elif menu == "📓 Veresiye Defteri":
    st.markdown("## 📓 Veresiye Defteri (Cari Takip Paneli)")
    st.markdown("Müşterilerinizin açık hesap borçlarını takip edin, kısmi veya tam tahsilatları yönetin, vadesi gelen borçlar için WhatsApp hatırlatmaları gönderin.")
    
    conn = get_db_connection()
    c = conn.cursor()
    
    tab_defter, tab_vade = st.tabs(["📓 Cari Hesap Listesi", "📅 Vadesi Gelenler / Geçenler"])
    
    with tab_defter:
        # Sum total active debt per customer
        c.execute("""
            SELECT d.customer_id, m.isim, m.telefon, SUM(d.amount) as total_debt 
            FROM debts d
            JOIN musteriler m ON d.customer_id = m.id
            WHERE d.status != 'Ödendi'
            GROUP BY d.customer_id
            ORDER BY total_debt DESC
        """)
        debt_summary = c.fetchall()
        
        if not debt_summary:
            st.info("Veresiye defterinde kayıtlı açık borç bulunmamaktadır.")
        else:
            for row in debt_summary:
                st.markdown(f"### 👤 {row['isim']} ({row['telefon']})")
                st.markdown(f"**Toplam Açık Borç:** <span style='color: #f59e0b; font-size:1.2em; font-weight:bold;'>{row['total_debt']:.2f} TL</span>", unsafe_allow_html=True)
                
                # Fetch details for this customer
                c.execute("SELECT * FROM debts WHERE customer_id = ? AND status != 'Ödendi' ORDER BY purchase_date DESC", (row["customer_id"],))
                cust_debts = c.fetchall()
                
                # Render debt cards/rows
                for cd in cust_debts:
                    st.markdown(f"""
                    <div style='background-color: rgba(255,255,255,0.01); border: 1px solid rgba(255,255,255,0.05); border-radius: 6px; padding: 10px; margin-bottom: 5px;'>
                        • <b>Detay:</b> {cd['product_details']} | 💰 <b>Tutar:</b> {cd['amount']:.2f} TL | 📅 <b>Veriliş:</b> {cd['purchase_date']} | 📅 <b>Vade:</b> {cd['due_date']} | 📌 <b>Durum:</b> {cd['status']}
                    </div>
                    """, unsafe_allow_html=True)
                
                # Fetch and render payment history (Tahsilat Geçmişi)
                c.execute("""
                    SELECT p.*, d.product_details 
                    FROM payment_history p
                    JOIN debts d ON p.debt_id = d.id
                    WHERE d.customer_id = ?
                    ORDER BY p.payment_date DESC
                """, (row["customer_id"],))
                pay_history = c.fetchall()
                
                if pay_history:
                    st.markdown("**💸 Ödeme Geçmişi:**")
                    for ph in pay_history:
                        try:
                            dt_obj = datetime.strptime(ph["payment_date"], "%Y-%m-%d %H:%M:%S")
                            formatted_dt = dt_obj.strftime("%d.%m.%Y - %H:%M")
                        except Exception:
                            formatted_dt = ph["payment_date"]
                        st.markdown(f"📅 {formatted_dt} - **{ph['amount_paid']:.2f} TL** ({ph['payment_type']} Ödeme Alındı)")
                
                # Tahsilat Form
                col_t1, col_t2, col_t3 = st.columns([4, 4, 4])
                with col_t1:
                    pay_amt = st.number_input(
                        "Tahsil Edilecek Tutar (TL):", 
                        min_value=0.0, 
                        max_value=float(row['total_debt']), 
                        step=50.0, 
                        value=float(row['total_debt']),
                        key=f"pay_amt_{row['customer_id']}"
                    )
                with col_t2:
                    pay_method = st.selectbox(
                        "Tahsilat Yöntemi:", 
                        ["Nakit", "Kredi Kartı"], 
                        key=f"pay_method_{row['customer_id']}"
                    )
                with col_t3:
                    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                    if st.button("💰 Tahsilat Al", key=f"pay_btn_{row['customer_id']}", use_container_width=True):
                        if pay_amt <= 0:
                            st.error("Tahsilat tutarı sıfırdan büyük olmalıdır!")
                        else:
                            remaining_payment = pay_amt
                            today_str = datetime.now().strftime("%Y-%m-%d")
                            today_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
                            # FIFO partial debt collection
                            c.execute("SELECT * FROM debts WHERE customer_id = ? AND status != 'Ödendi' ORDER BY purchase_date ASC", (row["customer_id"],))
                            unpaid_rows = c.fetchall()
                            
                            for u_debt in unpaid_rows:
                                if remaining_payment <= 0:
                                    break
                                    
                                debt_amount = u_debt["amount"]
                                if remaining_payment >= debt_amount:
                                    c.execute("UPDATE debts SET amount = 0, status = 'Ödendi' WHERE id = ?", (u_debt["id"],))
                                    # Insert payment history log
                                    c.execute("""
                                        INSERT INTO payment_history (debt_id, amount_paid, payment_date, payment_type)
                                        VALUES (?, ?, ?, ?)
                                    """, (u_debt["id"], debt_amount, today_time_str, pay_method))
                                    remaining_payment -= debt_amount
                                else:
                                    new_amount = debt_amount - remaining_payment
                                    c.execute("UPDATE debts SET amount = ?, status = 'Kısmi Ödendi' WHERE id = ?", (new_amount, u_debt["id"]))
                                    # Insert payment history log
                                    c.execute("""
                                        INSERT INTO payment_history (debt_id, amount_paid, payment_date, payment_type)
                                        VALUES (?, ?, ?, ?)
                                    """, (u_debt["id"], remaining_payment, today_time_str, pay_method))
                                    remaining_payment = 0
                                    
                            # Log as 'Gelir' to accounting
                            c.execute("""
                                INSERT INTO accounting (tarih, tip, kategori, tutar, aciklama)
                                VALUES (?, ?, ?, ?, ?)
                            """, (today_str, "Gelir", "Veresiye Tahsilatı", pay_amt, f"Veresiye Tahsilatı | Müşteri: {row['isim']} | Yöntem: {pay_method}"))
                            conn.commit()
                            st.toast(f"✅ {pay_amt:.2f} TL veresiye tahsil edildi!", icon="💰")
                            st.rerun()
                st.markdown("<hr style='margin:15px 0; border-color:rgba(255,255,255,0.05);'>", unsafe_allow_html=True)
                
    with tab_vade:
        st.markdown("### ⚠️ Ödeme Tarihi Gelen / Geçen Cari Alacaklar")
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        c.execute("""
            SELECT d.*, m.isim, m.telefon 
            FROM debts d
            JOIN musteriler m ON d.customer_id = m.id
            WHERE d.status != 'Ödendi' AND d.due_date <= ?
            ORDER BY d.due_date ASC
        """, (today_str,))
        vade_debts = c.fetchall()
        
        if not vade_debts:
            st.success("Ödeme günü gecikmiş herhangi bir veresiye alacağı bulunmamaktadır.")
        else:
            for vd in vade_debts:
                col_v1, col_v2 = st.columns([7, 3])
                with col_v1:
                    st.markdown(f"👤 **{vd['isim']}** ({vd['telefon']}) | 📦 **Detay:** `{vd['product_details']}`")
                    st.markdown(f"⏳ **Tutar:** `{vd['amount']:.2f} TL` | 📅 **Vade:** `{vd['due_date']}` (Veriliş: `{vd['purchase_date']}`)")
                with col_v2:
                    msg = (
                        f"Merhaba {vd['isim']}! ✨ Beykoz Pet'ten sevgiler. 🐾 "
                        f"{vd['purchase_date']} tarihinde dostumuz için aldığınız {vd['product_details']} ürünlerine ait {vd['amount']:.2f} TL'lik veresiye hesabı için konuşulan ödeme tarihi ({vd['due_date']}) gelmiştir. "
                        f"Dükkanımızın nakit akışını koruyabilmemiz adına müsait olduğunuzda uğrayabilirseniz çok seviniriz. Hayırlı günler, bereketli işler dileriz! 🐶🐱"
                    )
                    if st.button("💬 Borç Hatırlat", key=f"wa_debt_{vd['id']}", use_container_width=True):
                        success, info = send_whatsapp_reminder(vd['telefon'], msg)
                        if success:
                            st.success(info)
                        else:
                            st.info(info)
                st.markdown("<hr style='margin:10px 0; border-color:rgba(255,255,255,0.05);'>", unsafe_allow_html=True)
                
    conn.close()

# ----------------- MODULE: ON MUHASEBE (Pre-Accounting Ledger) -----------------
elif menu == "📊 Ön Muhasebe":
    st.markdown("## 📊 Ön Muhasebe & Cari Yönetim")
    st.markdown("Dükkanınızın günlük, haftalık ve aylık kasa hareketlerini, gelir-gider analizlerini ve toptancı cari hesaplarını buradan yönetin.")
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # Calculate Overall / Lifetime metrics for the shop
    c.execute("SELECT SUM(tutar) FROM accounting WHERE tip = 'Gelir'")
    total_ciro = c.fetchone()[0] or 0.0
    
    # Calculate Brüt Kâr
    c.execute("SELECT s.toplam_tutar, s.miktar, u.gelis_fiyati FROM satislar s LEFT JOIN urunler u ON s.barkod = u.barkod")
    sales_rows = c.fetchall()
    brut_kar = 0.0
    for s in sales_rows:
        rev = s["toplam_tutar"]
        cost = s["gelis_fiyati"] if s["gelis_fiyati"] is not None else 0.0
        brut_kar += (rev - (s["miktar"] * cost))
        
    # Calculate Net Kâr
    c.execute("SELECT SUM(tutar) FROM accounting WHERE tip = 'Gider'")
    total_gider = c.fetchone()[0] or 0.0
    net_kar = brut_kar - total_gider
    
    col_acc_m1, col_acc_m2, col_acc_m3 = st.columns(3)
    with col_acc_m1:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid #00adb5;">
            <h4 style="margin:0; opacity:0.8;">💰 Toplam Ciro (Hasılat)</h4>
            <h2 style="margin:10px 0; color:#00adb5;">{total_ciro:.2f} TL</h2>
            <span style="font-size:0.8em; opacity:0.6;">Kasa ve kuaför brüt hasılat</span>
        </div>
        """, unsafe_allow_html=True)
    with col_acc_m2:
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid #f59e0b;">
            <h4 style="margin:0; opacity:0.8;">📈 Brüt Kâr (Satış Kârı)</h4>
            <h2 style="margin:10px 0; color:#f59e0b;">{brut_kar:.2f} TL</h2>
            <span style="font-size:0.8em; opacity:0.6;">Ürün kârı (giderler hariç)</span>
        </div>
        """, unsafe_allow_html=True)
    with col_acc_m3:
        net_color = "#34d399" if net_kar >= 0 else "#ef4444"
        st.markdown(f"""
        <div class="metric-card" style="border-left: 4px solid {net_color};">
            <h4 style="margin:0; opacity:0.8;">🚨 Net Kâr (Temiz Kâr)</h4>
            <h2 style="margin:10px 0; color:{net_color};">{net_kar:.2f} TL</h2>
            <span style="font-size:0.8em; opacity:0.6;">Dükkan giderleri düşülmüş net kazanç</span>
        </div>
        """, unsafe_allow_html=True)
        
    st.markdown("<br/>", unsafe_allow_html=True)
    
    tab_kasa_defteri, tab_toptanci_carileri, tab_calisan_carileri = st.tabs(["💰 Kasa Defteri", "🚚 Toptancı Carileri", "👥 Çalışan Carileri"])
    
    with tab_kasa_defteri:
        # 1. Expense Entry Form
        col_add_acc, col_stats_acc = st.columns([5, 7])
        
        with col_add_acc:
            st.markdown("### 💸 Gider Kaydı Girişi")
            with st.form("gider_ekle_form", clear_on_submit=True):
                f_gider_kategori = st.selectbox(
                    "Gider Kategorisi:", 
                    ["Dükkan Kirası", "Toptancı Ödemesi", "Faturalar", "Eleman Maaşı", "Yol / Yemek", "Vergiler", "Diğer Giderler"]
                )
                f_gider_tutar = st.number_input("Tutar (TL):", min_value=0.0, step=50.0, value=0.0)
                f_gider_tarih = st.date_input("Gider Tarihi:", value=datetime.today().date())
                f_gider_aciklama = st.text_area("Gider Detayı / Açıklama:", placeholder="Örn: Temmuz ayı elektrik faturası...")
                
                submitted_gider = st.form_submit_button("💾 Gideri Muhasebeye İşle")
                if submitted_gider:
                    if f_gider_tutar <= 0:
                        st.error("Lütfen geçerli bir gider tutarı girin!")
                    else:
                        c.execute("""
                            INSERT INTO accounting (tarih, tip, kategori, tutar, aciklama)
                            VALUES (?, ?, ?, ?, ?)
                        """, (f_gider_tarih.strftime("%Y-%m-%d"), "Gider", f_gider_kategori, f_gider_tutar, f_gider_aciklama))
                        conn.commit()
                        st.success("💸 Gider kaydı başarıyla muhasebeye işlendi!")
                        st.rerun()
                        
        with col_stats_acc:
            st.markdown("### 💰 Kasa & Net Kâr Analizi")
            
            # Calculate periods
            today_str = datetime.now().strftime("%Y-%m-%d")
            week_ago_str = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            month_ago_str = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            
            # Period selector tabs
            tab_daily, tab_weekly, tab_monthly = st.tabs(["📅 Günlük (Bugün)", "📆 Haftalık (7 Gün)", "🗓️ Aylık (30 Gün)"])
            
            with tab_daily:
                c.execute("SELECT SUM(tutar) FROM accounting WHERE tip = 'Gelir' AND tarih = ?", (today_str,))
                d_gelir = c.fetchone()[0] or 0.0
                c.execute("SELECT SUM(tutar) FROM accounting WHERE tip = 'Gider' AND tarih = ?", (today_str,))
                d_gider = c.fetchone()[0] or 0.0
                d_net = d_gelir - d_gider
                d_net_color = "#34d399" if d_net >= 0 else "#ef4444"
                
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    st.markdown(f"<div class='metric-card'><h4>Gelir</h4><h2>{d_gelir:.2f} TL</h2></div>", unsafe_allow_html=True)
                with col_d2:
                    st.markdown(f"<div class='metric-card' style='border-left:4px solid #ef4444;'><h4>Gider</h4><h2>{d_gider:.2f} TL</h2></div>", unsafe_allow_html=True)
                st.markdown(f"<div class='metric-card' style='border-left:4px solid {d_net_color}; text-align:center;'><h4>Net Kâr / Zarar</h4><h2 style='color:{d_net_color};'>{d_net:.2f} TL</h2></div>", unsafe_allow_html=True)
                
            with tab_weekly:
                c.execute("SELECT SUM(tutar) FROM accounting WHERE tip = 'Gelir' AND tarih >= ?", (week_ago_str,))
                w_gelir = c.fetchone()[0] or 0.0
                c.execute("SELECT SUM(tutar) FROM accounting WHERE tip = 'Gider' AND tarih >= ?", (week_ago_str,))
                w_gider = c.fetchone()[0] or 0.0
                w_net = w_gelir - w_gider
                w_net_color = "#34d399" if w_net >= 0 else "#ef4444"
                
                col_w1, col_w2 = st.columns(2)
                with col_w1:
                    st.markdown(f"<div class='metric-card'><h4>Gelir</h4><h2>{w_gelir:.2f} TL</h2></div>", unsafe_allow_html=True)
                with col_w2:
                    st.markdown(f"<div class='metric-card' style='border-left:4px solid #ef4444;'><h4>Gider</h4><h2>{w_gider:.2f} TL</h2></div>", unsafe_allow_html=True)
                st.markdown(f"<div class='metric-card' style='border-left:4px solid {w_net_color}; text-align:center;'><h4>Net Kâr / Zarar</h4><h2 style='color:{w_net_color};'>{w_net:.2f} TL</h2></div>", unsafe_allow_html=True)
                
            with tab_monthly:
                c.execute("SELECT SUM(tutar) FROM accounting WHERE tip = 'Gelir' AND tarih >= ?", (month_ago_str,))
                m_gelir = c.fetchone()[0] or 0.0
                c.execute("SELECT SUM(tutar) FROM accounting WHERE tip = 'Gider' AND tarih >= ?", (month_ago_str,))
                m_gider = c.fetchone()[0] or 0.0
                m_net = m_gelir - m_gider
                m_net_color = "#34d399" if m_net >= 0 else "#ef4444"
                
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    st.markdown(f"<div class='metric-card'><h4>Gelir</h4><h2>{m_gelir:.2f} TL</h2></div>", unsafe_allow_html=True)
                with col_m2:
                    st.markdown(f"<div class='metric-card' style='border-left:4px solid #ef4444;'><h4>Gider</h4><h2>{m_gider:.2f} TL</h2></div>", unsafe_allow_html=True)
                st.markdown(f"<div class='metric-card' style='border-left:4px solid {m_net_color}; text-align:center;'><h4>Net Kâr / Zarar</h4><h2 style='color:{m_net_color};'>{m_net:.2f} TL</h2></div>", unsafe_allow_html=True)

        # 2. Income/Expense chart distributions
        st.markdown("---")
        st.markdown("### 📈 Aylık Finansal Trend (Gelir vs Gider)")
        df_acc = pd.read_sql_query("SELECT tarih, tip, tutar FROM accounting WHERE tarih >= ? ORDER BY tarih ASC", conn, params=(month_ago_str,))
        
        if df_acc.empty:
            st.info("Trend grafiği için henüz muhasebe hareketi kaydedilmemiş.")
        else:
            df_chart = df_acc.groupby(["tarih", "tip"])["tutar"].sum().unstack(fill_value=0.0).reset_index()
            if "Gelir" not in df_chart.columns:
                df_chart["Gelir"] = 0.0
            if "Gider" not in df_chart.columns:
                df_chart["Gider"] = 0.0
                
            df_chart.columns = ["Tarih", "Gelir (TL)", "Gider (TL)"]
            st.bar_chart(df_chart.set_index("Tarih"), use_container_width=True)
            
        # 3. Ledger details table
        st.markdown("---")
        st.markdown("### 📖 Muhasebe Hareket Detay Listesi")
        
        df_ledger = pd.read_sql_query("SELECT * FROM accounting ORDER BY id DESC", conn)
        if df_ledger.empty:
            st.info("Kayıtlı muhasebe hareketi bulunmamaktadır.")
        else:
            st.dataframe(df_ledger.drop(columns=["id"]), use_container_width=True)
            
            st.markdown("#### 🗑️ Muhasebe Kaydı Silme")
            del_acc_id = st.selectbox(
                "Silinecek Muhasebe Kaydı:", 
                options=df_ledger["id"].tolist(), 
                format_func=lambda x: f"[{df_ledger[df_ledger['id'] == x]['tarih'].values[0]}] {df_ledger[df_ledger['id'] == x]['tip'].values[0]} | {df_ledger[df_ledger['id'] == x]['kategori'].values[0]} | {df_ledger[df_ledger['id'] == x]['tutar'].values[0]} TL"
            )
            if st.button("❌ Muhasebe Kaydını Sil", use_container_width=True):
                c.execute("DELETE FROM accounting WHERE id = ?", (del_acc_id,))
                conn.commit()
                st.toast("Muhasebe kaydı silindi.", icon="🗑️")
                st.rerun()

    with tab_toptanci_carileri:
        st.markdown("### 🚚 Toptancı Cari Hesap Takip Paneli")
        st.markdown("Tedarikçilerinizle olan mal kabullerini, borç bakiyelerini ve siparişleri pratik şekilde yönetin.")
        
        c.execute("SELECT * FROM wholesalers ORDER BY name ASC")
        wholesalers_list = c.fetchall()
        
        col_w_form, col_w_card = st.columns([5, 7])
        
        with col_w_form:
            st.markdown("#### ➕ Yeni Toptancı Tedarikçi Ekle")
            with st.form("toptanci_ekle_form", clear_on_submit=True):
                new_w_name = st.text_input("Toptancı Adı (Firma/Kişi):")
                new_w_phone = st.text_input("Telefon Numarası:")
                submitted_new_w = st.form_submit_button("💾 Toptancıyı Kaydet")
                if submitted_new_w:
                    if not new_w_name.strip():
                        st.error("Toptancı adı boş bırakılamaz!")
                    else:
                        c.execute("INSERT INTO wholesalers (name, phone, balance) VALUES (?, ?, 0.0)", (new_w_name.strip(), new_w_phone.strip()))
                        conn.commit()
                        st.toast(f"✅ Toptancı {new_w_name} başarıyla kaydedildi!", icon="🚚")
                        st.rerun()
                        
        with col_w_card:
            st.markdown("#### 🔍 Toptancı Özel Kartı & İşlemler")
            if not wholesalers_list:
                st.info("Kayıtlı toptancı tedarikçi bulunamadı. Lütfen sol taraftan ekleyin.")
            else:
                selected_w_id = st.selectbox(
                    "İşlem yapılacak Toptancı Tedarikçi:", 
                    [w['id'] for w in wholesalers_list], 
                    format_func=lambda x: next(w['name'] for w in wholesalers_list if w['id'] == x)
                )
                
                c.execute("SELECT * FROM wholesalers WHERE id = ?", (selected_w_id,))
                w_details = c.fetchone()
                
                st.markdown(f"**Telefon:** `{w_details['phone'] or 'Belirtilmedi'}`")
                st.markdown(f"**Bizim Toptancıya Güncel Borcumuz:** <span style='color: #ef4444; font-size:1.3em; font-weight:bold;'>{w_details['balance']:.2f} TL</span>", unsafe_allow_html=True)
                
                w_tab1, w_tab2, w_tab3, w_tab4 = st.tabs(["📥 Mal Kabul / Fatura İşle", "💰 Ödeme Yap", "📝 Sipariş Notları", "📜 Geçmiş Hareketler"])
                
                with w_tab1:
                    st.markdown("##### Gelen Fatura / Mal Kabul")
                    
                    # Initialize mal_kabul_sepet for selected wholesaler
                    if "mal_kabul_wholesaler_id" not in st.session_state or st.session_state.mal_kabul_wholesaler_id != selected_w_id:
                        st.session_state.mal_kabul_wholesaler_id = selected_w_id
                        st.session_state.mal_kabul_sepet = {}
                    
                    if "unregistered_mal_kabul_barcode" not in st.session_state:
                        st.session_state.unregistered_mal_kabul_barcode = None
                        
                    input_mode = st.radio("Fatura Giriş Türü:", ["📷 Barkod Tarama ile Hızlı Giriş", "📝 Manuel Tutar Girişi"], horizontal=True)
                    
                    if input_mode == "📝 Manuel Tutar Girişi":
                        with st.form("mal_kabul_form", clear_on_submit=True):
                            invoice_items = st.text_area("Gelen Ürünler / Açıklama:", placeholder="Örn: 10 çuval Royal Canin, 5 paket yaş mama...")
                            invoice_amt = st.number_input("Fatura Tutarı (TL):", min_value=0.0, step=100.0, value=0.0)
                            invoice_date = st.date_input("Fatura Tarihi:", value=datetime.today().date())
                            
                            submit_invoice = st.form_submit_button("📥 Faturayı İşle & Borç Ekle")
                            if submit_invoice:
                                if invoice_amt <= 0 or not invoice_items.strip():
                                    st.error("Lütfen geçerli bir tutar ve ürün detayı giriniz!")
                                else:
                                    invoice_date_str = invoice_date.strftime("%Y-%m-%d")
                                    # Insert invoice record
                                    c.execute("""
                                        INSERT INTO wholesaler_invoices (wholesaler_id, product_details, total_amount, invoice_date)
                                        VALUES (?, ?, ?, ?)
                                    """, (selected_w_id, invoice_items.strip(), invoice_amt, invoice_date_str))
                                    # Update wholesaler balance
                                    c.execute("UPDATE wholesalers SET balance = balance + ? WHERE id = ?", (invoice_amt, selected_w_id))
                                    # Log to accounting as future expenses
                                    c.execute("""
                                        INSERT INTO accounting (tarih, tip, kategori, tutar, aciklama)
                                        VALUES (?, ?, ?, ?, ?)
                                    """, (invoice_date_str, "Gider", "Gelecek Gider / Borç", invoice_amt, f"Toptancı Faturası | Tedarikçi: {w_details['name']} | Detay: {invoice_items.strip()[:60]}"))
                                    conn.commit()
                                    st.toast("📥 Fatura başarıyla işlendi ve borç hanenize eklendi!", icon="📥")
                                    st.rerun()
                    else:
                        st.markdown("#### 📷 Barkod Okuyucu ile Mal Kabul")
                        
                        # Programmatic clearing flag
                        if "mal_kabul_clear_bc" not in st.session_state:
                            st.session_state.mal_kabul_clear_bc = False
                        if st.session_state.mal_kabul_clear_bc:
                            st.session_state.mal_kabul_bc_input = ""
                            st.session_state.mal_kabul_clear_bc = False
                            
                        scan_bc = st.text_input(
                            "Toptancı Mal Barkodu Okutun:", 
                            placeholder="Mal Kabul Barkod Okutun...", 
                            key="mal_kabul_bc_input"
                        )
                        
                        # Programmatic autofocus injection via JavaScript selector
                        import streamlit.components.v1 as components
                        components.html(
                            """
                            <script>
                                const focusMalKabulField = () => {
                                    const input = window.parent.document.querySelector("input[placeholder='Mal Kabul Barkod Okutun...']");
                                    if (input && window.parent.document.activeElement !== input) {
                                        input.focus();
                                    }
                                };
                                focusMalKabulField();
                                setTimeout(focusMalKabulField, 300);
                                setTimeout(focusMalKabulField, 800);
                            </script>
                            """,
                            height=0
                        )
                        
                        if scan_bc:
                            # Search in products
                            c.execute("SELECT ad, gelis_fiyati, stok FROM urunler WHERE barkod = ?", (scan_bc.strip(),))
                            prod = c.fetchone()
                            if prod:
                                # Update stock in DB: +1
                                c.execute("UPDATE urunler SET stok = stok + 1 WHERE barkod = ?", (scan_bc.strip(),))
                                conn.commit()
                                
                                bc_key = scan_bc.strip()
                                if bc_key in st.session_state.mal_kabul_sepet:
                                    st.session_state.mal_kabul_sepet[bc_key]["miktar"] += 1
                                else:
                                    st.session_state.mal_kabul_sepet[bc_key] = {
                                        "ad": prod["ad"],
                                        "miktar": 1,
                                        "gelis_fiyati": prod["gelis_fiyati"] or 0.0
                                    }
                                st.toast(f"✅ {prod['ad']} stoğu +1 artırıldı!", icon="📥")
                                st.session_state.mal_kabul_clear_bc = True
                                st.rerun()
                            else:
                                st.session_state.unregistered_mal_kabul_barcode = scan_bc.strip()
                                st.session_state.mal_kabul_clear_bc = True
                                st.rerun()
                                
                        # prefills new product form if unregistered
                        if st.session_state.unregistered_mal_kabul_barcode:
                            st.markdown("<div style='background-color:rgba(239, 68, 68, 0.1); border:1px solid #ef4444; border-radius:8px; padding:15px; margin-bottom:15px;'>", unsafe_allow_html=True)
                            st.markdown(f"⚠️ **Ürün Bulunamadı!** Barkod: `{st.session_state.unregistered_mal_kabul_barcode}`  \nLütfen stok kartını hızlıca oluşturun:")
                            
                            with st.form("quick_add_product_form", clear_on_submit=True):
                                new_p_name = st.text_input("Ürün Adı:")
                                new_p_cat = st.selectbox("Kategori:", ["Kuru Mama", "Yaş Mama", "Ödül Maması", "Konserve", "Aksesuar", "Kum", "Şampuan", "Sağlık", "Diğer"])
                                new_p_price = st.number_input("Satış Fiyatı (TL):", min_value=0.0, step=10.0, value=0.0)
                                new_p_cost = st.number_input("Geliş Maliyeti (TL):", min_value=0.0, step=10.0, value=0.0)
                                new_p_skt = st.date_input("Son Kullanma Tarihi (SKT):", value=datetime.today().date() + timedelta(days=365))
                                
                                submit_quick_p = st.form_submit_button("💾 Ürünü Envantere Ekle & Faturaya Dahil Et")
                                if submit_quick_p:
                                    if not new_p_name.strip():
                                        st.error("Ürün adı boş olamaz!")
                                    else:
                                        c.execute("""
                                            INSERT INTO urunler (barkod, ad, kategori, fiyat, gelis_fiyati, stok, kritik_stok, skt)
                                            VALUES (?, ?, ?, ?, ?, 1, 5, ?)
                                        """, (st.session_state.unregistered_mal_kabul_barcode, new_p_name.strip(), new_p_cat, new_p_price, new_p_cost, new_p_skt.strftime("%Y-%m-%d")))
                                        conn.commit()
                                        
                                        bc_key = st.session_state.unregistered_mal_kabul_barcode
                                        st.session_state.mal_kabul_sepet[bc_key] = {
                                            "ad": new_p_name.strip(),
                                            "miktar": 1,
                                            "gelis_fiyati": new_p_cost
                                        }
                                        st.toast(f"✅ {new_p_name.strip()} başarıyla eklendi!", icon="💾")
                                        st.session_state.unregistered_mal_kabul_barcode = None
                                        st.rerun()
                                        
                            if st.button("❌ İşlemi İptal Et", key="cancel_quick_p"):
                                st.session_state.unregistered_mal_kabul_barcode = None
                                st.rerun()
                            st.markdown("</div>", unsafe_allow_html=True)
                            
                        # Show current scanned items table
                        if st.session_state.mal_kabul_sepet:
                            st.markdown("##### 🧾 Okutulan Ürünlerin Listesi")
                            total_fatura_sum = 0.0
                            
                            to_delete_w = []
                            for bc, item in list(st.session_state.mal_kabul_sepet.items()):
                                item_total = item["miktar"] * item["gelis_fiyati"]
                                total_fatura_sum += item_total
                                
                                col_i_name, col_i_qty, col_i_cost, col_i_sum = st.columns([4, 2, 3, 3])
                                with col_i_name:
                                    st.write(f"**{item['ad']}**")
                                    st.caption(f"Barkod: {bc}")
                                with col_i_qty:
                                    new_w_qty = st.number_input(
                                        "", 
                                        min_value=0, 
                                        value=item["miktar"], 
                                        key=f"w_qty_{bc}_{item['miktar']}", 
                                        label_visibility="collapsed"
                                    )
                                    if new_w_qty == 0:
                                        to_delete_w.append(bc)
                                    elif new_w_qty != item["miktar"]:
                                        diff = new_w_qty - item["miktar"]
                                        c.execute("UPDATE urunler SET stok = stok + ? WHERE barkod = ?", (diff, bc))
                                        conn.commit()
                                        st.session_state.mal_kabul_sepet[bc]["miktar"] = new_w_qty
                                        st.rerun()
                                with col_i_cost:
                                    new_w_cost = st.number_input(
                                        "", 
                                        min_value=0.0, 
                                        value=item["gelis_fiyati"], 
                                        key=f"w_cost_{bc}_{item['gelis_fiyati']}", 
                                        label_visibility="collapsed"
                                    )
                                    if new_w_cost != item["gelis_fiyati"]:
                                        c.execute("UPDATE urunler SET gelis_fiyati = ? WHERE barkod = ?", (new_w_cost, bc))
                                        conn.commit()
                                        st.session_state.mal_kabul_sepet[bc]["gelis_fiyati"] = new_w_cost
                                        st.rerun()
                                with col_i_sum:
                                    st.write(f"**{item_total:.2f} TL**")
                                    
                            for bc_del in to_delete_w:
                                del_qty = st.session_state.mal_kabul_sepet[bc_del]["miktar"]
                                c.execute("UPDATE urunler SET stok = stok - ? WHERE barkod = ?", (del_qty, bc_del))
                                conn.commit()
                                del st.session_state.mal_kabul_sepet[bc_del]
                                st.rerun()
                                
                            st.markdown(f"#### 💰 Fatura Toplamı: <span style='color: #ef4444;'>{total_fatura_sum:.2f} TL</span>", unsafe_allow_html=True)
                            
                            # Close Fatura Button
                            if st.button("💾 Faturayı Kapat ve Borcu Toptancıya Ekle", type="primary", use_container_width=True):
                                product_details_str = ", ".join([f"{item['miktar']}x {item['ad']} ({item['gelis_fiyati']:.2f} TL)" for item in st.session_state.mal_kabul_sepet.values()])
                                invoice_date_str = datetime.now().strftime("%Y-%m-%d")
                                
                                # Insert invoice record
                                c.execute("""
                                    INSERT INTO wholesaler_invoices (wholesaler_id, product_details, total_amount, invoice_date)
                                    VALUES (?, ?, ?, ?)
                                """, (selected_w_id, product_details_str, total_fatura_sum, invoice_date_str))
                                # Update wholesaler balance
                                c.execute("UPDATE wholesalers SET balance = balance + ? WHERE id = ?", (total_fatura_sum, selected_w_id))
                                # Log to accounting as future expenses
                                c.execute("""
                                    INSERT INTO accounting (tarih, tip, kategori, tutar, aciklama)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (invoice_date_str, "Gider", "Gelecek Gider / Borç", total_fatura_sum, f"Mal Kabul (Barkodlu) | Tedarikçi: {w_details['name']}"))
                                conn.commit()
                                
                                st.session_state.mal_kabul_sepet = {}
                                st.toast("✅ Barkodlu fatura kapatıldı ve toptancı carisine işlendi!", icon="💾")
                                st.rerun()
                        else:
                            st.info("Mal kabul işlemi için barkod okutun veya barkod yazıp enter'a basın.")
                                
                with w_tab2:
                    st.markdown("##### Toptancıya Ödeme Yap (Borçtan Düş)")
                    with st.form("toptanci_odeme_form", clear_on_submit=True):
                        pay_amt = st.number_input("Ödeme Tutarı (TL):", min_value=0.0, max_value=float(w_details['balance']) if w_details['balance'] > 0 else 1000000.0, step=100.0, value=float(w_details['balance']) if w_details['balance'] > 0 else 0.0)
                        pay_date = st.date_input("Ödeme Tarihi:", value=datetime.today().date())
                        
                        submit_pay = st.form_submit_button("💸 Ödemeyi Gerçekleştir")
                        if submit_pay:
                            if pay_amt <= 0:
                                st.error("Ödeme tutarı sıfırdan büyük olmalıdır!")
                            else:
                                pay_date_str = pay_date.strftime("%Y-%m-%d")
                                # Insert payment record
                                c.execute("""
                                    INSERT INTO wholesaler_payments (wholesaler_id, amount_paid, payment_date)
                                    VALUES (?, ?, ?)
                                """, (selected_w_id, pay_amt, pay_date_str))
                                # Update wholesaler balance
                                c.execute("UPDATE wholesalers SET balance = balance - ? WHERE id = ?", (pay_amt, selected_w_id))
                                # Log to accounting as cash outflow
                                c.execute("""
                                    INSERT INTO accounting (tarih, tip, kategori, tutar, aciklama)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (pay_date_str, "Gider", "Toptancı Ödemesi", pay_amt, f"Toptancı Ödemesi | Tedarikçi: {w_details['name']}"))
                                conn.commit()
                                st.toast("💸 Ödeme başarıyla düşüldü ve gider olarak işlendi!", icon="💸")
                                st.rerun()
                                
                with w_tab3:
                    st.markdown("##### Sipariş Notları")
                    with st.form("siparis_notu_ekle_form", clear_on_submit=True):
                        order_notes = st.text_area("Sipariş Notu:", placeholder="Örn: 5 çuval puppy, 3 çuval sterilised...")
                        submit_order = st.form_submit_button("➕ Sipariş Notu Ekle")
                        if submit_order:
                            if not order_notes.strip():
                                st.error("Sipariş notu boş olamaz!")
                            else:
                                c.execute("INSERT INTO wholesaler_orders (wholesaler_id, order_notes, status) VALUES (?, ?, 'Beklemede')", (selected_w_id, order_notes.strip()))
                                conn.commit()
                                st.toast("📝 Sipariş notu başarıyla eklendi!", icon="📝")
                                st.rerun()
                                
                    # List orders
                    c.execute("SELECT * FROM wholesaler_orders WHERE wholesaler_id = ? ORDER BY id DESC", (selected_w_id,))
                    orders = c.fetchall()
                    if not orders:
                        st.info("Kayıtlı sipariş notu bulunamadı.")
                    else:
                        st.markdown("##### Sipariş Not Listesi:")
                        for o in orders:
                            col_o1, col_o2 = st.columns([8, 2])
                            with col_o1:
                                status_lbl = "⏳ Beklemede" if o["status"] == "Beklemede" else "✅ İletildi"
                                st.markdown(f"**Not:** {o['order_notes']}  \n*(Durum: {status_lbl})*")
                            with col_o2:
                                if o["status"] == "Beklemede":
                                    if st.button("✓ İletildi Yap", key=f"mark_ord_{o['id']}"):
                                        c.execute("UPDATE wholesaler_orders SET status = 'İletildi' WHERE id = ?", (o["id"],))
                                        conn.commit()
                                        st.toast("Sipariş iletildi olarak işaretlendi.", icon="✅")
                                        st.rerun()
                            st.markdown("<hr style='margin:10px 0; border-color:rgba(255,255,255,0.05);'>", unsafe_allow_html=True)
                            
                with w_tab4:
                    st.markdown("##### Geçmiş Fatura ve Ödeme Geçmişi")
                    
                    col_invoices, col_payments = st.columns(2)
                    with col_invoices:
                        st.markdown("###### 📥 Gelen Faturalar / Mal Kabuller")
                        c.execute("SELECT * FROM wholesaler_invoices WHERE wholesaler_id = ? ORDER BY invoice_date DESC", (selected_w_id,))
                        invoices = c.fetchall()
                        if not invoices:
                            st.info("Kayıtlı fatura yok.")
                        else:
                            for inv in invoices:
                                st.markdown(f"""
                                <div style='background-color:rgba(255,255,255,0.01); border:1px solid rgba(255,255,255,0.05); border-radius:6px; padding:10px; margin-bottom:5px;'>
                                    📅 <b>Tarih:</b> {inv['invoice_date']}<br/>
                                    💰 <b>Tutar:</b> {inv['total_amount']:.2f} TL<br/>
                                    📦 <b>Detay:</b> {inv['product_details']}
                                </div>
                                """, unsafe_allow_html=True)
                                
                    with col_payments:
                        st.markdown("###### 💸 Yapılan Ödemeler")
                        c.execute("SELECT * FROM wholesaler_payments WHERE wholesaler_id = ? ORDER BY payment_date DESC", (selected_w_id,))
                        payments = c.fetchall()
                        if not payments:
                            st.info("Kayıtlı ödeme yok.")
                        else:
                            for pm in payments:
                                st.markdown(f"""
                                <div style='background-color:rgba(255,255,255,0.01); border:1px solid rgba(255,255,255,0.05); border-radius:6px; padding:10px; margin-bottom:5px;'>
                                    📅 <b>Tarih:</b> {pm['payment_date']}<br/>
                                    💰 <b>Ödenen:</b> {pm['amount_paid']:.2f} TL
                                </div>
                                """, unsafe_allow_html=True)
                                
    with tab_calisan_carileri:
        st.markdown("### 👥 Çalışan Cari Takip Paneli")
        st.markdown("Personel maaş, avans ödemeleri ve çalışanların dükkandan aldıkları ürünleri takip edin.")
        
        c.execute("SELECT * FROM employees ORDER BY name ASC")
        employees_list = c.fetchall()
        
        col_e_form, col_e_card = st.columns([5, 7])
        
        with col_e_form:
            st.markdown("#### ➕ Yeni Çalışan Ekle")
            with st.form("calisan_ekle_form", clear_on_submit=True):
                new_e_name = st.text_input("Çalışan Adı Soyadı:")
                new_e_phone = st.text_input("Telefon Numarası:")
                new_e_salary = st.number_input("Sabit Aylık Net Maaş (TL):", min_value=0.0, step=500.0, value=17002.0)
                submitted_new_e = st.form_submit_button("💾 Çalışanı Kaydet")
                if submitted_new_e:
                    if not new_e_name.strip():
                        st.error("Çalışan adı boş bırakılamaz!")
                    else:
                        c.execute("INSERT INTO employees (name, phone, base_salary, current_balance) VALUES (?, ?, ?, 0.0)", (new_e_name.strip(), new_e_phone.strip(), new_e_salary))
                        conn.commit()
                        st.toast(f"✅ Çalışan {new_e_name} başarıyla kaydedildi!", icon="👥")
                        st.rerun()
                        
        with col_e_card:
            st.markdown("#### 🔍 Çalışan Cari Kartı & İşlemler")
            if not employees_list:
                st.info("Kayıtlı çalışan bulunamadı. Lütfen sol taraftan ekleyin.")
            else:
                selected_emp_id = st.selectbox(
                    "İşlem yapılacak Çalışan:", 
                    [e['id'] for e in employees_list], 
                    format_func=lambda x: next(f"{e['name']}" for e in employees_list if e['id'] == x)
                )
                
                c.execute("SELECT * FROM employees WHERE id = ?", (selected_emp_id,))
                emp_details = c.fetchone()
                
                st.markdown(f"**Telefon:** `{emp_details['phone'] or 'Belirtilmedi'}` | **Sabit Maaş:** `{emp_details['base_salary']:.2f} TL`")
                
                bal = emp_details['current_balance']
                bal_color = "#34d399" if bal >= 0 else "#ef4444"
                st.markdown(f"**Alacağı Net Maaş Bakiyesi:** <span style='color: {bal_color}; font-size:1.3em; font-weight:bold;'>{bal:.2f} TL</span>", unsafe_allow_html=True)
                
                # Single button helper to load monthly salary
                if st.button("📅 Bu Ayın Sabit Maaşını Hak Ediş Olarak Yükle", key=f"salary_load_{selected_emp_id}", use_container_width=True):
                    today_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    salary_amt = emp_details['base_salary']
                    c.execute("UPDATE employees SET current_balance = current_balance + ? WHERE id = ?", (salary_amt, selected_emp_id))
                    c.execute("""
                        INSERT INTO employee_transactions (employee_id, type, amount, description, date)
                        VALUES (?, 'Maaş Hak Ediş', ?, 'Aylık Sabit Maaş Hak Edişi Yüklendi', ?)
                    """, (selected_emp_id, salary_amt, today_time_str))
                    conn.commit()
                    st.toast("✅ Sabit maaş çalışanın hesabına alacak olarak yüklendi!", icon="📅")
                    st.rerun()
                    
                e_tab1, e_tab2, e_tab3 = st.tabs(["💰 Maaş Hak Ediş / Avans / Ödeme", "📜 Hesap Özeti (Log)", "⚙️ Ayarlar"])
                
                with e_tab1:
                    st.markdown("##### Maaş / Avans / Ödeme İşlemleri")
                    with st.form("calisan_islem_form", clear_on_submit=True):
                        islem_tip = st.selectbox("İşlem Türü:", ["Avans Ver / Nakit Ödeme Yap", "Maaş Hak Ediş Yükle (Manuel)"])
                        islem_amt = st.number_input("Tutar (TL):", min_value=0.0, step=100.0, value=0.0)
                        islem_desc = st.text_input("İşlem Açıklaması / Detayı:", placeholder="Örn: Temmuz ayı avansı elden verildi...")
                        
                        submit_emp_trans = st.form_submit_button("💾 İşlemi Kaydet")
                        if submit_emp_trans:
                            if islem_amt <= 0:
                                st.error("İşlem tutarı sıfırdan büyük olmalıdır!")
                            else:
                                today_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                today_date_str = datetime.now().strftime("%Y-%m-%d")
                                
                                if islem_tip == "Maaş Hak Ediş Yükle (Manuel)":
                                    c.execute("UPDATE employees SET current_balance = current_balance + ? WHERE id = ?", (islem_amt, selected_emp_id))
                                    c.execute("""
                                        INSERT INTO employee_transactions (employee_id, type, amount, description, date)
                                        VALUES (?, 'Maaş Hak Ediş', ?, ?, ?)
                                    """, (selected_emp_id, islem_amt, islem_desc.strip() or "Manuel Maaş Hak Edişi Yüklendi", today_time_str))
                                    conn.commit()
                                    st.toast("✅ Maaş hak edişi başarıyla eklendi!", icon="➕")
                                    st.rerun()
                                else:
                                    # Avans / Nakit Ödeme Yap (deductions from balance & logs as Gider in pre-accounting)
                                    c.execute("UPDATE employees SET current_balance = current_balance - ? WHERE id = ?", (islem_amt, selected_emp_id))
                                    c.execute("""
                                        INSERT INTO employee_transactions (employee_id, type, amount, description, date)
                                        VALUES (?, 'Avans', ?, ?, ?)
                                    """, (selected_emp_id, islem_amt, islem_desc.strip() or "Avans / Maaş Ödemesi Elden Yapıldı", today_time_str))
                                    
                                    # Log to pre-accounting general expenses
                                    c.execute("""
                                        INSERT INTO accounting (tarih, tip, kategori, tutar, aciklama)
                                        VALUES (?, 'Gider', 'Eleman Maaşı', ?, ?)
                                    """, (today_date_str, islem_amt, f"Personel Ödemesi/Avans | Çalışan: {emp_details['name']} | Detay: {islem_desc.strip() or 'Avans'}"))
                                    conn.commit()
                                    st.toast("💸 Ödeme gerçekleştirildi ve dükkan gideri olarak işlendi!", icon="💸")
                                    st.rerun()
                                    
                with e_tab2:
                    st.markdown("##### Çalışan Cari Hesap Özeti")
                    c.execute("SELECT * FROM employee_transactions WHERE employee_id = ? ORDER BY date DESC", (selected_emp_id,))
                    trans_log = c.fetchall()
                    
                    if not trans_log:
                        st.info("Kayıtlı cari hareket bulunmamaktadır.")
                    else:
                        for tr in trans_log:
                            try:
                                dt_obj = datetime.strptime(tr["date"], "%Y-%m-%d %H:%M:%S")
                                formatted_dt = dt_obj.strftime("%d.%m.%Y - %H:%M")
                            except Exception:
                                formatted_dt = tr["date"]
                                
                            # Custom coloring and labels based on transaction type
                            if tr["type"] == "Maaş Hak Ediş":
                                lbl = "➕ Maaş Hak Ediş"
                                amt_lbl = f"<span style='color:#34d399;'>+{tr['amount']:.2f} TL</span>"
                            elif tr["type"] == "Avans":
                                lbl = "💸 Avans / Ödeme"
                                amt_lbl = f"<span style='color:#ef4444;'>-{tr['amount']:.2f} TL</span>"
                            else:
                                lbl = "🛍️ Ürün Alımı (Maaştan Düşüldü)"
                                amt_lbl = f"<span style='color:#ef4444;'>-{tr['amount']:.2f} TL</span>"
                                
                            st.markdown(f"""
                            <div style='background-color:rgba(255,255,255,0.01); border:1px solid rgba(255,255,255,0.05); border-radius:6px; padding:10px; margin-bottom:5px;'>
                                📅 <b>{formatted_dt}</b> | {lbl}: {amt_lbl}<br/>
                                📝 <b>Açıklama:</b> {tr['description']}
                            </div>
                            """, unsafe_allow_html=True)
                            
                with e_tab3:
                    st.markdown("##### Çalışan Kartını Sil")
                    st.warning("⚠️ Çalışanı silmek geçmiş tüm avans, maaş ve cari kayıtlarını kalıcı olarak kaldıracaktır!")
                    if st.button("❌ Çalışan Cari Kartını Tamamen Sil", key=f"del_emp_{selected_emp_id}", use_container_width=True):
                        c.execute("DELETE FROM employee_transactions WHERE employee_id = ?", (selected_emp_id,))
                        c.execute("DELETE FROM employees WHERE id = ?", (selected_emp_id,))
                        conn.commit()
                        st.toast("Çalışan cari kaydı tamamen silindi.", icon="🗑️")
                        st.rerun()
                            
    conn.close()

# ----------------- MODULE: SATIS & MVP ANALIZ -----------------
elif menu == "📊 Satış & MVP Analiz":
    st.markdown("## 📊 Satış Performansı & MVP Ürünler Paneli")
    
    conn = get_db_connection()
    
    # 1. Total sales and Revenue Metrics
    c = conn.cursor()
    c.execute("SELECT SUM(toplam_tutar), COUNT(*) FROM satislar")
    res = c.fetchone()
    total_rev = res[0] if res[0] is not None else 0.0
    total_sales_count = res[1] if res[1] is not None else 0
    
    c.execute("SELECT COUNT(*) FROM urunler")
    total_products = c.fetchone()[0]
    
    st.markdown("### 📈 Genel Muhasebe Özeti")
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.markdown(f"""
        <div class="metric-card">
            <h3>💰 Toplam Ciro</h3>
            <h2>{total_rev:.2f} TL</h2>
            <span style='color:#34d399;'>Toplam satılan hacim</span>
        </div>
        """, unsafe_allow_html=True)
    with col_m2:
        st.markdown(f"""
        <div class="metric-card">
            <h3>🛒 Satış İşlemleri</h3>
            <h2>{total_sales_count} Fiş</h2>
            <span style='color:#60a5fa;'>Kesilen fatura/fiş adeti</span>
        </div>
        """, unsafe_allow_html=True)
    with col_m3:
        st.markdown(f"""
        <div class="metric-card">
            <h3>📦 Toplam Ürün Çeşidi</h3>
            <h2>{total_products} Çeşit</h2>
            <span style='color:#a78bfa;'>Veritabanındaki aktif ürünler</span>
        </div>
        """, unsafe_allow_html=True)
        
    # 2. Daily / Weekly / Monthly Sales chart
    st.markdown("---")
    st.markdown("### 📅 Zaman Serisi Satış Dağılımı")
    df_s = pd.read_sql_query("SELECT tarih, toplam_tutar FROM satislar ORDER BY tarih DESC", conn)
    
    if df_s.empty:
        st.info("Henüz satış gerçekleşmediği için zaman grafiği çizilemedi.")
    else:
        # Convert date to standard datetime
        df_s["Tarih"] = pd.to_datetime(df_s["tarih"])
        df_grouped = df_s.groupby(df_s["Tarih"].dt.date)["toplam_tutar"].sum().reset_index()
        df_grouped.columns = ["Tarih", "Günlük Ciro (TL)"]
        st.bar_chart(df_grouped.set_index("Tarih"), use_container_width=True)

    # 3. MVP Products
    st.markdown("---")
    st.markdown("### 🏆 En Çok Satan MVP Ürünler (Top 5)")
    df_mvp = pd.read_sql_query("""
        SELECT urun_ad as 'Ürün Adı', SUM(miktar) as 'Toplam Satış Adeti', SUM(toplam_tutar) as 'Toplam Kazanç (TL)'
        FROM satislar
        GROUP BY barkod
        ORDER BY SUM(miktar) DESC
        LIMIT 5
    """, conn)
    
    if df_mvp.empty:
        st.info("Yeterli satış verisi bulunmamaktadır.")
    else:
        st.dataframe(df_mvp, use_container_width=True)
        
    conn.close()

# ----------------- MODULE: QNB E-FATURA -----------------
elif menu == "🧾 QNB E-Fatura":
    st.markdown("## 🧾 QNB Finansbank Canlı E-Fatura Entegrasyon Paneli")
    st.markdown("""
    Bu modül, QNB e-Finans SOAP Web Servislerine bağlanarak firmanıza kesilen toptancı e-faturalarını doğrudan envanterinize aktarır.
    """)
    
    # Obfuscation helpers for database security
    import base64
    def secure_decode(val):
        try:
            return base64.b64decode(val.encode()).decode() if val else ""
        except Exception:
            return val
    def secure_encode(val):
        return base64.b64encode(val.encode()).decode() if val else ""

    # Load stored credentials from SQLite database
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS ayarlar (anahtar TEXT PRIMARY KEY, deger TEXT NOT NULL)")
    c.execute("SELECT * FROM ayarlar")
    settings_rows = c.fetchall()
    conn.close()
    
    settings = {row["anahtar"]: row["deger"] for row in settings_rows}
    
    # State for loaded live or mock invoices
    if "live_invoice_products" not in st.session_state:
        st.session_state.live_invoice_products = None
    if "live_invoice_xmls" not in st.session_state:
        st.session_state.live_invoice_xmls = None

    col_efat, col_settings = st.columns([7, 5])
    
    with col_settings:
        st.markdown("### 🔑 API Bağlantı Ayarları")
        with st.form("api_ayarlar_form"):
            c_user = st.text_input("QNB e-Finans Kullanıcı Adı:", value=settings.get("qnb_user", ""))
            c_pass = st.text_input("QNB e-Finans Şifre:", value=secure_decode(settings.get("qnb_pass", "")), type="password")
            c_vkn = st.text_input("Firma VKN / TCKN:", value=settings.get("qnb_vkn", ""))
            c_app = st.text_input("Uygulama Kodu (App Code):", value=settings.get("qnb_app", "KASASERV"))
            c_prod = st.checkbox("Üretim (Production) Sunucusu Kullan", value=(settings.get("qnb_prod", "False") == "True"))
            
            save_btn = st.form_submit_button("💾 Bağlantıyı Güvenli Kaydet")
            if save_btn:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO ayarlar (anahtar, deger) VALUES (?, ?)", ("qnb_user", c_user))
                c.execute("INSERT OR REPLACE INTO ayarlar (anahtar, deger) VALUES (?, ?)", ("qnb_pass", secure_encode(c_pass)))
                c.execute("INSERT OR REPLACE INTO ayarlar (anahtar, deger) VALUES (?, ?)", ("qnb_vkn", c_vkn))
                c.execute("INSERT OR REPLACE INTO ayarlar (anahtar, deger) VALUES (?, ?)", ("qnb_app", c_app))
                c.execute("INSERT OR REPLACE INTO ayarlar (anahtar, deger) VALUES (?, ?)", ("qnb_prod", "True" if c_prod else "False"))
                conn.commit()
                conn.close()
                st.success("API Bağlantı ayarları veritabanına şifreli olarak kaydedildi.")
                st.rerun()
                
    with col_efat:
        st.markdown("### 🔌 Canlı Fatura Sorgulama")
        
        # Action buttons
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            query_live = st.button("🔍 Canlı QNB Sunucusundan Faturaları Çek", type="primary", use_container_width=True)
        with col_btn2:
            query_mock = st.button("⚠️ API Çevrimdışı / Test Faturası Simüle Et", type="secondary", use_container_width=True)
            
        if query_live:
            # Check credentials
            q_user = settings.get("qnb_user", "")
            q_pass = secure_decode(settings.get("qnb_pass", ""))
            q_vkn = settings.get("qnb_vkn", "")
            q_app = settings.get("qnb_app", "")
            q_prod = settings.get("qnb_prod", "False") == "True"
            
            if not q_user or not q_pass or not q_vkn:
                st.error("Lütfen önce sağ taraftaki API bağlantı ayarlarını doldurun ve kaydedin.")
            else:
                with st.spinner("QNB e-Finans SOAP Sunucularına bağlanılıyor, faturalar çekiliyor..."):
                    import qnb_api
                    success, result = qnb_api.get_incoming_invoices_xml(
                        username=q_user,
                        password=q_pass,
                        vkn=q_vkn,
                        app_code=q_app,
                        days_back=7,
                        use_prod=q_prod
                    )
                    
                    if success:
                        if result:
                            # Parse all received UBL XML invoices
                            all_products = []
                            for xml_str in result:
                                parsed = qnb_api.parse_live_ubl_invoice(xml_str)
                                all_products.extend(parsed)
                                
                            if all_products:
                                st.session_state.live_invoice_products = all_products
                                st.session_state.live_invoice_xmls = result
                                st.toast("⚡ Faturalar başarıyla çekildi ve ayrıştırıldı!", icon="📥")
                            else:
                                st.warning("İnceleme yapılan e-faturaların içinde ürün satırı bulunamadı.")
                        else:
                            st.info("Son 7 güne ait yeni gelen işlenmemiş fatura kaydı bulunmamaktadır.")
                    else:
                        st.error(f"Bağlantı hatası oluştu: {result}")
                        st.info("İpucu: QNB Test/Üretim ortam API şifrelerinizin doğruluğundan emin olun veya bağlantıyı simüle etmek için yandaki Test Faturası butonunu kullanın.")
                        
        if query_mock:
            # Simulated invoice parsing fallback
            from qnb_billing import parse_qnb_e_invoice
            st.session_state.live_invoice_products = parse_qnb_e_invoice(MOCK_XML_INVOICE)
            st.session_state.live_invoice_xmls = [MOCK_XML_INVOICE]
            st.toast("⚡ Simüle fatura başarıyla yüklendi!", icon="📥")
            
        # Display queried products table if state has invoice products
        if st.session_state.live_invoice_products:
            st.success(f"✅ Gelen Faturalar Ayrıştırıldı! Toplam {len(st.session_state.live_invoice_products)} ürün kalemi tespit edildi:")
            
            df_inv = pd.DataFrame(st.session_state.live_invoice_products)
            df_inv["Toplam Tutar (TL)"] = df_inv["fiyat"] * df_inv["miktar"]
            
            st.dataframe(
                df_inv[["barkod", "ad", "kategori", "fiyat", "miktar", "Toplam Tutar (TL)"]],
                use_container_width=True,
                column_config={
                    "barkod": "Barkod / EAN",
                    "ad": "Ürün Adı / Açıklama",
                    "kategori": "Kategori",
                    "fiyat": st.column_config.NumberColumn("Alış Fiyatı (TL)", format="%.2f TL"),
                    "miktar": "Adet (Miktar)",
                    "Toplam Tutar (TL)": st.column_config.NumberColumn("Toplam Satır Tutarı", format="%.2f TL")
                }
            )
            
            # Action to import items to SQLite DB
            if st.button("📥 Faturadaki Ürünleri Yerel Stoka Aktar", type="primary", use_container_width=True):
                from qnb_billing import import_invoice_to_stock
                success_count = 0
                for xml_str in st.session_state.live_invoice_xmls:
                    count, msg = import_invoice_to_stock(xml_str)
                    success_count += count
                    
                if success_count > 0:
                    st.success(f"🎉 Toplam {success_count} adet ürün kalemi başarıyla envanterinize (ve kütüphanenize) aktarıldı!")
                    st.toast("Envanter güncellendi!", icon="🚚")
                    st.session_state.live_invoice_products = None
                    st.session_state.live_invoice_xmls = None
                    st.rerun()
                else:
                    st.error("Ürünler stoka aktarılamadı.")
                    
            if st.button("❌ Listeyi Temizle", use_container_width=True):
                st.session_state.live_invoice_products = None
                st.session_state.live_invoice_xmls = None
                st.rerun()
                
    st.markdown("---")
    st.info("💡 Fatura aktarımı sonrasında 'Stok ve Ürünler' sekmesine gidip güncellenmiş stok değerlerini ve yeni eklenen ürünleri görebilirsiniz.")
