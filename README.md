# Early mobility and new pressure injury in the ICU (MIMIC-IV)

## About (English)

**Aim:** Retrospective cohort study of the association between early mobility level in the intensive care unit (Johns Hopkins Highest Level of Mobility, JH-HLM, first 72 hours) and newly developed pressure injury, using MIMIC-IV.

**Data access:** The scripts target **MIMIC-IV 3.1** (they also run on the 2.2 demo). **No data are included in this repository**, and none should be added. Access requires a [PhysioNet](https://physionet.org/content/mimiciv/3.1/) account with credentialed access, completion of the CITI "Data or Specimens Only Research" course, and signing the MIMIC-IV data use agreement (DUA). Pass the data folder (containing `hosp/` and `icu/`) with `--veri <MIMIC_DIR>` or the `MIMIC_DIR` environment variable. Output folders (`outputs*/`) are not tracked. Requirements: Python 3.12 (`requirements.txt`), R 4.6.1 with `survival`.

**Run order** (from the project root; code comments and console messages are in Turkish):

| Step | Script | Purpose |
|---|---|---|
| 01 | `01_parquet.py` | CSV.gz → Parquet |
| 02 | `02_itemid_sozlugu.py` | Candidate itemids; then manual review → `config/itemids_onayli.csv` (from `ozel/itemid_onay_sablonu.csv`) |
| 03 | `03_on_denetim.py` | Data audit |
| 04 | `04_kritik_kontroller.py` | Cohort and outcome definition |
| 05 | `05_analiz_seti.py` | Analysis dataset |
| 06 | `06_istatistik.py`, `06b_fine_gray.R`, `06c_ph.R` | Statistics (Python + R) |
| 07 | `07_ml.py` | Machine learning |
| 08 | `08_kumeleme.py` | Mobility trajectory clustering |
| 09 | `09_makale.py` | Manuscript tables and figures |

**License:** Code is released under the MIT License (`LICENSE`). SQL files in `code/mimic_code_sql/` are adapted from MIT-LCP [mimic-code](https://github.com/MIT-LCP/mimic-code) and remain under their own license (`code/mimic_code_sql/LICENSE`).

---

# MIMIC-IV: Yoğun bakımda mobilite ve yeni basınç yarası

## Bu depo hakkında

**Çalışma:** Yoğun bakımda erken mobilite düzeyi (JH-HLM, ilk 72 saat) ile yeni gelişen basınç yarası arasındaki ilişki, MIMIC-IV retrospektif kohort çalışması.

**Veri:** Betikler **MIMIC-IV 3.1** için yazıldı (demo sürümü 2.2 ile de çalışır). **Veri bu depoda yok** ve depoya konmamalıdır. MIMIC-IV'e erişim için [PhysioNet](https://physionet.org/content/mimiciv/3.1/) hesabı, kimlik doğrulaması (credentialed access), CITI "Data or Specimens Only Research" eğitimi ve veri kullanım sözleşmesinin (DUA) imzalanması gerekir. İndirdiğin klasörün yolunu `--veri <MIMIC_DIR>` argümanıyla veya `MIMIC_DIR` ortam değişkeniyle ver. Betiklerin ürettiği `outputs*/` klasörleri de depoya girmez.

**Çalıştırma sırası** (ayrıntılar aşağıda, "Çalıştırma sırası" bölümünde):

| Adım | Betik | İş |
|---|---|---|
| 01 | `01_parquet.py` | CSV.gz → Parquet |
| 02 | `02_itemid_sozlugu.py` | Aday itemid'ler; ardından elle onay → `config/itemids_onayli.csv` (`ozel/itemid_onay_sablonu.csv`'den) |
| 03 | `03_on_denetim.py` | Ön denetim |
| 04 | `04_kritik_kontroller.py` | Kohort ve sonuç tanımı |
| 05 | `05_analiz_seti.py` | Analiz seti |
| 06 | `06_istatistik.py`, `06b_fine_gray.R`, `06c_ph.R` | İstatistik (Python + R) |
| 07 | `07_ml.py` | Makine öğrenmesi |
| 08 | `08_kumeleme.py` | Mobilite yörüngesi kümeleme |
| 09 | `09_makale.py` | Makale tabloları ve şekilleri |

**Lisans:** Kod MIT lisanslıdır (`LICENSE`). `code/mimic_code_sql/` altındaki SQL dosyaları MIT-LCP [mimic-code](https://github.com/MIT-LCP/mimic-code) deposundan uyarlanmıştır ve kendi lisansı (`code/mimic_code_sql/LICENSE`) geçerlidir.

---

Veri hazırlığından makale tablolarına kadar tüm betikler (01–09). Kodlar MIMIC-IV demo verisinde (100 hasta, sürüm 2.2) uçtan uca test edildi; analizler MIMIC-IV 3.1 üzerinde yapılır.

## Kurulum

Python 3.12 ve R 4.6.1 (`survival` paketi; Fine-Gray ve orantılı hazard analizleri için, bkz. "R kurulumu") gerekir.

```
pip install -r requirements.txt
```

## Veri klasörü

PhysioNet'ten indirdiğin klasörü olduğu gibi kullan. İçinde `hosp/` ve `icu/` klasörleri olmalı:

```
<MIMIC_DIR>/hosp/patients.csv.gz
<MIMIC_DIR>/icu/chartevents.csv.gz
```

Bu klasörü OneDrive, Google Drive veya iCloud ile eşitlenen bir yere koyma.

## Çalıştırma sırası

Komutları proje klasörünün içinden çalıştır.

```
python code/01_parquet.py            --veri <MIMIC_DIR>
python code/02_itemid_sozlugu.py     --veri <MIMIC_DIR>
python code/03_on_denetim.py         --veri <MIMIC_DIR>
python code/04_kritik_kontroller.py  --veri <MIMIC_DIR>
python code/05_analiz_seti.py        --veri <MIMIC_DIR>
python code/06_istatistik.py         --cikti outputs_tam
& "C:\Program Files\R\R-4.6.1\bin\Rscript.exe" code/06b_fine_gray.R outputs_tam
& "C:\Program Files\R\R-4.6.1\bin\Rscript.exe" code/06c_ph.R outputs_tam
python code/07_ml.py         --cikti outputs_tam
python code/08_kumeleme.py   --veri <MIMIC_DIR> --cikti outputs_tam
python code/09_makale.py     --cikti outputs_tam --dil tr
python code/09_makale.py     --cikti outputs_tam --dil en
```

Komutlar PowerShell içindir: tırnaklı yolla bir programı çalıştırmak için başa `&` (çağrı operatörü) gerekir; cmd'de `&` olmadan yazılır. `python`, sanal ortam etkin değilse `.venv\Scripts\python` olmalıdır.

Bellek sorunu yaşarsan her komutun sonuna `--bellek 4GB` ekle.

1. `01_parquet.py` tabloları Parquet biçimine çevirir. Tek seferlik bir iştir; tam veride uzun sürebilir. Sonraki betikler bu dosyalarla hızlı çalışır.
2. `02_itemid_sozlugu.py` değişkenlerin aday kayıt numaralarını (itemid) bulur. İki dosya yazar: `ozel/itemid_adaylari.csv` (kayıt ve yatış sayılarıyla, incelerken bakmak için) ve `ozel/itemid_onay_sablonu.csv` (`degisken_grubu, itemid, label, linksto, onay, gerekce`; sayı sütunu yok).
3. **Elle kontrol (atlanmamalı):** Onay dosyası **şablondan** üretilir. `itemid_onay_sablonu.csv`'yi aç, her satırı incele (gerekirse aday dosyasındaki sayılara bak), kullanılacak satırların `onay` sütununa 1 yaz, `gerekce`yi doldur. Dosyayı `config/itemids_onayli.csv` adıyla kaydet. Aday dosyasını onay dosyası olarak kaydetme: kayıt ve yatış sayıları depoya ve makalenin ekine girmemeli; 03, 04 ve 05 onay dosyasında bu sütunları görürse uyarı verir. Bu tablo makalenin ekine girer. Dosya yoksa 03 ve 04 adayların tamamını kullanır; bu yalnızca deneme içindir.
4. `03_on_denetim.py` her değişkenin kayıt sayısını, yıllara göre dağılımını, en sık değerlerini ve dönüşüm kurallarına uymayan değerleri çıkarır.
5. `04_kritik_kontroller.py` kohort akışını, yeni basınç yarası sayısını, JH-HLM'nin yıllara göre kaydedilme oranını, Braden eksiksizliğini ve bakım planlarının görünürlüğünü hesaplar. Birincil kohortu sonuç zamanlarıyla `ozel/04_kohort.parquet` dosyasına yazar.
6. `05_analiz_seti.py` (Faz 2) her kohort yatışı için tek satırlık analiz setini `ozel/analiz_seti.parquet` dosyasına, değişken özetini (doluluk, medyan/IQR veya yüzde) `paylasilabilir/05a_degisken_ozeti.csv` dosyasına yazar. Önce 04 çalıştırılmalı. SOFA, mekanik ventilasyon, vazopresör ve Charlson için mimic-code concept SQL'leri kullanılır; kaynak ve commit `code/mimic_code_sql/README.md` dosyasında.

7. `06_istatistik.py` (Faz 2) Tablo 1, kümülatif insidans, birincil ve duyarlılık modellerini ve model karşılaştırmasını hesaplar. Girdi `ozel/analiz_seti.parquet`; tüm tablolar `paylasilabilir/` altına yazılır. Fine-Gray (`06b_fine_gray.R`) ve orantılı hazard analizleri (`06c_ph.R`) için R betikleri 06'dan sonra çalıştırılır. 06c, 06'nın yazdığı `06d_modeller.csv` dosyasına satır eklediği için 06 her yeniden çalıştığında 06c de yeniden çalıştırılmalı.
8. `07_ml.py` (Faz 3) makine öğrenmesi: 0–72 saat verileriyle 72–168 saatte yeni basınç yarası. Girdi `ozel/analiz_seti.parquet` ve `ozel/04_kohort.parquet` (subject_id). `xgboost` ve `shap` paketlerini ister (`requirements.txt`). Tam veride uzun sürer (iç içe çapraz doğrulama: model başına 5 dış kat × 40 deneme × 3 iç kat eğitim).
9. `08_kumeleme.py` (Faz 4) keşfedici kümeleme: 0–72 saat JH-HLM yörüngeleri (12 saatlik bloklar) Gaussian Mixture ile kümelenir; kümeler Tablo 1, kümülatif insidans ve Cox modeliyle karşılaştırılır. `chartevents` için `--veri` ister; 06'nın atanmış verisini kullandığı için 06'dan sonra çalıştırılır.
10. `09_makale.py` (Faz 5) makale tabloları (.docx, APA 7) ve şekilleri, `--dil tr` veya `--dil en`. Yalnızca `paylasilabilir/` okunur; 06c, 07 ve 08'den sonra çalıştırılır. `python-docx` paketini ister.

### R kurulumu (Fine-Gray ve orantılı hazard için)

1. CRAN'dan R 4.x indir ve kur: https://cran.r-project.org/bin/windows/base/ (bu bilgisayarda R 4.6.1 kurulu: `C:\Program Files\R\R-4.6.1`).
2. Ek paket gerekmez: `survival` ve `splines` R ile birlikte gelir. Kontrol (PowerShell): `& "C:\Program Files\R\R-4.6.1\bin\Rscript.exe" -e "packageVersion('survival')"`. Analizlerde kullanılan sürüm: R 4.6.1, `survival` 3.8.6 (20 Ekim 2026).
3. R PATH'te değilse `Rscript.exe`'yi tam yoluyla çağır (yukarıdaki komut).

## Çıktılar ve paylaşım

Çıktılar iki klasöre yazılır:

- `outputs/ozel/` yalnızca senin içindir. Küçük sayılar ve kayıt tarihleri bu klasörde açık durur.
- `outputs/paylasilabilir/` hocayla ve benimle paylaşabileceğin özet tablolardır. 1 ile 4 arasındaki sayılar "<5" olarak gizlenir; bu sayıları geri hesaplatan yüzdeler de boş bırakılır.

### Tablolar arası gizleme (`code/istatistik_ortak.py`)

Bir tabloda gizlenen hücre başka bir tablodaki açık sayılardan geri hesaplanmasın diye 06 ve 08'de şu kurallar uygulanır (07'de aynı türden bir örtüşme bulunmadı: 07d alt grupları 72–168 saat sonucuna göre, Tablo 1'ler 28 günlük sonuca göre veya başka gruplara göre):

- **Tablo 1 tamamlayıcı gizlemesi** (`tablo1_tamamlayici`): yeni basınç yarası hücresi (`olay_tipi = yeni_by`) mümkünse tamamlayıcı olarak seçilmez (`SONUC_KORUNAN`), çünkü aynı sayı kümülatif insidans ve Cox tablolarında açık yazılır; bunun yerine örneğin ölüm veya taburculuk hücresi gizlenir. Aynı tercih, Tablo 1'den önce çalışan ilk tamamlayıcı adımda da (`mimic_db.ozet_tablosu_gizle`, `korunan` parametresi) uygulanır; 05a'da `korunan` verilmez, çıktısı değişmez.
- **Fark** (`tablo1_fark_gizle`): bir grupta yeni basınç yarası (28 gün) − 72–168 saat yeni basınç yarası (168. saatten sonraki olaylar) 1–4 ise o grubun 72–168 saat hücreleri gizlenir (evre 2 ve bilinen evre tanımları için de).
- **Kümülatif insidans** (`kumulatif_insidans_capraz`, 06c ve 08f): idari sansür yalnızca 28. günde olduğu için `kumulatif_olay` ve `kumulatif_insidans` × grup büyüklüğü o güne kadarki olay sayısını, 25. gündeki `risk_altinda` ise idari sansür sayısını verir. Bu yüzden Tablo 1'de gizlenen yeni basınç yarası / 72–168 saat / idari sansür sayısına eşit olan hücreler "gizli"; `kumulatif_olay` "<5" olan satırda `kumulatif_insidans` ve GA'sı boş. Yeni basınç yarası hücresi gizli olan grubun eğrisi grafiğe çizilmez (eğri olay sayısını verir).
- **Cox olay sayıları** (08e, 08h): Tablo 1'de sonuç hücresi gizli olan kümenin olay sayıları yazılmaz; bir kümenin bir dönem olay sayısı gizliyse diğer dönemi ve toplamı da gizlenir; kümeler arası toplam bilindiği için tek gizli kalırsa en küçük ikinci de gizlenir.
- **06a ↔ 06b:** 06b'deki `jh_hlm_grup` × "var" hücresi 06a'daki o grubun yeni basınç yarası hücresiyle aynı sayıdır; biri gizliyse diğeri de gizlenir.
- **08g ↔ 08 ana çözüm:** yukarıdaki "Duyarlılık, k = 3" maddesi (fark saldırısı).

Not: 06c'de bu düzeltmeden önce, `kumulatif_olay` "<5" iken `kumulatif_insidans` açık kalıyordu (insidans × grup büyüklüğü küçük sayıyı veriyordu). Tam veride (20 Ekim 2026) bu durum yoktu; demoda vardı.

`data/` klasörünü ve `outputs/ozel/` içeriğini kimseyle paylaşma, çevrim içi yapay zekâ araçlarına yükleme.

## Kodlarda uygulanan veri kuralları

Bu kuralların tamamı `code/kurallar.py` dosyasındadır ve yöntem bölümünde raporlanmalıdır.

- **JH-HLM** iki ayrı itemid ile (229319 ve 229321) metin olarak kaydediliyor, örneğin "2b - Turning in bed". Baştaki rakam alınır; MIMIC'in 2a, 2b ve 2c alt düzeylerinin üçü de 2 sayılır.
- **Braden toplam skoru kayıtlı değil.** Altı alt boyut metin olarak tutuluyor; standart Braden puanlamasıyla sayıya çevrilip toplanır (6 ile 23 arası). Yalnızca altı alt boyutun aynı anda kaydedildiği setler kullanılır. Mobilite dışı skor duyusal algı, nem, beslenme ve sürtünme alt boyutlarının toplamıdır.
- **Basınç yarası evresi** iki biçimde kaydediliyor: eski "Pressure Ulcer Stage #1..#10" ve yeni "Pressure ulcer #1..#10- Stage". Etiketteki "#2" yaranın sıra numarasıdır, evresi değildir. Evre alanlarında çok sık görülen "Not applicable" ve "Status Changed: Skin Impairment" değerleri yara sayılmaz.
- Evreler 1, 2, 3, 4, DDH (derin doku hasarı), EV (evrelendirilemeyen) ve BILINMIYOR olarak sınıflandırılır. 04 betiğindeki "evre 2 ve üstü" sayımı DDH ve EV'yi kapsar, BILINMIYOR'u kapsamaz.
- Eski şablondaki evre 4 metni de "Full thickness skin loss" ile başlıyor ("... with damage to muscle, bone ..."). Bu yüzden "damage to muscle" ifadesi evre 3'ten önce kontrol edilir ve evre 4 sayılır.
- **BILINMIYOR**: "Unknown" (yeni şablon) ve "Unable to assess; dressing not removed" (eski şablon). Yara var ama evresi bilinmiyor. Hem "ilk 72 saatte basınç yarası kaydı yok" dışlamasında hem yeni yara sayımında yara sayılır. Duyarlılık analizi için 04b'de yalnızca BILINMIYOR kaydıyla yeni sayılan yatışlar hariç sayı da verilir (`yeni_by_bilinmiyor_haric`).
- Bu kurallara uymayan değerler `tanimsiz` olur ve yara sayılmaz.
- **Yeni "Pressure Injury" şablonu** (Pressure Injury Location 229864, No Pressure Injury Present 229865) ayrı bir grupta (`by_yeni_sablon`) tutulur. Bu şablonda evre alanı yoktur ve yaralar numaralanmaz; bu yüzden sonuç tanımında kullanılmaz.
- **Yaranın tespit tarihi** chartevents'te değil datetimeevents tablosunda tutuluyor. Demo veride bu alanda hiç kayıt yok. Tespit tarihi yoğun bakım girişinden sonraki 72. saatten önce olan bir yarası bulunan yatışlar kohorttan çıkarılır (04a'da ayrı adım). Yara numarası eşleştirilmez: tespit tarihi 72. saatten önce olan herhangi bir yara yeterlidir.
- **Kabulde basınç yarası** işareti (itemid 228649) 0/1 değer alıyor; 1 olan yatışlar kohorttan çıkarılır.
- **Yaş**, yoğun bakıma kabul yılına göre hesaplanır: anchor_age + (kabul yılı − anchor_year).

### Analiz seti (05) kuralları

- **Pencere:** Tüm değişkenler `intime` ile `intime + 72 saat` arasından hesaplanır; SOFA ilk 24 saatten. Aralık tipi kayıtlar (ventilasyon, vazopresör, sedatif infüzyon) pencereyle örtüşüyorsa sayılır. İki istisna var: boy ve kilo (aşağıda) ile Charlson ve komorbiditeler. Charlson ve komorbiditeler taburculukta kodlanan ICD tanılarından gelir (yatışın tamamı, zaman bilgisi yok).
- **Basınç yarası tanı kodları** (ICD-9 707.0x, ICD-10 L89) hiçbir değişkene girmez; tanı tablosundan bu kodlar çıkarıldıktan sonra Charlson hesaplanır.
- **BMI:** İlk boy (cm; inch × 2,54) ve ilk kilo (kg; lbs × 0,4536). Bu ikisinde pencere hastane yatışının başından (`admittime`) `intime + 72 saat`e kadardır, çünkü boy ve kilo çoğunlukla YB girişinden önce kaydediliyor ve sonuç bilgisi taşımıyor. Makul aralık dışı boy (120–220 cm dışı) ve kilo (25–300 kg dışı) kayıtları kullanılmaz; aralık içi ilk kayıt alınır, yoksa boş. Aralık içi boy ve kiloyla hesaplanan BMI 12–70 dışındaysa BMI boş sayılır (atamadan önce). Bu nedenle boş kalan yatış sayıları `05a_degisken_ozeti.csv` içinde `tip = aralik_disi_eksik` satırlarındadır. 06'da atanan BMI de 12–70 aralığına sınırlanır.
- **Onaylanmamış itemid:** Var/yok ve sayım değişkenlerinde ilgili itemid grubu onay dosyasında onaylanmamışsa değişken 0 değil boş yazılır.
- **SOFA:** mimic-code `first_day_sofa` puanlaması, pencere `intime`'dan başlar (mimic-code'da `intime − 6 saat`). Dobutamin kardiyovasküler puana girer (mimic-code'daki gibi). Demoda doğrulama: aynı SQL `intime − 6 saat` penceresiyle çalıştırılınca mimic-code ile 29/29 yatışta her bileşen aynı; `intime` penceresiyle toplam SOFA korelasyonu 0,993, ortalama fark −0,28 puan (23/29 yatış aynı).
- **Vazopresör:** norepinefrin, epinefrin, dopamin, fenilefrin veya vazopressin. Dobutamin inotrop olduğu için dahil değil (SOFA'da kullanılır).
- **Sedatif infüzyon:** propofol, midazolam, deksmedetomidin; yalnızca `ordercategorydescription = 'Continuous Med'` kayıtları (bolus dozlar sayılmaz).
- **RASS:** metindeki sayı (−5…+4); en düşük ve ortalama.
- **Fiziksel kısıtlama:** "Restraint (Non-violent)" veya "Restraints (Violent)" alanında "On" değeri.
- **Laboratuvar:** ilk değer ve en kötü değer (albumin ve hemoglobin en düşük; glukoz, kreatinin ve laktat en yüksek).
- **Charlson:** mimic-code indeksi (yaş puanı dahil); `charlson_yassiz` yaş puanı çıkarılmış hâlidir.
- **Braden:** altı alt boyutun aynı anda kaydedildiği tam setler; her skor için ilk ve en düşük.
- **JH-HLM:** aynı anda çelişkili kayıtta en yüksek düzey alınır. İlk, en yüksek, ortalama ve kayıt sayısı (farklı zaman). Grup (1–3 / 4–5 / 6–8) en yüksek düzeye göre.
- **Pozisyon değiştirme:** Turn/Position kaydı olan farklı zaman sayısı, 24 saate bölünmüş (72 saat / 3).
- **Cihazlar:** tedavi edici yatak (değeri olan herhangi bir kayıt), basınç azaltıcı cihaz ("None" dışında), yardımcı cihaz ("None" ve "Independent" dışında). Kaydı olmayan yatış 0 sayılır. RN mobilite hedefi ve bakım planları için de kayıt varsa 1.
- **Sonuç:** olaya kadar süre 72. saatten itibaren saat olarak. Olay tipi: ilk yeni basınç yarası; yoksa YB çıkışı (ölüm veya taburculuk; ölümde de YB çıkış saati kullanılır); 28. günde (672. saat) idari sansür. YB çıkışından sonraki yara kaydı olay sayılmaz; 72–168 saat göstergesi dahil. 04b, 04b2 ve 04j aynı tanımı kullanır (yara kaydı 72. saat ile `min(672, yb_saat)` arasında), bu yüzden 04b ve 06 aynı olay sayısını verir. İlk yarası YB çıkışından sonra kaydedilen yatış sayısını 05 konsola yazar (tam veride <5). Evre 2 ve üstü için aynı iki sonuç ayrıca hesaplanır.
- **05a gizleme:** 1–4 arası sayılar "<5". Küçük bir hücreyi geri hesaplatan sayılar "gizli". Kategorik değişkende tek bir gizli kategori kalırsa en küçük ikinci kategori de gizlenir. 5'ten az dolu değişkende medyan ve IQR boş bırakılır.
- **Yoğun bakımda ölüm**, ölüm zamanının yoğun bakım giriş ve çıkış zamanları arasında olmasıdır.

### İstatistik (06) kuralları

- **Maruziyet:** JH-HLM grubu (0–72 saatteki en yüksek düzey; 1–3 referans, 4–5, 6–8). Duyarlılık (h): en yüksek düzey sürekli, 1 birim artış.
- **Karıştırıcılar:** yaş, cinsiyet, BMI, `sofa_24s`, mekanik ventilasyon, vazopresör, sedatif infüzyon (`sedatif_herhangi`), RASS en düşük, fiziksel kısıtlama, Braden mobilite dışı skor (0–72 saatteki en düşük), `charlson_yassiz`, `anchor_year_group` (kukla, referans en eski grup). Cox modellerinde `first_careunit` strata; lojistik modellerde kukla. 100'den az yatışı olan birimler (`SEYREK_BIRIM`) hem strata'da hem kuklada (Fine-Gray dahil) "diger" olarak birleştirilir; Tablo 1 (06a, 06b) de birimleri birleşik gösterir; "diger"e giren birimler ve yatış sayıları `06a_tablo1_jhhlm.csv` sonundaki `tip = not` satırlarındadır (tek bir "<5" kalırsa en küçük ikinci sayı da "gizli"). Tablo 1'de tamamlayıcı gizleme: bir kategoride (gruplar arası satır) ya da bir grupta (kategoriler arası) tek gizli hücre kalırsa en küçük ikinci hücre de "gizli" yapılır; değişiklik kalmayana kadar tekrarlanır.
- **Birincil model:** cause-specific Cox. Olay yeni basınç yarası; YB ölümü, canlı taburculuk ve 28. gün idari sansürü sansür sayılır (cause-specific hazard tanımı gereği). Süre 72. saatten itibaren saat.
- **Standart hata (hasta kümesi):** bir hastanın birden fazla YB yatışı kohorta girebildiği için bütün Cox ve Fine-Gray modellerinde standart hatalar hasta düzeyinde kümelenmiş robust (Lin-Wei sandwich) tahmindir: R'da `coxph(..., cluster = subject_id)` (birincil strata birim × dönem, 06j, tt, Fine-Gray'in ağırlıklı `coxph`'u), Python'da lifelines `cluster_col = "subject_id"` (06 birincil ve b, d–h duyarlılık analizleri; 08e, 08g, 08h). `subject_id` 04'ün kohort dosyasından alınır ve `ozel/06_atanmis_veri.csv.gz`'ye yazılır. Ana sütunlar (`se`, `alt_95`, `ust_95`, `p`) robust; kümelenmemiş (naif) değerler aynı satırda `se_naif`, `alt_95_naif`, `ust_95_naif`, `p_naif` sütunlarında (06d, 06i, 06j, 08e, 08g, 08h). İkisi yan yana 09'un Ek Tablo E6'sında. Duyarlılık (c) lojistik modelinde de standart hata hasta düzeyinde kümelenmiştir (statsmodels `fit(cov_type="cluster", cov_kwds={"groups": subject_id})`; naif değerler aynı biçimde `*_naif` sütunlarında). cox.zph testi (06e2) kümelenmemiştir. lifelines robust kovaryansın yalnızca köşegenini verir (`standard_errors_`; `variance_matrix_` naiftir) ve geç girişte (`entry_col`) robust standart hatayı doğru hesaplamaz; bu yüzden 08h'de 2. dönemin zamanı 96. saatten başlatılır ve dönem strataya eklenir (geç girişli bölünmüş modelle katsayı ve standart hata aynı; sahte sette doğrulandı), etkileşim ayrı bir parametrelendirmede (küme + küme × dönem 2) tek katsayı olarak kestirilir.
- **Yarışan olaylar (Aalen-Johansen ve Fine-Gray):** olay tipleri yeni basınç yarası, YB ölümü ve canlı taburculuk; ölüm ve canlı taburculuk ikisi de yarışan olaydır, yalnızca 28. gün idari sansürü sansürdür. Gerekçe: sonuç yoğun bakımla sınırlıdır; taburcu edilen hastada YB'de yeni basınç yarası tanım gereği gerçekleşemez. Taburculuğu sansür saymak, taburcu olan hastaların YB'de kalmaya devam etseydi aynı riski taşıyacağını varsayar ve kümülatif insidansı olduğundan yüksek gösterir.
- **Eksik veri:** MICE, m = 20 (`--m`). scikit-learn `IterativeImputer` (BayesianRidge, `sample_posterior=True`, 10 tur), atama modelinde üç sonuç tanımının olay göstergesi ve Nelson-Aalen kümülatif hazard'ı, 72–168 saat göstergeleri ve YB birimi kuklaları. İkili değişkenler yuvarlanır, değerler gözlenen en küçük ile en büyük arasında tutulur. BMI çarpık dağıldığı için log ölçeğinde atanır ve sonra geri dönüştürülür; atanan BMI değerlerinin en küçük, en büyük ve medyan değeri (tüm atamalar birlikte) `06d2_atama_eksik_oranlari.csv` dosyasında ayrı satırlardadır. Sonuçlar Rubin kurallarıyla birleştirilir (t dağılımı, Rubin serbestlik derecesi). Değişken başına eksik oranı `06d2_atama_eksik_oranlari.csv`.
- **E-değeri:** birincil HR için VanderWeele-Ding E-değeri, nokta tahmini ve GA'nın 1'e yakın sınırı (sınır 1'i kesiyorsa 1). İki versiyon `06d_modeller.csv` içinde ayrı `analiz_kodu` ile: `birincil_e_degeri_hr` (HR doğrudan RR yerine, seyrek sonuç varsayımı) ve `birincil_e_degeri_sik` (sık sonuç dönüşümü, RR ≈ (1 − 0.5^√HR) / (1 − 0.5^√(1/HR)); VanderWeele 2017). Değer `etki` sütunundadır.
- **Orantılı hazard (R, `06c_ph.R`; tek kaynak `survival::cox.zph`):** Python'daki lifelines testi kaldırıldı. Tüm modeller cause-specific Cox, strata = YB birimi (birleştirilmiş) × `anchor_year_group`, yıl kuklaları modelde yok; tüm atanmış veri setlerinde kestirilip Rubin kurallarıyla birleştirilir.
  - Bu strata ile birincil HR: `06d_modeller.csv`, `analiz_kodu = birincil_strata_birim_yil` (`birincil` satırları `first_careunit` strata ve yıl kuklalı modeldir).
  - `06e2_ph_varsayimi_coxzph.csv`: aynı model için `cox.zph` (rank dönüşümü), global ve değişken bazında; ilk atanmış setin ki-kare ve p değeri (`p_ilk_atama`) ve tüm atamaların D2 yöntemiyle birleştirilmiş p değeri (`p_birlesik_d2`; Li, Meng ve Raghunathan 1991).
  - `06j_donem_hr.csv`: `survSplit` ile takip 72–168 saat ve >168 saat olarak bölünür; JH-HLM grupları için dönem bazında HR ve dönem × maruziyet etkileşimi (>168 HR / 72–168 HR oranı, p). `n` ve `olay` ilk atanmış setten (ikinci dönemde n = 168. saatte risk altındaki yatış).
  - `06e3_schoenfeld_jhhlm.png/.svg`: ilk atanmış set, jh_4_5 ve jh_6_8 için yumuşatılmış beta(t) (doğal spline, 4 sd) ve %95 GA bandı; tek tek artık noktaları çizilmez, eğri zamanın 5.–95. yüzdeliği arasındadır. Kesikli çizgi sabit HR katsayısı.
  - **VIF** Python'da, birincil model, ilk atanmış veri seti (`06f_vif.csv`).
- **Duyarlılık:** (a) Fine-Gray (R, `survival::finegray` + `coxph`, aynı atanmış veri setleri ve terimler; ölüm ve canlı taburculuk yarışan olay); (b) evre 2 ve üstü sonuç; (c) 72–168 saat penceresi, lojistik regresyon (OR); (d) BILINMIYOR hariç sonuç (olay zamanı bilinen evreli ilk kayıt); (e) albümin eklenmiş (0–72 saatteki en düşük); (f) önleyici girişimler eklenmiş (tedavi edici yatak, basınç azaltıcı cihaz, pozisyon değiştirme sıklığı); (g) tam kayıtlı analiz; (h) JH-HLM sürekli; (i) Braden mobilite dışı, vazopresör, sedatif, SOFA ve `charlson_yassiz` için × log(saat) etkileşimi (`tt`) eklenmiş model, strata birim × yıl, yalnızca JH-HLM HR'leri (R, `06c_ph.R`, `analiz_kodu = i_tt_log_zaman`).
- **Kümülatif insidans:** JH-HLM grubuna göre Aalen-Johansen (ölüm ve canlı taburculuk yarışan olay; idari sansür sansür). Güven aralığı yüzdelik bootstrap (`--bootstrap`, 1000). Zaman ekseni 72. saatten sonraki gün (0–25; 25. gün = girişten sonraki 28. gün).
- **Model 1–4 karşılaştırması (ikincil):** 72–168 saat yeni basınç yarası, lojistik regresyon, yalnızca o modelin değişkenleri (Model 1 Braden toplam, Model 2 JH-HLM grubu, Model 3 ikisi, Model 4 mobilite dışı Braden + JH-HLM; Braden skorları 0–72 saatteki en düşük). Dört modelin değişkenleri tam olan ortak örneklem. Tahminler 10 katlı tabakalı çapraz doğrulamadan; AUROC için yüzdelik bootstrap %95 GA, AUROC farkı için DeLong testi ve bootstrap GA, kalibrasyon eğimi (y ~ logit p), kalibrasyon kesişimi (logit p offset), Brier skoru.
- **Çıktı biçimi:** sayılar yuvarlanmadan, nokta ondalıklı ham değer. Her model satırında `analiz_tipi` (birincil / duyarlılık / ikincil). Demoda modeller yakınsamaz; hata veren analizler `06z_hatalar.csv` dosyasına yazılır, akış sürer.
- **Hasta düzeyi ara dosya:** `ozel/06_atanmis_veri.csv.gz` (R için atanmış veri setleri); yalnızca `ozel/` altında.

### Makine öğrenmesi (07) kuralları

- **Görev:** 0–72 saat verileriyle 72–168 saatte yeni basınç yarası (0/1; `yeni_by_72_168`; YB çıkışından sonraki kayıt sayılmaz).
- **Özellikler:** 05'teki tüm değişkenler. Hariç tutulanlar:
  - kimlikler;
  - sonuç ve zaman değişkenleri (`sure_saat*`, `olay_tipi*`, `yeni_by_72_168*`);
  - `anchor_year_group` (dönemsel bölmenin değişkeni);
  - AM-PAC (dolu %6).

  Basınç yarası tanı kodları (ICD-9 707.0x, ICD-10 L89) zaten 05'te hiçbir değişkene girmez. Kategorik değişkenler (cinsiyet, kabul tipi, birleştirilmiş YB birimi, JH-HLM grubu) kukla değişkene çevrilir. Özellik listesi ve eksik yüzdeleri `07a_ozellikler.csv` dosyasında.
- **Doğrulama:** her çıktıda `analiz_tipi` sütunu var.
  - `ic_dogrulama`: iç içe çapraz doğrulama. Dış döngü `GroupKFold(5)` (subject_id ile, karıştırılmış). İç döngü `GroupKFold(3)` ile hiperparametre seçer. Metrikler beş dış katın birleştirilmiş kat dışı tahminlerinden hesaplanır.
  - `donemsel_dogrulama`: dönemsel (`anchor_year_group`) doğrulama. `anchor_year_group` 2008–2016 grubu eğitim, 2017–2022 grubu test. İki tarafta da bulunan hasta test tarafından çıkarılır; sayısı `07g_bolme.csv` dosyasında.
  - **Not:** `anchor_year_group` takvim yılı değildir. MIMIC-IV gizlilik için her hastanın tarihlerini geleceğe kaydırır; `anchor_year_group`, hastanın `anchor_year` yılının gerçekte hangi 3 yıllık döneme düştüğünü gösterir ve hasta düzeyindedir. Bir hastanın bütün yatışları aynı gruptadır, ama yatışın gerçek takvim yılı grubun dışına taşabilir. Bu yüzden bu bölme kesin bir zamansal (takvim) doğrulama değil, yaklaşık bir dönemsel doğrulamadır; "zamansal doğrulama" ifadesi kullanılmaz.
  - Eğitilmiş modeller (iç doğrulamanın beş dış katı ve dönemsel eğitim seti) yalnızca `ozel/07_modeller/` altına yazılır, paylaşılmaz.
- **Modeller:** L2 lojistik regresyon, Random Forest, XGBoost. Karşılaştırma tabanları:
  - yalnızca Braden toplam (0–72 saatteki en düşük; cezasız lojistik, medyan atama);
  - Braden kesim noktaları (Braden ≤ k ise risk var): ≤ 18 protokolde önceden belirlenmişti; ≤ 12 ve ≤ 14 tam veri sonuçlarından sonra eklendi, çünkü kohortta neredeyse herkes ≤ 18 çıktı. Çıktılarda `belirleme` sütunu `onceden_belirlenmis` / `sonradan_eklenen` değerini alır. Braden yoksa yatış risk yok sayılır; bu yatışların sayısı `07g_bolme.csv` dosyasında.
- **Dengesizlik:** düzeltme yok; modeller ağırlıksız (`class_weight`, `scale_pos_weight` ve SMOTE kullanılmaz). Gerekçe: van den Goorbergh ve ark. (2022, JAMIA) dengesizlik düzeltmelerinin ayırt ediciliği artırmadan kalibrasyonu bozduğunu gösterdi; bu çalışmada kalibrasyon ve karar eğrisi raporlandığı için tahminlerin kalibre olması gerekir.
- **Eksik veri:** XGBoost eksik değerleri kendisi ele alır. L2 lojistik ve Random Forest için eğitim katında fit edilen medyan atama ve eksiklik göstergesi pipeline içindedir, bu yüzden sızıntı olmaz. L2 lojistikte ayrıca standartlaştırma var.
- **Hiperparametre:** `RandomizedSearchCV`, model başına 40 deneme (`--deneme`), iç döngüde 3 katlı `GroupKFold`, skor AUROC, `n_jobs=-1`, tohum 2026 (`--tohum`). Seçilen değerler `07e_hiperparametreler.csv` dosyasında.
- **Metrikler** (`07b_metrikler.csv`): test kümesinde hesaplanır; %95 GA 1000 tekrarlı yüzdelik bootstrap ile (`--bootstrap`).
  - Olasılık tahmini yapan modeller: AUROC, AUPRC (average precision), Brier skoru, kalibrasyon eğimi (y ~ logit p), kalibrasyon kesişimi (logit p offset).
  - Her Braden kesim noktasının (≤ 18, ≤ 14, ≤ 12) duyarlılığında modelin özgüllüğü: ROC eğrisinde modelin duyarlılığının ilk kez bu değere ulaştığı nokta (`ozgulluk_braden<k>_duyarliliginda`).
  - Her kesim noktası için: AUROC, duyarlılık, özgüllük, pozitif ve negatif kestirim değeri (`ppd`, `npd`).
  - AUROC farkı DeLong testiyle hesaplanır; GA DeLong standart hatasından (`07c_auroc_farki.csv`). Karşılaştırmalar: üç model − Braden toplam lojistik; XGBoost − L2 lojistik; Random Forest − L2 lojistik.
- **Grafikler** (PNG ve SVG):
  - ROC ve PR eğrileri (üç Braden kesim noktası nokta olarak);
  - kalibrasyon: tahmin ondalıklarına göre gruplanmış; 5'ten az yatışlı grup çizilmez;
  - karar eğrisi: net fayda, eşik 0,02–0,30; Braden ≤ 18, Braden ≤ 12 (sonradan eklenen), "herkese" ve "hiç kimseye" eğrileriyle birlikte.
- **SHAP:** dönemsel testte AUROC'u daha yüksek olan ağaç modeli (RF veya XGBoost) kullanılır, dönemsel test setinden en fazla 2000 yatışla.
  - `07f_shap_ozet.csv` ve `07_shap_ortalama` grafiği: ilk 20 özelliğin ortalama |SHAP| değeri.
  - `07_shap_bagimlilik`: ilk 10 özellik için, özellik değerinin ondalıklarına göre ortalama SHAP. 10'dan az farklı değeri olan özellikte gruplar değerin kendisidir. 5'ten az yatışlı grup çizilmez, eksik değerler dışarıda bırakılır.
  - Tek tek hasta noktalarını gösteren beeswarm grafiği yalnızca `ozel/07_shap_beeswarm.png` dosyasına yazılır.
- **Alt gruplar** (`07d_alt_gruplar.csv`): cinsiyet, yaş grubu (<65 / 65–79 / 80+), birleştirilmiş YB birimi.
  - AUROC yalnızca olay ve olaysız sayısı en az 5 ise hesaplanır (bootstrap GA ile).
  - `n` ve `olay` 1–4 ise "<5" yazılır.
  - Olaysız sayısı 1–4 ise `olay` "gizli" yazılır.
  - Bir alt grup değişkeninde tek gizli hücre kalırsa en küçük ikinci hücre de "gizli" yapılır.
- **Yalnızca özel:** `07_modeller/` (`ic_kat<k>_<model>.joblib`, dış kat test yatışları `ic_katlar.joblib`, dönemsel `<model>.joblib`), `07_tahminler.parquet`, `07_shap_beeswarm.png`.
- **`--yalnizca-degerlendirme`:** hiperparametre araması ve eğitim yapılmaz. `ozel/07_modeller/` altındaki modeller yüklenir; metrikler, grafikler, SHAP ve alt gruplar yeniden üretilir. `07e_hiperparametreler.csv` korunur. Kayıtlı model yoksa betik durur; bir doğrulamanın modeli eksikse o doğrulama `07z_hatalar.csv` dosyasına yazılır, diğeri sürer. Aynı modellerle sonuçlar eğitimli çalıştırmayla birebir aynıdır (aynı `--tohum` ve `--bootstrap`).

### Keşfedici kümeleme (08) kuralları

Bütün çıktılarda `analiz_tipi = kesfedici`. Bu analiz önceden belirlenmiş bir hipotez testi değildir, keşfedicidir.

- **Yörünge:** her kohort yatışı için 0–72 saat altı adet 12 saatlik bloğa bölünür. Her blokta JH-HLM'nin en yüksek düzeyi alınır; aynı anda çelişkili kayıt varsa en yüksek düzey. Kayıtsız blok bir önceki bloğun değerini alır (ileri taşıma); baştaki boş bloklar ilk dolu bloğun değerini alır. Blok bazında kayıtlı ve doldurulan yatışlar ile yatış başına doldurulan blok sayısının dağılımı `08a_yorunge_doldurma.csv` dosyasında.
- **Kümeleme:** 6 boyutlu yörünge üzerinde Gaussian Mixture (scikit-learn, tam kovaryans, `n_init = 10`, tohum 2026), k = 2–6. JH-HLM tamsayı olduğu için bir kümenin tek noktaya çöküp varyansının sıfıra inmesini önlemek amacıyla kovaryansa 1/12 eklenir (`reg_covar`; yuvarlama varyansı).
  - Kümeler ortalama yörünge düzeyine göre numaralanır: `kume_1` en düşük.
  - **k seçimi:** en küçük kümesi ≥ %5 olan k'lar içinde en düşük BIC (`kurala_gore_secilen`). Klinik yorumlanabilirlik elle değerlendirilir; gerekirse `--k` ile başka k kullanılır (`kullanilan_k`).
  - **Kararlılık:** 200 bootstrap (`--bootstrap-kume`; Hennig 2007, clusterboot). Her tekrarda bootstrap örnekte yeniden kümelenir; özgün her küme için örnekteki en iyi eşleşen kümeyle Jaccard benzerliği hesaplanır; küme bazında ortalama. Bütün k'lar için BIC, küme büyüklükleri ve Jaccard `08b_k_secimi.csv` dosyasında.
- **Küme tanımı** (`08c_kume_yorunge.csv`, `.png`, `.svg`): seçilen k için küme bazında blok ortalaması ve %95 GA (t dağılımı); grafikte yalnızca ortalama ve GA bandı vardır, tek tek yatış çizgisi yoktur. 5'ten az yatışlı kümenin ortalaması yazılmaz, çizilmez.
  - `ad_onerisi`, kurala dayalı bir öneridir: ortalama ≤ 2,5 ve belirgin artış yoksa "yatakta kalan"; ilk iki blok ≥ 6 ise "erken yürüyen"; ≥ 4,5 ise "erken mobilize olan"; son iki blok ilk ikisinden ≥ 1,5 yüksekse "geç mobilize olan"; ≥ 1,5 düşükse "mobilitesi azalan"; diğerleri "orta düzeyde sabit".
  - `ad_onayli`: onaylanan adlar (20 Ekim 2026, tam veri, k = 5; `ONAYLI_ADLAR`): kume_1 yatakta kalan, kume_2 mobilitesi azalan, kume_3 geç mobilize olan (36. saat sonrası), kume_4 erken mobilize olan (12–36. saat), kume_5 baştan mobil. Adlar yalnızca k ve küme büyüklükleri onaylanan çözümle aynıysa yazılır; çözüm değişirse sütun boş kalır, betik uyarı verir ve adlar yeniden onaylanmalıdır. Adlar 08c, 08d, 08e, 08f ve 08h'de kullanılır.
- **Kümelere göre** (`08d_tablo1_kume.csv`, 06a biçimi; YB birimleri 06'daki gibi birleşik): Tablo 1 değişkenleri. `08d2_kume_sonuc_ozeti.csv` aynı gizlenmiş tablodan şu satırları alır: yeni basınç yarası (72. saat – 28. gün, YB süresince), 72–168 saat yeni basınç yarası, bakım planı görülme oranı (Impaired Mobility, Activity Intolerance, Altered Skin Integrity).
  - **Bakım planı pencereleri:** `sayi` / `yuzde` 0–72 saat (05'teki analiz seti değişkeni: `intime` ile `intime + 72 saat` arasında boş olmayan değerli kayıt). `sayi_yb_suresince` / `yuzde_yb_suresince` YB süresince (`intime` ile `outtime` arasında boş olmayan değerli kayıt). Karşılaştırma için: `04e_bakim_plani_gorunurlugu.csv` pencere ve değer filtresi olmadan yatışa bağlı her kaydı sayar (YB çıkışından sonraki ve boş değerli kayıtlar dahil); bu yüzden 08'in YB süresince sayısından biraz yüksek olabilir.
- **Kümülatif insidans** (`08f_kumulatif_insidans.csv`, `.png`, `.svg`): kümelere göre Aalen-Johansen, 06c ile aynı olay tanımı (ölüm ve canlı taburculuk yarışan olay, 28. gün idari sansür), bootstrap GA (`--bootstrap`, 1000).
- **Küme → yeni basınç yarası** (`08e_kume_cox.csv`): cause-specific Cox, birincil modelle aynı karıştırıcılar (yıl kuklaları dahil, JH-HLM grupları yerine küme kuklaları) ve aynı strata (birleştirilmiş `first_careunit`). 06'nın MICE atamaları (`ozel/06_atanmis_veri.csv.gz`) kullanılır, Rubin kurallarıyla birleştirilir. Referans `kume_1` (ortalama yörüngesi en düşük, önerilen adı "yatakta kalan"); bu yüzden 08, 06'dan sonra çalıştırılmalı. Küme bazında yatış ve olay sayısı ilk atamadan.
- **Dönemlere göre küme HR** (`08h_kume_donem_hr.csv`): takip 06j gibi 72. saatten sonraki 96. saatte (YB'de 168. saat) bölünür; 72–168 saat dönemi `sure < 96` (05'teki `yeni_by_72_168` ile aynı), >168 saat dönemi 96. saatte risk altındakiler (geç giriş). Her küme için iki dönemin HR'si (küme × dönem kuklaları; karıştırıcılar ve strata 08e ile aynı) ve etkileşim (>168 HR / 72–168 HR oranı, Wald p, Rubin). `yatis` ve `olay_sayisi` ilk atamadan, dönem başına.
- **Duyarlılık, k = 3** (`08g_k3_duyarlilik.csv`, `bolum` sütunu): k = 3 çözümünün küme büyüklükleri ve ortalama yörüngesi (`yorunge`) ve küme Cox HR'leri (`cox_hr`, 08e ile aynı model, referans kume_1). Ana çözümle birlikte okunduğunda birkaç yatışı ayıran k = 3 kümelerinin (ana çözümdeki kümelerin bir birleşimiyle 1–4 yatış farkı olan) olay sayısı ve ortalama yörüngesi yazılmaz (`fark_riski_nedeniyle_gizli`).
- **Gizleme:** 1–4 arası sayılar "<5". Tamamlayıcı gizleme: toplamı bilinen bir grupta (bir bloğun üç sayısı, doldurulan blok dağılımı, her k'da küme büyüklükleri, Cox'ta küme yatış/olay sayıları, dönem tablosunda dönem başına olay sayıları, YB süresince bakım planı sayıları) tek gizli hücre kalırsa en küçük ikinci hücre de "gizli". Bir blokta doldurulan toplam (kohort − kayıtlı) 1–4 ise kayıtlı sayı da gizlenir. Tablo 1'de 06 ile aynı kurallar. Tablolar arası gizleme için aşağıdaki "Tablolar arası gizleme" bölümüne bakın.
- **Yalnızca özel:** `08_kumeler.parquet` (yatış düzeyinde yörünge ve küme).

### Makale tabloları ve şekilleri (09)

`09_makale.py --dil tr|en` yalnızca `paylasilabilir/` dosyalarını (ve ek tablo E5 için `config/itemids_onayli.csv`) okur; `ozel/` okunmaz. Çıktılar `<cikti>/makale_<dil>/` klasörüne yazılır: tablolar `.docx` (APA 7: yatay çizgiler, dikey çizgi yok, not satırı; geniş tablolar yatay sayfa), şekiller PNG (300 dpi) ve SVG. Girdisi olmayan ya da hata veren çıktı atlanır ve `09z_atlananlar.csv` dosyasına yazılır (demoda E2, S3–S6).

- **Biçim:** tr: ondalık virgül (0,77), binlik nokta (15.243), "p < 0,001", "%95 GA". en: ondalık nokta, binlik virgül, "p < .001" (p'de baştaki sıfır yok), "95% CI". Negatif sayılarda eksi işareti (−). Gizlenmiş hücreler ("<5", "gizli") aynen yazılır; tablo notunda açıklanır (İngilizcede de "gizli" olarak kalır).
- **Sonradan eklenenler:** Braden ≤ 14 ve ≤ 12 tablo ve şekillerde "ᵃ" ile işaretlidir.
- **Etiketler** (`code/etiketler.py`): bütün analiz değişkenleri ve 07 özellikleri (kuklalar ve Random Forest eksiklik göstergeleri dahil) için Türkçe ve İngilizce etiketler; Tablo 1, S6 (SHAP) ve ek tablolar aynı sözlüğü kullanır. Etiket adı, istatistiği (ilk, en kötü, en düşük, ortalama, en yüksek) ve birimi içerir, örneğin "Hemoglobin, en kötü (g/dL)" / "Haemoglobin, worst (g/dL)"; pencere (0–72 saat, SOFA ilk 24 saat) tablo ve şekil notlarındadır. Eksiklik göstergesi "(eksik)" / "(missing)" ekiyle yazılır. 07a veya 07f'de sözlükte olmayan bir özellik varsa 09 uyarı verir, `ETIKET` satırıyla `09z_atlananlar.csv` dosyasına yazar ve o özelliği ham adıyla çizer.

| Çıktı | Dosya | Kaynak (`paylasilabilir/`) |
|---|---|---|
| T1 Kohort özellikleri, JH-HLM grubuna göre | `T1_kohort_ozellikleri.docx` | `06a_tablo1_jhhlm.csv` |
| T2 Birincil Cox: genel HR, strata birim × dönem HR, dönem bazında HR ve etkileşim p, sürekli etki, E-değerleri | `T2_birincil_cox.docx` | `06d_modeller.csv` (`birincil`, `birincil_strata_birim_yil`, `h_jh_surekli`, `birincil_e_degeri_*`), `06j_donem_hr.csv` |
| T3 Duyarlılık analizleri (a–j) | `T3_duyarlilik.docx` | `06d_modeller.csv`, `06i_fine_gray.csv` |
| T4 Model performansı ve DeLong farkları | `T4_model_performansi.docx` | `07b_metrikler.csv`, `07c_auroc_farki.csv` |
| T5 Braden kesim noktaları ve aynı duyarlılıkta özgüllük | `T5_braden_kesim.docx` | `07b_metrikler.csv` |
| T6 Mobilite kümeleri: tanım, büyüklük, sonuç, Cox ve dönem HR, bakım planı | `T6_mobilite_kumeleri.docx` | `08c_kume_yorunge.csv`, `08d2_kume_sonuc_ozeti.csv`, `08e_kume_cox.csv`, `08h_kume_donem_hr.csv` |
| E1 Eksik veri | `E1_eksik_veri.docx` | `05a_degisken_ozeti.csv`, `06d2_atama_eksik_oranlari.csv` |
| E2 Schoenfeld (cox.zph) | `E2_schoenfeld.docx` | `06e2_ph_varsayimi_coxzph.csv` |
| E3 Alt gruplarda AUROC | `E3_alt_gruplar.docx` | `07d_alt_gruplar.csv` |
| E4 k = 3 duyarlılığı | `E4_k3_duyarlilik.docx` | `08g_k3_duyarlilik.csv` |
| E5 itemid listesi (onaylanan ve gerekçeli reddedilen; kayıt sayıları yok) | `E5_itemid_listesi.docx` | `config/itemids_onayli.csv` |
| E6 Kümelenmemiş ve robust (hasta kümesi) GA yan yana | `E6_robust_karsilastirma.docx`, `.csv` | `06d_modeller.csv`, `06i_fine_gray.csv`, `06j_donem_hr.csv`, `08e_kume_cox.csv`, `08h_kume_donem_hr.csv` (`*_naif` sütunları) |
| S1 Kohort akış şeması (STROBE/RECORD; dışlananı olmayan adım çizilmez) | `S1_kohort_akisi.png/.svg` | `04a_kohort_akisi.csv` |
| S2 Kümülatif insidans, JH-HLM gruplarına göre (yayımlanan günlerde nokta ve %95 GA, risk altındaki sayılar) | `S2_kumulatif_insidans.png/.svg` | `06c_kumulatif_insidans.csv` |
| S3 Dönem bazında HR orman grafiği | `S3_donem_hr_orman.png/.svg` | `06j_donem_hr.csv`, `08h_kume_donem_hr.csv` (küme adı `08c`) |
| S4 ROC ve kalibrasyon, dönemsel doğrulama | `S4_roc_kalibrasyon.png/.svg` | `07h_egri_noktalari.csv`, `07b_metrikler.csv` |
| S5 Karar eğrisi, dönemsel doğrulama | `S5_karar_egrisi.png/.svg` | `07h_egri_noktalari.csv` |
| S6 Ortalama \|SHAP\|, ilk 15 | `S6_shap.png/.svg` | `07f_shap_ozet.csv` |
| S7 Küme yörüngeleri | `S7_kume_yorungeleri.png/.svg` | `08c_kume_yorunge.csv` |

- **S2:** `06c` yalnızca 1, 3, 7, 14, 21 ve 25. günleri yayımladığı için eğri bu noktalar arasında düz çizgiyle birleştirilir; tam basamaklı eğri yayımlanmaz (günlük artışlar küçük sayılar verebilir).
- **S4–S5 için 07 eğri noktaları** (`07h_egri_noktalari.csv`, `--yalnizca-degerlendirme` ile de yazılır): ROC, her model ve doğrulama türü için 0–1 arası 100 noktalık sabit 1 − özgüllük ızgarasında doğrusal enterpole duyarlılık (`egri = roc`) ve Braden kesim noktaları (`roc_kesim`); kalibrasyon ondalık dilimleri, ortalama tahmin ve gözlenen oran (5'ten az olaylı ya da olaysız sayısı 1–4 olan dilim gizli ve çizilmez); karar eğrisi net faydası, eşik 0,02–0,30, 0,01 adım (modeller, Braden ≤ 12, ≤ 14, ≤ 18, `herkese`, `hic kimseye`). Tek tek tahmin değeri ya da her eşikteki ham ROC noktası yazılmaz. 07'nin kendi kalibrasyon grafiği de aynı kuralla çizilir. Sütunlar: `analiz_tipi`, `egri`, `model`, `x`, `y`, `n`, `olay`, `belirleme`.

### TRIPOD+AI kontrol listesi taslağı

Konular TRIPOD+AI (Collins ve ark., BMJ 2024) bölümlerine göre özetlenmiştir. Madde numaraları yayımlanmış listeyle karşılaştırılarak eklenmeli.

| TRIPOD+AI konusu | Nerede |
|---|---|
| Başlık, özet, giriş, amaç | Makale metni (elle) |
| Veri kaynağı, dönem, ortam | README "Veri klasörü" ve "Kodlarda uygulanan veri kuralları"; MIMIC-IV 3.1 |
| Katılımcılar, dahil etme/dışlama, akış | `04a_kohort_akisi.csv`, `07g_bolme.csv` |
| Veri hazırlama, ön işleme | README 05 ve 07 kuralları; `05a_degisken_ozeti.csv`, `config/itemids_onayli.csv` |
| Sonuç tanımı ve zamanlaması | README "Sonuç" maddesi; `04b_sonuc_sayilari.csv` |
| Öngörücüler (tanım, ölçüm zamanı) | `07a_ozellikler.csv`; README 05 kuralları (0–72 saat penceresi) |
| Örneklem büyüklüğü, olay sayısı | `07g_bolme.csv`, `07b_metrikler.csv` (`n`, `olay`) |
| Eksik veri | `07a_ozellikler.csv` (`eksik_yuzde`); README 07 "Eksik veri" |
| Veri bölme ve doğrulama stratejisi | README 07 "Doğrulama"; `07g_bolme.csv` |
| Model türleri, hiperparametre arama | README 07 "Modeller" ve "Hiperparametre"; `07e_hiperparametreler.csv` |
| Sınıf dengesizliği | README 07 "Dengesizlik" |
| Performans ölçütleri (ayırt etme, kalibrasyon, klinik fayda) | `07b_metrikler.csv`, `07c_auroc_farki.csv`, `07_roc_*`, `07_pr_*`, `07_kalibrasyon_*`, `07_karar_egrisi_*` |
| Karşılaştırma tabanı | Braden toplam lojistik; Braden ≤ 18 (önceden belirlenmiş), ≤ 14 ve ≤ 12 (sonradan eklenen) (`07b`, `07c`) |
| Adalet, alt grup performansı | `07d_alt_gruplar.csv` |
| Açıklanabilirlik | `07f_shap_ozet.csv`, `07_shap_ortalama`, `07_shap_bagimlilik` |
| Model çıktısı ve kullanım eşiği | Olasılık; karar eğrisi (`07_karar_egrisi_*`) |
| Eğitim ve değerlendirme verisi farkları | `07g_bolme.csv` (`anchor_year_group` dönemleri); 05a ve 06a ile karşılaştırma (elle) |
| Model spesifikasyonu, paylaşım | `ozel/07_modeller/` (DUA nedeniyle paylaşılmaz); kod `code/07_ml.py` |
| Etik onay, veri erişimi | PhysioNet DUA, MIMIC-IV kurum onayı (makale metni) |
| Açık bilim: kod, protokol | `code/` klasörü; "Yöntem (Revize v3)" belgesi |
| Hasta ve kamu katılımı | Yok (makale metninde belirtilecek) |
| Sınırlılıklar, yorum, genellenebilirlik | Makale metni (elle) |

## Demo veride ilk sonuçlar

Bu sayılar yalnızca 100 hastalık demodan; tam veride farklı çıkacaktır.

- 140 yoğun bakım yatışından 29'u son kohorta kaldı. En büyük kayıp en az 72 saat kalma şartında (85 yatış) ve ilk 72 saatte JH-HLM kaydı bulunma şartında (23 yatış).
- Kohortta 4 yatışta 72. saatten sonra yeni basınç yarası gelişti.
- İlk 72 saatte JH-HLM kaydı bulunan yatış oranı 2011-2013 döneminde %38, 2014-2016 döneminde %71. Tam veride bu fark sürerse ana analizi JH-HLM'nin rutin kaydedildiği yıllarla sınırlamak gerekebilir.
- Kohorttaki 29 yatışın hepsinde 72. saatten önce eksiksiz bir Braden seti var (medyan toplam 14).
- Mobiliteyle ilgili bakım planları seyrek: Impaired Mobility 2, Activity Intolerance 1, Altered Skin Integrity 4 yatışta.

## Tam veride ilk bakılacak şeyler

1. `04b_sonuc_sayilari.csv`: yeni basınç yarası sayısı. Birkaç yüzün altındaysa sonuç tanımı hocayla birlikte genişletilir.
2. `04c_jhhlm_yil.csv`: JH-HLM'nin yıllara göre kaydedilme oranı.
3. `03d_kurala_uymayan_degerler.csv`: demoda boş çıktı; tam veride dolu gelirse `kurallar.py` güncellenmeli. Paylaşılabilir kopyada n<5 olan satırlar tamamen atılır (serbest metin riski).
4. `04f_ayni_an_coklu_itemid.csv`: aynı yatışta, aynı saatte aynı gruptan birden fazla itemid; değerleri farklıysa çift sayım riski var.
5. `04g_tespit_tarihi_kontrolu.csv`: yeni sayılan yaralarda tespit tarihinin dolu olma oranı. Tespit tarihi 72. saatten önce olanlar kohortta dışlandığı için `tespit_72_oncesi_yatis` 0 olmalı. Yeni şablonda tespit tarihi #N evre #N ile eşleştirilir; eski şablonda eşleştirme yapılmaz, yalnızca aynı yatışta tespit tarihinin dolu olup olmadığına bakılır.
6. `04b_sonuc_sayilari.csv` ek sütunları: `tanimsiz` evre kayıtları yara sayılmaz; `yalnizca_tanimsiz_ile_yeni` ve `tanimsiz_72_oncesi_kohort_yatis` bu kuralın etkisini gösterir. `yeni_by_bilinmiyor_haric` BILINMIYOR için duyarlılık sayısıdır. Yıllara göre oran `04b2_yeni_by_yil.csv` dosyasında.
7. `04h_eski_sablon_jhhlm.csv`: aynı yatışta eski şablon evre kaydı ve JH-HLM kaydı birlikte var mı. Tam veride (20 Ekim 2026) eski şablon kaydı olan 5.344 yatışın hiçbirinde JH-HLM kaydı yok; kohort tamamen yeni şablon dönemine ait.
8. `04i_tutarlilik_kontrolu.csv`: önceki tanımla yeni sayılıp eşleştirmeli kurala göre tespit tarihi 72. saatten önce olan yatışlar (A) ve bunlardan birincil kohortta kalanlar (B). B sıfır olmalı.
9. `04j_uzlastirma.csv`: önceki tanım (Unknown, Unable to assess ve Status Changed yara sayılmaz; tespit tarihi adımı yok) ile birincil tanım arasında yeni yara geçişi ve nedenleri. Nedenler kohort adımlarının sırasıyla atanır. Status Changed iki tanımda da yara olmadığı için o satır yapısı gereği 0'dır. İki tanımda da YB çıkışından sonraki yara kaydı sayılmaz. Birincil toplam 04b ve 06'daki olay sayısıyla aynı olmalı (tam veride 1.439; bu değişiklikten önce 1.480 önceki ve 1.441 birincil idi, önceki toplam da biraz azalabilir).
