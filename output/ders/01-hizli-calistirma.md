# Derste çalıştırma: önce bunu yap

14 Ekim 2026 için, bu bilgisayarda kontrol edildi. Mevcut `.venv` kaldırılmış bir Windows Store Python kurulumuna bağlıydı; `pyvenv.cfg` mevcut Anaconda Python 3.12 yoluna bağlandı. Paketler korunarak CLI ve dashboard doğrulandı.

## 1. En hızlı gösterim: mevcut gerçek çıktılar

PowerShell aç ve çalıştır:

```powershell
cd C:\Projeler\sentinel-crop-pipeline
.\.venv\Scripts\python.exe -m streamlit run src/sentinel_crop_pipeline/dashboard/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

Tarayıcı: http://127.0.0.1:8501

Sunucu zaten açıksa aynı adrese git; ikinci kez başlatmana gerek yok. Kapatmak için sunucunun terminalinde Ctrl+C. Port doluysa komutta 8502 kullan ve tarayıcıda da 8502 aç.

Aktivasyon ve PowerShell execution policy ayarı gerekmiyor. `output/ders/demo-baslat.bat` dosyasına çift tıklamak da aynı işi yapar.

### 3 dakikalık demo sırası

1. **Patch browser:** 2025-06-02 tarihli ilk sahneyi seç. Bir yamayı göster: “Büyük uydu görüntüsünü modelin işleyebileceği 256×256 parçalar haline getiriyorum.” RGB, insanın görebildiği renkli gösterimdir; model girdisi altı kanallıdır.
2. **Split map:** “Aynı coğrafi blok farklı tarihlerde de aynı grupta tutuluyor; böylece modelin testte daha önce gördüğü konumu ezberlemesini azaltıyorum.” Mavi eğitim, turuncu doğrulama, kırmızı test. Ayrı blokların sınırları yine komşu olabilir; sıfır sızıntı garantisi verme.
3. **Scene table:** “Sahnenin genel bulut yüzdesi yetmiyor; çalışma alanındaki geçersiz pikselleri ayrıca kontrol ediyorum.” Turuncu `needs_manual_review`, reddedilme değildir: otomatik kuralları geçen fakat ek görsel inceleme bekleyen sahnedir.
4. **Run history:** “Her aşamanın ne yaptığını kaydediyorum; aynı yöntemi tekrar çalıştırabilir ve kararları denetleyebilirim.” Etiketleme geçmişindeki uyarı kayıtları başarılı yer gerçeği üretimi değildir.

**Kontrol edilen gerçek veriler:** 9 Haziran 2025 sahnesi; 990 yama; 648 eğitim / 180 doğrulama / 162 test; 9 mekânsal blok. 990 TIFF ve 990 NPY dosyasının tamamı mevcut. Bir NPY şekli `(6,256,256)`; bantlar B02, B03, B04, B08, NDVI, MASK. Bu sayılar model doğruluğu değildir.

## 2. İnternetsiz yedek

`sunum.html` dosyasını çift tıklayarak aç. Gerçek RGB ve NDVI görselleri dosyanın içine gömülü. Sağ/sol okla ilerle, N ile konuşmacı notlarını aç, tarayıcıda F11 ile tam ekran yap. Bu, canlı Streamlit arayüzüne erişemediğin durumda aynı hikâyeyi gösterecek yedektir.

## 3. Terminalde komutların çalıştığını göster

```powershell
.\.venv\Scripts\python.exe -m sentinel_crop_pipeline.cli --help
```

“Beş ayrı aşama var: keşfet, indir, ön işle, parçalara ayır, etiketle.”

Mevcut veriyi göstermek için yeniden indirme gerekmiyor. Bugün derste `run-all` başlatmak yerine önceden üretilmiş çıktıları kullan: Haziran denemesinde sıkıştırılmış indirme yaklaşık 480 MB idi.

## 4. Gerçek veriyi yeniden üretmek istersen

Bu bölüm ders öncesi hazırlık içindir; internet ve CDSE OAuth bilgileri gerekir. Anahtarları `.env` içinde tut; sınıfa bu dosyayı yansıtma. Mevcut `.env` içeriği bu hazırlık sırasında okunmadı.

```powershell
cd C:\Projeler\sentinel-crop-pipeline
.\.venv\Scripts\python.exe -m sentinel_crop_pipeline.cli discover --config config/urla_june_subset.yaml
.\.venv\Scripts\python.exe -m sentinel_crop_pipeline.cli download --config config/urla_june_subset.yaml --yes
.\.venv\Scripts\python.exe -m sentinel_crop_pipeline.cli preprocess --config config/urla_june_subset.yaml
.\.venv\Scripts\python.exe -m sentinel_crop_pipeline.cli patch --config config/urla_june_subset.yaml
```

Her komut başarıyla bitince sonrakine geç. Alternatif tek komut:

```powershell
.\.venv\Scripts\python.exe -m sentinel_crop_pipeline.cli run-all --config config/urla_june_subset.yaml --yes
```

`run-all` etiketlemeyi içermez. Yeniden keşif katalog ve seçim kayıtlarını, yeniden yama üretimi indeks dosyasını günceller. Mevcut ders çıktısını korumak istiyorsan farklı çıktı dizinleriyle ayrı bir çalışma kopyası kullan.

`--skip-scl` yalnızca piksel bazlı SCL kontrolünü atlar; keşfin STAC araması internet istemeye devam eder. İnternetsiz keşif komutu değildir.

## 5. Yer gerçeği ve eğitim

Gerçek ürün parselleri `data/labels/parcels.geojson` olarak hazırlanmalı; `crop_type` özelliği, görüntüyle uyumlu sezon ve doğru koordinat sistemi kontrol edilmeli. Ardından:

```powershell
.\.venv\Scripts\python.exe -m sentinel_crop_pipeline.cli label --config config/urla_june_subset.yaml
```

`examples/sample_parcels.geojson` sentetiktir; yalnızca etiketleme mekanizmasını denemek içindir. Gerçek domates/mısır/bağ doğrulaması olarak sunulmaz. Bugün gerçek yer gerçeği maskeleri mevcut çıktılarda yok.

**Bu depoda model eğitimi/inference komutu yok.** U-Net eğitimini bu veri çiftlerini tüketen ayrı bir eğitim çalışmasıyla yapmak gerekir. F1/IoU ve nihai ürün haritası bugünkü demo çıktıları değildir.

## 6. Başka bilgisayarda ilk kurulum

Python 3.10+ kurulu olmalı. PowerShell:

```powershell
git clone https://github.com/muend/sentinel-crop-pipeline.git
cd sentinel-crop-pipeline
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dashboard]"
```

GitHub klonu büyük `data/raw`, `data/interim`, `data/patches` çıktılarını getirmez. Dashboard boşsa veri yeniden üretilmeli veya mevcut çalışma çıktıları o bilgisayara taşınmalıdır. `sunum.html` tek başına taşınabilir.

## Sık sorunlar

| Sorun | Hızlı çözüm |
|---|---|
| `No Python at ...` | Sanal ortamın temel Python yolu değişmiştir. Bugünkü makinede düzeltildi; başka makinede yeni venv kur. |
| Streamlit bulunamıyor | `.venv` Python’u ile `-m pip install -e ".[dashboard]"` çalıştır. |
| Etiket görünmüyor | Gerçek parsel verisi ve başarılı `label` aşaması henüz yok; bugün beklenen durum. |
| NDRE uyarısı | B05 indirilmediği için hesaplanmıyor. B05 eklemek yeni indirilecek veri için geçerli; eski TIFF’ye bant eklemez. |
| Harita açılmıyor / ekran sorunlu | Yerel HTML sunumunda RGB/NDVI görsellerini göster. |

Doğrulama: CLI yardım komutu başarılı; Streamlit uygulama testi sıfır exception; beş sekme mevcut; yerel sunucu 8501’de açıldı. Bu oturumda yeni CDSE indirmesi veya model eğitimi yapılmadı.
