import sys
from scraper import scrape_barcode_online

def run_test(barcode):
    print("=" * 60)
    print(f"🔍 BARKOD TEST SORGUSU BAŞLATILDI: {barcode}")
    print("=" * 60)
    
    result = scrape_barcode_online(barcode)
    
    print("-" * 60)
    if result:
        print("🎉 SORGUNUN DÖNDÜRDÜĞÜ ÜRÜN BİLGİLERİ:")
        print(f"👉 Ürün Adı : {result['ad']}")
        print(f"👉 Kategori : {result['kategori']}")
        print(f"👉 Fiyat    : {result['fiyat']} TL")
        print(f"👉 Görsel   : {result['gorsel_url']}")
    else:
        print("❌ HATA: Ürün hiçbir kaynakta bulunamadı!")
    print("=" * 60)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        barcode = sys.argv[1].strip()
        run_test(barcode)
    else:
        print("ℹ️ Test etmek istediğiniz barkodu girin (veya çıkmak için 'q' yazın):")
        while True:
            try:
                barcode_input = input("Barkod > ").strip()
                if not barcode_input:
                    continue
                if barcode_input.lower() == 'q':
                    print("Test sonlandırıldı.")
                    break
                run_test(barcode_input)
                print()
            except (KeyboardInterrupt, EOFError):
                print("\nTest sonlandırıldı.")
                break
