# Konuşma kartları ve proje incelemesi

## Önce ana mesaj

“Urla’da hangi tarımsal ürünün nerede yetiştiğini güncel uydu verisiyle haritalamak istiyorum. Bunun için önce güvenilir veri hazırlamak, ardından sahada doğrulanmış etiketlerle bir model eğitmek gerekiyor. Bugün veri hazırlama aşamasının çalışan çıktısını göstereceğim.”

İki PDF aynı projenin belgeleri: biri 2025/1 başvuru kaydı, diğeri 7 sayfalık araştırma önerisi. Kabul bilgisi senin beyanına dayanıyor; dosyalar bir kabul karar yazısı değil. Sınıfa gösterilecek malzemelere başvuru formundaki kimlik, adres, telefon ve banka bilgileri alınmadı.

## 15 dakikalık akış: her kartta tek fikir

### 0:00–1:00 | Sorun
Söyle: “Planlama için yalnızca tarım alanının nerede olduğunu bilmek yetmiyor. O alanlarda hangi ürünlerin yetiştiğini de bilmek gerekiyor.”
Bağla: Ürün deseni, arazi kullanımını ve tarımsal planlamayı yorumlamaya yardımcı olabilir. Haritadan tek başına verim, fiyat veya arz fazlası çıkarmıyoruz.

### 1:00–2:00 | Araştırma sorusu
Söyle: “Sentinel-2 verileri ve sahada doğrulanmış ürün etiketleriyle Urla’daki ürün türlerini ne kadar güvenilir ayırt edebiliriz?”
Amaç 1: ürün desenini haritalamak. Amaç 2: yöntemi tekrar kullanılabilir şekilde ortaya koymak. İlçenin tamamını her ayrıntısıyla tanımak yerine ilk etapta veri bulunan pilot parsellerle başlamak daha gerçekçi.

### 2:00–4:00 | Yöntem
Söyle: “Uyduyu birden fazla kanalla ölçüm yapan bir kamera gibi düşünebilirsiniz. Görünen renklerin yanında bitkiyi ayırt etmeye yardımcı yakın kızılötesi bilgisi de var.”
Adımlar: görüntü seçimi → bulut/gölge maskeleme → bantlar ve NDVI → yama üretimi → yer gerçeği → model → bağımsız test.
CNN çevredeki örüntülerden özellik öğrenir. U-Net, CNN tabanlı bir segmentasyon mimarisidir; her piksele sınıf atamayı hedefler. “CNN ile U-Net iki bağımsız rakip yöntem” diye anlatma.

### 4:00–7:00 | Canlı demo
Hızlı çalıştırma rehberindeki dört ekranı göster. Ekranda ilk olarak görüntüyü aç; kodu ve dosya ağacını sona bırak. Bir çıktı gösterirken sırayla şunları söyle: “Bu nedir? Nasıl üretildi? Araştırmada ne işe yarar?”
Kısa rakamlar: 9 sahne → 990 yama → 648/180/162 ayrımı. “990 bağımsız tarla” deme; aynı coğrafi konumun farklı tarihlerdeki görüntüleri de bu sayının içinde.

### 7:00–9:00 | Bugün ulaşılan aşama
Söyle: “Veri hazırlama hattı gerçek uydu verisiyle çalışıyor. Ürünleri doğru tanıdığını söylemek için gerçek parsel etiketleriyle eğitim ve bağımsız değerlendirme yapmam gerekiyor.”
Arazi maskesi ile ürün etiketi farklıdır: MASK geçerli/geçersiz pikseli gösterir, domates/mısır/bağ sınıfını göstermez. NDVI bitki örtüsüyle ilişkili bir indeks; tek başına ürün adı vermez.

### 9:00–13:00 | Arkadaşlara başvuru dersi
Söyle: “Benim örneğimden alınacak şey başlığı kopyalamak değil; sorunu, veriyi, yöntemi, ölçümü ve B planını birbirine bağlamak.”
Beş kısa yönlendirme: dar bir soru seç; veriye erişimi erkenden dene; danışmanınla yöntemi sınırla; başarıyı ölç; riskin hangi iş paketini etkilediğini yaz.
Güncel başvuru süreci ve çalışma kâğıdı ayrı rehberde.

