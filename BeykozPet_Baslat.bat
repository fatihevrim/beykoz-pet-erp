@echo off
title Beykoz Pet AI ERP & POS Baslatici
echo ==========================================================
echo Beykoz Pet AI ERP and POS Sistemi Baslatiliyor...
echo ==========================================================
echo.

rem Navigate to the project directory
cd /d "C:\Users\fatih\.gemini\antigravity\scratch\beykoz_pet"

rem Start main Streamlit server on default port 8501
echo [1/2] Streamlit POS sunucusu (Port 8501) arka planda baslatiliyor...
start /b python -m streamlit run app.py --server.port 8501 --server.headless true

rem Wait for servers to boot up
echo [2/2] Sunucunun hazir olmasi bekleniyor (3 saniye)...
timeout /t 3 /nobreak >nul

rem Open default web browser pointing to POS app
echo Tarayici aciliyor: http://localhost:8501
start http://localhost:8501

echo.
echo ==========================================================
echo Beykoz Pet ERP and POS basariyla acildi!
echo.
echo Bilgisayardan kullanim: http://localhost:8501
echo.
echo Kapatmak icin bu pencereyi kapatabilirsiniz.
echo ==========================================================
echo.
pause
