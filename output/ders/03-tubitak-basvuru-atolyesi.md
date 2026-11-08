# Arkadaşlar için TÜBİTAK 2209-A başvuru atölyesi

14 Ekim 2026 itibarıyla hazırlanan ders materyali. Aşağıdaki içerik bir yazım ve tasarım rehberidir; sistem alanları ve karakter sınırları için güncel resmi bilgi notu esas alınır.

## Güncel süreç: eski PDF’yi aynen şablon alma

2026 başvuru ve danışman onayı için son tarih **11 Kasım 2026, 17.30**. Başvurular TYBS üzerinden. Araştırma önerisi formu sistemde girilen bilgilerden otomatik oluşuyor; eski araştırma önerisi PDF’sini yükleme adımı bulunmuyor. Kuruluş yetkilisinin e-imza dönemi 16–23 Kasım 2026. ARBİS kayıtlarını, danışman bilgilerini ve tüm onay adımlarını erkenden kontrol et.

Resmi değerlendirme ağırlıkları: bilimsel nitelik %35, yöntem %25, proje yönetimi %20, yaygın etki %20. Program sayfasında destek üst sınırı 12.000 TL, süre en çok 12 ay olarak belirtiliyor. Eski projedeki 9.000 TL, yeni çağrının üst sınırı değildir. Proje desteğinde üretken yapay zekâ kullanımına ilişkin TÜBİTAK rehberini ve danışman kontrolünü dikkate al.