### 13:00–15:00 | Kapanış ve soru
Söyle: “Bu projenin bana öğrettiği şey, iyi bir modelin güvenilir veri ve doğru test tasarımı gerektirdiği. Bir proje fikrini başvuruya dönüştürürken önce hangi soruyu hangi veriyle cevaplayacağınızı netleştirin.”
Sınıfa etkinlik: “Sizin alanınızda ölçmek istediğiniz bir sorunu bir cümleyle yazın. Sonra verinizin nereden geleceğini ekleyin.”

## Yalnızca 5 dakika varsa

1. 40 sn sorun ve soru.
2. 40 sn uydu → veri → model zinciri.
3. 2 dk RGB ve split ekranı.
4. 40 sn tamamlanan veri hazırlığı / gelecek eğitim ayrımı.
5. 1 dk başvuru için soru + veri + ölçüm + B planı.

## Belgelerdeki proje tasarımı

| Boyut | Belgede önerilen | Bugünkü somut karşılık |
|---|---|---|
| Bölge | Urla; veri sorunu halinde diğer İzmir ovaları | Geçici dikdörtgen Urla AOI; resmi ilçe sınırı değil |
| Veri | Ekim–hasat Sentinel-2 L2A, B2/B3/B4/B8 | Haziran 2025 için 9 sahne; veri hattı mevcut |
| Yer gerçeği | GPS/saha ürün etiketleri; izinli ÇKS alternatif kaynak | Gerçek ürün etiketleri demo indeksinde yok |
| Eğitim | Python/Keras, GPU, CNN/U-Net | Bu repo eğitime girdi hazırlar; eğitim kodu içermez |
| Bölme | %70 / %15 / %15 | Blok bütünlüğü nedeniyle %65,5 / %18,2 / %16,4 |
| Ölçüm | Hata matrisi, F1, IoU | Henüz bu demo için ölçülmüş model skoru yok |
| Bütçe | Başvuruda önerilen toplam 9.000 TL | 1.000 TL ulaşım, 8.000 TL hizmet; onaylanan ödeme diye sunma |
| Süre | 12 aylık plan | Ay 1–2 veri; 3–5 etiket; 6–9 eğitim; 10–11 test/harita; 12 rapor |

## Güçlü yanlar: kabul nedenini bildiğimiz iddiası olmadan

- Şehir ve bölge planlama sorununu veri bilimiyle ilişkilendiriyor.
- Pilot alanı ve veri kaynağı belli; dört ana yöntem aşaması var.
- Etiketli yer gerçeği veri setini ayrı bir araştırma çıktısı sayıyor.
- Bulut, saha erişimi ve veri eksikliği için alternatifler düşünüyor.
- Kod paylaşımı ve tekrar üretilebilirlik hedefi somut bir depoya dönüşmüş.

Bunlar metinden görülen güçlü yönlerdir. Panel geri bildirimi olmadığı için “şu sebeple kabul edildi” diye kesin konuşulamaz.

## Derste dürüstçe anlatabileceğin geliştirme alanları