Kaynak: [TÜBİTAK 2209-A resmi program sayfası](https://tubitak.gov.tr/tr/burslar/lisans-onlisans/destek-programlari/2209-universite-ogrencileri-arastirma-projeleri-destekleme-programi). Sayfadaki 2026 çağrı duyurusu ve Başvuru İçeriği Bilgi Notu bağlantılarını birlikte incele. Özet süreç bilgileri 14 Ekim 2026’da doğrulandı.

## Sınıfta vereceğin 7 kısa öneri

1. “Yapay zekâ yapacağım” yerine bir araştırma sorusu yaz.
2. Veri erişimini başvurudan önce küçük örnekle dene.
3. Bir temel yöntem ve karşılaştırma planı belirle.
4. Başarıyı ölçülebilir çıktı ve metrikle tanımla.
5. İş paketlerine süre, sorumlu, çıktı ve B planı ekle.
6. Bütçedeki her kalemi bir faaliyetin ihtiyacına bağla.
7. Özeti en son yaz; danışman ve kurum onaylarını son güne bırakma.

## Fikirden araştırma sorusuna

Zayıf: “Tarımda yapay zekâ kullanmak.”

Daha güçlü: “Urla’daki seçili tarım parsellerinde, aynı sezona ait Sentinel-2 görüntüleri ve doğrulanmış ürün etiketleriyle U-Net’in sınıf bazlı başarısı bir temel yönteme göre nasıl değişir?”

Bu, kabul edilmiş metnin birebir cümlesi değil; kapsamı ve karşılaştırmayı netleştiren bir geliştirme önerisidir.

Başka alana aktarım: “[Bölgede/grupta] [sorun] için [veri] kullanarak [yöntem A] ile [yöntem B]’yi [ölçüt] bakımından karşılaştıracağım.”

## Dört bölümü birbirine bağla

| Bölüm | Cevaplaması gereken | Bu projeden örnek | Kaçınılacak yaklaşım |
|---|---|---|---|
| Bilimsel nitelik | Sorun ne; mevcut bilgi nerede eksik; sorum ne? | Yerel ürün desenini güncel, doğrulanmış verilerle inceleme | Sadece teknoloji adı ve genel önem |
| Yöntem | Hangi veri, örnekleme, etiket, karşılaştırma ve analiz? | Bantlar, saha parselleri, U-Net adayı, bloklu test | “Model eğitilecek” ile yetinme |
| Proje yönetimi | Kim, ne zaman, hangi çıktıyı; başarısızlık halinde ne yapacak? | Bulut ve etiket erişimi B planı | “Gerekirse başka yöntem” gibi belirsiz cümle |
| Yaygın etki | Kim kullanacak, hangi somut çıktı paylaşılacak? | Tekrar kullanılabilir veri hattı ve doğrulanmış ürün haritası | Doğrudan bütün ekonomik kayıpları çözeceğini iddia etme |

## Doldurulabilir tek sayfalık çalışma kâğıdı

**Ad / bölüm:** ........................................................

**Sorun (1 cümle):** ...................................................

**Araştırma sorusu (1 cümle):** .........................................

**Kapsam: bölge / dönem / hedef grup:** .................................

**Literatürdeki boşluk ve bunu destekleyen 3–5 kaynak:** .................

**Veri kaynağı / erişim durumu / gerekli izin:** ..........................

**Küçük ön deneme: neyi çalıştırdım, ne gördüm?** .........................

**Ana yöntem ve karşılaştırma:** ........................................

**Bağımsız test / örnekleme planı:** .....................................

**Başarı ölçütü ve gerekçesi:** ..........................................

**En büyük risk / B planı / devreye girme koşulu:** .......................

**Somut çıktı / kim yararlanacak:** ......................................

**Danışman / mevcut altyapı / bütçe ihtiyacı:** ...........................

Bu kâğıt resmi başvuru formu değildir; TYBS alanlarını doldurmadan önce düşünceyi netleştirir.

## İş paketi örneği: yeni başvuruya uyarlanabilir

| Paket | Çıktı | Ölçüm | Risk ve B planı |
|---|---|---|---|
| Veri hazırlığı | Kontrol edilmiş görüntü ve kalite kayıtları | Kullanılabilir sahne/alan sayısı, eksik bant kontrolü | Bulut yüksekse uygun tarih penceresi ve alanı yeniden değerlendir |
| Yer gerçeği | Sezon bilgili parsel etiketleri | Sınıf başına parsel sayısı; doğrulama kaydı | İzinli veri gecikirse doğrulanabilir pilot alanı küçült |
| Model karşılaştırması | Aynı bölmeyle eğitilmiş temel yöntem ve U-Net | Eğitim kayıtları, sabit test ayrımı | GPU erişimi azalırsa küçük model/batch ve kapsam |
| Bağımsız değerlendirme | Sınıf bazlı hata matrisi, F1/IoU ve yorumlanan harita | Test performansı; hataların coğrafi dağılımı | Az örnekli sınıfları açıkça raporla; sonuç iddiasını sınırla |

Süre ve sorumluları kendi koşullarına göre ekle. Örnek sayısı ve hedef puanları veriye bakmadan uydurma. Raporlama ve paylaşımı güncel bilgi notunun iş paketi kurallarına uygun yerleştir.

## Bütçe gerekçesi nasıl yazılır?

“Hizmet alımı: 8.000 TL” tek başına yeterince açıklayıcı değildir. Hangi hizmetin hangi miktarda, neden gerekli olduğu ve hangi iş paketine hizmet ettiği belirtilmeli. Eski projede önerilen toplam 9.000 TL, 1.000 TL ulaşım ve 8.000 TL hizmet alımı olarak girilmiş; bu, bu kalemlerin kesin olarak ödendiği anlamına gelmez.

Örnek gerekçe şablonu: “[İş paketi] için [mal/hizmet], [birim × miktar] gerekir. Kurumda mevcut [altyapı] bu ihtiyacı [neden] karşılayamıyor. Tahmini maliyetin dayanağı [teklif/tarife]dir.”

## Göndermeden önce kontrol

- [ ] Soru, amaç, yöntem ve çıktı aynı problemi ele alıyor.
- [ ] Veri kaynağı ve izinler gerçekçi; ön deneme yapılmış.
- [ ] Literatür iddiaları asıl kaynaklarla kontrol edilmiş.
- [ ] Başarı ölçütleri izlenebilir; henüz elde edilmemiş sonuçlar gelecek zamanla yazılmış.
- [ ] Veri bölmesi ve karşılaştırma adil; test verisi geliştirme için kullanılmıyor.
- [ ] İş paketlerinde çıktı, sorumlu, zaman ve risk tedbiri var.
- [ ] Bütçe gerekli faaliyetlerle açıklanmış.
- [ ] TYBS minimum karakter sınırları ve güncel bilgi notu kontrol edilmiş.
- [ ] ARBİS, danışman onayı ve kurum e-imzası takvimi takip ediliyor.
- [ ] Yardımcı yapay zekâ araçlarının çıktıları doğrulanmış; kullanım güncel rehbere uygun açıklanmış.

## Kabul hakkında kullanacağın doğru dil

“Benim projemde sorun, yöntem, takvim ve B planını birlikte kurmaya çalıştım. Bunlar size de yardımcı olabilir.”

“Bu şekilde yazarsanız kesin kabul edilir” deme. Elimizde panelin kabul gerekçesi yok. Destek almak, araştırmanın hipotezinin doğrulandığı anlamına da gelmez.

## 5 dakikalık sınıf etkinliği

1 dakika: herkes sorusunu yazar. 1 dakika: veri kaynağını ve erişimini yazar. 1 dakika: nasıl ölçeceğini yazar. 1 dakika: en büyük riski ve B planını yazar. 1 dakika: yanındaki kişi sorunun yöntemle cevaplanıp cevaplanmadığını kontrol eder.