1. **Karşılaştırma gerekli:** öneri CNN/U-Net üstünlüğünü yer yer kesin ifade ediyor. Bunu araştırılacak hipotez olarak anlat. Aynı veri/split üzerinde Random Forest gibi bir temel yöntemle karşılaştırmadan üstünlük kanıtlanmaz.
2. **10 m çözünürlük sınırı:** her piksel yaklaşık 10×10 m alan temsil eder. Dar seralar, küçük parseller ve birbirine benzer ürünler karışabilir. 20 m bantları 10 m’ye yeniden örneklemek gerçek mekânsal ayrıntıyı artırmaz.
3. **Başarı ölçütü:** “yüksek doğruluk” sayısal değil. Danışmanla sınıf bazlı F1, macro-F1, IoU, örnek sayısı ve temel yöntem karşılaştırması belirlenmeli. Ölçülmemiş bir eşik veya puanı sonuç gibi verme.
4. **Etiket ile sezon uyumu:** 2025 görüntüsüne bugün gözlenen ürünü doğrudan etiketleme; aynı parselde ürün değişmiş olabilir. Güvenilir 2025 kayıtları veya görüntüyle eşzamanlı saha verisi gerekir.
5. **Mekânsal ayrım:** blok bazlı ayrım iyi bir önlem; sınırdan geçen parseller ve komşu bloklar için ek parsel gruplama/buffer değerlendirmesi gerekebilir. Farklı tarihlerde aynı konum train ve testte karışmamalı.
6. **Zaman serisi B planı:** repo tarihler boyunca uyumlu gridler üretir; CNN/RNN veya zaman serisi modeli eğitmiyor. Fenoloji modeli, eksik veri stratejisi ve etiket zamanlaması ayrıca tasarlanmalı.
7. **ÇKS erişimi:** izin alınacağı varsayımı tek başına veri erişimini garanti etmez. Yetkili kurumla erişilebilir alanları ve zamanlamayı önceden netleştir.
8. **Arz haritası ifadesi:** ürün alanı haritası arz planlamasına girdi olabilir; üretim miktarı için verim, hasat ve başka veriler de gerekir. Erken uyarı/ekonomik kaybı azaltma, henüz gerçekleşmiş etki değildir.
9. **Takvim tutarlılığı:** eski form notu literatür/raporu bağımsız iş adımı yapmamayı söylerken tabloda rapor ayrı satırdır. Yeni başvuruda güncel bilgi notuna göre, araştırma iş paketlerini ölçülebilir çıktılarla kur.
10. **Kaynakça:** bu oturumda tüm makalelerin içerikleri doğrulanmadı. Başvuruda her iddiayı ilgili asıl makalenin yöntemi ve verisiyle kontrol et; özellikle RF/SVM’nin mekânsal özellik kullanamayacağı gibi mutlak genellemelerden kaçın.

## Soru gelirse: 20 saniyelik cevaplar

**Modelin doğruluğu kaç?** “Henüz burada model doğruluğu göstermiyorum. Gösterdiğim, gerçek uydu verisiyle doğrulanmış veri hazırlama hattı. Etiketli bağımsız testten sonra F1 ve IoU raporlanacak.”

**Neden U-Net?** “Hedef her pikselin ürün sınıfını üretmek. U-Net bu segmentasyon işine uygun bir aday; üstünlüğünü temel yöntemle karşılaştırarak ölçmek gerekiyor.”

**NDVI ürünleri ayırıyor mu?** “Bitki örtüsüne dair bilgi sağlar. Ürün türü için bantlar, tarihler, mekânsal bağlam ve doğrulanmış etiketler birlikte kullanılmalı.”

**Neden oranlar tam 70/15/15 değil?** “Bütün coğrafi blokları birlikte ayırıyoruz. Dokuz blok olduğunda tam oran yerine blok bütünlüğünü korumak daha önemli.”

**Saha olmadan yapılır mı?** “Doğrulanmış ve aynı sezona ait alternatif etiket kaynağı varsa mümkün. Sentetik örnekler gerçek performans ölçümü için yeterli değil.”

**Hangi kısmı kendin yaptın?** Kendi gerçek katkılarını belirt: soru ve yöntem tasarımı, veri hattının geliştirilmesi, entegrasyon, kontroller ve belgeleme. Danışmanlık ve kullandığın yardımcı araçların katkısını doğru ifade et.

## Anlatım tekniği

Bir ekranda tek mesaj; rakamdan sonra anlamını söyle; kısaltmayı ilk kullanımda açıkla; her 2–3 dakikada görsel değiştir. PDF’yi baştan sona okumak yerine problem → yöntem → gerçek çıktı → sınırlılık → başvuru dersi akışını kullan.

Kaynaklar: Kullanıcının paylaştığı başvuru kaydı ve araştırma önerisi; yerel README, `docs/validation-run.md`, `config/urla_june_subset.yaml`, gerçek `data/patches/index.csv` ve günlükler. Kod kapsamı: https://github.com/muend/sentinel-crop-pipeline
